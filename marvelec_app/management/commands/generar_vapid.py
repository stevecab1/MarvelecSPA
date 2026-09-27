from django.core.management.base import BaseCommand

from marvelec_app.push import generar_claves_vapid


class Command(BaseCommand):
    help = 'Genera claves VAPID para notificaciones push (pegarlas como variables de entorno en Render).'

    def handle(self, *args, **opciones):
        claves = generar_claves_vapid()
        privada = claves['private_key'].strip().replace('\n', '\n')
        self.stdout.write('Copia estas variables de entorno en Render (Environment):\n')
        self.stdout.write(f"VAPID_PUBLIC_KEY={claves['public_key']}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={privada}")
        self.stdout.write(self.style.WARNING(
            '\nNo las cambies después: si cambian, todos los dispositivos deben volver a activar las notificaciones.'
        ))
