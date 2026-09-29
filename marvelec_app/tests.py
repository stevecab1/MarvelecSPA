import io
import json
import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import consultas
from .models import (
    Obra, Subetapa, ReporteAvance, RegistroPunto, PerfilTrabajador,
    Notificacion, ResumenDiarioEnviado, SuscripcionPush,
)


class ReporteAvanceTests(TestCase):
    def setUp(self):
        self.obra = Obra.objects.create(nombre="Hospital Test", direccion="Calle Falsa 123")
        self.subetapa = Subetapa.objects.create(obra=self.obra, nombre="Piso 1")
        self.user = User.objects.create_user(username="trabajador1", password="clave12345")
        # El perfil ahora se crea explícitamente (ya no hay señal automática).
        PerfilTrabajador.objects.create(
            usuario=self.user,
            rol=PerfilTrabajador.ROL_TRABAJADOR,
            obra_asignada=self.obra,
        )

    def test_total_puntos_se_calcula_automaticamente(self):
        """Al guardar registros de puntos, el total del reporte se actualiza vía señal."""
        reporte = ReporteAvance.objects.create(
            trabajador=self.user, obra=self.obra, subetapa=self.subetapa
        )
        RegistroPunto.objects.create(reporte=reporte, tipo_punto=RegistroPunto.TIPO_RED, cantidad=5)
        RegistroPunto.objects.create(reporte=reporte, tipo_punto=RegistroPunto.TIPO_FUERZA, cantidad=3)

        reporte.refresh_from_db()
        self.assertEqual(reporte.total_puntos, 8)

    def test_vista_crea_perfil_si_no_existe(self):
        """Un usuario sin perfil recibe uno (rol trabajador) al entrar al dashboard."""
        usuario_sin_perfil = User.objects.create_user(username="sinperfil", password="clave12345")
        self.assertFalse(PerfilTrabajador.objects.filter(usuario=usuario_sin_perfil).exists())

        self.client.login(username="sinperfil", password="clave12345")
        self.client.get("/panel/", follow=True)

        self.assertTrue(PerfilTrabajador.objects.filter(usuario=usuario_sin_perfil).exists())

    def test_trabajador_va_a_su_dashboard(self):
        """El login de un trabajador redirige a su formulario de reporte."""
        self.client.login(username="trabajador1", password="clave12345")
        r = self.client.get("/panel/")
        self.assertRedirects(r, "/panel/trabajador/")


class RobustezTests(TestCase):
    """Tests de las validaciones de robustez añadidas."""

    def setUp(self):
        self.obra_a = Obra.objects.create(nombre="Obra A", direccion="calle 1")
        self.obra_b = Obra.objects.create(nombre="Obra B", direccion="calle 2")
        self.sub_a = Subetapa.objects.create(obra=self.obra_a, nombre="Piso A")
        self.sub_b = Subetapa.objects.create(obra=self.obra_b, nombre="Piso B")
        self.user = User.objects.create_user(username="trab", password="clave12345")
        PerfilTrabajador.objects.create(
            usuario=self.user, rol=PerfilTrabajador.ROL_TRABAJADOR, obra_asignada=self.obra_a
        )

    def test_subetapa_de_otra_obra_es_rechazada(self):
        from django.core.exceptions import ValidationError
        reporte = ReporteAvance(trabajador=self.user, obra=self.obra_a, subetapa=self.sub_b)
        with self.assertRaises(ValidationError):
            reporte.full_clean(exclude=['total_puntos'])

    def test_subetapa_correcta_es_valida(self):
        reporte = ReporteAvance(trabajador=self.user, obra=self.obra_a, subetapa=self.sub_a)
        # No debe lanzar excepción.
        reporte.full_clean(exclude=['total_puntos'])


# =========================================================
# Revisión, notificaciones, envío sin señal y panel de supervisión
# =========================================================

