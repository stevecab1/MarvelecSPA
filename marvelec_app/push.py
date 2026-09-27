# marvelec_app/push.py
"""
Módulo de notificaciones push (Web Push / VAPID).
Genera las claves VAPID automáticamente la primera vez, las guarda en un archivo
local y las reutiliza en adelante. No requiere configuración manual.
"""
import json
import os
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required

from .models import SuscripcionPush, PerfilTrabajador

# Ruta donde se guardan las claves VAPID generadas automáticamente
VAPID_KEYS_FILE = Path(settings.BASE_DIR) / 'vapid_keys.json'


def _get_vapid_keys():
    """Obtiene o genera las claves VAPID (se crean una sola vez)."""
    if VAPID_KEYS_FILE.exists():
        with open(VAPID_KEYS_FILE) as f:
            return json.load(f)

    import base64
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    vapid = Vapid()
    vapid.generate_keys()

    private_pem = vapid.private_pem().decode()
    raw_pub = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_key_b64 = base64.urlsafe_b64encode(raw_pub).decode().rstrip('=')

    keys = {
        'private_key': private_pem,
        'public_key': public_key_b64,
    }

    with open(VAPID_KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)
    print(f"VAPID keys generadas y guardadas en {VAPID_KEYS_FILE}")
    return keys


@require_GET
@login_required
def vapid_public_key(request):
    """Devuelve la clave pública VAPID al navegador para suscribirse."""
    keys = _get_vapid_keys()
    return JsonResponse({'public_key': keys['public_key']})


@require_POST
@login_required
def suscribir_push(request):
    """Guarda o actualiza la suscripción push de un usuario."""
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint')
        p256dh = data.get('keys', {}).get('p256dh', '')
        auth = data.get('keys', {}).get('auth', '')

        if not endpoint:
            return JsonResponse({'error': 'Faltan datos'}, status=400)

        SuscripcionPush.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                'usuario': request.user,
                'p256dh': p256dh,
                'auth': auth,
            }
        )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def enviar_notificacion_push(usuario_destino, titulo, cuerpo, url='/panel/'):
    """
    Envía una notificación push a TODOS los dispositivos de un usuario.
    Se llama desde signals.py cuando un trabajador envía un reporte.
    """
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("AVISO: pywebpush no está instalado. No se envían notificaciones push.")
        return

    keys = _get_vapid_keys()
    suscripciones = SuscripcionPush.objects.filter(usuario=usuario_destino)

    payload = json.dumps({
        'title': titulo,
        'body': cuerpo,
        'url': url,
        'tag': 'reporte-nuevo',
    })

    for sub in suscripciones:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=keys['private_key'],
                vapid_claims={'sub': 'mailto:notificaciones@marvelec.cl'},
            )
        except Exception as e:
            # Si la suscripción expiró o fue revocada, la eliminamos
            if hasattr(e, 'response') and e.response and e.response.status_code in (404, 410):
                sub.delete()
            else:
                print(f"Error enviando push a {sub.usuario.username}: {e}")


def notificar_supervisores_de_obra(reporte):
    """
    Notifica a todos los supervisores y gerentes asociados a la obra
    del reporte recién creado (push + email).
    """
    from django.contrib.auth.models import User

    titulo = '📋 Nuevo reporte de avance'
    trabajador_nombre = reporte.trabajador.get_full_name() or reporte.trabajador.username
    cuerpo = (
        f'{trabajador_nombre} reportó {reporte.total_puntos} puntos '
        f'en {reporte.obra.nombre} / {reporte.subetapa.nombre}'
    )

    perfiles = PerfilTrabajador.objects.filter(
        rol__in=[PerfilTrabajador.ROL_SUPERVISOR, PerfilTrabajador.ROL_GERENCIA]
    ).select_related('usuario')

    destinatarios_email = []

    for perfil in perfiles:
        if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada_id:
            if perfil.obra_asignada_id != reporte.obra_id:
                continue
        enviar_notificacion_push(
            perfil.usuario, titulo, cuerpo,
            url=f'/panel/supervision/?obra={reporte.obra_id}'
        )
        if perfil.usuario.email:
            destinatarios_email.append(perfil.usuario.email)

    if destinatarios_email:
        enviar_notificacion_email(reporte, destinatarios_email)


def enviar_notificacion_email(reporte, destinatarios):
    """Envía un correo a los supervisores/gerentes cuando se crea un reporte."""
    from django.core.mail import send_mail
    from django.conf import settings

    trabajador_nombre = reporte.trabajador.get_full_name() or reporte.trabajador.username

    conteo = {}
    for registro in reporte.registros.all():
        conteo[registro.get_tipo_punto_display()] = registro.cantidad

    detalle_puntos = '\n'.join(
        f'  - {tipo}: {cant}' for tipo, cant in conteo.items() if cant > 0
    )

    asunto = (
        f'[MARVELEC] {trabajador_nombre} reportó {reporte.total_puntos} puntos '
        f'en {reporte.obra.nombre}'
    )

    mensaje = (
        f'Nuevo reporte de avance\n'
        f'========================\n\n'
        f'Trabajador: {trabajador_nombre}\n'
        f'Obra: {reporte.obra.nombre}\n'
        f'Subetapa: {reporte.subetapa.nombre}\n'
        f'Fecha: {reporte.fecha_hora.strftime("%d-%m-%Y %H:%M")}\n\n'
        f'Puntos ejecutados ({reporte.total_puntos} total):\n'
        f'{detalle_puntos}\n'
    )

    if reporte.comentario:
        mensaje += f'\nComentario: {reporte.comentario}\n'

    mensaje += '\n--\nMARVELEC SPA - Sistema de Reporte y Seguimiento de Avance'

    try:
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinatarios,
            fail_silently=True,
        )
    except Exception:
        pass
