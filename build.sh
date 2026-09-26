#!/usr/bin/env bash
# Script de build para Render (se ejecuta automáticamente al desplegar).
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
