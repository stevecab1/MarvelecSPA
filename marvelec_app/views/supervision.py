# marvelec_app/views/supervision.py
"""Programa de supervisión / gerencia (PC)."""
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core import signing
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import consultas, etapas, importador
from ..forms import CargarPuntosForm, LiberarIncidenciaForm, RevisionAsistenciaForm
from ..models import Asistencia, Incidencia, Punto, Rack, ReporteAvance, TipoIncidencia
from ..servicios import liberar_incidencia as liberar, revisar_asistencia as revisar_marca, revisar_reporte
from .comunes import es_fetch, redirigir_seguro, revisor_requerido

SALT_CARGA = 'marvelec.cargar-puntos'


def _contexto_filtros(perfil, filtros):
    obras = consultas.obras_visibles(perfil)
    return {
        'filtros': filtros,
        'obras_disponibles': obras,
        'obra_fija': consultas.obra_fija(perfil),
        'racks_por_obra': consultas.racks_por_obra(obras),
        'trabajadores_disponibles': consultas.trabajadores_de(perfil),
        'estados': ReporteAvance.ESTADO_CHOICES,
        'etapas_choices': etapas.CHOICES,
    }


def _querystring(filtros):
    params = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in filtros.items() if v}
    return urlencode(params)


def _obra_elegida(request, perfil):
    """Obra del supervisor, la pedida en ?obra= (si puede verla) o la primera activa."""
    obras = consultas.obras_visibles(perfil)
    obra_id = consultas.obra_fija(perfil) or consultas.parse_int(request.GET.get('obra'))
    obra = obras.filter(pk=obra_id).first() if obra_id else None
    return obra or obras.filter(activa=True).first() or obras.first(), obras


def _rack_visible(perfil, pk):
    rack = get_object_or_404(Rack.objects.select_related('obra'), pk=pk)
    if not perfil.puede_revisar_obra(rack.obra_id):
        raise Http404
    return rack


# =========================================================
# RESUMEN
# =========================================================

@revisor_requerido
def dashboard_supervisor(request):
    perfil = request.perfil
    hoy = consultas.hoy_local()
    # Atajos de período (Hoy / 7 días / 30 días / Este mes); por defecto, últimos 30 días.
    rangos = {'hoy': hoy, '7': hoy - timedelta(days=6), '30': hoy - timedelta(days=29), 'mes': hoy.replace(day=1)}
    if 'desde' in request.GET:
        rango = ''
    else:
        rango = request.GET.get('rango', '30')
        rango = rango if rango in rangos else '30'
    filtros = consultas.leer_filtros(request.GET, desde_por_defecto=rangos[rango] if rango else None)
    hasta = filtros['hasta'] or hoy

    base = consultas.reportes_visibles(perfil)
    reportes = consultas.aplicar_filtros(base, filtros)
    avances = consultas.avances_de(reportes, filtros)
    por_etapa = consultas.avance_por_etapa(avances)
    ranking = consultas.ranking_trabajadores(reportes, filtros['desde'], hasta)
    jornadas = sum(r['jornadas'] for r in ranking)
    equivalente = sum(r['equivalente'] for r in ranking)

    asistencia_hoy = consultas.asistencia_del_dia(perfil, hoy, filtros['obra'])
    incidencias = consultas.incidencias_visibles(perfil).filter(estado=Incidencia.ESTADO_ABIERTA)
    if filtros['obra']:
        incidencias = incidencias.filter(punto__rack__obra_id=filtros['obra'])

    context = {
        **_contexto_filtros(perfil, filtros),
        'perfil': perfil,
        'hoy': hoy,
        'total_puntos': sum(por_etapa.values()),
        'certificados': por_etapa[etapas.FINAL],
        'total_reportes': reportes.count(),
        'pendientes': base.filter(estado=ReporteAvance.ESTADO_PENDIENTE).exclude(trabajador=request.user).count(),
        'rendimiento': round(100 * equivalente / jornadas) if jornadas else 0,
        'incidencias_abiertas': incidencias.count(),
        'marcaron_hoy': sum(1 for _, a in asistencia_hoy if a),
        'a_cargo': len(asistencia_hoy),
        'sin_marcar': [p for p, a in asistencia_hoy if a is None],
        'top': ranking[:5],
        'max_top': max((r['rendimiento'] for r in ranking[:5]), default=0),
        'recientes': reportes.order_by('-fecha_hora')[:8],
        'querystring': _querystring(filtros),
        'graficos': {
            'por_dia': consultas.serie_avance_por_dia(avances, filtros['desde'], hasta),
            'por_etapa': {
                'labels': [e.nombre for e in etapas.ETAPAS],
                'claves': [e.clave for e in etapas.ETAPAS],
                'valores': [por_etapa[e.clave] for e in etapas.ETAPAS],
            },
        },
        'rango': rango,
    }
    return render(request, 'marvelec_app/supervision/resumen.html', context)


