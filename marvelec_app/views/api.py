# marvelec_app/views/api.py
"""
APIs que usa la app del celular. Todo lo que el trabajador envía pasa primero por la bandeja
del teléfono (outbox.js), así que cada endpoint es idempotente gracias a `uuid_cliente`.
"""
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..forms import AsistenciaForm, IncidenciaForm, ReporteAvanceForm
from ..servicios import crear_reporte, leer_uuid, marcar_asistencia, registrar_incidencia
from .comunes import get_perfil


def _rechazo_previo(request):
    """Sesión expirada o registro guardado en el teléfono por otro usuario."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'mensaje': 'Sesión expirada.'}, status=401)
    usuario_id = request.POST.get('usuario_id')
    if usuario_id and usuario_id != str(request.user.id):
        return JsonResponse({'ok': False, 'mensaje': 'Este registro pertenece a otro usuario.'}, status=409)
    return None


def _errores(form):
    errores = form.errors.get_json_data()
    primero = next((e[0]['message'] for e in errores.values() if e), 'Datos inválidos.')
    return JsonResponse({'ok': False, 'mensaje': primero, 'errores': errores}, status=400)


def _envio(request):
    return {
        'uuid_cliente': leer_uuid(request.POST.get('uuid_cliente')),
        'fecha_cliente': request.POST.get('fecha_hora_cliente'),
        'offline': request.POST.get('offline') == '1',
    }


@require_POST
def api_crear_reporte(request):
    rechazo = _rechazo_previo(request)
    if rechazo:
        return rechazo

    perfil = get_perfil(request.user)
    archivos = request.FILES
    if 'foto_llegada' in archivos and 'foto' not in archivos:
        # Celulares con la versión anterior de la app (en caché o con reportes guardados sin señal).
        archivos = archivos.copy()
        archivos['foto'] = archivos['foto_llegada']
    form = ReporteAvanceForm(request.POST, archivos, obra_asignada=perfil.obra_asignada)
    if not form.is_valid():
        return _errores(form)

    try:
        reporte, creado = crear_reporte(request.user, form, **_envio(request))
    except ValidationError as e:
        return JsonResponse({'ok': False, 'mensaje': ' '.join(e.messages)}, status=400)

    return JsonResponse({
        'ok': True,
        'id': reporte.pk,
        'duplicado': not creado,
        'total_puntos': reporte.total_puntos,
        'omitidos': reporte.omitidos,
        'url': reverse('marvelec_app:reporte_detalle', args=[reporte.pk]),
    }, status=201 if creado else 200)


@require_POST
def api_incidencia(request):
    rechazo = _rechazo_previo(request)
    if rechazo:
        return rechazo

    perfil = get_perfil(request.user)
    form = IncidenciaForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
    if not form.is_valid():
        return _errores(form)

    d = form.cleaned_data
    try:
        creadas, omitidos, nuevas = registrar_incidencia(
            request.user, form.puntos, d['tipo'], d.get('foto'), d['comentario'], d['latitud'], d['longitud'],
            **_envio(request),
        )
    except ValidationError as e:
        return JsonResponse({'ok': False, 'mensaje': ' '.join(e.messages)}, status=400)

    return JsonResponse({
        'ok': True, 'duplicado': not nuevas, 'n': len(creadas), 'omitidos': omitidos,
        'codigos': [i.punto.codigo for i in creadas],
    }, status=201 if nuevas else 200)


@require_POST
def api_asistencia(request):
    rechazo = _rechazo_previo(request)
    if rechazo:
        return rechazo

    perfil = get_perfil(request.user)
    form = AsistenciaForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
    if not form.is_valid():
        return _errores(form)

    d = form.cleaned_data
    try:
        asistencia, creada = marcar_asistencia(
            request.user, d['obra'], d['foto'], d['latitud'], d['longitud'], d.get('precision'), **_envio(request),
        )
    except ValidationError as e:
        return JsonResponse({'ok': False, 'mensaje': ' '.join(e.messages)}, status=400)

    return JsonResponse({
        'ok': True, 'duplicado': not creada, 'id': asistencia.pk, 'estado': asistencia.estado,
        'fecha': asistencia.fecha.isoformat(),
    }, status=201 if creada else 200)
