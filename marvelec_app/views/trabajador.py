# marvelec_app/views/trabajador.py
"""App del trabajador (celular): llegada, avance por punto, incidencias e historial."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .. import consultas
from ..forms import AsistenciaForm, IncidenciaForm, ReporteAvanceForm, obras_permitidas
from ..models import Asistencia, AvancePunto, Incidencia, ReporteAvance
from ..servicios import corregir_reporte, crear_reporte, marcar_asistencia as marcar, registrar_incidencia
from .comunes import get_perfil


def _avisar_omitidos(request, omitidos):
    if omitidos:
        detalle = '; '.join(f"{o['codigo']}: {o['motivo']}" if o.get('codigo') else o['motivo'] for o in omitidos[:5])
        extra = f' (y {len(omitidos) - 5} más)' if len(omitidos) > 5 else ''
        messages.warning(request, f'{len(omitidos)} no registrado(s): {detalle}{extra}')


def _mensajes_error(request, error):
    for mensaje in error.messages:
        messages.error(request, mensaje)


@login_required
def dashboard_trabajador(request):
    perfil = get_perfil(request.user)
    hoy = consultas.hoy_local()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    mis_reportes = ReporteAvance.objects.filter(trabajador=request.user)
    mis_avances = AvancePunto.objects.filter(reporte__trabajador=request.user)

    context = {
        'perfil': perfil,
        'hoy': hoy,
        'asistencia_hoy': Asistencia.objects.filter(trabajador=request.user, fecha=hoy).first(),
        'puntos_hoy': mis_avances.filter(reporte__fecha_hora__date=hoy).count(),
        'puntos_semana': mis_avances.filter(reporte__fecha_hora__date__gte=inicio_semana).count(),
        'reportes_semana': mis_reportes.filter(fecha_hora__date__gte=inicio_semana).count(),
        'observados': mis_reportes.filter(estado=ReporteAvance.ESTADO_OBSERVADO).select_related('rack'),
        'mis_incidencias': Incidencia.objects.filter(
            reportada_por=request.user, estado=Incidencia.ESTADO_ABIERTA
        ).select_related('punto__tipo', 'punto__rack', 'tipo')[:10],
        'recientes': mis_reportes.select_related('obra', 'rack').prefetch_related('avances')[:5],
    }
    return render(request, 'marvelec_app/trabajador/inicio.html', context)


def _contexto_selector(perfil, form, reporte=None):
    return {
        'perfil': perfil,
        'form': form,
        'selector': consultas.datos_selector(obras_permitidas(perfil.obra_asignada), excluir_reporte=reporte),
        'reporte': reporte,
    }


@login_required
def nuevo_reporte(request):
    """Formulario de avance. Con JS se envía por la API (con soporte sin señal); sin JS, por aquí."""
    perfil = get_perfil(request.user)
    if request.method == 'POST':
        form = ReporteAvanceForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
        if form.is_valid():
            try:
                reporte, _ = crear_reporte(request.user, form)
                messages.success(request, f'Reporte enviado: {reporte.total_puntos} etapa(s) registradas.')
                _avisar_omitidos(request, reporte.omitidos)
                return redirect('marvelec_app:panel_trabajador')
            except ValidationError as e:
                _mensajes_error(request, e)
        else:
            messages.error(request, 'Revisa los datos del reporte.')
    else:
        form = ReporteAvanceForm(obra_asignada=perfil.obra_asignada)
    return render(request, 'marvelec_app/trabajador/nuevo_reporte.html', _contexto_selector(perfil, form))


@login_required
def editar_reporte(request, pk):
    """El trabajador corrige un reporte que el supervisor observó."""
    reporte = get_object_or_404(ReporteAvance.objects.select_related('obra', 'rack'), pk=pk)
    if not reporte.puede_editar(request.user):
        raise Http404
    perfil = get_perfil(request.user)

    if request.method == 'POST':
        form = ReporteAvanceForm(request.POST, request.FILES, instance=reporte, obra_asignada=perfil.obra_asignada)
        if form.is_valid():
            try:
                reporte = corregir_reporte(reporte, form)
                messages.success(request, 'Reporte corregido y enviado nuevamente a revisión.')
                _avisar_omitidos(request, reporte.omitidos)
                return redirect('marvelec_app:reporte_detalle', pk=reporte.pk)
            except ValidationError as e:
                _mensajes_error(request, e)
        else:
            messages.error(request, 'Revisa los datos del reporte.')
    else:
        form = ReporteAvanceForm(instance=reporte, obra_asignada=perfil.obra_asignada)
    return render(request, 'marvelec_app/trabajador/nuevo_reporte.html',
                  _contexto_selector(perfil, form, reporte=reporte))


@login_required
def nueva_incidencia(request):
    perfil = get_perfil(request.user)
    if request.method == 'POST':
        form = IncidenciaForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
        if form.is_valid():
            d = form.cleaned_data
            try:
                creadas, omitidos, _ = registrar_incidencia(
                    request.user, form.puntos, d['tipo'], d.get('foto'), d['comentario'], d['latitud'], d['longitud'],
                )
                messages.success(request, f'Incidencia registrada en {len(creadas)} punto(s). Se avisó al supervisor.')
                for texto in omitidos:
                    messages.warning(request, texto)
                return redirect('marvelec_app:panel_trabajador')
            except ValidationError as e:
                _mensajes_error(request, e)
        else:
            messages.error(request, 'Revisa los datos de la incidencia.')
    else:
        form = IncidenciaForm(obra_asignada=perfil.obra_asignada)
    return render(request, 'marvelec_app/trabajador/incidencia.html', _contexto_selector(perfil, form))


@login_required
def marcar_asistencia(request):
    perfil = get_perfil(request.user)
    hoy = consultas.hoy_local()
    asistencia_hoy = Asistencia.objects.filter(trabajador=request.user, fecha=hoy).first()
    if request.method == 'POST':
        form = AsistenciaForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
        if form.is_valid():
            d = form.cleaned_data
            try:
                marcar(request.user, d['obra'], d['foto'], d['latitud'], d['longitud'], d.get('precision'))
                messages.success(request, 'Llegada registrada. Tu supervisor la confirmará.')
                return redirect('marvelec_app:panel_trabajador')
            except ValidationError as e:
                _mensajes_error(request, e)
        else:
            messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    else:
        form = AsistenciaForm(obra_asignada=perfil.obra_asignada)
    return render(request, 'marvelec_app/trabajador/asistencia.html', {
        'perfil': perfil, 'form': form, 'asistencia_hoy': asistencia_hoy, 'hoy': hoy,
    })


@login_required
def historial_trabajador(request):
    ver = request.GET.get('ver', 'reportes')
    context = {'ver': ver}
    if ver == 'llegadas':
        context['asistencias'] = Asistencia.objects.filter(trabajador=request.user).select_related('obra')[:62]
    elif ver == 'incidencias':
        context['incidencias'] = Incidencia.objects.filter(reportada_por=request.user).select_related(
            'punto__tipo', 'punto__rack', 'tipo'
        )[:60]
    else:
        reportes = ReporteAvance.objects.filter(trabajador=request.user).select_related(
            'obra', 'rack'
        ).prefetch_related('avances')
        estado = request.GET.get('estado', '')
        if estado in dict(ReporteAvance.ESTADO_CHOICES):
            reportes = reportes.filter(estado=estado)
        context.update({
            'ver': 'reportes',
            'pagina': Paginator(reportes, 20).get_page(request.GET.get('page')),
            'estado': estado,
        })
    return render(request, 'marvelec_app/trabajador/historial.html', context)
