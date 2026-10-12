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

RUN mkdir -p /app/data/raw \
    && chmod +x deploy/web/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["deploy/web/entrypoint.sh"]
