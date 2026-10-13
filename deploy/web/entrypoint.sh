#!/bin/sh
# Se ejecuta al arrancar el contenedor "web". docker-compose ya espera a que
# "db" este healthy (pg_isready) antes de levantar este servicio, asi que
# migrate puede conectarse directo, sin loop de reintentos.
set -e

# Sembrar /app/data/raw (volumen) con los 3 JSON pesados horneados en la
# imagen, pero SOLO si todavia no estan ahi - una extraccion en vivo mas
# nueva que ya haya en el volumen nunca se pisa.
for f in categorias.json carreras.json linkcarreras.json; do
    if [ ! -f "/app/data/raw/$f" ] && [ -f "/app/data/raw_seed/$f" ]; then
        cp "/app/data/raw_seed/$f" "/app/data/raw/$f"
        echo "Sembrado /app/data/raw/$f desde la imagen (primera vez)."
    fi
done

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recolectando archivos estaticos..."
python manage.py collectstatic --noinput

echo "Levantando gunicorn..."
exec gunicorn gatfh.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120
