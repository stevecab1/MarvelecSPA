# marvelec_app/consultas.py
"""
Consultas compartidas entre las pantallas de supervisión, la app del trabajador, las
exportaciones a Excel y el resumen diario. Un solo lugar para permisos, filtros e indicadores.
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from . import etapas
from .models import (
    Asistencia, AvancePunto, Incidencia, Obra, Paquete, PerfilTrabajador, Punto, Rack, ReporteAvance,
)

DIAS_RITMO = 14  # ventana para medir el ritmo real de cada etapa


def hoy_local():
    return timezone.localdate()


# =========================================================
# Permisos por rol
# =========================================================

def obra_fija(perfil):
    """Obra a la que está limitado el usuario (supervisor con obra asignada), o None."""
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada_id:
        return perfil.obra_asignada_id
    return None


def obras_visibles(perfil):
    fija = obra_fija(perfil)
    return Obra.objects.filter(pk=fija) if fija else Obra.objects.all()


def reportes_visibles(perfil):
    """Reportes que el usuario puede ver: los propios (trabajador), su obra (supervisor) o todos (gerencia)."""
    reportes = ReporteAvance.objects.select_related(
        'trabajador', 'obra', 'rack', 'revisado_por'
    ).prefetch_related('avances')
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return reportes.filter(trabajador=perfil.usuario)
    fija = obra_fija(perfil)
    return reportes.filter(obra_id=fija) if fija else reportes


def incidencias_visibles(perfil):
    incidencias = Incidencia.objects.select_related(
        'punto__tipo', 'punto__rack__obra', 'punto__paquete', 'tipo', 'reportada_por', 'liberada_por'
    )
    fija = obra_fija(perfil)
    return incidencias.filter(punto__rack__obra_id=fija) if fija else incidencias


def trabajadores_de(perfil):
    """Perfiles de trabajadores que el supervisor/gerente tiene a cargo."""
    perfiles = PerfilTrabajador.objects.filter(
        rol=PerfilTrabajador.ROL_TRABAJADOR, usuario__is_active=True
    ).select_related('usuario', 'obra_asignada')
    fija = obra_fija(perfil)
    if fija:
        perfiles = perfiles.filter(obra_asignada_id=fija)
    return perfiles.order_by('usuario__first_name', 'usuario__username')


# =========================================================
# Filtros del querystring
# =========================================================

def parse_fecha(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def parse_int(valor):
    try:
        return int(valor) if valor else None
    except (TypeError, ValueError):
        return None


def leer_filtros(params, desde_por_defecto=None):
    """Normaliza los filtros (los valores inválidos se ignoran)."""
    estados_validos = {e for e, _ in ReporteAvance.ESTADO_CHOICES}
    estado = params.get('estado') or ''
    etapa = params.get('etapa') or ''
    filtros = {
        'obra': parse_int(params.get('obra')),
        'rack': parse_int(params.get('rack')),
        'trabajador': parse_int(params.get('trabajador')),
        'etapa': etapa if etapa in etapas.POR_CLAVE else '',
        'estado': estado if estado in estados_validos else '',
        'desde': parse_fecha(params.get('desde')),
        'hasta': parse_fecha(params.get('hasta')),
    }
    if 'desde' not in params and desde_por_defecto is not None:
        filtros['desde'] = desde_por_defecto
    return filtros


def aplicar_filtros(reportes, filtros):
    if filtros.get('obra'):
        reportes = reportes.filter(obra_id=filtros['obra'])
    if filtros.get('rack'):
        reportes = reportes.filter(rack_id=filtros['rack'])
    if filtros.get('trabajador'):
        reportes = reportes.filter(trabajador_id=filtros['trabajador'])
    if filtros.get('estado'):
        reportes = reportes.filter(estado=filtros['estado'])
    if filtros.get('etapa'):
        reportes = reportes.filter(avances__etapa=filtros['etapa']).distinct()
    if filtros.get('desde'):
        reportes = reportes.filter(fecha_hora__date__gte=filtros['desde'])
    if filtros.get('hasta'):
        reportes = reportes.filter(fecha_hora__date__lte=filtros['hasta'])
    return reportes


def avances_de(reportes, filtros=None):
    """Avances (punto × etapa) de un conjunto de reportes; con filtro de etapa si viene."""
    avances = AvancePunto.objects.filter(reporte__in=reportes.order_by().values('pk'))
    if filtros and filtros.get('etapa'):
        avances = avances.filter(etapa=filtros['etapa'])
    return avances


def racks_por_obra(obras):
    """{obra_id: [{id, nombre}]} para filtros dependientes en el navegador."""
    datos = {}
    for rack in Rack.objects.filter(obra__in=obras).order_by('nombre'):
        datos.setdefault(str(rack.obra_id), []).append({'id': rack.id, 'nombre': rack.nombre})
    return datos


# =========================================================
# Gráficos e indicadores del período
# =========================================================

def serie_avance_por_dia(avances, desde, hasta):
    """Etapas completadas por día, una serie por etapa (días sin avance en 0)."""
    filas = (
        avances.annotate(dia=TruncDate('reporte__fecha_hora'))
        .values('dia', 'etapa').annotate(total=Count('id')).order_by()
    )
    por_dia = defaultdict(dict)
    for f in filas:
        por_dia[f['dia']][f['etapa']] = f['total']

    if not desde:
        desde = min(por_dia) if por_dia else hasta
    dias = []
    d = desde
    while d <= hasta:
        dias.append(d)
        d += timedelta(days=1)
    dias = dias[-120:]  # evita gráficos ilegibles con rangos enormes

    return {
        'labels': [d.strftime('%d-%m') for d in dias],
        'series': {e.clave: [por_dia.get(d, {}).get(e.clave, 0) for d in dias] for e in etapas.ETAPAS},
        'nombres': {e.clave: e.nombre for e in etapas.ETAPAS},
    }


def avance_por_etapa(avances):
    conteo = {e.clave: 0 for e in etapas.ETAPAS}
    for f in avances.values('etapa').annotate(total=Count('id')).order_by():
        conteo[f['etapa']] = f['total']
    return conteo


def ranking_trabajadores(reportes, desde=None, hasta=None):
    """
    Desempeño por trabajador (base para bonificaciones):
    - puntos: etapas completadas (punto × etapa)
    - jornadas: días con asistencia confirmada (si aún no hay, días con reporte)
    - rendimiento: % respecto del estándar de cada etapa ("TIEMPOS DE LOS PROCESOS"), así una
      certificación y una bajada pesan según lo que cuesta cada una.
    """
    por_trabajador = {}
    filas = (
        reportes.order_by()
        .values('trabajador_id', 'trabajador__username', 'trabajador__first_name', 'trabajador__last_name')
        .annotate(
            reportes=Count('id'),
            dias_reporte=Count(TruncDate('fecha_hora'), distinct=True),
            aprobados=Count('id', filter=Q(estado=ReporteAvance.ESTADO_APROBADO)),
            observados=Count('id', filter=Q(estado=ReporteAvance.ESTADO_OBSERVADO)),
        )
    )
    for f in filas:
        nombre = f"{f['trabajador__first_name']} {f['trabajador__last_name']}".strip()
        por_trabajador[f['trabajador_id']] = {
            'id': f['trabajador_id'], 'nombre': nombre or f['trabajador__username'],
            'reportes': f['reportes'], 'dias_reporte': f['dias_reporte'],
            'pct_aprobados': round(100 * f['aprobados'] / f['reportes']) if f['reportes'] else 0,
            'observados': f['observados'], 'puntos': 0, 'por_etapa': {}, 'equivalente': 0.0,
        }
    if not por_trabajador:
        return []

    for f in (avances_de(reportes).values('reporte__trabajador_id', 'etapa')
              .annotate(n=Count('id')).order_by()):
        r = por_trabajador[f['reporte__trabajador_id']]
        r['puntos'] += f['n']
        r['por_etapa'][f['etapa']] = f['n']
        r['equivalente'] += f['n'] / etapas.POR_CLAVE[f['etapa']].estandar

    asistencias = Asistencia.objects.filter(
        trabajador_id__in=por_trabajador, estado=Asistencia.ESTADO_CONFIRMADA
    )
    if desde:
        asistencias = asistencias.filter(fecha__gte=desde)
    if hasta:
        asistencias = asistencias.filter(fecha__lte=hasta)
    confirmadas = dict(asistencias.values('trabajador_id').annotate(n=Count('id')).values_list('trabajador_id', 'n'))

    ranking = []
    for r in por_trabajador.values():
        r['jornadas_asistencia'] = confirmadas.get(r['id'], 0)
        r['jornadas'] = r['jornadas_asistencia'] or r['dias_reporte']
        r['puntos_jornada'] = round(r['puntos'] / r['jornadas'], 1) if r['jornadas'] else 0
        r['rendimiento'] = round(100 * r['equivalente'] / r['jornadas']) if r['jornadas'] else 0
        r['detalle_etapas'] = [(etapas.POR_CLAVE[c].corto, r['por_etapa'][c]) for c in etapas.ordenar(r['por_etapa'])]
        ranking.append(r)
    ranking.sort(key=lambda r: (-r['rendimiento'], -r['puntos']))
    return ranking


# =========================================================
# Estado de la obra (puntos × etapas)
# =========================================================

def estado_racks(racks):
    """
    Matriz rack × etapa: puntos totales, hechos por etapa, bloqueados.
    Devuelve (filas, total) donde cada fila es {'rack', 'total', 'etapas': [{clave, n, pct}], 'bloqueados'}.
    """
    racks = list(racks)
    ids = [r.pk for r in racks]
    totales = dict(Punto.objects.filter(rack_id__in=ids).values('rack_id').annotate(n=Count('id'))
                   .values_list('rack_id', 'n'))
    hechos = defaultdict(dict)
    for f in (AvancePunto.objects.filter(punto__rack_id__in=ids).values('punto__rack_id', 'etapa')
              .annotate(n=Count('id')).order_by()):
        hechos[f['punto__rack_id']][f['etapa']] = f['n']
    bloqueados = dict(
        Incidencia.objects.filter(punto__rack_id__in=ids, estado=Incidencia.ESTADO_ABIERTA)
        .values('punto__rack_id').annotate(n=Count('punto', distinct=True)).values_list('punto__rack_id', 'n')
    )

    def fila(nombre, total, por_etapa, bloq, rack=None):
        return {
            'rack': rack, 'nombre': nombre, 'total': total, 'bloqueados': bloq,
            'etapas': [
                {'clave': e.clave, 'nombre': e.nombre, 'corto': e.corto, 'n': por_etapa.get(e.clave, 0),
                 'pct': round(100 * por_etapa.get(e.clave, 0) / total) if total else 0}
                for e in etapas.ETAPAS
            ],
            'certificados': por_etapa.get(etapas.FINAL, 0),
        }

    filas = [fila(r.nombre, totales.get(r.pk, 0), hechos[r.pk], bloqueados.get(r.pk, 0), r) for r in racks]
    suma = defaultdict(int)
    for r in racks:
        for clave, n in hechos[r.pk].items():
            suma[clave] += n
    total = fila('Total', sum(totales.values()), suma, sum(bloqueados.values()))
    return filas, total


def sumar_dias_habiles(desde, dias):
    """Fecha tras `dias` jornadas de lunes a viernes."""
    fecha, restantes = desde, int(round(dias))
    while restantes > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            restantes -= 1
    return fecha


def proyeccion(racks, total, hoy=None):
    """
    Para cada etapa: lo que falta, el ritmo real (últimos DIAS_RITMO días, en jornadas de lunes a viernes)
    y cuándo terminaría a ese ritmo. También los días-persona que faltan según el estándar.
    """
    hoy = hoy or hoy_local()
    desde = hoy - timedelta(days=DIAS_RITMO - 1)
    habiles = sum(1 for i in range(DIAS_RITMO) if (desde + timedelta(days=i)).weekday() < 5) or 1
    recientes = dict(
        AvancePunto.objects.filter(punto__rack__in=racks, reporte__fecha_hora__date__gte=desde)
        .values('etapa').annotate(n=Count('id')).values_list('etapa', 'n')
    )
    filas = []
    for celda in total['etapas']:
        etapa = etapas.POR_CLAVE[celda['clave']]
        faltan = max(0, total['total'] - celda['n'])
        ritmo = round(recientes.get(etapa.clave, 0) / habiles, 1)
        dias = faltan / ritmo if ritmo else None
        filas.append({
            'etapa': etapa, 'hechos': celda['n'], 'faltan': faltan, 'pct': celda['pct'], 'ritmo': ritmo,
            'dias': round(dias, 1) if dias is not None else None,
            'fin': sumar_dias_habiles(hoy, dias) if dias is not None and faltan else (hoy if not faltan else None),
            'dias_persona': round(faltan / etapa.estandar, 1),
        })
    return filas


def resumen_obra(obra, hoy=None):
    """KPIs y proyección de una obra para el panel 'Avance de obra'."""
    hoy = hoy or hoy_local()
    racks = Rack.objects.filter(obra=obra).order_by('nombre')
    filas, total = estado_racks(racks)
    proy = proyeccion(racks, total, hoy)
    fin_estimado = None
    if total['total'] and all(p['fin'] for p in proy):
        fin_estimado = max(p['fin'] for p in proy)
    atraso = None
    if fin_estimado and obra.fecha_termino_planificada:
        atraso = (fin_estimado - obra.fecha_termino_planificada).days
    return {
        'obra': obra, 'filas': filas, 'total': total, 'proyeccion': proy,
        'fin_estimado': fin_estimado, 'atraso': atraso,
        'holgura': -atraso if atraso is not None and atraso <= 0 else None,
        'pct_certificado': round(100 * total['certificados'] / total['total']) if total['total'] else 0,
    }


# =========================================================
# Puntos de un rack (detalle y selector del celular)
# =========================================================

def puntos_de_rack(rack):
    """Puntos del rack agrupados por paquete, con sus etapas hechas y si están bloqueados."""
    puntos = list(rack.puntos.select_related('tipo', 'paquete__zona'))
    hechas = defaultdict(set)
    for punto_id, etapa in AvancePunto.objects.filter(punto__rack=rack).values_list('punto_id', 'etapa'):
        hechas[punto_id].add(etapa)
    bloqueos = {}
    for inc in Incidencia.objects.filter(punto__rack=rack, estado=Incidencia.ESTADO_ABIERTA).select_related('tipo'):
        bloqueos.setdefault(inc.punto_id, inc.tipo.nombre)

    grupos = {}
    for p in puntos:
        p.etapas_hechas = hechas[p.pk]
        p.n_etapas = len(p.etapas_hechas)
        p.completo = etapas.FINAL in p.etapas_hechas
        p.bloqueo = bloqueos.get(p.pk, '')
        siguiente = [e for e in etapas.ETAPAS if e.clave not in p.etapas_hechas and not etapas.faltantes(e.clave, p.etapas_hechas)]
        p.siguiente = siguiente[0].corto if siguiente else ''
        clave = p.paquete.numero if p.paquete_id else None
        grupos.setdefault(clave, {'paquete': p.paquete, 'puntos': []})['puntos'].append(p)
    return [grupos[k] for k in sorted(grupos, key=lambda k: (k is None, k or 0))]


def datos_selector(obras, excluir_reporte=None):
    """
    Racks, paquetes y puntos (con etapas hechas como máscara de bits y bloqueo) para el selector
    del celular. Va incrustado en la página para que funcione sin señal.
    Al corregir un reporte se excluyen sus propios avances (si no, sus puntos aparecerían como hechos).
    """
    bit = {e.clave: 1 << i for i, e in enumerate(etapas.ETAPAS)}
    mascara = defaultdict(int)
    avances = AvancePunto.objects.filter(punto__rack__obra__in=obras)
    if excluir_reporte is not None:
        avances = avances.exclude(reporte=excluir_reporte)
    for punto_id, etapa in avances.values_list('punto_id', 'etapa'):
        mascara[punto_id] |= bit[etapa]
    bloqueados = set(Incidencia.objects.filter(
        punto__rack__obra__in=obras, estado=Incidencia.ESTADO_ABIERTA
    ).values_list('punto_id', flat=True))

    racks = {}
    for r in Rack.objects.filter(obra__in=obras).order_by('nombre'):
        racks[r.pk] = {'id': r.pk, 'nombre': r.nombre, 'obra': r.obra_id, 'paquetes': {}, 'puntos': []}
    for paq in Paquete.objects.filter(rack__obra__in=obras).select_related('zona'):
        racks[paq.rack_id]['paquetes'][paq.numero] = [paq.metros, paq.zona.nombre if paq.zona_id else '']
    for p in (Punto.objects.filter(rack__obra__in=obras)
              .values('id', 'rack_id', 'tipo__sigla', 'numero', 'paquete__numero')
              .order_by('tipo__orden', 'tipo__sigla', 'numero')):
        racks[p['rack_id']]['puntos'].append([
            p['id'], p['tipo__sigla'], p['numero'], p['paquete__numero'], mascara[p['id']], int(p['id'] in bloqueados),
        ])
    return {'etapas': etapas.para_js(), 'racks': list(racks.values())}


def historial_punto(punto):
    """Línea de tiempo del punto: etapas registradas e incidencias, en orden cronológico."""
    eventos = []
    for a in punto.avances.select_related('reporte__trabajador', 'reporte__revisado_por'):
        eventos.append({'tipo': 'avance', 'fecha': a.reporte.fecha_hora, 'avance': a, 'reporte': a.reporte})
    for inc in punto.incidencias.select_related('tipo', 'reportada_por', 'liberada_por'):
        eventos.append({'tipo': 'incidencia', 'fecha': inc.creada, 'incidencia': inc})
        if inc.liberada_en:
            eventos.append({'tipo': 'liberacion', 'fecha': inc.liberada_en, 'incidencia': inc})
    return sorted(eventos, key=lambda e: e['fecha'])


# =========================================================
# Asistencia
# =========================================================

def asistencia_del_dia(perfil, fecha, obra_id=None):
    """[(perfil_trabajador, asistencia | None)] de los trabajadores a cargo."""
    a_cargo = trabajadores_de(perfil)
    if obra_id:
        a_cargo = a_cargo.filter(obra_asignada_id=obra_id)
    marcas = {
        a.trabajador_id: a for a in
        Asistencia.objects.filter(fecha=fecha, trabajador__in=[p.usuario_id for p in a_cargo])
        .select_related('obra', 'revisado_por')
    }
    return [(p, marcas.get(p.usuario_id)) for p in a_cargo]


def asistencia_mensual(perfil, anio, mes, obra_id=None):
    """Matriz trabajador × día del mes con el estado de cada marca y los días confirmados."""
    dias = [date(anio, mes, d) for d in range(1, calendar.monthrange(anio, mes)[1] + 1)]
    a_cargo = list(trabajadores_de(perfil).filter(obra_asignada_id=obra_id) if obra_id else trabajadores_de(perfil))
    marcas = defaultdict(dict)
    for a in Asistencia.objects.filter(trabajador__in=[p.usuario_id for p in a_cargo], fecha__in=dias):
        marcas[a.trabajador_id][a.fecha] = a
    filas = []
    for p in a_cargo:
        celdas = [marcas[p.usuario_id].get(d) for d in dias]
        filas.append({
            'perfil': p, 'celdas': celdas,
            'confirmados': sum(1 for c in celdas if c and c.estado == Asistencia.ESTADO_CONFIRMADA),
            'pendientes': sum(1 for c in celdas if c and c.estado == Asistencia.ESTADO_PENDIENTE),
            'rechazados': sum(1 for c in celdas if c and c.estado == Asistencia.ESTADO_RECHAZADA),
        })
    return dias, filas


def asistencia_confirmada(trabajador_id, fecha):
    return Asistencia.objects.filter(
        trabajador_id=trabajador_id, fecha=fecha, estado=Asistencia.ESTADO_CONFIRMADA
    ).exists()