# =========================================================
# AVANCE DE OBRA, RACK Y PUNTO
# =========================================================

@revisor_requerido
def avance_obra(request):
    obra, obras = _obra_elegida(request, request.perfil)
    context = {'obras_disponibles': obras, 'obra_fija': consultas.obra_fija(request.perfil), 'hoy': consultas.hoy_local()}
    if obra:
        context.update(consultas.resumen_obra(obra))
        context['estandares'] = etapas.ETAPAS
    return render(request, 'marvelec_app/supervision/avance_obra.html', context)


@revisor_requerido
def rack_detalle(request, pk):
    rack = _rack_visible(request.perfil, pk)
    filas, _ = consultas.estado_racks([rack])
    grupos = consultas.puntos_de_rack(rack)

    pendiente = request.GET.get('pendiente', '')
    solo_bloqueados = request.GET.get('bloqueados') == '1'
    if pendiente in etapas.POR_CLAVE or solo_bloqueados:
        for g in grupos:
            g['puntos'] = [
                p for p in g['puntos']
                if (not solo_bloqueados or p.bloqueo) and (pendiente not in etapas.POR_CLAVE or pendiente not in p.etapas_hechas)
            ]
        grupos = [g for g in grupos if g['puntos']]

    return render(request, 'marvelec_app/supervision/rack_detalle.html', {
        'rack': rack, 'fila': filas[0], 'grupos': grupos, 'etapas_lista': etapas.ETAPAS,
        'pendiente': pendiente, 'solo_bloqueados': solo_bloqueados,
        'pendiente_nombre': etapas.nombre(pendiente) if pendiente in etapas.POR_CLAVE else '',
    })


@revisor_requerido
def punto_detalle(request, pk):
    punto = get_object_or_404(Punto.objects.select_related('rack__obra', 'tipo', 'paquete__zona'), pk=pk)
    if not request.perfil.puede_revisar_obra(punto.rack.obra_id):
        raise Http404
    hechas = {a.etapa: a for a in punto.avances.select_related('reporte__trabajador')}
    return render(request, 'marvelec_app/supervision/punto_detalle.html', {
        'punto': punto,
        'estado_etapas': [(e, hechas.get(e.clave)) for e in etapas.ETAPAS],
        'eventos': consultas.historial_punto(punto),
        'abiertas': punto.incidencias.filter(estado=Incidencia.ESTADO_ABIERTA).select_related('tipo', 'reportada_por'),
        'liberar_form': LiberarIncidenciaForm(),
    })


# =========================================================
# INCIDENCIAS
# =========================================================

