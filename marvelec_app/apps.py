from django.apps import AppConfig


class MarvelecAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marvelec_app'
    verbose_name = 'MARVELEC - Reporte de Avance'

    def ready(self):
        import marvelec_app.signals  # noqa: F401