class BaseEscenario(TestCase):
    """Dos obras, trabajadores y un supervisor por obra, y un gerente."""

    def setUp(self):
        self.obra_a = Obra.objects.create(nombre="Hospital A")
        self.obra_b = Obra.objects.create(nombre="Hospital B")
        self.sub_a = Subetapa.objects.create(obra=self.obra_a, nombre="Piso 1")
        self.sub_b = Subetapa.objects.create(obra=self.obra_b, nombre="Piso 9")
        self.trab_a = self._usuario("trab_a", PerfilTrabajador.ROL_TRABAJADOR, self.obra_a, "Pedro", "Soto")
        self.trab_a2 = self._usuario("trab_a2", PerfilTrabajador.ROL_TRABAJADOR, self.obra_a, "Juan", "Pérez")
        self.trab_b = self._usuario("trab_b", PerfilTrabajador.ROL_TRABAJADOR, self.obra_b)
        self.sup_a = self._usuario("sup_a", PerfilTrabajador.ROL_SUPERVISOR, self.obra_a)
        self.sup_b = self._usuario("sup_b", PerfilTrabajador.ROL_SUPERVISOR, self.obra_b)
        self.gerente = self._usuario("gerente", PerfilTrabajador.ROL_GERENCIA, None)

    def _usuario(self, username, rol, obra, nombre='', apellido=''):
        u = User.objects.create_user(username=username, password="clave12345",
                                     first_name=nombre, last_name=apellido)
        PerfilTrabajador.objects.create(usuario=u, rol=rol, obra_asignada=obra)
        return u

    def _login(self, usuario):
        self.client.login(username=usuario, password="clave12345")

    def _reporte(self, trabajador=None, obra=None, sub=None, red=0, fuerza=0, ilum=0, **extra):
        reporte = ReporteAvance.objects.create(
            trabajador=trabajador or self.trab_a, obra=obra or self.obra_a, subetapa=sub or self.sub_a, **extra
        )
        for tipo, cant in (('red', red), ('fuerza', fuerza), ('iluminacion', ilum)):
            if cant:
                RegistroPunto.objects.create(reporte=reporte, tipo_punto=tipo, cantidad=cant)
        reporte.refresh_from_db()
        return reporte

    def _datos_reporte(self, **extra):
        datos = {'obra': self.obra_a.pk, 'subetapa': self.sub_a.pk, 'comentario': 'ok',
                 'red': 5, 'fuerza': 3, 'iluminacion': 0}
        datos.update(extra)
        return datos


class CrearReporteTests(BaseEscenario):

    def test_formulario_crea_reporte_y_notifica_revisores_de_la_obra(self):
        self._login("trab_a")
        r = self.client.post(reverse('marvelec_app:nuevo_reporte'), self._datos_reporte())
        self.assertRedirects(r, reverse('marvelec_app:panel_trabajador'))

        reporte = ReporteAvance.objects.get()
        self.assertEqual(reporte.total_puntos, 8)
        self.assertEqual(reporte.estado, ReporteAvance.ESTADO_PENDIENTE)
        # Los puntos en 0 no se guardan.
        self.assertEqual(reporte.registros.count(), 2)

        notificados = set(Notificacion.objects.values_list('usuario__username', flat=True))
        self.assertEqual(notificados, {'sup_a', 'gerente'})

    def test_api_es_idempotente_con_uuid_cliente(self):
        self._login("trab_a")
        datos = self._datos_reporte(uuid_cliente=str(uuid.uuid4()), offline='1')
        r1 = self.client.post(reverse('marvelec_app:api_crear_reporte'), datos)
        r2 = self.client.post(reverse('marvelec_app:api_crear_reporte'), datos)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()['duplicado'])
        self.assertEqual(ReporteAvance.objects.count(), 1)
        self.assertTrue(ReporteAvance.objects.get().enviado_offline)

    def test_api_respeta_hora_del_celular_pero_no_futura(self):
        self._login("trab_a")
        hace_2h = timezone.now() - timedelta(hours=2)
        self.client.post(reverse('marvelec_app:api_crear_reporte'),
                         self._datos_reporte(fecha_hora_cliente=hace_2h.isoformat()))
        reporte = ReporteAvance.objects.get()
        self.assertLess(abs((reporte.fecha_hora - hace_2h).total_seconds()), 1)

        futuro = timezone.now() + timedelta(days=2)
        self.client.post(reverse('marvelec_app:api_crear_reporte'),
                         self._datos_reporte(fecha_hora_cliente=futuro.isoformat()))
        ultimo = ReporteAvance.objects.order_by('-pk').first()
        self.assertLess(ultimo.fecha_hora, timezone.now() + timedelta(minutes=1))

    def test_api_rechaza_subetapa_de_otra_obra(self):
        self._login("trab_a")
        r = self.client.post(reverse('marvelec_app:api_crear_reporte'), self._datos_reporte(subetapa=self.sub_b.pk))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])
        self.assertEqual(ReporteAvance.objects.count(), 0)

    def test_api_sin_sesion_responde_401(self):
        r = self.client.post(reverse('marvelec_app:api_crear_reporte'), self._datos_reporte())
        self.assertEqual(r.status_code, 401)

    def test_api_no_envia_reporte_guardado_por_otro_usuario(self):
        self._login("trab_a")
        r = self.client.post(reverse('marvelec_app:api_crear_reporte'),
                             self._datos_reporte(usuario_id=self.trab_a2.pk))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(ReporteAvance.objects.count(), 0)

    def _imagen(self):
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = io.BytesIO()
        Image.new('RGB', (4, 4), 'purple').save(buffer, 'PNG')
        return SimpleUploadedFile('foto.png', buffer.getvalue(), content_type='image/png')

    def test_api_guarda_foto_del_avance_con_nombre_nuevo_y_antiguo(self):
        """'foto_llegada' lo envían celulares con la versión anterior de la app en caché."""
        self._login("trab_a")
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            for clave in ('foto', 'foto_llegada'):
                r = self.client.post(reverse('marvelec_app:api_crear_reporte'),
                                     self._datos_reporte(**{clave: self._imagen()}))
                self.assertEqual(r.status_code, 201, clave)
                reporte = ReporteAvance.objects.get(pk=r.json()['id'])
                self.assertTrue(reporte.foto.name.startswith('reportes/avance/'), clave)


