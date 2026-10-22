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
#
# --timeout 600: una extraccion (ej. "0. Extraer carreras" sobre todas las facultades, o
# "1" sobre muchos cursos seleccionados a la vez) es una sola request sincronica que gunicorn
# mantiene abierta de punta a punta - el polling de /extraccion/progreso/ para el spinner es
# solo cosmetico, en paralelo, no la vuelve async. Con el limite viejo de 120s, una
# extraccion grande (sobre todo la primera vez, sin nada cacheado) hacia que gunicorn matara
# el worker a mitad de camino -> 500 / "Error de red" en el navegador, sin que hubiera ningun
# bug real en el scraping (confirmado 2026-10-22). Caddy (el proxy compartido del VPS) no
# tiene su propio timeout corto, asi que subir este alcanza.
echo "Levantando gunicorn..."
exec gunicorn gatfh.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 600
