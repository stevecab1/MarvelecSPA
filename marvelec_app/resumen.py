# marvelec_app/resumen.py
"""
Resumen diario para supervisores y gerencia: avance por etapa del día, incidencias,
asistencia (quién no marcó llegada) y reportes por revisar.
"""
from django.db import IntegrityError, transaction
from django.urls import reverse

from . import consultas, etapas
from .models import Asistencia, Incidencia, Notificacion, PerfilTrabajador, ReporteAvance, ResumenDiarioEnviado
from .notificaciones import notificar


def _nombres(perfiles, maximo=4):
    nombres = [p.usuario.get_full_name() or p.usuario.username for p in perfiles]
    if len(nombres) > maximo:
        return ', '.join(nombres[:maximo]) + f' y {len(nombres) - maximo} más'
    return ', '.join(nombres)


def resumen_para(perfil, fecha):
    """Datos del resumen del día para un supervisor o gerente."""
    base = consultas.reportes_visibles(perfil)
    del_dia = base.filter(fecha_hora__date=fecha)
    por_etapa = consultas.avance_por_etapa(consultas.avances_de(del_dia))
    asistencia = consultas.asistencia_del_dia(perfil, fecha)
    incidencias = consultas.incidencias_visibles(perfil)
    return {
        'reportes': del_dia.count(),
        'puntos': sum(por_etapa.values()),
        'por_etapa': [(etapas.POR_CLAVE[c].corto, n) for c, n in por_etapa.items() if n],
        'a_cargo': len(asistencia),
        'sin_marcar': [p for p, a in asistencia if a is None],
        'sin_confirmar': sum(1 for _, a in asistencia if a and a.estado == Asistencia.ESTADO_PENDIENTE),
        'incidencias_nuevas': incidencias.filter(creada__date=fecha).count(),
        'incidencias_abiertas': incidencias.filter(estado=Incidencia.ESTADO_ABIERTA).count(),
        'pendientes': base.filter(estado=ReporteAvance.ESTADO_PENDIENTE).count(),
    }


def texto_resumen(datos):
    partes = []
    if datos['por_etapa']:
        partes.append(', '.join(f'{nombre} {n}' for nombre, n in datos['por_etapa']))
    else:
        partes.append('Sin avance registrado')
    if datos['sin_marcar']:
        partes.append(f"Sin marcar llegada ({len(datos['sin_marcar'])}): {_nombres(datos['sin_marcar'])}")
    elif datos['a_cargo']:
        partes.append('Todos marcaron llegada')
    if datos['sin_confirmar']:
        partes.append(f"{datos['sin_confirmar']} llegada(s) sin confirmar")
    if datos['incidencias_abiertas']:
        partes.append(f"{datos['incidencias_abiertas']} punto(s) bloqueados ({datos['incidencias_nuevas']} nuevos)")
    if datos['pendientes']:
        partes.append(f"{datos['pendientes']} reporte(s) por revisar")
    return '. '.join(partes) + '.'


def enviar_resumen_diario(fecha, forzar=False):
    """Envía el resumen del día a cada supervisor/gerente. No se repite para la misma fecha."""
    if not forzar and ResumenDiarioEnviado.objects.filter(fecha=fecha).exists():
        return {'enviado': False, 'motivo': 'Ya se envió el resumen de este día.', 'destinatarios': 0}

    revisores = PerfilTrabajador.objects.filter(
        rol__in=[PerfilTrabajador.ROL_SUPERVISOR, PerfilTrabajador.ROL_GERENCIA],
        usuario__is_active=True,
    ).select_related('usuario', 'obra_asignada')

    url = reverse('marvelec_app:panel_supervision') + f'?desde={fecha.isoformat()}&hasta={fecha.isoformat()}'
    enviados = 0
    for perfil in revisores:
        datos = resumen_para(perfil, fecha)
        if not datos['reportes'] and not datos['a_cargo'] and not datos['incidencias_abiertas']:
            continue
        titulo = f"Resumen del {fecha:%d-%m}: {datos['puntos']} etapas"
        if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada:
            titulo += f" en {perfil.obra_asignada.nombre}"
        notificar([perfil.usuario], Notificacion.TIPO_RESUMEN_DIARIO, titulo, texto_resumen(datos), url)
        enviados += 1

    try:
        with transaction.atomic():
            ResumenDiarioEnviado.objects.update_or_create(fecha=fecha, defaults={'destinatarios': enviados})
    except IntegrityError:
        pass
    return {'enviado': True, 'destinatarios': enviados}
