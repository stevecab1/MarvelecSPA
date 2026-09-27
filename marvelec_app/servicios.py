# marvelec_app/servicios.py
"""
Reglas de negocio de los reportes, compartidas por el formulario web y la API
que usa la app del celular para enviar reportes guardados sin señal.
"""
import uuid
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ReporteAvance
from .notificaciones import notificar_nuevo_reporte, notificar_revision

# Un reporte guardado sin señal puede llegar hasta 7 días después.
MAX_ATRASO_OFFLINE = timedelta(days=7)


def leer_uuid(valor):
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def leer_fecha_cliente(valor):
    """
    Hora en que el trabajador creó el reporte en su celular. Se acepta sólo si es
    razonable (no futura, no más antigua que MAX_ATRASO_OFFLINE); si no, se usa la hora actual.
    """
    ahora = timezone.now()
    if not valor:
        return ahora
    try:
        fecha = datetime.fromisoformat(str(valor))
    except ValueError:
        return ahora
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    if fecha > ahora + timedelta(minutes=5) or fecha < ahora - MAX_ATRASO_OFFLINE:
        return ahora
    return min(fecha, ahora)


def crear_reporte(usuario, form, puntos_form, uuid_cliente=None, fecha_cliente=None, offline=False):
    """
    Guarda un reporte nuevo de forma atómica y notifica a los supervisores.
    Idempotente: si ya existe un reporte con el mismo uuid_cliente, lo devuelve sin duplicarlo.
    Devuelve (reporte, creado).
    """
    if uuid_cliente:
        existente = ReporteAvance.objects.filter(uuid_cliente=uuid_cliente, trabajador=usuario).first()
        if existente:
            return existente, False

    try:
        with transaction.atomic():
            reporte = form.save(commit=False)
            reporte.trabajador = usuario
            reporte.fecha_hora = leer_fecha_cliente(fecha_cliente)
            reporte.uuid_cliente = uuid_cliente
            reporte.enviado_offline = offline
            reporte.full_clean(exclude=['total_puntos'])  # valida coherencia obra-subetapa
            reporte.save()
            puntos_form.guardar(reporte)
    except IntegrityError:
        # Dos reintentos simultáneos del mismo envío: gana el primero.
        existente = ReporteAvance.objects.filter(uuid_cliente=uuid_cliente, trabajador=usuario).first()
        if existente:
            return existente, False
        raise

    notificar_nuevo_reporte(reporte)
    return reporte, True


def corregir_reporte(reporte, form, puntos_form):
    """El trabajador corrige un reporte observado: vuelve a quedar pendiente de revisión."""
    with transaction.atomic():
        reporte = form.save(commit=False)
        reporte.full_clean(exclude=['total_puntos'])
        reporte.estado = ReporteAvance.ESTADO_PENDIENTE
        reporte.save()
        puntos_form.guardar(reporte)
    notificar_nuevo_reporte(reporte, corregido=True)
    return reporte


def revisar_reporte(reporte, revisor, accion, comentario=''):
    """Aprueba u observa un reporte y avisa al trabajador."""
    if accion == 'aprobar':
        reporte.aprobar(revisor)
    else:
        reporte.observar(revisor, comentario.strip())
    notificar_revision(reporte)
    return reporte
