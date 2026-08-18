# Plan de Desarrollo — Fase 2 (Multiusuario + Despliegue)

**Generado**: 2026-08-18
**Alcance de este documento**: decisiones de diseño acordadas para preparar el Centralizador
para pruebas en Render, migrar a Postgres, y sentar las bases de un sistema multiusuario
(estudiantes, docentes, gestores) sin necesidad de rehacer el trabajo más adelante.

**Principio guía del MVP**: se implementa para un solo usuario activo a la vez, pero el diseño
de datos y concurrencia ya contempla múltiples usuarios desde el inicio — para no tener que
migrar el esquema ni la arquitectura de concurrencia cuando se sume el segundo usuario real.

---

## 0. Progreso

- [x] **Paso 1 (secretos)**: `gatfh/settings.py` y `gatfh/config.py` leen de `.env` vía
  `python-dotenv`. `.env.example` creado como plantilla. Verificado con `manage.py check`.
- [x] **Paso 2 (Postgres)**: Postgres 18 local instalado y corriendo, base `centralizador`
  creada, `DATABASE_URL` conectado vía `dj-database-url` (con fallback a SQLite si no está
  definida). Migraciones aplicadas y datos reimportados desde `data/raw/*.json`
  (16 materias, 12 estudiantes, 669 tareas, 288 entregas). Se decidió arrancar limpio en vez
  de migrar `db.sqlite3` tal cual.
- [x] Fix de entorno: venv recreado (apuntaba a una instalación de Python de otra máquina).
- [x] Fix de encoding: `manage.py` fuerza stdout/stderr a UTF-8 en Windows (la consola usa
  `cp1252` por defecto y rompía con los `print` que usan `✔`/`✓` en el proyecto).
- [x] `requirements.txt` creado con las versiones exactas instaladas.
- [ ] **Bug encontrado, pendiente para la sección 4**: `import_all_data` nunca llama a
  `services/imports/profesores.py::importar_profesores()` — la tabla `Profesor` queda vacía
  tras una importación limpia. Hay que sumarlo al comando antes de poder probar el matching de
  roles por materia.

---

## 0.1. Orden de ejecución acordado

1. Sanear secretos (mover `gatfh/config.py` a variables de entorno)
2. Migrar a Postgres (local ya instalado vía winget; falta conectar Django)
3. Preparar el proyecto para Render (requirements, Procfile, settings de producción)
4. Roles por materia (estudiante/profesor) — costo bajo, solo capa de vistas
5. Gestor (tabla `GestorMateria` + probe de acceso real contra Moodle)
6. Credenciales por usuario cifradas (reemplaza el cookie/sesskey global actual)
7. Cola de extracción en Postgres (un solo carril para el MVP, diseñada para N carriles)
8. Ajuste del pipeline de datos (JSON de staging + paso directo en memoria al import)
9. Extensión de navegador para captura de cookie (después de validar el piloto)
10. `git init` + `.gitignore` (al final, una vez saneados los secretos)
11. Evaluar migración de Render a servidor propio + Celery/Redis cuando haga falta paralelismo real

---

## 1. Despliegue en Render

### Gaps encontrados (ninguno resuelto aún)
- No hay `requirements.txt`, `Procfile`/`render.yaml`, ni `runtime.txt`.
- `gatfh/settings.py`: `SECRET_KEY` hardcodeado, `DEBUG = True`, `ALLOWED_HOSTS = []`, sin
  `STATIC_ROOT` ni whitenoise para servir estáticos en producción.
- Falta `CSRF_TRUSTED_ORIGINS` para el dominio `*.onrender.com`.
- **Crítico**: `gatfh/config.py` tiene hardcodeados la URL real del Moodle institucional y un
  valor real de cookie `MoodleSession`. Debe moverse a variables de entorno antes de que el
  proyecto tenga un repo git (independientemente de que `git init` se haga al final).

### A implementar
- `requirements.txt`: `django`, `requests`, `aiohttp`, `beautifulsoup4`, `openpyxl`,
  `python-dateutil`, `gunicorn`, `whitenoise`, `psycopg2-binary`, `dj-database-url`.
