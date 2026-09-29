# marvelec_project/settings.py
#
# Funciona en local (SQLite) y en Render (PostgreSQL) sin tocar nada.
# En Render, solo tienes que setear las variables de entorno:
#   SECRET_KEY, DATABASE_URL, RENDER_EXTERNAL_HOSTNAME

import os
import sys
import dj_database_url
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Falta la variable de entorno SECRET_KEY (obligatoria en producción).')
    SECRET_KEY = 'dev-insecure-marvelec-k3y-solo-desarrollo'

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Render proporciona esta variable automáticamente
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Host adicional manual (útil para testing)
extra_host = os.environ.get('EXTRA_ALLOWED_HOST')
if extra_host:
    ALLOWED_HOSTS.append(extra_host)


INSTALLED_APPS = [
    # Tema del panel de administración (debe ir antes de django.contrib.admin).
    'unfold',
    'unfold.contrib.filters',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'marvelec_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Servir estáticos en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'marvelec_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'marvelec_app.context_processors.app',
            ],
        },
    },
]

WSGI_APPLICATION = 'marvelec_project.wsgi.application'


# Base de datos: usa DATABASE_URL si existe (Render/producción), si no, SQLite local.
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        # Neon suspende la base tras un rato sin uso: verificar la conexión antes de reutilizarla.
        conn_health_checks=True,
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # En producción: archivos comprimidos y con hash en el nombre (el celular nunca usa CSS/JS viejo).
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage' if TESTING
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- Configuraciones propias del proyecto ---
LOGIN_URL = 'marvelec_app:login'
LOGIN_REDIRECT_URL = 'marvelec_app:panel'
LOGOUT_REDIRECT_URL = 'marvelec_app:login'

# Sesión larga: el trabajador no debe tener que volver a ingresar cada día en la obra.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_SAVE_EVERY_REQUEST = False

# --- Notificaciones push (Web Push / VAPID) ---
# Generar una vez con: python manage.py generar_vapid  y pegarlas en Render.
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'notificaciones@marvelec.cl')

# Envío de push/correo en un hilo aparte (en tests se envía de inmediato).
NOTIF_SINCRONO = TESTING

# Token para disparar tareas programadas (resumen diario) desde GitHub Actions.
CRON_TOKEN = os.environ.get('CRON_TOKEN', '')

# Producción detrás del proxy HTTPS de Render
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# --- CSRF para producción (HTTPS) ---
CSRF_TRUSTED_ORIGINS = []
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# --- Email (SMTP) ---
# En desarrollo usa la consola (imprime el correo en terminal).
# En producción, configurar las variables de entorno con un SMTP real (Gmail, SendGrid, etc.)
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL') or (
    f'MARVELEC SPA <{EMAIL_HOST_USER or "notificaciones@marvelec.cl"}>'
)


# --- Panel de administración (django-unfold) ---
def _admin_url(modelo):
    return reverse_lazy(f'admin:{modelo}_changelist')


UNFOLD = {
    'SITE_TITLE': 'MARVELEC SPA',
    'SITE_HEADER': 'MARVELEC SPA',
    'SITE_SUBHEADER': 'Administración',
    'SITE_URL': '/panel/',
    'SITE_ICON': {
        'light': lambda request: static('marvelec_app/icons/icon-96x96.png'),
        'dark': lambda request: static('marvelec_app/icons/icon-96x96.png'),
    },
    'SITE_FAVICONS': [
        {'rel': 'icon', 'sizes': '96x96', 'type': 'image/png',
         'href': lambda request: static('marvelec_app/icons/icon-96x96.png')},
    ],
    # Morado MARVELEC (#3a288f = tono 600, el que Unfold usa en botones y enlaces).
    'COLORS': {
        'primary': {
            '50': 'oklch(97% .014 290)',
            '100': 'oklch(94% .03 289)',
            '200': 'oklch(88.5% .058 287)',
            '300': 'oklch(80% .1 286)',
            '400': 'oklch(68% .155 285)',
            '500': 'oklch(56% .195 284)',
            '600': 'oklch(36.9% .16 283.2)',
            '700': 'oklch(32.2% .143 282.6)',
            '800': 'oklch(27% .116 282.6)',
            '900': 'oklch(22% .095 282)',
            '950': 'oklch(16% .07 282)',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': False,
        'navigation': [
            {
                'title': 'Obras',
                'items': [
                    {'title': 'Obras', 'icon': 'apartment', 'link': _admin_url('marvelec_app_obra')},
                    {'title': 'Subetapas', 'icon': 'layers', 'link': _admin_url('marvelec_app_subetapa')},
                ],
            },
            {
                'title': 'Personal',
                'items': [
                    {'title': 'Usuarios', 'icon': 'person', 'link': _admin_url('auth_user')},
                    {'title': 'Perfiles y roles', 'icon': 'badge',
                     'link': _admin_url('marvelec_app_perfiltrabajador')},
                ],
            },
            {
                'title': 'Reportes',
                'items': [
                    {'title': 'Reportes de avance', 'icon': 'assignment',
                     'link': _admin_url('marvelec_app_reporteavance')},
                ],
            },
            {
                'title': 'Sistema',
                'collapsible': True,
                'items': [
                    {'title': 'Notificaciones', 'icon': 'notifications',
                     'link': _admin_url('marvelec_app_notificacion')},
                    {'title': 'Suscripciones push', 'icon': 'phonelink_ring',
                     'link': _admin_url('marvelec_app_suscripcionpush')},
                    {'title': 'Resúmenes diarios', 'icon': 'summarize',
                     'link': _admin_url('marvelec_app_resumendiarioenviado')},
                    {'title': 'Grupos', 'icon': 'group', 'link': _admin_url('auth_group')},
                ],
            },
            {
                'title': 'Aplicación',
                'items': [
                    {'title': 'Volver a la app', 'icon': 'arrow_back', 'link': '/panel/'},
                ],
            },
        ],
    },
}
