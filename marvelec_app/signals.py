# marvelec_app/signals.py
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AvancePunto, ReporteAvance


@receiver(post_save, sender=AvancePunto)
def recalcular_total_al_guardar(sender, instance, **kwargs):
    """Si se agrega un avance (p. ej. desde el admin), se actualiza el total del reporte."""
    instance.reporte.calcular_total_puntos()


@receiver(post_delete, sender=AvancePunto)
def recalcular_total_al_borrar(sender, instance, **kwargs):
    try:
        instance.reporte.calcular_total_puntos()
    except ReporteAvance.DoesNotExist:
        pass  # se está borrando el reporte completo
