import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """La foto del reporte pasa a ser evidencia del avance; la llegada se registrará aparte."""

    dependencies = [
        ('marvelec_app', '0004_reportes_existentes_aprobados'),
    ]

    operations = [
        migrations.RenameField(
            model_name='reporteavance',
            old_name='foto_llegada',
            new_name='foto',
        ),
        migrations.AlterField(
            model_name='reporteavance',
            name='foto',
            field=models.ImageField(
                blank=True, null=True, upload_to='reportes/avance/%Y/%m/', verbose_name='Foto del avance'
            ),
        ),
        migrations.AlterField(
            model_name='reporteavance',
            name='fecha_hora',
            field=models.DateTimeField(
                db_index=True, default=django.utils.timezone.now, verbose_name='Fecha y hora'
            ),
        ),
    ]
