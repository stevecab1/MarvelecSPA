# marvelec_app/context_processors.py
from .models import Asistencia, Incidencia, Notificacion, PerfilTrabajador, ReporteAvance


def app(request):
    """Datos que usan los layouts: perfil, contador de avisos y pendientes del supervisor."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    perfil = PerfilTrabajador.objects.filter(usuario=user).select_related('obra_asignada').first()
    datos = {
        'perfil_app': perfil,
        'es_revisor': bool(perfil and perfil.es_supervisor_o_gerencia),
        'no_leidas': Notificacion.objects.filter(usuario=user, leida=False).count(),
    }
    if datos['es_revisor']:
        from .consultas import hoy_local, incidencias_visibles, obra_fija, reportes_visibles
        datos['pendientes_revision'] = reportes_visibles(perfil).filter(
            estado=ReporteAvance.ESTADO_PENDIENTE
        ).exclude(trabajador=user).count()
        datos['incidencias_abiertas'] = incidencias_visibles(perfil).filter(
            estado=Incidencia.ESTADO_ABIERTA
        ).count()
        asistencias = Asistencia.objects.filter(fecha=hoy_local(), estado=Asistencia.ESTADO_PENDIENTE)
        fija = obra_fija(perfil)
        datos['asistencias_pendientes'] = (asistencias.filter(obra_id=fija) if fija else asistencias).count()
    return datos
