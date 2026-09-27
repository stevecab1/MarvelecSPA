# marvelec_app/push.py
"""
Módulo de notificaciones push (Web Push / VAPID).

Las claves VAPID se leen de las variables de entorno VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY
(obligatorio en Render: el disco se borra en cada deploy y, si las claves cambian, todas las
suscripciones quedan inválidas). Genéralas una vez con `python manage.py generar_vapid`.
En desarrollo, si no hay variables, se generan y guardan en vapid_keys.json.
"""
import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required

from .models import SuscripcionPush

# Ruta donde se guardan las claves VAPID generadas automáticamente
VAPID_KEYS_FILE = Path(settings.BASE_DIR) / 'vapid_keys.json'


def generar_claves_vapid():
    """Genera un par nuevo de claves VAPID: {'private_key': PEM, 'public_key': base64url}."""
    import base64
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    vapid = Vapid()
    vapid.generate_keys()
    raw_pub = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return {
        'private_key': vapid.private_pem().decode(),
        'public_key': base64.urlsafe_b64encode(raw_pub).decode().rstrip('='),
    }


def _get_vapid_keys():
    """Obtiene las claves VAPID desde el entorno o, en desarrollo, desde/hacia un archivo local."""
    if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY:
        # En variables de entorno los saltos de línea del PEM suelen venir escritos como "\n".
        return {
            'public_key': settings.VAPID_PUBLIC_KEY,
            'private_key': settings.VAPID_PRIVATE_KEY.replace('\\n', '\n'),
        }

    if VAPID_KEYS_FILE.exists():
        with open(VAPID_KEYS_FILE) as f:
            return json.load(f)

    keys = generar_claves_vapid()
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


@require_POST
@login_required
def desuscribir_push(request):
    """Elimina la suscripción push de este dispositivo (el usuario desactivó los avisos)."""
    try:
        endpoint = json.loads(request.body).get('endpoint')
    except ValueError:
        endpoint = None
    if endpoint:
        SuscripcionPush.objects.filter(endpoint=endpoint, usuario=request.user).delete()
    return JsonResponse({'ok': True})


def enviar_notificacion_push(usuario_destino, titulo, cuerpo, url='/panel/', tag='marvelec', no_leidas=None):
    """Envía una notificación push a TODOS los dispositivos (celular, PC) de un usuario."""
    try:
        from pywebpush import webpush
    except ImportError:
        print("AVISO: pywebpush no está instalado. No se envían notificaciones push.")
        return

    suscripciones = list(SuscripcionPush.objects.filter(usuario=usuario_destino))
    if not suscripciones:
        return

    keys = _get_vapid_keys()
    payload = json.dumps({
        'title': titulo,
        'body': cuerpo,
        'url': url,
        'tag': tag,
        'no_leidas': no_leidas,
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
                vapid_claims={'sub': f'mailto:{settings.VAPID_CLAIM_EMAIL}'},
                ttl=24 * 60 * 60,
            )
        except Exception as e:
            # Si la suscripción expiró o fue revocada, la eliminamos
            respuesta = getattr(e, 'response', None)
            if respuesta is not None and respuesta.status_code in (404, 410):
                sub.delete()
            else:
                print(f"Error enviando push a {sub.usuario.username}: {e}")


def enviar_notificacion_email(reporte, destinatarios):
    """Envía un correo a los supervisores/gerentes cuando se crea un reporte."""
    from django.core.mail import send_mail

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
        f'Fecha: {timezone.localtime(reporte.fecha_hora).strftime("%d-%m-%Y %H:%M")}\n\n'
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