class PermisosTests(BaseEscenario):

    def test_supervisor_no_ve_reporte_de_otra_obra(self):
        reporte_b = self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, red=1)
        self._login("sup_a")
        r = self.client.get(reverse('marvelec_app:reporte_detalle', args=[reporte_b.pk]))
        self.assertEqual(r.status_code, 404)

    def test_gerencia_ve_todo_y_trabajador_solo_lo_suyo(self):
        reporte_b = self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, red=1)
        self._login("gerente")
        self.assertEqual(self.client.get(reverse('marvelec_app:reporte_detalle', args=[reporte_b.pk])).status_code, 200)
        self._login("trab_a")
        self.assertEqual(self.client.get(reverse('marvelec_app:reporte_detalle', args=[reporte_b.pk])).status_code, 404)

    def test_trabajador_no_accede_a_supervision(self):
        self._login("trab_a")
        r = self.client.get(reverse('marvelec_app:lista_reportes'))
        self.assertRedirects(r, reverse('marvelec_app:panel_trabajador'))

    def test_supervisor_no_puede_revisar_reporte_de_otra_obra(self):
        reporte_b = self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, red=1)
        self._login("sup_a")
        r = self.client.post(reverse('marvelec_app:revisar_reporte', args=[reporte_b.pk]), {'accion': 'aprobar'})
        self.assertEqual(r.status_code, 404)
        reporte_b.refresh_from_db()
        self.assertEqual(reporte_b.estado, ReporteAvance.ESTADO_PENDIENTE)