@revisor_requerido
def incidencias(request):
    perfil = request.perfil
    estado = request.GET.get('estado', Incidencia.ESTADO_ABIERTA)
    estado = estado if estado in dict(Incidencia.ESTADO_CHOICES) else Incidencia.ESTADO_ABIERTA
    qs = consultas.incidencias_visibles(perfil).filter(estado=estado)
    obra_id = consultas.parse_int(request.GET.get('obra'))
    rack_id = consultas.parse_int(request.GET.get('rack'))
    tipo_id = consultas.parse_int(request.GET.get('tipo'))
    if obra_id:
        qs = qs.filter(punto__rack__obra_id=obra_id)
    if rack_id:
        qs = qs.filter(punto__rack_id=rack_id)
    if tipo_id:
        qs = qs.filter(tipo_id=tipo_id)
    qs = qs.order_by('creada' if estado == Incidencia.ESTADO_ABIERTA else '-liberada_en')

    # Tiempo detenido promedio por tipo (incidencias ya liberadas, últimos 90 días).
    liberadas = consultas.incidencias_visibles(perfil).filter(
        estado=Incidencia.ESTADO_LIBERADA, liberada_en__gte=timezone.now() - timedelta(days=90)
    )
    por_tipo = {}
    for inc in liberadas:
        dato = por_tipo.setdefault(inc.tipo.nombre, [0, 0.0])
        dato[0] += 1
        dato[1] += inc.tiempo_detenido.total_seconds() / 3600
    promedios = sorted(((t, n, round(h / n, 1)) for t, (n, h) in por_tipo.items()), key=lambda x: -x[2])

    obras = consultas.obras_visibles(perfil)
    return render(request, 'marvelec_app/supervision/incidencias.html', {
        'pagina': Paginator(qs, 30).get_page(request.GET.get('page')),
        'estado': estado,
        'promedios': promedios,
        'obras_disponibles': obras,
        'obra_fija': consultas.obra_fija(perfil),
        'racks_por_obra': consultas.racks_por_obra(obras),
        'tipos': TipoIncidencia.objects.all(),
        'filtros': {'obra': obra_id, 'rack': rack_id, 'tipo': tipo_id},
        'liberar_form': LiberarIncidenciaForm(),
    })


@require_POST
@revisor_requerido
def liberar_incidencia(request, pk):
    incidencia = get_object_or_404(
        Incidencia.objects.select_related('punto__rack', 'punto__tipo', 'tipo', 'reportada_por'), pk=pk
    )
    if not request.perfil.puede_revisar_obra(incidencia.punto.rack.obra_id):
        raise Http404
    form = LiberarIncidenciaForm(request.POST)
    form.is_valid()
    liberar(incidencia, request.user, form.cleaned_data.get('comentario', ''))
    texto = f'{incidencia.punto.codigo} liberado; ya puede seguir avanzando.'
    if es_fetch(request):
        return JsonResponse({'ok': True, 'mensaje': texto})
    messages.success(request, texto)
    return redirigir_seguro(request, reverse('marvelec_app:incidencias'))


# =========================================================
# ASISTENCIA
# =========================================================

@revisor_requerido
def asistencia_dia(request):
    perfil = request.perfil
    hoy = consultas.hoy_local()
    fecha = consultas.parse_fecha(request.GET.get('fecha')) or hoy
    obra_id = consultas.obra_fija(perfil) or consultas.parse_int(request.GET.get('obra'))
    filas = consultas.asistencia_del_dia(perfil, fecha, obra_id)
    return render(request, 'marvelec_app/supervision/asistencia.html', {
        'fecha': fecha, 'hoy': hoy, 'filas': filas,
        'anterior': fecha - timedelta(days=1), 'siguiente': fecha + timedelta(days=1) if fecha < hoy else None,
        'marcaron': sum(1 for _, a in filas if a),
        'pendientes': sum(1 for _, a in filas if a and a.estado == Asistencia.ESTADO_PENDIENTE),
        'obras_disponibles': consultas.obras_visibles(perfil),
        'obra_fija': consultas.obra_fija(perfil),
        'obra_id': obra_id,
    })


@revisor_requerido
def asistencia_mes(request):
    perfil = request.perfil
    hoy = consultas.hoy_local()
    try:
        anio, mes = (int(x) for x in request.GET.get('mes', '').split('-'))
        date(anio, mes, 1)
    except ValueError:
        anio, mes = hoy.year, hoy.month
    obra_id = consultas.obra_fija(perfil) or consultas.parse_int(request.GET.get('obra'))
    dias, filas = consultas.asistencia_mensual(perfil, anio, mes, obra_id)
    primero = date(anio, mes, 1)
    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)
    return render(request, 'marvelec_app/supervision/asistencia_mes.html', {
        'dias': dias, 'filas': filas, 'primero': primero, 'hoy': hoy,
        'anterior': anterior, 'siguiente': siguiente if siguiente <= hoy else None,
        'obras_disponibles': consultas.obras_visibles(perfil),
        'obra_fija': consultas.obra_fija(perfil),
        'obra_id': obra_id,
        'querystring': urlencode({k: v for k, v in {'mes': f'{anio}-{mes:02d}', 'obra': obra_id or ''}.items() if v}),
    })


