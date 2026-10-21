from django.db import migrations

TIPOS_PUNTO = ['DT', 'VD', 'RI']

# Tomadas de los reportes reales por WhatsApp (ver "Contexto Proyecto"). El nombre se puede editar en el admin.
TIPOS_INCIDENCIA = [
    ('Sin canalización', False),
    ('Materiales obstruyendo', False),
    ('Caja inaccesible', False),
    ('No se encuentra en terreno', False),
    ('No conecta', False),
    ('Tierra cruzada', True),
    ('Fallo por distancia', True),
]


def crear(apps, schema_editor):
    TipoPunto = apps.get_model('marvelec_app', 'TipoPunto')
    TipoIncidencia = apps.get_model('marvelec_app', 'TipoIncidencia')
    for orden, sigla in enumerate(TIPOS_PUNTO, start=1):
        TipoPunto.objects.get_or_create(sigla=sigla, defaults={'orden': orden})
    for orden, (nombre, falla) in enumerate(TIPOS_INCIDENCIA, start=1):
        TipoIncidencia.objects.get_or_create(
            nombre=nombre, defaults={'es_falla_certificacion': falla, 'orden': orden}
        )


class Migration(migrations.Migration):

    dependencies = [
        ('marvelec_app', '0009_rack_obligatorio'),
    ]

    operations = [
        migrations.RunPython(crear, migrations.RunPython.noop),
    ]