class RevisionTests(BaseEscenario):

    def test_aprobar_notifica_al_trabajador(self):
        reporte = self._reporte(red=4)
        self._login("sup_a")
        r = self.client.post(reverse('marvelec_app:revisar_reporte', args=[reporte.pk]),
                             {'accion': 'aprobar'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.json()['estado'], 'aprobado')
        reporte.refresh_from_db()
        self.assertEqual(reporte.revisado_por, self.sup_a)
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.trab_a, tipo=Notificacion.TIPO_REPORTE_APROBADO).exists())

    def test_observar_exige_comentario(self):
        reporte = self._reporte(red=4)
        self._login("sup_a")
        r = self.client.post(reverse('marvelec_app:revisar_reporte', args=[reporte.pk]),
                             {'accion': 'observar', 'comentario': ''}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 400)
        reporte.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteAvance.ESTADO_PENDIENTE)

    def test_flujo_observar_y_corregir(self):
        reporte = self._reporte(red=4)
        self._login("sup_a")
        self.client.post(reverse('marvelec_app:revisar_reporte', args=[reporte.pk]),
                         {'accion': 'observar', 'comentario': 'Faltan puntos de fuerza'})
        reporte.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteAvance.ESTADO_OBSERVADO)
        self.assertTrue(Notificacion.objects.filter(usuario=self.trab_a, tipo='reporte_observado').exists())

        # Otro trabajador no puede editarlo.
        self._login("trab_a2")
        self.assertEqual(self.client.get(reverse('marvelec_app:editar_reporte', args=[reporte.pk])).status_code, 404)

        # El autor lo corrige: vuelve a pendiente y se avisa al supervisor.
        self._login("trab_a")
        self.assertEqual(self.client.get(reverse('marvelec_app:editar_reporte', args=[reporte.pk])).status_code, 200)
        r = self.client.post(reverse('marvelec_app:editar_reporte', args=[reporte.pk]),
                             self._datos_reporte(red=4, fuerza=6))
        self.assertRedirects(r, reverse('marvelec_app:reporte_detalle', args=[reporte.pk]))
        reporte.refresh_from_db()
        self.assertEqual(reporte.estado, ReporteAvance.ESTADO_PENDIENTE)
        self.assertEqual(reporte.total_puntos, 10)
        self.assertTrue(Notificacion.objects.filter(usuario=self.sup_a, tipo='reporte_corregido').exists())

        # Ya no está observado: no se puede volver a editar.
        self.assertEqual(self.client.get(reverse('marvelec_app:editar_reporte', args=[reporte.pk])).status_code, 404)

    def test_aprobacion_masiva_solo_de_reportes_visibles(self):
        r1 = self._reporte(red=1)
        r2 = self._reporte(trabajador=self.trab_a2, red=2)
        rb = self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, red=3)
        self._login("sup_a")
        self.client.post(reverse('marvelec_app:revisar_masivo'), {'ids': [r1.pk, r2.pk, rb.pk]})
        estados = dict(ReporteAvance.objects.values_list('pk', 'estado'))
        self.assertEqual(estados[r1.pk], 'aprobado')
        self.assertEqual(estados[r2.pk], 'aprobado')
        self.assertEqual(estados[rb.pk], 'pendiente')


class NotificacionesTests(BaseEscenario):

    def test_estado_y_marcar_leida(self):
        reporte = self._reporte(red=1)
        n = Notificacion.objects.create(usuario=self.sup_a, tipo='nuevo_reporte', titulo='x',
                                        url=reverse('marvelec_app:reporte_detalle', args=[reporte.pk]))
        self._login("sup_a")
        data = self.client.get(reverse('marvelec_app:notificaciones_estado')).json()
        self.assertEqual(data['no_leidas'], 1)
        self.assertEqual(data['pendientes_revision'], 1)

        r = self.client.post(reverse('marvelec_app:notificacion_leer', args=[n.pk]), HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.json()['url'], n.url)
        n.refresh_from_db()
        self.assertTrue(n.leida)

    def test_no_se_puede_leer_notificacion_ajena(self):
        n = Notificacion.objects.create(usuario=self.sup_b, tipo='nuevo_reporte', titulo='x')
        self._login("sup_a")
        r = self.client.post(reverse('marvelec_app:notificacion_leer', args=[n.pk]))
        self.assertEqual(r.status_code, 404)

    def test_push_se_envia_a_dispositivos_suscritos(self):
        SuscripcionPush.objects.create(usuario=self.sup_a, endpoint='https://push.example/1', p256dh='k', auth='a')
        self._login("trab_a")
        with mock.patch('pywebpush.webpush') as webpush:
            self.client.post(reverse('marvelec_app:api_crear_reporte'), self._datos_reporte())
        self.assertEqual(webpush.call_count, 1)
        self.assertIn('Nuevo reporte', webpush.call_args.kwargs['data'])


