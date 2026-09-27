from datetime import date

from django.core.management.base import BaseCommand, CommandError

from marvelec_app.consultas import hoy_local
from marvelec_app.resumen import enviar_resumen_diario


class Command(BaseCommand):
    help = 'Envía el resumen diario de avance a supervisores y gerencia (notificación + push).'

    def add_arguments(self, parser):
        parser.add_argument('--fecha', help='Fecha del resumen (YYYY-MM-DD). Por defecto, hoy.')
        parser.add_argument('--forzar', action='store_true', help='Enviar aunque ya se haya enviado ese día.')

    def handle(self, *args, **opciones):
        try:
            fecha = date.fromisoformat(opciones['fecha']) if opciones['fecha'] else hoy_local()
        except ValueError:
            raise CommandError('Fecha inválida: usa el formato YYYY-MM-DD.')
        r = enviar_resumen_diario(fecha, forzar=opciones['forzar'])
        if r['enviado']:
            self.stdout.write(self.style.SUCCESS(f"Resumen del {fecha} enviado a {r['destinatarios']} persona(s)."))
        else:
            self.stdout.write(self.style.WARNING(r['motivo']))