- `settings.py` leyendo `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` desde variables de entorno
  (con defaults seguros de desarrollo local si no están definidas).
- `STATICFILES_STORAGE` con whitenoise + `STATIC_ROOT`.
- `Procfile`: `web: gunicorn gatfh.wsgi`.

---

## 2. Base de datos: Postgres

### Decisión: migrar a Postgres ya, no esperar
**Motivo**: los Web Services de Render tienen filesystem efímero — `db.sqlite3` se borraría en
cada redeploy o reinicio. Dado que los datos scrapeados de Moodle son costosos de regenerar,
no vale la pena arriesgar perderlos por mantener SQLite en un entorno de pruebas real.

### Estado
- Postgres 17 instalado localmente vía `winget install -e --id PostgreSQL.PostgreSQL.17`.
- Base local `centralizador` creada con `createdb`.

### Pendiente
- Agregar `psycopg2-binary` + `dj-database-url` a `requirements.txt`.
- `settings.py`: leer `DATABASE_URL` con fallback a SQLite si la variable no existe (mismo
  archivo sirve para local y Render sin duplicar configuración).
- Crear base de datos Postgres administrada en Render (tier gratuito) para el entorno de pruebas.

---

## 3. Captura de cookie de sesión Moodle

### Descartado: login server-side con usuario/contraseña
Moodle usa OAuth contra cuentas Google del dominio institucional (`@tecba.edu.bo`). Automatizar
ese login (POST directo) no es viable: Google bloquea/detecta logins programáticos y sería
violar sus términos. No se investiga más esta vía.

### MVP: cookie manual (se mantiene)
El flujo actual (pegar el valor de `MoodleSession` copiado de DevTools) se mantiene para el MVP
de un usuario. No es ideal para el usuario promedio, pero es funcional y no bloquea el resto del
plan.

### Fase posterior: extensión de navegador
- Manifest V3, permiso `cookies` + `host_permissions` sobre el dominio de Moodle y el dominio de
  Render del Centralizador.
- Lee `MoodleSession` con `chrome.cookies.get()` (funciona aunque la cookie sea `HttpOnly`,
  a diferencia de un bookmarklet).
- Envía la cookie a un endpoint nuevo (`/web/session-cookie/api/`) vía `fetch` con
  `credentials: 'include'`, aprovechando que el usuario ya tiene sesión Django abierta en el
  mismo navegador — sin pasos de emparejamiento adicionales.
- **Distribución durante el piloto**: modo desarrollador (`Load unpacked`) — cero costo, cero
  espera de revisión. Solo evaluar publicación (Edge Add-ons primero, gratis y con revisión más
  rápida; Chrome Web Store después, ~$5 + revisión de días/semanas por el permiso sensible
  `cookies`) una vez validado el piloto con un grupo reducido de docentes.

---

## 4. Roles: estudiante / profesor / gestor

### Hallazgo clave: el mecanismo de detección de rol ya existe, parcialmente
- `scraping/scrapers/profesores.py::procesar_profesor` ya escanea la tabla de participantes de
  cada materia y extrae quién tiene rol "Profesor" — esto puebla `Materia.profesores`.
- `web/views.py::get_current_profesor` (líneas 60-73) ya compara el nombre de la cuenta logueada
  contra `Profesor.nombre`, pero como comparación **global de cuenta**, no por materia.

### Decisión: el rol se computa por materia, no se almacena
```python
es_profesor_en_esta_materia = materia.profesores.filter(nombre__iexact=mi_nombre).exists()
```
Una misma cuenta puede ser profesor en una materia y estudiante (solo matriculado) en otra —
esto ya ocurría sin problemas en la extracción actual, según lo observado. **No se necesitan
tablas nuevas para estudiantes**: la extracción es idéntica para todos los roles, solo cambia
qué columnas/vistas se muestran según el resultado de esa comparación.

### Mejora de robustez pendiente: matching por `moodle_userid`, no por nombre
El nombre como clave de comparación es frágil (colisiones, variantes de escritura). Se debe
capturar el `userid` de la propia sesión logueada (regex sobre `M.cfg`, igual técnica que ya se
usa para extraer el `sesskey` en `scraping/scrapers/session.py:26`) y comparar por ID en vez de
por string.