class ResumenDiarioTests(BaseEscenario):

    def test_resumen_lista_quien_no_reporto_y_no_se_duplica(self):
        self._reporte(red=7)  # sólo Pedro (trab_a) reportó hoy
        call_command('resumen_diario', stdout=io.StringIO())

        n = Notificacion.objects.get(usuario=self.sup_a, tipo='resumen_diario')
        self.assertIn('7 puntos', n.titulo)
        self.assertIn('Juan Pérez', n.cuerpo)
        self.assertNotIn('Pedro Soto', n.cuerpo)
        self.assertTrue(Notificacion.objects.filter(usuario=self.gerente, tipo='resumen_diario').exists())

        call_command('resumen_diario', stdout=io.StringIO())
        self.assertEqual(Notificacion.objects.filter(usuario=self.sup_a, tipo='resumen_diario').count(), 1)
        self.assertEqual(ResumenDiarioEnviado.objects.count(), 1)

    @override_settings(CRON_TOKEN='secreto')
    def test_endpoint_requiere_token(self):
        url = reverse('marvelec_app:tarea_resumen_diario')
        self.assertEqual(self.client.post(url, HTTP_X_CRON_TOKEN='malo').status_code, 403)
        r = self.client.post(url, HTTP_X_CRON_TOKEN='secreto')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['enviado'])

    @override_settings(CRON_TOKEN='')
    def test_endpoint_deshabilitado_sin_token_configurado(self):
        r = self.client.post(reverse('marvelec_app:tarea_resumen_diario'), HTTP_X_CRON_TOKEN='')
        self.assertEqual(r.status_code, 403)


class ConsultasTests(BaseEscenario):

    def test_filtros_por_fecha_estado_y_ranking(self):
        viejo = self._reporte(red=10, fecha_hora=timezone.now() - timedelta(days=40))
        self._reporte(red=6)
        self._reporte(red=4, estado='aprobado')
        self._reporte(trabajador=self.trab_a2, red=3)

        qs = consultas.reportes_visibles(self.sup_a.perfil)
        filtros = consultas.leer_filtros({}, desde_por_defecto=consultas.hoy_local() - timedelta(days=29))
        recientes = consultas.aplicar_filtros(qs, filtros)
        self.assertNotIn(viejo, recientes)
        self.assertEqual(recientes.count(), 3)

        aprobados = consultas.aplicar_filtros(qs, consultas.leer_filtros({'estado': 'aprobado'}))
        self.assertEqual(aprobados.count(), 1)

        ranking = consultas.ranking_trabajadores(recientes)
        pedro = next(r for r in ranking if r['id'] == self.trab_a.pk)
        self.assertEqual(pedro['puntos'], 10)
        self.assertEqual(pedro['jornadas'], 1)
        self.assertEqual(pedro['puntos_jornada'], 10)
        self.assertEqual(pedro['pct_aprobados'], 50)

    def test_filtros_invalidos_se_ignoran(self):
        filtros = consultas.leer_filtros({'obra': 'abc', 'desde': '2026-99-99', 'estado': 'otro'})
        self.assertIsNone(filtros['obra'])
        self.assertIsNone(filtros['desde'])
        self.assertEqual(filtros['estado'], '')

    def test_excel_respeta_filtros(self):
        import openpyxl
        self._reporte(red=1)
        self._reporte(trabajador=self.trab_a2, red=2)
        self._login("sup_a")
        r = self.client.get(reverse('marvelec_app:exportar_excel'), {'trabajador': self.trab_a2.pk})
        ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
        # encabezado + 1 reporte + fila de totales
        self.assertEqual(ws.max_row, 3)
        self.assertEqual(ws.cell(row=2, column=2).value, 'Juan Pérez')


