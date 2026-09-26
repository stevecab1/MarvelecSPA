# marvelec_app/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import RegistroPunto


@receiver(post_save, sender=RegistroPunto)
def recalcular_total_al_guardar(sender, instance, **kwargs):
    """Cada vez que se guarda un registro de puntos, se actualiza el total del reporte."""
    instance.reporte.calcular_total_puntos()


@receiver(post_delete, sender=RegistroPunto)
def recalcular_total_al_borrar(sender, instance, **kwargs):
    """Si se elimina un registro de puntos, también se recalcula el total del reporte."""
    try:
        instance.reporte.calcular_total_puntos()
    except Exception:
        pass
