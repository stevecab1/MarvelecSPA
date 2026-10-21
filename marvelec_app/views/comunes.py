# marvelec_app/views/comunes.py
"""Autenticación, utilidades de permisos, detalle/revisión de reportes, avisos, tareas y PWA."""
from functools import wraps
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timesince import timesince
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .. import consultas
from ..forms import RevisionForm
from ..models import Notificacion, PerfilTrabajador, ReporteAvance
from ..servicios import revisar_reporte

# Cambiar al modificar sw.js para forzar su actualización en los dispositivos.
SW_VERSION = '3.0.0'


# =========================================================
# UTILIDADES
# =========================================================

def get_perfil(user):
    """Devuelve el PerfilTrabajador del usuario, creándolo si por algún motivo no existe."""
    perfil, _ = PerfilTrabajador.objects.select_related('obra_asignada').get_or_create(usuario=user)
    return perfil


def revisor_requerido(vista):
    """Sólo supervisores y gerencia; un trabajador vuelve a su app."""
    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        perfil = get_perfil(request.user)
        if not perfil.es_supervisor_o_gerencia:
            return redirect('marvelec_app:panel_trabajador')
        request.perfil = perfil
        return vista(request, *args, **kwargs)
    return envoltura


def es_fetch(request):
    return request.headers.get('X-Requested-With') == 'fetch'


def redirigir_seguro(request, por_defecto):
    siguiente = request.POST.get('next')
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
        return redirect(siguiente)
    return redirect(por_defecto)


# =========================================================
# AUTENTICACIÓN
# =========================================================

def login_usuario(request):
    if request.user.is_authenticated:
        return redirect('marvelec_app:panel')

    siguiente = request.POST.get('next') or request.GET.get('next') or ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
                return redirect(siguiente)
            return redirect('marvelec_app:panel')
        messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'registration/login.html', {'next': siguiente})


def logout_usuario(request):
    logout(request)
    return redirect(reverse('marvelec_app:login') + '?salida=1')


@login_required
def dashboard_redirect(request):
    perfil = get_perfil(request.user)
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return redirect('marvelec_app:panel_trabajador')
    return redirect('marvelec_app:panel_supervision')


# =========================================================
# DETALLE Y REVISIÓN DE REPORTES
# =========================================================

@login_required
def reporte_detalle(request, pk):
    perfil = get_perfil(request.user)
    reporte = get_object_or_404(
        ReporteAvance.objects.select_related('trabajador', 'obra', 'rack', 'revisado_por')
        .prefetch_related('avances__punto__tipo'),
        pk=pk,
    )
    if not reporte.puede_ver(perfil):
        raise Http404

    puede_revisar = perfil.puede_revisar_obra(reporte.obra_id) and reporte.trabajador_id != request.user.id
    context = {
        'reporte': reporte,
        'perfil': perfil,
        'grupos': reporte.codigos_por_etapa(),
        'puede_revisar': puede_revisar,
        'puede_editar': reporte.puede_editar(request.user),
        'revision_form': RevisionForm() if puede_revisar else None,
        'siguiente_pendiente': None,
    }
    if puede_revisar:
        context['siguiente_pendiente'] = consultas.reportes_visibles(perfil).filter(
            estado=ReporteAvance.ESTADO_PENDIENTE
        ).exclude(pk=reporte.pk).exclude(trabajador=request.user).order_by('fecha_hora').first()
        context['asistencia_confirmada'] = consultas.asistencia_confirmada(
            reporte.trabajador_id, timezone.localtime(reporte.fecha_hora).date()
        )

    plantilla = 'marvelec_app/reporte_detalle.html' if perfil.es_supervisor_o_gerencia \
        else 'marvelec_app/trabajador/reporte_detalle.html'
    return render(request, plantilla, context)


