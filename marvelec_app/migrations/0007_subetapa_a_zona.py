from django.db import migrations


class Migration(migrations.Migration):
    """Las subetapas pasan a llamarse zonas (piso, ala o sector); se conservan los datos."""

    dependencies = [
        ('marvelec_app', '0006_borrar_reportes_formato_antiguo'),
    ]

    operations = [
        migrations.RenameModel('Subetapa', 'Zona'),
    ]
