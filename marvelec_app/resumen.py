# marvelec_app/resumen.py
"""
Resumen diario para supervisores y gerencia: cuántos reportes y puntos hubo en el día,
qué trabajadores a cargo NO reportaron y cuántos reportes quedan por revisar.
"""
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.urls import reverse

from . import consultas
from .models import Notificacion, PerfilTrabajador, ReporteAvance, ResumenDiarioEnviado
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
    reportaron = set(del_dia.values_list('trabajador_id', flat=True))
    a_cargo = list(consultas.trabajadores_de(perfil))
    return {
        'reportes': del_dia.count(),
        'puntos': del_dia.aggregate(t=Sum('total_puntos'))['t'] or 0,
        'a_cargo': len(a_cargo),
        'sin_reportar': [p for p in a_cargo if p.usuario_id not in reportaron],
        'pendientes': base.filter(estado=ReporteAvance.ESTADO_PENDIENTE).count(),
    }


def texto_resumen(datos):
    partes = [f"{datos['reportes']} reporte(s) · {datos['puntos']} puntos"]
    if datos['sin_reportar']:
        partes.append(f"Sin reportar ({len(datos['sin_reportar'])}): {_nombres(datos['sin_reportar'])}")
    elif datos['a_cargo']:
        partes.append('Todos los trabajadores reportaron')
    if datos['pendientes']:
        partes.append(f"{datos['pendientes']} por revisar")
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
        if not datos['reportes'] and not datos['a_cargo']:
            continue
        titulo = f"Resumen del {fecha:%d-%m}: {datos['puntos']} puntos"
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
