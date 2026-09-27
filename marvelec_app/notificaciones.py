# marvelec_app/notificaciones.py
"""
Centro de notificaciones: cada aviso queda guardado (campanita en la app) y además
se envía como push a los dispositivos del usuario. El envío push/correo corre en un
hilo aparte para que el trabajador no espere al enviar su reporte.
"""
import logging
import threading

from django.conf import settings
from django.contrib.auth.models import User
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.urls import reverse

from .models import Notificacion, PerfilTrabajador

logger = logging.getLogger(__name__)


def _en_segundo_plano(funcion, *args):
    """Ejecuta `funcion` tras el commit, en un hilo (o de inmediato si NOTIF_SINCRONO, p. ej. en tests)."""
    if settings.NOTIF_SINCRONO:
        funcion(*args)
        return

    def ejecutar():
        try:
            funcion(*args)
        except Exception:
            logger.exception('Error enviando notificaciones')
        finally:
            close_old_connections()

    transaction.on_commit(lambda: threading.Thread(target=ejecutar, daemon=True).start())


def _enviar_push(usuario_ids, titulo, cuerpo, url, tipo):
    from .push import enviar_notificacion_push
    for usuario in User.objects.filter(pk__in=usuario_ids):
        no_leidas = Notificacion.objects.filter(usuario=usuario, leida=False).count()
        try:
            enviar_notificacion_push(usuario, titulo, cuerpo, url=url, tag=tipo, no_leidas=no_leidas)
        except Exception:
            logger.exception('Error enviando push a %s', usuario.username)


def notificar(usuarios, tipo, titulo, cuerpo='', url='', reporte=None):
    """Crea la notificación en la app para cada usuario y la envía como push."""
    usuarios = list({u.pk: u for u in usuarios}.values())
    if not usuarios:
        return []
    creadas = Notificacion.objects.bulk_create([
        Notificacion(usuario=u, tipo=tipo, titulo=titulo, cuerpo=cuerpo, url=url, reporte=reporte)
        for u in usuarios
    ])
    _en_segundo_plano(_enviar_push, [u.pk for u in usuarios], titulo, cuerpo, url, tipo)
    return creadas


def revisores_de_obra(obra_id):
    """Supervisores de la obra (o sin obra fija) y gerencia, activos."""
    perfiles = PerfilTrabajador.objects.filter(usuario__is_active=True).filter(
        Q(rol=PerfilTrabajador.ROL_GERENCIA)
        | Q(rol=PerfilTrabajador.ROL_SUPERVISOR, obra_asignada_id=obra_id)
        | Q(rol=PerfilTrabajador.ROL_SUPERVISOR, obra_asignada__isnull=True)
    ).select_related('usuario')
    return [p.usuario for p in perfiles]


def url_reporte(reporte):
    return reverse('marvelec_app:reporte_detalle', args=[reporte.pk])


# --- Eventos del sistema ---

def notificar_nuevo_reporte(reporte, corregido=False):
    """Avisa a supervisores y gerencia de la obra que llegó (o se corrigió) un reporte."""
    destinatarios = [u for u in revisores_de_obra(reporte.obra_id) if u.pk != reporte.trabajador_id]
    if corregido:
        tipo = Notificacion.TIPO_REPORTE_CORREGIDO
        titulo = 'Reporte corregido'
        cuerpo = f'{reporte.nombre_trabajador} corrigió su reporte en {reporte.obra.nombre} / {reporte.subetapa.nombre}'
    else:
        tipo = Notificacion.TIPO_NUEVO_REPORTE
        titulo = 'Nuevo reporte de avance'
        cuerpo = (
            f'{reporte.nombre_trabajador} reportó {reporte.total_puntos} puntos '
            f'en {reporte.obra.nombre} / {reporte.subetapa.nombre}'
        )
    notificar(destinatarios, tipo, titulo, cuerpo, url_reporte(reporte), reporte)

    # Respaldo por correo (sólo reportes nuevos).
    correos = [u.email for u in destinatarios if u.email]
    if correos and not corregido:
        from .push import enviar_notificacion_email
        _en_segundo_plano(enviar_notificacion_email, reporte, correos)


def notificar_revision(reporte):
    """Avisa al trabajador que su reporte fue aprobado u observado."""
    if reporte.estado == reporte.ESTADO_APROBADO:
        tipo = Notificacion.TIPO_REPORTE_APROBADO
        titulo = 'Reporte aprobado'
        cuerpo = f'Tu reporte de {reporte.total_puntos} puntos en {reporte.subetapa.nombre} fue aprobado.'
    else:
        tipo = Notificacion.TIPO_REPORTE_OBSERVADO
        titulo = 'Reporte observado: requiere corrección'
        cuerpo = reporte.comentario_revision or 'Tu supervisor dejó una observación en tu reporte.'
    notificar([reporte.trabajador], tipo, titulo, cuerpo, url_reporte(reporte), reporte)
