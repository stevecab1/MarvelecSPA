# marvelec_app/context_processors.py
from .models import Notificacion, PerfilTrabajador, ReporteAvance


def app(request):
    """Datos que usan los layouts: perfil, contador de avisos y reportes por revisar."""
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
        from .consultas import reportes_visibles
        datos['pendientes_revision'] = reportes_visibles(perfil).filter(
            estado=ReporteAvance.ESTADO_PENDIENTE
        ).exclude(trabajador=user).count()
    return datos
