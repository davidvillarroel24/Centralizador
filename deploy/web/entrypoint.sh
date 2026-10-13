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

# 2 workers: con una extraccion en curso (sincronica, puede tardar) el sitio sigue
# respondiendo para el resto en el otro worker. El boton "Detener extraccion" ya no
# depende de en que worker cae el click (extraction_lock.py guarda el pedido de parada
# en la base, no en memoria de un proceso), asi que no hace falta bajar a 1 worker para
# que funcione.
echo "Levantando gunicorn..."
exec gunicorn gatfh.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120
