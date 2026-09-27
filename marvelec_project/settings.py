# marvelec_project/settings.py
#
# Funciona en local (SQLite) y en Render (PostgreSQL) sin tocar nada.
# En Render, solo tienes que setear las variables de entorno:
#   SECRET_KEY, DATABASE_URL, RENDER_EXTERNAL_HOSTNAME

import os
import sys
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'dev-insecure-marvelec-k3y-c4mbi4r-en-produccion'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

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
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'MARVELEC SPA <>')