### Gestor: alcance elegido, no flag global
Un gestor no "ve todo" — declara sobre qué facultades/carreras/materias ejerce seguimiento.

**Tabla nueva**:
```python
class GestorMateria(models.Model):
    gestor = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='materias_gestionadas')
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name='gestores')
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
    acceso_confirmado = models.BooleanField(default=False)

    class Meta:
        unique_together = ('gestor', 'materia')
```
- Soporta N gestores por materia y N materias por gestor.
- Selección "toda la facultad X" se **expande** a filas individuales por materia en el momento
  de elegir (no se guarda la facultad como alcance vivo) — evita el caso ambiguo de herencia
  automática cuando se agregan materias nuevas a esa facultad más adelante.
- **Gate de acceso**: la opción de activar modo gestor solo se muestra si la cuenta ya está
  reconocida como `Profesor` en al menos una materia (mismo mecanismo de matching de arriba).
- **Probe de acceso real**: antes de scrapear en profundidad una materia del alcance elegido, se
  hace una petición liviana a la página del curso y se busca el patrón de bloqueo de Moodle:
  ```
  Opciones de matriculación
  Profesor: <nombre>
  No se puede auto matricular en este curso.
  ```
  Si aparece, la materia se descarta del scrape (`acceso_confirmado = False`) y se le informa al
  usuario antes de lanzar la extracción completa, evitando esperas largas para resultados vacíos.

---

## 5. Credenciales de Moodle por usuario

### Bug encontrado (afecta incluso al MVP de un solo usuario)
`MoodleSession()` se instancia sin argumentos en `web/views.py:246` y lee
`config.COOKIES` — el diccionario **hardcodeado** en `gatfh/config.py` — nunca
`request.session['MoodleSession']`. El flujo de "recuperar sesión" pegando el cookie en la web
no llega al scraper. Esto probablemente explica fallos intermitentes ya observados.

### Corrección de diseño: cifrado, no hash
El código existente (`profesor.moodle_session_hash = make_password(cookie_value)`) usa hash de
una sola vía (mecanismo para contraseñas) — un cookie de sesión necesita **cifrado reversible**,
porque hay que reenviarlo tal cual a Moodle en cada request futuro.

```python
class CredencialMoodleMixin(models.Model):
    moodle_cookie_enc = models.BinaryField(null=True, blank=True)  # cifrado con Fernet
    moodle_sesskey = models.CharField(max_length=64, null=True, blank=True)
    cookie_actualizado = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
```
- `Profesor` y `Estudiante` heredan este mixin — cada cuenta con su propia cookie/sesskey, sin
  colisión entre usuarios.
- Cifrado con `cryptography.fernet.Fernet`, clave en variable de entorno separada de
  `SECRET_KEY` (secreto de Render, nunca en el repo).
- `MoodleSession` deja de leer `config.COOKIES`/`config.SESSKEY` globales; recibe el cookie
  descifrado como parámetro del usuario que disparó la operación.
- `cookie_actualizado` permite decidir cuándo pedir recaptura sin esperar a que falle un scrape.

### Reutilización de sesskey (ya diseñada, pero apagada)
`scraping/scrapers/session.py::get_sesskey` tiene la lógica de reutilización comentada — hoy
siempre re-extrae el sesskey en cada operación aunque el cacheado siga siendo válido. Se debe
reactivar `sesskey_valido()` (ya implementado, sin usar) y mover el cacheo de un archivo global
(`config_runtime.json`) a los campos del mixin de arriba, por usuario.

---

## 6. Control de concurrencia contra Moodle (MVP: un carril, diseño: N carriles)

### Decisión: cola en Postgres en vez de Celery/Redis por ahora
Vale solo mientras el despliegue sea Render con un solo web service. Migrar a Celery/Redis
cuando se mueva a servidor propio o el volumen de usuarios lo justifique.