def _asistencia_visible(perfil, pk):
    asistencia = get_object_or_404(Asistencia.objects.select_related('trabajador', 'obra'), pk=pk)
    if not perfil.puede_revisar_obra(asistencia.obra_id):
        raise Http404
    return asistencia


@require_POST
@revisor_requerido
def revisar_asistencia(request, pk):
    asistencia = _asistencia_visible(request.perfil, pk)
    form = RevisionAsistenciaForm(request.POST)
    if not form.is_valid():
        mensaje = ' '.join(form.non_field_errors()) or 'Acción inválida.'
        if es_fetch(request):
            return JsonResponse({'ok': False, 'mensaje': mensaje}, status=400)
        messages.error(request, mensaje)
    else:
        revisar_marca(asistencia, request.user, form.cleaned_data['accion'], form.cleaned_data['motivo'])
        if es_fetch(request):
            return JsonResponse({'ok': True, 'estado': asistencia.estado,
                                 'etiqueta': asistencia.get_estado_display()})
        messages.success(request, f'Asistencia {asistencia.get_estado_display().lower()}.')
    return redirigir_seguro(request, reverse('marvelec_app:asistencia_dia') + f'?fecha={asistencia.fecha.isoformat()}')


@require_POST
@revisor_requerido
def confirmar_asistencias(request):
    ids = [i for i in request.POST.getlist('ids') if i.isdigit()]
    n = 0
    for asistencia in Asistencia.objects.filter(pk__in=ids, estado=Asistencia.ESTADO_PENDIENTE).select_related('obra'):
        if request.perfil.puede_revisar_obra(asistencia.obra_id):
            revisar_marca(asistencia, request.user, 'confirmar')
            n += 1
    messages.success(request, f'{n} llegada(s) confirmadas.')
    return redirigir_seguro(request, reverse('marvelec_app:asistencia_dia'))


# =========================================================
# REVISIÓN DE REPORTES
# =========================================================

def _marcar_sin_asistencia(reportes):
    """Marca los reportes de días en que el trabajador no tiene asistencia confirmada (registro inconsistente)."""
    claves = {(r.trabajador_id, timezone.localtime(r.fecha_hora).date()) for r in reportes}
    if not claves:
        return
    confirmadas = set(Asistencia.objects.filter(
        trabajador_id__in={t for t, _ in claves}, fecha__in={f for _, f in claves},
        estado=Asistencia.ESTADO_CONFIRMADA,
    ).values_list('trabajador_id', 'fecha'))
    for r in reportes:
        r.sin_asistencia = (r.trabajador_id, timezone.localtime(r.fecha_hora).date()) not in confirmadas


@revisor_requerido
def cola_revision(request):
    perfil = request.perfil
    filtros = consultas.leer_filtros(request.GET)
    pendientes = consultas.aplicar_filtros(consultas.reportes_visibles(perfil), filtros).filter(
        estado=ReporteAvance.ESTADO_PENDIENTE
    ).exclude(trabajador=request.user).prefetch_related('avances__punto__tipo').order_by('fecha_hora')
    pagina = Paginator(pendientes, 20).get_page(request.GET.get('page'))
    _marcar_sin_asistencia(pagina.object_list)
    return render(request, 'marvelec_app/supervision/revisar.html', {
        **_contexto_filtros(perfil, filtros),
        'pagina': pagina,
        'total': pagina.paginator.count,
    })


@require_POST
@revisor_requerido
def revisar_masivo(request):
    """Aprueba varios reportes pendientes a la vez."""
    ids = [i for i in request.POST.getlist('ids') if i.isdigit()]
    reportes = consultas.reportes_visibles(request.perfil).filter(
        pk__in=ids, estado=ReporteAvance.ESTADO_PENDIENTE
    ).exclude(trabajador=request.user)
    n = 0
    for reporte in reportes:
        revisar_reporte(reporte, request.user, 'aprobar')
        n += 1
    texto = f'{n} reporte(s) aprobados.'
    if es_fetch(request):
        return JsonResponse({'ok': True, 'aprobados': n, 'mensaje': texto})
    messages.success(request, texto)
    return redirect('marvelec_app:cola_revision')


