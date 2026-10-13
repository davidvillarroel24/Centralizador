# Centralizador Académico en el VPS compartido (Contabo)

Sigue la misma convención que los demás proyectos del VPS (ver el README de
`proxy-compartido` para la plantilla general): un solo proxy compartido con
HTTPS automático, cada proyecto con su propia base de datos en una red
interna, y límites de memoria/CPU para no afectar a los demás.

## 1. Clonar y configurar

```bash
cd /srv/centralizador/deploy
cp .env.example .env
nano .env        # completar (generar secretos con: openssl rand -hex 32)
```

## 2. Levantar

```bash
docker compose up -d --build
```

La primera vez, `migrate` crea todas las tablas en una base vacía (no hay
`db/init/` con datos base: el administrador se crea con
`docker compose exec web python manage.py crear_admin`, o registrando un
usuario cuyo nombre coincida con un `Profesor` ya importado — ver el README
de la raíz del repo, sección de flujo de extracción).

El certificado HTTPS lo obtiene el proxy compartido en menos de un minuto
después de que `DOMINIO` en `.env` apunte al VPS.

## 3. Operación diaria

```bash
cd /srv/centralizador/deploy
docker compose ps                 # estado
docker compose logs -f web        # logs de Django/gunicorn
docker compose up -d --build      # actualizar a mano
docker compose exec web python manage.py <comando>   # cualquier comando CLI del proyecto
```

**Respaldos**: automáticos todos los días a las 3:00 en `deploy/respaldos/`
(14 diarios, 4 semanales, 3 mensuales):

```bash
scp -r eddy@<ip-del-vps>:/srv/centralizador/deploy/respaldos ./respaldos-centralizador
```

Restaurar uno:

```bash
gunzip -c respaldos/daily/<archivo>.sql.gz | docker compose exec -T db psql -U centralizador -d centralizador
```

## 4. Deploy automático en cada push

Cada push a `main` corre `.github/workflows/deploy-vps.yml`: GitHub entra al
VPS y hace `git pull` + `docker compose up -d --build`. El progreso se ve en
la pestaña **Actions** del repositorio.

Configuración (una sola vez):

1. En el VPS, una llave **solo para GitHub**, limitada a ejecutar el deploy
   de Centralizador (el `command=` impide usarla para cualquier otra cosa
   aunque se filtre):

   ```bash
   ssh-keygen -t ed25519 -N "" -C "github-actions-centralizador" -f /root/llave-github-centralizador
   echo "command=\"cd /srv/centralizador && git pull --ff-only && cd deploy && docker compose up -d --build && docker image prune -f\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat /root/llave-github-centralizador.pub)" >> /home/<usuario>/.ssh/authorized_keys
   cat /root/llave-github-centralizador      # copiar a GitHub y despues borrar los dos archivos
   ```

   (`<usuario>` es el usuario del VPS dueño de `/srv/centralizador`, igual
   que `eddy` en TiendaClick — ver sección "Preparar el VPS" en el README
   del proyecto que lo comparte.)

2. GitHub → **Settings → Secrets and variables → Actions**:
   - Secrets: `VPS_HOST` (IP del VPS), `VPS_USER` (el `<usuario>` de arriba),
     `VPS_SSH_KEY` = la llave privada completa (`llave-github-centralizador`,
     con las líneas BEGIN/END).
   - Variables: `VPS_DEPLOY_ACTIVO` = `true` (en `false` o borrada, el
     deploy automático se apaga sin tocar secretos).

Si un deploy falla, la versión anterior sigue funcionando: Docker solo
reemplaza los contenedores si la construcción terminó bien.

Ver en qué commit está el VPS:
`cd /srv/centralizador && sudo -u <usuario> git log --oneline -1`
(como root, git exige el `sudo -u <usuario>` por "dubious ownership").

## 5. Conectar pgAdmin/DBeaver desde tu PC

La base **no** publica el puerto 5432 al mundo (regla del VPS compartido);
`docker-compose.yml` solo lo bindea a `127.0.0.1` del propio VPS, así que
hace falta un túnel SSH para llegar desde tu computadora.

1. Abrir el túnel (dejar esta terminal abierta mientras usás pgAdmin/DBeaver):

   ```bash
   ssh -L 5433:127.0.0.1:5432 root@169.58.97.170
   ```

   (con PuTTY: pestaña **Connection → SSH → Tunnels**, *Source port* `5433`,
   *Destination* `127.0.0.1:5432`, **Add**, y recién después conectar en
   **Session**.)

2. En pgAdmin/DBeaver, nueva conexión:

   | Campo | Valor |
   |---|---|
   | Host | `127.0.0.1` (o `localhost`) |
   | Puerto | `5433` |
   | Base de datos | el `POSTGRES_DB` de tu `.env` |
   | Usuario | el `POSTGRES_USER` de tu `.env` |
   | Password | el `POSTGRES_PASSWORD` de tu `.env` |

3. Cerrar la terminal del túnel corta la conexión. El puerto 5432 sigue sin
   ser alcanzable desde fuera del VPS en ningún momento — el túnel SSH es el
   único camino.

## 6. Qué NO vive en Docker

- La cookie de Moodle de cada usuario: vive solo en su sesión de navegador
  (`SESSION_ENGINE = signed_cookies`), nunca en la base de datos ni en el
  `.env` de este stack — por diseño (D1b, ver README de la raíz).
- `data/raw/*.json` (staging del scraper) persiste entre reconstrucciones
  gracias al volumen `data_raw`. `categorias.json`, `carreras.json` y
  `linkcarreras.json` además viajan commiteados en el repo y horneados en la
  imagen (ver `.gitignore`/`.dockerignore`): `entrypoint.sh` los copia al
  volumen la primera vez que arranca vacío, sin pisar nunca una extracción
  más nueva que ya esté ahí. Si se borra el volumen a propósito
  (`docker compose down -v`), vuelve a sembrarse solo con la versión del
  repo en el próximo arranque; los datos ya importados a Postgres no
  dependen de esto.
