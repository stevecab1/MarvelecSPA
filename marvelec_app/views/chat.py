# marvelec_app/views/chat.py
"""
Chat de consultas: conversaciones privadas entre un trabajador y su jefatura.

No hay grupos ni mensajes entre trabajadores. El hilo abierto se actualiza por sondeo
(`mensajes`), no por WebSocket: Render en plan gratuito no mantiene conexiones abiertas.
"""
from django.contrib import messages as avisos
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import consultas
from ..models import Conversacion, Mensaje
from ..servicios import enviar_mensaje, marcar_leidos
from .comunes import es_fetch, get_perfil

MENSAJES_POR_PAGINA = 60


def _layout(perfil):
    """El chat se ve igual en celular y PC; sólo cambia el marco."""
    return 'layouts/escritorio.html' if perfil.es_supervisor_o_gerencia else 'layouts/movil.html'


def _conversacion_visible(usuario, pk):
    conversacion = get_object_or_404(
        Conversacion.objects.select_related('usuario_menor', 'usuario_mayor'), pk=pk
    )
    if not conversacion.puede_ver(usuario):
        raise Http404
    return conversacion


def _json_mensaje(mensaje, usuario):
    return {
        'id': mensaje.pk,
        'texto': mensaje.texto,
        'foto': mensaje.foto.url if mensaje.foto else '',
        'propio': mensaje.autor_id == usuario.pk,
        'autor': mensaje.autor.get_full_name() or mensaje.autor.username,
        'hora': timezone.localtime(mensaje.enviado).strftime('%H:%M'),
        'fecha': timezone.localtime(mensaje.enviado).strftime('%d-%m-%Y'),
    }


@login_required
def bandeja(request):
    """Conversaciones con actividad y, debajo, con quién más se puede hablar."""
    perfil = get_perfil(request.user)
    sin_leer = consultas.sin_leer_por_conversacion(request.user)

    # Dos consultas: las conversaciones con el id de su último mensaje, y esos mensajes.
    hilos = consultas.conversaciones_de(request.user).annotate(
        ultimo_id=Subquery(
            Mensaje.objects.filter(conversacion=OuterRef('pk')).order_by('-enviado').values('pk')[:1]
        )
    )
    ultimos = Mensaje.objects.filter(pk__in=[h.ultimo_id for h in hilos if h.ultimo_id]).select_related('autor')
    ultimos = {m.pk: m for m in ultimos}

    conversaciones = []
    con_hilo = set()
    for hilo in hilos:
        ultimo = ultimos.get(hilo.ultimo_id)
        if ultimo is None:
            continue  # creada pero sin mensajes: aparece como contacto, no en la bandeja
        otro = hilo.otro(request.user)
        con_hilo.add(otro.pk)
        conversaciones.append({
            'conversacion': hilo,
            'otro': otro,
            'ultimo': ultimo,
            'propio': ultimo.autor_id == request.user.pk,
            'sin_leer': sin_leer.get(hilo.pk, 0),
        })

    disponibles = [p for p in consultas.contactos(perfil) if p.usuario_id not in con_hilo]
    return render(request, 'marvelec_app/chat/bandeja.html', {
        'layout': _layout(perfil),
        'perfil': perfil,
        'conversaciones': conversaciones,
        'contactos': disponibles,
    })


@login_required
def abrir(request, usuario_pk):
    """Abre (o crea) la conversación con esa persona, si está entre sus contactos."""
    perfil = get_perfil(request.user)
    otro = get_object_or_404(User, pk=usuario_pk, is_active=True)
    if not consultas.puede_conversar(perfil, otro):
        raise Http404
    conversacion, _ = Conversacion.entre(request.user, otro)
    return redirect('marvelec_app:chat_conversacion', pk=conversacion.pk)


@login_required
def conversacion(request, pk):
    perfil = get_perfil(request.user)
    hilo = _conversacion_visible(request.user, pk)
    marcar_leidos(hilo, request.user)

    mensajes = list(
        hilo.mensajes.select_related('autor').order_by('-enviado')[:MENSAJES_POR_PAGINA]
    )[::-1]
    return render(request, 'marvelec_app/chat/conversacion.html', {
        'layout': _layout(perfil),
        'perfil': perfil,
        'conversacion': hilo,
        'otro': hilo.otro(request.user),
        'mensajes': mensajes,
        'ultimo_id': mensajes[-1].pk if mensajes else 0,
    })


@require_POST
@login_required
def enviar(request, pk):
    hilo = _conversacion_visible(request.user, pk)
    try:
        mensaje = enviar_mensaje(request.user, hilo, request.POST.get('texto', ''), request.FILES.get('foto'))
    except ValidationError as e:
        texto = ' '.join(e.messages)
        if es_fetch(request):
            return JsonResponse({'ok': False, 'mensaje': texto}, status=400)
        avisos.error(request, texto)
        return redirect('marvelec_app:chat_conversacion', pk=pk)

    if es_fetch(request):
        return JsonResponse({'ok': True, 'mensaje': _json_mensaje(mensaje, request.user)}, status=201)
    return redirect('marvelec_app:chat_conversacion', pk=pk)


@login_required
def mensajes_nuevos(request, pk):
    """Sondeo del hilo abierto: devuelve lo posterior a `desde` y lo marca leído."""
    hilo = _conversacion_visible(request.user, pk)
    desde = consultas.parse_int(request.GET.get('desde')) or 0
    nuevos = list(hilo.mensajes.select_related('autor').filter(pk__gt=desde))
    if nuevos:
        marcar_leidos(hilo, request.user)
    return JsonResponse({
        'mensajes': [_json_mensaje(m, request.user) for m in nuevos],
        'ultimo_id': nuevos[-1].pk if nuevos else desde,
    })