### Mecanismo correcto (no "check-then-insert")
Revisar-si-hay-alguien-activo y luego insertar es una condición de carrera clásica bajo
concurrencia real. La forma correcta usa el locking nativo de Postgres:
```sql
SELECT * FROM peticiones
WHERE estado = 'pendiente'
ORDER BY creado ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```
Esto garantiza que dos procesos nunca tomen la misma fila, sin necesidad de lógica de aplicación
adicional. Para el MVP el "límite de carriles" es 1 (`LIMIT 1`); subir a N carriles más adelante
es cambiar ese número, no rediseñar el mecanismo.

### Ejecución: worker separado, no dentro del request HTTP
Render corta requests largos (~100s de timeout de proxy) y un scraping de varios minutos
bloquearía el proceso web para todos los usuarios. La vista solo inserta la fila `pendiente` y
responde de inmediato ("quedaste en cola"); un proceso aparte (management command en loop,
sin necesitar Redis) hace polling con el `FOR UPDATE SKIP LOCKED` de arriba.

### Tres capas para garantizar que un scraping muerto no siga pidiendo indefinidamente
1. **Por request individual**: `aiohttp.ClientTimeout(total=30)` al crear el `ClientSession`
   (hoy no existe timeout en `scraping/scrapers/tareas.py:66` ni en `profesores.py`).
2. **Por job completo**: `asyncio.wait_for(job(), timeout=120)` — cancela todas las tareas
   pendientes del job al vencer. Esta es la forma correcta de "matar" trabajo async.
3. **Por cola** (respaldo): timeout de fila en `peticiones` a 2 minutos (bajado de la propuesta
   inicial de 15) — un poco por encima del timeout de la capa 2, para que normalmente sea la
   capa 2 la que corte primero.

**Prerequisito para que la capa 2 funcione**: corregir los `except:` desnudos en
`scraping/scrapers/session.py:48` y `:83` — en Python, `asyncio.CancelledError` hereda de
`BaseException`, así que un `except:` genérico también la atrapa y anula la cancelación
silenciosamente. Cambiar a `except Exception:` (o relanzar `CancelledError` explícitamente).
Revisar el resto de scrapers por el mismo patrón antes de confiar en el timeout.

---

## 7. Pipeline de datos: extracción → staging → Postgres

### Se mantiene el staging en JSON
Es una decisión de diseño correcta (separa el costo/riesgo de scrapear Moodle de la carga a
DB, permite reprocesar sin volver a scrapear si el bug está en el import) — coincide con el
marco conceptual ya documentado en la sección 2.2.8 (ETL) del proyecto de grado.

### Mejoras a aplicar
- **Evitar el reread redundante**: hoy el scraper escribe JSON y un comando separado lo vuelve a
  leer del disco. Como ahora ambos pasos ocurren en la misma ejecución del worker de la cola, la
  función de scraping debe pasarle los datos **directamente en memoria** a la función de
  importación; el archivo JSON queda solo como registro de auditoría/respaldo para reprocesar
  manualmente si hace falta.
- **Nombres de archivo por job**: `gatfh/config.py` usa rutas fijas (`JSON_TAREAS`,
  `JSON_ESTUDIANTES`, etc.) — seguro mientras la cola tenga un solo carril, pero colisionaría si
  más adelante hay más de un job corriendo en paralelo. Incluir el id de usuario/job en el
  nombre desde ahora evita tener que tocarlo después.

### Corrección adicional encontrada (no relacionada a concurrencia)
`scraping/scrapers/tareas.py:73` tiene hardcodeado `range(1, 13)` para las secciones/unidades de
una materia. Si una materia tiene más de 12 unidades, las siguientes nunca se scrapean (pérdida
silenciosa de datos); si tiene menos, se piden secciones vacías de más. Debe reemplazarse por
una detección dinámica del número real de secciones antes de lanzar el `gather`.

---

## 8. Fuera de alcance del MVP (anotado para más adelante)

- Migración de Render a servidor propio + Celery/Redis (cuando el volumen de usuarios simultáneos
  lo justifique).
- Persistir el alcance de gestor como "facultad viva" con herencia automática de materias nuevas.
- CRUD de configuración, filtros de reportes, predicciones ML (ya documentado como pendiente en
  `TAREAS_COMPLETADAS.md`, sin relación directa con este plan de multiusuario).