class PantallasTests(BaseEscenario):
    """Todas las pantallas cargan sin errores para cada rol."""

    def setUp(self):
        super().setUp()
        self.reporte = self._reporte(red=3, fuerza=2, comentario='Todo bien')
        self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, ilum=5)
        Notificacion.objects.create(usuario=self.trab_a, tipo='reporte_aprobado', titulo='Aprobado', cuerpo='ok')

    def _ok(self, nombre, *args, params=None):
        r = self.client.get(reverse(f'marvelec_app:{nombre}', args=args), params or {})
        self.assertEqual(r.status_code, 200, f'{nombre} -> {r.status_code}')
        return r

    def test_pantallas_trabajador(self):
        self._login("trab_a")
        for nombre in ('panel_trabajador', 'nuevo_reporte', 'historial_trabajador', 'notificaciones'):
            self._ok(nombre)
        self._ok('historial_trabajador', params={'estado': 'pendiente'})
        self._ok('reporte_detalle', self.reporte.pk)

    def test_pantallas_supervision(self):
        for usuario in ('sup_a', 'gerente'):
            self._login(usuario)
            r = self._ok('panel_supervision')
            self.assertContains(r, 'datos-graficos')
            for rango in ('hoy', '7', 'mes'):
                self._ok('panel_supervision', params={'rango': rango})
            self._ok('panel_supervision', params={'desde': '2020-01-01', 'hasta': '2030-01-01', 'obra': self.obra_a.pk})
            for nombre in ('cola_revision', 'lista_reportes', 'trabajadores', 'notificaciones'):
                self._ok(nombre)
            self._ok('lista_reportes', params={'estado': 'pendiente', 'obra': self.obra_a.pk, 'subetapa': self.sub_a.pk})
            r = self._ok('reporte_detalle', self.reporte.pk)
            self.assertContains(r, 'Aprobar')

    def test_pwa_y_login(self):
        r = self._ok('service_worker')
        self.assertEqual(r['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertContains(r, 'importScripts')
        r = self._ok('manifest')
        self.assertEqual(json.loads(r.content)['short_name'], 'MARVELEC')
        self._ok('login')

    def test_logout_por_post(self):
        self._login("trab_a")
        r = self.client.post(reverse('marvelec_app:logout'))
        self.assertRedirects(r, reverse('marvelec_app:login') + '?salida=1')
        r = self.client.get(reverse('marvelec_app:panel'))
        self.assertRedirects(r, reverse('marvelec_app:login') + '?next=/panel/')


class AdminTests(BaseEscenario):
    """Panel de administración (tema Unfold)."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('admin', 'admin@marvelec.cl', 'clave12345')

    def test_listados_del_admin_cargan_con_totales(self):
        self._reporte(red=2, fuerza=1)
        self._reporte(trabajador=self.trab_b, obra=self.obra_b, sub=self.sub_b, ilum=4)
        self._login('admin')
        for nombre in ('admin:index', 'admin:auth_user_changelist', 'admin:auth_group_changelist'):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)
        for modelo in ('obra', 'subetapa', 'perfiltrabajador', 'reporteavance', 'notificacion',
                       'suscripcionpush', 'resumendiarioenviado'):
            r = self.client.get(reverse(f'admin:marvelec_app_{modelo}_changelist'))
            self.assertEqual(r.status_code, 200, modelo)

        r = self.client.get(reverse('admin:marvelec_app_obra_changelist'))
        totales = {o.nombre: (o._n_subetapas, o._total_puntos) for o in r.context['cl'].result_list}
        self.assertEqual(totales, {'Hospital A': (1, 3), 'Hospital B': (1, 4)})

    def test_accion_aprobar_solo_pendientes_y_avisa_al_trabajador(self):
        pendiente = self._reporte(red=2)
        observado = self._reporte(red=1, estado=ReporteAvance.ESTADO_OBSERVADO)
        self._login('admin')
        self.client.post(reverse('admin:marvelec_app_reporteavance_changelist'), {
            'action': 'aprobar_seleccionados', '_selected_action': [pendiente.pk, observado.pk],
        })
        pendiente.refresh_from_db()
        observado.refresh_from_db()
        self.assertEqual(pendiente.estado, ReporteAvance.ESTADO_APROBADO)
        self.assertEqual(pendiente.revisado_por, self.admin)
        self.assertEqual(observado.estado, ReporteAvance.ESTADO_OBSERVADO)
        self.assertEqual(Notificacion.objects.filter(
            usuario=self.trab_a, tipo=Notificacion.TIPO_REPORTE_APROBADO).count(), 1)