@require_POST
@revisor_requerido
def revisar(request, pk):
    """Aprobar u observar un reporte (formulario normal o fetch desde la cola de revisión)."""
    reporte = get_object_or_404(ReporteAvance.objects.select_related('trabajador', 'obra', 'rack'), pk=pk)
    if not request.perfil.puede_revisar_obra(reporte.obra_id) or reporte.trabajador_id == request.user.id:
        raise Http404

    form = RevisionForm(request.POST)
    if not form.is_valid():
        mensaje = ' '.join(form.non_field_errors()) or 'Acción inválida.'
        if es_fetch(request):
            return JsonResponse({'ok': False, 'mensaje': mensaje}, status=400)
        messages.error(request, mensaje)
        return redirect('marvelec_app:reporte_detalle', pk=pk)

    revisar_reporte(reporte, request.user, form.cleaned_data['accion'], form.cleaned_data['comentario'])
    texto = 'Reporte aprobado.' if reporte.estado == ReporteAvance.ESTADO_APROBADO else 'Reporte observado; se avisó al trabajador.'

    if es_fetch(request):
        return JsonResponse({'ok': True, 'estado': reporte.estado, 'mensaje': texto})
    messages.success(request, texto)
    return redirigir_seguro(request, reverse('marvelec_app:reporte_detalle', args=[pk]))


# =========================================================
# CENTRO DE NOTIFICACIONES
# =========================================================

def _notif_json(n):
    return {
        'id': n.id,
        'tipo': n.tipo,
        'titulo': n.titulo,
        'cuerpo': n.cuerpo,
        'leida': n.leida,
        'hace': timesince(n.creada).split(',')[0],
        'url_leer': reverse('marvelec_app:notificacion_leer', args=[n.pk]),
    }


@login_required
def notificaciones(request):
    perfil = get_perfil(request.user)
    pagina = Paginator(Notificacion.objects.filter(usuario=request.user), 30).get_page(request.GET.get('page'))
    plantilla = 'marvelec_app/supervision/notificaciones.html' if perfil.es_supervisor_o_gerencia \
        else 'marvelec_app/trabajador/notificaciones.html'
    return render(request, plantilla, {'pagina': pagina, 'perfil': perfil})


@never_cache
@login_required
def notificaciones_estado(request):
    """JSON para la campanita: cantidad de no leídas y últimas 10."""
    qs = Notificacion.objects.filter(usuario=request.user)
    data = {
        'no_leidas': qs.filter(leida=False).count(),
        'ultimas': [_notif_json(n) for n in qs[:10]],
    }
    perfil = get_perfil(request.user)
    if perfil.es_supervisor_o_gerencia:
        data['pendientes_revision'] = consultas.reportes_visibles(perfil).filter(
            estado=ReporteAvance.ESTADO_PENDIENTE
        ).exclude(trabajador=request.user).count()
    return JsonResponse(data)


@require_POST
@login_required
def notificacion_leer(request, pk):
    n = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    if not n.leida:
        n.leida = True
        n.save(update_fields=['leida'])
    destino = n.url or reverse('marvelec_app:notificaciones')
    if es_fetch(request):
        return JsonResponse({'ok': True, 'url': destino})
    return redirect(destino)


@require_POST
@login_required
def notificaciones_leer_todas(request):
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    if es_fetch(request):
        return JsonResponse({'ok': True})
    return redirect('marvelec_app:notificaciones')


# =========================================================
# TAREAS PROGRAMADAS (disparadas por GitHub Actions)
# =========================================================

@csrf_exempt  # protegido por el token X-Cron-Token
@require_POST
def tarea_resumen_diario(request):
    token = request.headers.get('X-Cron-Token', '')
    if not settings.CRON_TOKEN or not hmac.compare_digest(token, settings.CRON_TOKEN):
        return JsonResponse({'ok': False, 'mensaje': 'No autorizado'}, status=403)
    from ..resumen import enviar_resumen_diario
    resultado = enviar_resumen_diario(consultas.hoy_local())
    return JsonResponse({'ok': True, **resultado})


# =========================================================
# PWA: Service Worker y manifest servidos desde la raíz
# =========================================================

def service_worker(request):
    contenido = render_to_string('marvelec_app/pwa/sw.js', {'version': SW_VERSION})
    response = HttpResponse(contenido, content_type='application/javascript; charset=utf-8')
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


def manifest(request):
    contenido = render_to_string('marvelec_app/pwa/manifest.webmanifest')
    response = HttpResponse(contenido, content_type='application/manifest+json; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    return response