@revisor_requerido
def lista_reportes(request):
    perfil = request.perfil
    filtros = consultas.leer_filtros(request.GET)
    reportes = consultas.aplicar_filtros(consultas.reportes_visibles(perfil), filtros).order_by('-fecha_hora')
    pagina = Paginator(reportes, 25).get_page(request.GET.get('page'))
    return render(request, 'marvelec_app/supervision/reportes.html', {
        **_contexto_filtros(perfil, filtros),
        'pagina': pagina,
        'total_puntos': consultas.avances_de(reportes, filtros).count(),
        'querystring': _querystring(filtros),
    })


@revisor_requerido
def trabajadores(request):
    perfil = request.perfil
    hoy = consultas.hoy_local()
    filtros = consultas.leer_filtros(request.GET, desde_por_defecto=hoy.replace(day=1))
    reportes = consultas.aplicar_filtros(consultas.reportes_visibles(perfil), filtros)
    ranking = consultas.ranking_trabajadores(reportes, filtros['desde'], filtros['hasta'] or hoy)

    con_reportes = {r['id'] for r in ranking}
    a_cargo = consultas.trabajadores_de(perfil)
    if filtros['obra']:
        a_cargo = a_cargo.filter(obra_asignada_id=filtros['obra'])
    sin_actividad = [p for p in a_cargo if p.usuario_id not in con_reportes]

    ultimos = dict(reportes.order_by().values('trabajador_id').annotate(ultimo=Max('fecha_hora'))
                   .values_list('trabajador_id', 'ultimo'))
    for r in ranking:
        r['ultimo'] = ultimos.get(r['id'])

    return render(request, 'marvelec_app/supervision/trabajadores.html', {
        **_contexto_filtros(perfil, filtros),
        'ranking': ranking,
        'max_rendimiento': max((r['rendimiento'] for r in ranking), default=0),
        'sin_actividad': sin_actividad,
        'querystring': _querystring(filtros),
        'estandares': etapas.ETAPAS,
    })


# =========================================================
# CARGA DE PUNTOS DESDE EXCEL
# =========================================================

@revisor_requerido
def cargar_puntos(request):
    perfil = request.perfil
    obras = consultas.obras_visibles(perfil)

    if request.method == 'POST' and 'confirmar' in request.POST:
        try:
            datos = signing.loads(request.POST.get('datos', ''), salt=SALT_CARGA, max_age=3600)
            obra = obras.get(pk=datos['obra'])
        except (signing.BadSignature, KeyError, obras.model.DoesNotExist):
            messages.error(request, 'La vista previa expiró o no es válida. Vuelve a subir la planilla.')
            return redirect('marvelec_app:cargar_puntos')
        resumen = importador.aplicar(importador.Resultado.desde_lista(datos['puntos']), obra)
        messages.success(
            request, f"Carga lista: {resumen['creados']} punto(s) nuevos y {resumen['actualizados']} actualizados "
                     f"en {resumen['racks']} rack(s)."
        )
        return redirect(reverse('marvelec_app:avance_obra') + f'?obra={obra.pk}')

    form = CargarPuntosForm(request.POST or None, request.FILES or None, obras=obras)
    context = {'form': form}
    if request.method == 'POST' and form.is_valid():
        obra = form.cleaned_data['obra']
        resultado = importador.leer_excel(form.cleaned_data['archivo'])
        context.update({
            'obra': obra,
            'resultado': resultado,
            'racks': resultado.resumen_por_rack(),
            'comparacion': importador.comparar(resultado, obra),
            'datos': signing.dumps({'obra': obra.pk, 'puntos': resultado.serializar()}, salt=SALT_CARGA, compress=True)
            if resultado.puntos and not resultado.errores else '',
        })
    return render(request, 'marvelec_app/supervision/cargar_puntos.html', context)


@revisor_requerido
def plantilla_puntos(request):
    libro = importador.plantilla_tabla()
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="plantilla_puntos_marvelec.xlsx"'
    libro.save(response)
    return response
