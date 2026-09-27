# marvelec_app/consultas.py
"""
Consultas compartidas entre el panel de supervisión, la lista de reportes,
la exportación a Excel y el resumen diario. Un solo lugar para los permisos y filtros.
"""
from datetime import date, timedelta

from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Obra, Subetapa, PerfilTrabajador, ReporteAvance, RegistroPunto


def hoy_local():
    return timezone.localdate()


def reportes_visibles(perfil):
    """Reportes que el usuario puede ver: su obra (supervisor) o todas (gerencia)."""
    reportes = ReporteAvance.objects.select_related(
        'trabajador', 'obra', 'subetapa', 'revisado_por'
    ).prefetch_related('registros')
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return reportes.filter(trabajador=perfil.usuario)
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada_id:
        return reportes.filter(obra_id=perfil.obra_asignada_id)
    return reportes


def obras_visibles(perfil):
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada_id:
        return Obra.objects.filter(pk=perfil.obra_asignada_id)
    return Obra.objects.all()


def _parse_fecha(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _parse_int(valor):
    try:
        return int(valor) if valor else None
    except (TypeError, ValueError):
        return None


def leer_filtros(params, desde_por_defecto=None):
    """Normaliza los filtros del querystring (valores inválidos se ignoran)."""
    estados_validos = {e for e, _ in ReporteAvance.ESTADO_CHOICES}
    estado = params.get('estado') or ''
    filtros = {
        'obra': _parse_int(params.get('obra')),
        'subetapa': _parse_int(params.get('subetapa')),
        'trabajador': _parse_int(params.get('trabajador')),
        'estado': estado if estado in estados_validos else '',
        'desde': _parse_fecha(params.get('desde')),
        'hasta': _parse_fecha(params.get('hasta')),
    }
    if 'desde' not in params and desde_por_defecto is not None:
        filtros['desde'] = desde_por_defecto
    return filtros


def aplicar_filtros(reportes, filtros):
    if filtros.get('obra'):
        reportes = reportes.filter(obra_id=filtros['obra'])
    if filtros.get('subetapa'):
        reportes = reportes.filter(subetapa_id=filtros['subetapa'])
    if filtros.get('trabajador'):
        reportes = reportes.filter(trabajador_id=filtros['trabajador'])
    if filtros.get('estado'):
        reportes = reportes.filter(estado=filtros['estado'])
    if filtros.get('desde'):
        reportes = reportes.filter(fecha_hora__date__gte=filtros['desde'])
    if filtros.get('hasta'):
        reportes = reportes.filter(fecha_hora__date__lte=filtros['hasta'])
    return reportes


def trabajadores_de(perfil):
    """Perfiles de trabajadores que el supervisor/gerente tiene a cargo."""
    perfiles = PerfilTrabajador.objects.filter(
        rol=PerfilTrabajador.ROL_TRABAJADOR, usuario__is_active=True
    ).select_related('usuario', 'obra_asignada')
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada_id:
        perfiles = perfiles.filter(obra_asignada_id=perfil.obra_asignada_id)
    return perfiles.order_by('usuario__first_name', 'usuario__username')


# --- Datos para gráficos y KPIs ---

def serie_puntos_por_dia(reportes, desde, hasta):
    """Puntos por día y tipo, rellenando con 0 los días sin reportes."""
    filas = (
        RegistroPunto.objects.filter(reporte__in=reportes.values('pk'))
        .annotate(dia=TruncDate('reporte__fecha_hora'))
        .values('dia', 'tipo_punto')
        .annotate(total=Sum('cantidad'))
    )
    por_dia = {}
    for f in filas:
        por_dia.setdefault(f['dia'], {})[f['tipo_punto']] = f['total']

    if not desde:
        desde = min(por_dia) if por_dia else hasta
    dias = []
    d = desde
    while d <= hasta:
        dias.append(d)
        d += timedelta(days=1)
    # Evita gráficos ilegibles con rangos enormes.
    dias = dias[-120:]

    return {
        'labels': [d.strftime('%d-%m') for d in dias],
        'series': {
            tipo: [por_dia.get(d, {}).get(tipo, 0) for d in dias]
            for tipo, _ in RegistroPunto.TIPO_CHOICES
        },
    }


def puntos_por_tipo(reportes):
    filas = (
        RegistroPunto.objects.filter(reporte__in=reportes.values('pk'))
        .values('tipo_punto').annotate(total=Sum('cantidad'))
    )
    conteo = {tipo: 0 for tipo, _ in RegistroPunto.TIPO_CHOICES}
    for f in filas:
        conteo[f['tipo_punto']] = f['total']
    return conteo


def puntos_por_subetapa(reportes, limite=12):
    filas = (
        reportes.order_by().values('subetapa__nombre', 'obra__nombre')
        .annotate(total=Sum('total_puntos'))
        .order_by('-total')[:limite]
    )
    return [
        {'nombre': f['subetapa__nombre'], 'obra': f['obra__nombre'], 'total': f['total'] or 0}
        for f in filas
    ]


def ranking_trabajadores(reportes):
    """
    Indicador de desempeño por trabajador: puntos, jornadas (días distintos con reporte)
    y puntos por jornada. Base para bonificaciones.
    """
    filas = (
        reportes.order_by()
        .values('trabajador_id', 'trabajador__username', 'trabajador__first_name', 'trabajador__last_name')
        .annotate(
            puntos=Sum('total_puntos'),
            reportes=Count('id'),
            jornadas=Count(TruncDate('fecha_hora'), distinct=True),
            aprobados=Count('id', filter=Q(estado=ReporteAvance.ESTADO_APROBADO)),
            observados=Count('id', filter=Q(estado=ReporteAvance.ESTADO_OBSERVADO)),
        )
    )
    ranking = []
    for f in filas:
        nombre = f"{f['trabajador__first_name']} {f['trabajador__last_name']}".strip()
        jornadas = f['jornadas'] or 0
        ranking.append({
            'id': f['trabajador_id'],
            'nombre': nombre or f['trabajador__username'],
            'puntos': f['puntos'] or 0,
            'reportes': f['reportes'],
            'jornadas': jornadas,
            'puntos_jornada': round((f['puntos'] or 0) / jornadas, 1) if jornadas else 0,
            'pct_aprobados': round(100 * f['aprobados'] / f['reportes']) if f['reportes'] else 0,
            'observados': f['observados'],
        })
    ranking.sort(key=lambda r: (-r['puntos_jornada'], -r['puntos']))
    return ranking


def subetapas_por_obra(obras):
    """{obra_id: [{id, nombre}, ...]} para filtrar subetapas en el navegador (también sin señal)."""
    datos = {}
    for sub in Subetapa.objects.filter(obra__in=obras).order_by('nombre'):
        datos.setdefault(str(sub.obra_id), []).append({'id': sub.id, 'nombre': sub.nombre})
    return datos
