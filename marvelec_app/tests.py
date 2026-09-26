from django.test import TestCase
from django.contrib.auth.models import User
from .models import Obra, Subetapa, ReporteAvance, RegistroPunto, PerfilTrabajador


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
