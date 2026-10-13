# Imagen de la app web (Django + gunicorn + whitenoise). Se construye con
# contexto en la raiz del repo (ver deploy/docker-compose.yml: build.context: ..),
# para poder copiar todo el proyecto, no solo esta carpeta.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# curl: lo usa el healthcheck del servicio "web" en docker-compose.yml.
# psycopg2-binary (requirements.txt) ya trae el driver de Postgres compilado,
# por eso no hace falta gcc/libpq-dev aca.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# categorias.json/carreras.json/linkcarreras.json viajan commiteados en el repo
# (son los mas pesados de re-extraer de Moodle). En runtime, /app/data/raw es
# un volumen (ver docker-compose.yml) para que tareas.json/estudiantes.json no
# se pierdan con un rebuild - pero eso mismo tapa lo que venga horneado en esa
# ruta. Por eso se guarda una copia aparte en data/raw_seed/, fuera del punto
# de montaje: entrypoint.sh la usa para "sembrar" el volumen la primera vez
# (o si alguno de los 3 faltara), sin pisar nunca una extraccion mas nueva que
# ya este en el volumen.
RUN mkdir -p /app/data/raw_seed \
    && for f in categorias.json carreras.json linkcarreras.json; do \
         if [ -f "/app/data/raw/$f" ]; then cp "/app/data/raw/$f" "/app/data/raw_seed/$f"; fi; \
       done \
    && mkdir -p /app/data/raw \
    && chmod +x deploy/web/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["deploy/web/entrypoint.sh"]
