from django.db import migrations


def borrar_reportes_antiguos(apps, schema_editor):
    """
    Los reportes por cantidades (red/fuerza/iluminación) no se pueden convertir al seguimiento
    por punto y etapa: eran datos de prueba previos al piloto. Se borran con sus avisos.
    """
    ReporteAvance = apps.get_model('marvelec_app', 'ReporteAvance')
    ReporteAvance.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marvelec_app', '0005_reporteavance_foto'),
    ]

    operations = [
        migrations.RunPython(borrar_reportes_antiguos, migrations.RunPython.noop),
    ]
