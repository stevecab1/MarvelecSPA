#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Crear superusuario de forma directa con Python
python manage.py shell -c "
from django.contrib.auth.models import User
import os
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin12345')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@marvelec.cl')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, password=password, email=email)
    print(f'Superusuario {username} creado exitosamente.')
else:
    print(f'Superusuario {username} ya existe, no se creó de nuevo.')
"