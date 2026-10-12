#!/bin/sh
# Se ejecuta al arrancar el contenedor "web". docker-compose ya espera a que
# "db" este healthy (pg_isready) antes de levantar este servicio, asi que
# migrate puede conectarse directo, sin loop de reintentos.
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recolectando archivos estaticos..."
python manage.py collectstatic --noinput

echo "Levantando gunicorn..."
exec gunicorn gatfh.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120
