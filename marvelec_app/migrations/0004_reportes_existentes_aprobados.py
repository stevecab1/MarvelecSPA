from django.db import migrations


def aprobar_existentes(apps, schema_editor):
    """Los reportes creados antes de existir la revisión quedan aprobados (no llenan la cola)."""
    ReporteAvance = apps.get_model('marvelec_app', 'ReporteAvance')
    ReporteAvance.objects.filter(estado='pendiente').update(estado='aprobado')


class Migration(migrations.Migration):

    dependencies = [
        ('marvelec_app', '0003_revision_offline_notificaciones'),
    ]

    operations = [
        migrations.RunPython(aprobar_existentes, migrations.RunPython.noop),
    ]
