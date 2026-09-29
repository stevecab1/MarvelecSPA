#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Crear el superusuario inicial solo si hay contraseña definida en el entorno
# (nunca con una clave fija conocida).
python manage.py shell -c "
from django.contrib.auth.models import User
import os
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@marvelec.cl')
if not password:
    print('DJANGO_SUPERUSER_PASSWORD no definida: no se crea superusuario.')
elif User.objects.filter(username=username).exists():
    print(f'Superusuario {username} ya existe, no se creó de nuevo.')
else:
    User.objects.create_superuser(username=username, password=password, email=email)
    print(f'Superusuario {username} creado exitosamente.')
"
