# Centralizador Académico

Plataforma de monitoreo docente construida en **Django 6 + Postgres**. Transforma datos
extraídos de Moodle (materias, tareas, estudiantes, entregas) en indicadores, alertas y
reportes para el seguimiento académico.

Proyecto de grado — TECBA 2026.

> **Este archivo es el único punto de verdad sobre el estado del proyecto.**
> El roadmap vive en [`PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md).
> Los documentos anteriores (`PROYECTO_COMPLETADO.md`, `TAREAS_COMPLETADAS.md`,
> `QUICKSTART.md`) fueron escritos en junio 2026, quedaron desactualizados y se movieron a
> [`archivo/`](archivo/). No usarlos como referencia.

---

## 1. Estado real (actualizado 2026-10-15)

Lo que la Fase 1 dejó **realmente** funcionando, verificado contra el código —
no contra los documentos de junio, que inflaban el avance.

*Filas marcadas con fecha 10-15 son de esta pasada (último acceso a Moodle, extensión de
Chrome, bugs de sesión); 10-14 es la pasada anterior; el resto queda como en la revisión
del 10-01 (no se volvió a comprobar en esta actualización).*

| Módulo | Estado | Detalle |
|---|---|---|
| Routing + sidebar (8 módulos) | ✅ Funciona | `web/urls.py`, `web/templates/web/base.html` |
| Autenticación | ✅ `login_required` aplicado | Todas las vistas salvo login/register/logout exigen sesión (C2 resuelto, `LOGIN_URL` en `settings.py`). `register` sigue exigiendo que el usuario coincida con un `Profesor.nombre`. |
| Resumen (KPIs + Chart.js) | ⚠️ Frágil | Renderiza, pero el cálculo está envuelto en `except: pass` (una BD vacía muestra ceros indistinguibles de "sin alertas"); N+1 (~4000 queries medidos); "actividades" cuenta solo tareas cuyo título contiene `"Examen"`/`"tek"`, no todas |
| Materias / Docentes / Estudiantes | ⚠️ Listado básico | Consultas con algunas anotaciones; quedan `print()` de depuración en el código |
| Alertas | ⚠️ Parcial | 3 reglas efectivas (el README de junio decía 5): materias sin actividades, tareas sin cierre, sobrecarga >8 pendientes. "Sobrecarga" tiene **dos definiciones incompatibles** en `web/views.py` (≥3 el mismo día para el KPI, >8 pendientes para alertas) |
| Extracción (`/extraccion/`) | ✅ Pipeline reescrito (10-14) | "Normalizar" **se eliminó**; el scraping y la importación a BD quedaron en botones separados. Scraping real, detrás del candado: `extraer_carreras` / `extraer_tareas` / `estudiantes`. Importar JSON→BD, aparte: `importar_tareas` / `importar_estudiantes` / `importar_asignacion`. `asignacion` arma `asignacion.json` con los parciales/pesos del **profesor logueado** (ver fila Configuración), y un modal nuevo (`ver_asignacion` / `guardar_asignacion_manual`) deja revisarla y corregirla a mano antes de confirmarla. Los 5 importadores de jerarquía (`importar_facultades/carreras/niveles/profesores/materias`, antes solo CLI, §3.1) ahora también son botones del dashboard (`IMPORTADORES_CARRERAS`). El candado (`extraction_lock.py`) pasó de un `threading.Event()` en memoria a un `DbStopEvent` respaldado en `TrabajoExtraccion.detener`: con gunicorn corriendo 2 workers en el VPS (§10), un `Event()` de un worker no lo veía el otro, así que "Detener extracción" podía no hacer nada. `detener_extraccion` ahora también exige ser dueño del job o staff (antes cualquier logueado detenía la de cualquiera). Sigue sin confirmarse `extraer_tareas`/`estudiantes` de punta a punta contra Moodle real. |
| Cookie de Moodle | ✅ Nunca toca la BD (10-15) | Se pega directo en `/extraccion/` (cuadro nuevo, se opaca al guardar). Vive en `request.session`, y `SESSION_ENGINE` se cambió a `signed_cookies` (`gatfh/settings.py`): la sesión completa (incluida la cookie) queda en una cookie firmada del navegador, nunca en `django_session` de Postgres. El flujo viejo (`/session-cookie/`, `session_recovery.html`) sigue existiendo como fallback — tenía un bug (`handle_session_error`/`cookie_recovery_view`/el template redirigían a rutas hardcodeadas con prefijo `/web/`, que no existe: la app está montada en la raíz) que hacía que cualquier extracción sin cookie terminara en un 404 en vez del formulario de recuperación; corregido con `reverse()`. Las acciones que llaman a Moodle ahora frenan antes de tomar el candado si no hay cookie guardada, en vez de descubrirlo recién al fallar contra Moodle. Extensión de Chrome nueva (`chrome_extension/`, MV3) que lee `MoodleSession` del navegador y la pega sola en el campo (sin inhabilitar el pegado manual) — ver D1b. |
| ⚠️ **Esta fila y la de arriba están desactualizadas** (detectado 2026-10-23, al investigar C11/C12) | | El dashboard cambió más de lo que reflejan: las acciones ahora son `cargar_tareas`/`cargar_estudiantes`/`cargar_ultimo_acceso` (extraen **e importan** en un solo paso, no botones separados), hay roles Administrador/Decano (`cursos_base_por_rol`, `requiere_rol`), un endpoint de progreso (`/extraccion/progreso/`) y, el cambio más importante: **la cookie ya no es solo de sesión del navegador** — `Profesor.moodle_cookie_cifrada` la guarda cifrada en la base (`descifrar_cookie`, vence a las 2 horas), lo que contradice D1b (§5) y la fila "Cookie de Moodle" de arriba tal como está escrita hoy. No se investigó a fondo en esta sesión (quedó fuera del pedido original); falta un resync completo de §1/§5/D1b con el código actual. |
| Último acceso a Moodle (`AccesoCurso`) | ✅ Nuevo (10-15) | Scraper nuevo (`scraping/scrapers/participantes.py`, vía `/user/index.php?id=<curso>`) trae el padrón completo de inscritos de un curso (estudiantes y profesores, con su último acceso) — a diferencia de `estudiantes()`/`Entrega`, que solo ve a quien entregó algo. Botón "3b. Extraer último acceso" + importador a `AccesoCurso` (migración `0019`): una fila por `(Materia, moodle_userid)`, sin FK a `Estudiante`/`Profesor` porque el mismo id puede ser cualquiera de los dos según el curso — una sola tabla sirve para ambos. De paso corrigió el filtro de rol "estudiante"/"todos" del dashboard (`filter_courses_by_role`), que antes no tenía ninguna relación real con el usuario logueado (heurística: "cualquier materia sin profesor asignado en toda la BD"); ahora usa `AccesoCurso` para saber en qué materias el `moodle_id` del profesor logueado aparece con rol de estudiante. Pensado como insumo para el modelo de riesgo (§11): días desde el último acceso más reciente entre materias, para una alerta de abandono — todavía no integrado al dataset de entrenamiento. |
| Predicciones / Reportes | ⛔ Placeholder | Solo renderizan un mensaje fijo (`predicciones_view`/`reportes_view`, vista sin cambios). Trabajo de base para Predicciones (modelo de riesgo, Random Forest) ya empezado — ver §11 |
| Configuración (`/configuracion/`) | ✅ Funcional, por profesor (10-14) | Dejó de ser placeholder. Reemplaza a `config_tareas.json` (un archivo compartido, editado a mano) con dos tablas nuevas por `Profesor`: `FechasParciales` (rango de cada uno de los 4 parciales) y `PesosCategorias` (peso de Mi-Tek/E-Tek/Training/Design Lab/Examen). Alimenta directo a "Asignar tareas". |
| Notas y Excel | ✅ Nuevo (10-14) | `Entrega.nota`/`nota_maxima` (migración `0016`) + botón "Generar Excel" → `descargar_excel`: arma el archivo en memoria (`BytesIO`) y lo entrega como descarga directa (`FileResponse`), sin pasar por el disco del servidor como antes. |
| Importadores | ⚠️ Duplicados, parcialmente resuelto (10-14) | Ver §4. `services/imports/` (facultades/carreras/niveles/profesores/materias) es el canónico y ya tiene botón propio en el dashboard. `services/data_utils/` sigue siendo el que usan tareas/estudiantes/asignación (`import_tareas_from_json`, `import_estudiantes_from_json`, `import_asignacion_from_json`) — la migración de esos tres a `services/imports/` (D2) sigue sin hacerse. |
| Base de datos | ✅ Postgres | `DATABASE_URL` vía `dj-database-url`, fallback a SQLite. Migraciones `0001`–`0017`: `0014`/`0015` agregan `FechasParciales`/`PesosCategorias` y `Tarea.categoria`/`parcial`; `0016` agrega `Entrega.nota`/`nota_maxima`; `0017` agrega `TrabajoExtraccion.detener` (candado de parada). `0012`/`0013` (`Profesor.user`) siguen sin revisarse a fondo. |
| Preparación de deploy | ✅ Desplegado en VPS (10-14) | Corriendo en un VPS compartido (Contabo) vía Docker Compose, detrás de un proxy Caddy compartido con otros 3 proyectos — ver §10 y [`deploy/README.md`](deploy/README.md). Render quedó abandonado como ruta real (D3); el `Procfile` se mantiene en el repo sin usarse. |
| Interfaz (paleta / responsive) | ✅ Hecho | Paleta cambiada de naranja→azul→dorado+violeta ("Protoss"); sidebar oculto antes de login, colapsable en celular con botón hamburguesa; iconos de Bootstrap Icons (CDN) en vez de emojis; SweetAlert2 (CDN) para mensajes de error en vez de alertas nativas del navegador; autocompletado de nombre de docente en `/register/` (`<datalist>`); tablas/gráficos/sidebar responsive (breakpoints en `sidebar.css`/`dashboard.css`). |

*Commits revisados para esta actualización (`872cabd`..`0ccad6d`, 14 en total, más el
deploy en `deploy/`): pipeline de extracción reescrito y modal de asignación (5), hilo/
candado para 2 workers de gunicorn (3), SweetAlert2, descarga de notas en Excel, conexión
SSH a Postgres del VPS (3), deploy en VPS (§10).*

**Fase 2 (multiusuario): 0 % en código.** Lo hecho hasta ahora es infraestructura
(lectura de `.env`, Postgres, preparación para hosting).

---

## 2. Stack y estructura

- **Python 3.14** · **Django 6.0.5** · **PostgreSQL** (SQLite como fallback local)
- `aiohttp` + `beautifulsoup4` para el scraping · `requests` para la sesión
- `pandas` + `openpyxl` para exportar Excel · `Chart.js` (CDN) en el front
- Bootstrap Icons + SweetAlert2 (CDN) en el front · Docker Compose para el deploy

```
chrome_extension/ Extensión de Chrome (MV3) que captura MoodleSession — ver D1b
deploy/           Docker Compose para el VPS compartido (Contabo) — ver §10
gatfh/            Configuración Django (settings, urls, config.py, wsgi)
data/             Modelos: Profesor, Facultad, Carrera, Nivel, Materia, Unidad,
                  Tarea, Estudiante, Entrega, ArchivoTarea, AccesoCurso,
                  ConfiguracionInstitucional, TrabajoExtraccion + migraciones
web/              Vistas, templates, estáticos (el front completo)
scraping/scrapers/ Scrapers de Moodle (session, tareas, calificaciones, profesores,
                  carreras, detallesprofesores, participantes/último acceso,
                  normalización, asignartareas)
services/
  imports/        Importadores JSON→DB por entidad (8 comandos importar_*)  ← canónico (§3, decisión 2)
  data_utils/     Importadores antiguos (a eliminar — §3, decisión 2)
  extraccion/     Wrappers finos sobre los scrapers
  management/commands/  Comandos de extracción (extraer_*), importación (importar_*),
                  `exportar_dataset_ml` (§11) y `crear_admin` (seed del admin, ver §3)
  utils/          run_scraping, timing
data/raw/         Staging JSON de la extracción (gitignoreado — datos reales de personas)
data/ml/          Dataset de entrenamiento del modelo de riesgo (gitignoreado — ver §11)
```

Carpetas fuera del alcance del repo (gitignoreadas): `Versioines Demo/` (versión demo
previa `moodle_app_async`, de donde sale el flujo de comandos `importar_*`),
`Proyecto de grado/` (documento de tesis).

---

## 3. Puesta en marcha local

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env    # completar DJANGO_SECRET_KEY, MOODLE_BASE_URL, etc.
```

Si reinstalaste Postgres o es una base nueva, creala antes de migrar:

```powershell
# psql/createdb deben estar en el PATH (carpeta bin de la instalación de Postgres)
createdb -U postgres -h localhost centralizador
```

`.env` nunca se commitea. Si `DATABASE_URL` no está definida, el proyecto usa SQLite
automáticamente — y si cambiaste la contraseña del usuario `postgres` al reinstalar,
actualizala en `.env` antes de seguir.

```powershell
python manage.py migrate        # crea todas las tablas (auth, data, sessions...)
python manage.py crear_admin    # crea/resetea el admin de prueba "tecba" / "st4rcr4fT2"
python manage.py runserver      # http://localhost:8000/
```

### 3.1 Repoblar la base desde cero (Facultad/Carrera/Materia/Profesor)

Con la base recién migrada, `data/raw/*.json` vacío y `/web/login/` ya accesible con el
admin de `crear_admin`, el orden para tener datos reales es:

1. **Conseguir el cookie de Moodle** (`MoodleSession`, copiado de las DevTools del
   navegador con sesión activa) y pegarlo en el dashboard (`/extraccion/` → "Guardar
   cookie"). Vive solo en la sesión firmada del navegador, nunca en la base (D1b).
2. **Extraer la jerarquía de carreras** — botón **"0. Extraer carreras"** en el dashboard.
   Recorre todas las categorías de Moodle (`/course/index.php`, una request por categoría
   + paginación) y genera `data/raw/categorias.json`, `carreras.json` y `linkcarreras.json`.
   Sin esto el selector de cursos del dashboard queda vacío, porque `load_courses()` lee
   `Materia` desde Postgres, no JSON. Alternativa por CLI (mismo cookie, vía
   `MOODLE_SESSION_COOKIE` en `.env`): `python manage.py extraer_linkcarreras`.
3. **Importar `linkcarreras.json` a Postgres, en este orden exacto** (`importar_profesores`
   va *antes* que `importar_materias` — al revés de como podría parecer natural, porque
   `materias.py` enlaza cada `Materia` a su `Profesor` buscándolo ya creado; si corre antes,
   la unión M2M queda vacía en silencio, sin error):
   ```powershell
   python manage.py importar_facultades
   python manage.py importar_carreras
   python manage.py importar_niveles
   python manage.py importar_profesores
   python manage.py importar_materias
   ```
4. **Extraer tareas y estudiantes de las materias que te interesen**, desde el dashboard:
   botones "1. Extraer tareas del curso" y "4. Extraer estudiantes" (seleccionando cursos
   primero). Guardan `tareas.json`/`estudiantes.json` e importan a la DB en el mismo paso
   (`import_tareas_from_json`/`import_estudiantes_from_json`, vía `services/data_utils/`).
5. *(Opcional)* **Detalles y archivos adjuntos de cada tarea**: `python manage.py
   importar_detalles_tareas`, una vez tengas `detalle.json` (hoy solo sale de scraping
   manual anterior, no hay botón propio todavía).

Verificación rápida de que algo se pobló:
```powershell
python manage.py shell -c "
from data.models import Facultad, Carrera, Nivel, Materia, Profesor, Tarea, Estudiante, Entrega
for m in [Facultad, Carrera, Nivel, Materia, Profesor, Tarea, Estudiante, Entrega]:
    print(m.__name__, m.objects.count())
"
```

---

## 4. Flujo de datos

```
[Moodle]
  │  scraping (scraping/scrapers/*, cookie MoodleSession)
  ▼
[data/raw/*.json]   ← staging de auditoría; permite reimportar sin volver a scrapear
  │  comandos importar_* (services/imports/)
  ▼
[Postgres: Materia, Unidad, Tarea, Estudiante, Entrega, ...]
  │  queries + cálculo de KPIs / alertas
  ▼
[web/ : dashboard, resumen, listados, alertas]
```

Aparte, para las notas: `PesosCategorias`/`FechasParciales` (por profesor, en
`/configuracion/`) alimentan `asignacion_tareas()` → `asignacion.json` (editable desde el
modal de `/extraccion/`) → `Entrega.nota`/`nota_maxima` → botón "Generar Excel"
(`descargar_excel`, arma el archivo en memoria, sin tocar disco).

**Importador canónico:** `services/imports/` (comandos `importar_*`). El subsistema
`services/data_utils/` (usado hoy por el dashboard web y por `import_all_data`) crea una
Facultad/Carrera ficticia llamada `"Importadas"` y deja campos en NULL; **se elimina** en
Fase 2 (decisión 2). El dashboard debe migrarse a `services/imports/` antes de borrarlo.

---

## 5. Decisiones de diseño — Fase 2

Tomadas el 2026-08-30 tras la auditoría (§6). Reemplazan lo que decía
`PLAN_DESARROLLO.md` donde haya conflicto; ese archivo se re-ordena en base a esto.

### D1 — Identidad: se mantienen 3 tablas separadas
`User` / `Profesor` / `Estudiante` siguen siendo tablas independientes. **No** se crea una
identidad canónica. Se unifica la regla de "¿qué Profesor soy yo?" comparando por
`moodle_userid` (que ya existe como `Profesor.moodle_id`), no por nombre.

### D1b — La cookie de Moodle nunca se persiste
`MoodleSession` **solo vive en la memoria del navegador del usuario**. No se guarda en la
BD, ni en `request.session`, ni en archivo. El modelo:

- Una **extensión de navegador de instalación local** (descargable desde la propia página
  del Centralizador, **no publicada en tiendas**) mantiene la cookie.
- La envía con cada request de extracción on-demand.
- El servidor la usa en memoria solo durante ese job y la descarta.

**✅ Construida (10-15):** `chrome_extension/` (Manifest V3). `background.js` (service
worker) es el único archivo que toca `chrome.cookies`, lee `MoodleSession` del dominio de
Moodle configurado bajo pedido (no persiste nada); `content_script.js` corre solo en las
páginas de Centralizador y agrega un botón junto al campo de cookie ya existente en
`dashboard.html`/`session_recovery.html` — **no reemplaza el pegado manual**, el usuario
sigue revisando y confirmando con "Guardar cookie". Hoy se instala en modo desarrollador
desde un .zip descargable en `/configuracion/` (`web/static/web/downloads/`); dejarla lista
para la Chrome Web Store (privada/no listada, sin modo desarrollador para el usuario final)
es trabajo futuro — checklist en `chrome_extension/README.md`. Política de privacidad
pública (requisito de la Web Store) en `/extension/privacidad/`.

Esto **elimina** del plan original: `CredencialMoodleMixin`, cifrado Fernet y todo
almacenamiento de credenciales. El fix del bug de sesión pasa a ser:
`MoodleSession(cookie=...)` recibe la cookie como parámetro del request.

### D2 — Importador canónico: `services/imports/`
Se **borra** `services/data_utils/`. Se adopta el flujo de 8 comandos `importar_*`
(ya probado en `Versioines Demo/moodle_app_async/`). Pendiente: arreglar
`services/imports/estudiantes.py` (importa `ArchivoEntrega`, modelo inexistente → crash),
migrar el dashboard web, y normalizar las materias ya cargadas bajo la Facultad `"Importadas"`.

### D3 — Extracción on-demand + hosting real
La extracción se dispara **a demanda desde el navegador**, no por cron. Como Render corta
los requests a ~100 s, **se abandona Render** y se mueve todo a hosting/servidor real con
Postgres administrado ahí. La elección concreta de hosting está en análisis (§8).

### D4 — El rol "gestor" entra al alcance
Se implementa el paso 5 completo del plan: tabla `GestorMateria` + verificación de acceso
real contra Moodle antes de scrapear cada materia del alcance del gestor.

---

## 6. Problemas conocidos — auditoría Homúnculo (2026-08-30)

Hallazgos verificados sobre el código actual. Detalle completo en el historial de la
revisión; resumen accionable acá.

### Críticos

| # | Problema | Ubicación | Estado |
|---|---|---|---|
| C1 | **Secreto en el repo:** `gatfh/config_runtime.json` está trackeado y contiene un `SESSKEY` de Moodle. No está en `.gitignore`. `session.py` lo reescribia en cada scrape | `gatfh/config_runtime.json`, commit `cbe258a` | ✅ Agregado a `.gitignore`; `session.py` ya no escribe ese archivo (el sesskey vive en `self.sesskey`, por instancia). Pendiente: `git rm --cached` (lo hace el usuario, no Claude) |
| C2 | **Ninguna vista exige autenticación.** `login_required` importado y nunca aplicado. `/resumen/`, `/materias/`, etc. devuelven 200 anónimo con datos reales; `POST /extraccion/` anónimo dispara scraping. El `role` se toma de `request.GET` | `web/views.py` | ✅ `@login_required` en todas las vistas salvo login/register/logout |
| C3 | **`data\raw` con backslash literal** rompe en Linux (Render/VPS): produce un directorio llamado `data\raw`. `services/imports/` usa `data/raw/` → dos rutas distintas | `gatfh/config.py:9` + 8 literales en `services/imports/` | ✅ `config.py` usa `os.path.join(BASE_DIR, "data", "raw")`; los 8 literales de `services/imports/` ahora usan `config.DATA_DIR` |
| C4 | **Cookie vencida = scrape "exitoso" contaminante.** Moodle devuelve 200 con la página de login; el scraper la parsea como si fuera el curso y mete unidades fantasma en la BD sin lanzar excepción | `scraping/scrapers/tareas.py:16-20` | ✅ Se valida `"/login/" in str(resp.url)` en `tareas.py` y `session.py` antes de parsear |
| C5 | **Se pierden estudiantes** (solo con stdout UTF-8, o sea en Linux): una fila sin nombre hace `break` en vez de `continue` y descarta al resto de la tabla | `scraping/scrapers/detallesprofesores.py:96-98` | ✅ Cambiado a `continue` |
| C6 | **Dos subsistemas de importación** escribiendo las mismas tablas con semánticas incompatibles; el que corre primero gana. `services/imports/estudiantes.py:8` importa `ArchivoEntrega` (inexistente) → ese comando no arranca | `services/data_utils/` vs `services/imports/` | ⚠️ Parcial: se arregló el crash de `ArchivoEntrega` (se omite el guardado de adjuntos por estudiante, no existe ese modelo). La eliminación completa de `services/data_utils/` sigue pendiente |
| C7 | **La sección 4 del plan parte de una premisa falsa:** `procesar_profesor` NO puebla `Materia.profesores` (escribe un JSON que nadie lee). La M2M la puebla `carreras.py` → `linkcarreras.json` | `scraping/scrapers/profesores.py` | ⛔ Sin tocar |
| C8 | **`Materia.moodle_url` guardaba la URL de la primera tarea de la sección 1 (cualquier recurso al azar), no la URL del curso.** Como `load_courses()` (`web/views.py`) pasó a leer los cursos desde `Materia` en vez de `cursos.json` (necesario: `data/raw/*.json` está gitignoreado y no existe en Render), el scraper de "Extraer tareas" le pedía secciones a un link de tarea en vez de al curso — nunca iba a traer nada. Además faltaba por completo el botón/acción que dispara `obtener_tareas_async` y llena `tareas.json`, que es lo que "Normalizar" necesita para tener datos | `services/data_utils/import_to_db.py`, `web/views.py:load_courses` | ✅ `import_to_db.py` ahora toma la URL real desde `cursos.json` y se autocorrige en cada corrida de "Normalizar" si detecta una `moodle_url` que no es `/course/view.php`. Se agregó la acción `extraer_tareas` (botón "1. Extraer tareas del curso") que faltaba. Los 16 `Materia` de la BD **local** ya se corrigieron a mano; **la BD de Render (`centralizador_db2`) sigue con las URLs viejas, pendiente** |
| C9 | **Faltaba el paso previo a todo lo demás: no había forma de poblar `Facultad`/`Carrera`/`Materia`/`Profesor` desde el dashboard.** `load_courses()` lee `Materia` desde Postgres, pero nada en `/extraccion/` generaba `linkcarreras.json` ni lo importaba — el prototipo (`moodle_app_async`) sabe hacer el scraping (`categorias → carreras → linkcarreras`, ver `moodle/carreras.py`) pero nunca tuvo un loader de BD funcional (`crearbaseRelacional.py` tiene un import roto, `from moodle.config`, módulo que ya no existe, y no lo llama nada). Además el orden documentado acá mismo (`importar_materias` antes que `importar_profesores`) deja la M2M `Materia.profesores` vacía en silencio, porque `materias.py` busca el `Profesor` ya creado al enlazarlo | `web/views.py` (dashboard), `services/management/commands/importar_*` | ✅ Agregada la acción `extraer_carreras` (botón "0. Extraer carreras"), que corre la cadena de 3 pasos pasando el cookie explícito (mismo patrón que `extraer_tareas`/`estudiantes`, no la ruta vieja de `services/utils/run_scraping` que todavía usa `MoodleSession()` sin cookie). Orden de importación corregido en §3.1 (profesores antes que materias). Probado end-to-end en Postgres local: 779 materias / 157 profesores / 759 materias con profesor enlazado |
| C10 | **Redirect de error de sesión rompía con 404.** `handle_session_error`/`cookie_recovery_view` y `session_recovery.html` tenían hardcodeado el prefijo `/web/` (`/web/session-cookie/`, `/web/dashboard/`, `/web/resumen/`), pero la app está montada en la raíz (`gatfh/urls.py` incluye `web.urls` en `''`). Cualquier extracción con la cookie vencida o sin guardar terminaba en un 404 en vez de mostrar el formulario para pegarla de nuevo | `web/views.py`, `web/templates/web/session_recovery.html` | ✅ Reemplazados todos los hardcodeos por `reverse('dashboard')`/`reverse('session_cookie')`/`reverse('resumen')`/`{% url %}`. Además, las acciones que llaman a Moodle (`extraer_carreras`/`extraer_tareas`/`estudiantes`/`extraer_participantes`) ahora frenan con un mensaje claro si no hay cookie guardada **antes** de tomar el candado, en vez de ocuparlo para nada y descubrirlo recién al fallar contra Moodle |
| C11 | **Selección de cursos sin límite en `/extraccion/`.** Los checkboxes (`name="courses"`, grilla de materias) permitían marcar cualquier cantidad para las acciones que llaman a Moodle de verdad, síncronas dentro del request (hoy combinadas en "1. Extraer, asignar e importar tareas" / "2. Extraer e importar estudiantes" / "3. Extraer e importar último acceso" — `cargar_tareas`/`cargar_estudiantes`/`cargar_ultimo_acceso`). Una selección grande encadena muchos requests secuenciales (con sleeps entre ellas) en un solo POST, con riesgo de WORKER TIMEOUT de gunicorn (bullet ya documentado en "Importantes" más abajo) | `web/templates/web/dashboard.html`, `web/views.py:dashboard` | ✅ Corregido (2026-10-23), a propósito **sin** convertir la grilla en selección única: "4. Generar Excel" y "Revisar asignación" no llaman a Moodle y sí tiene sentido pedirles varios cursos a la vez, así que la grilla sigue siendo multi-select. En su lugar: (1) `dashboard.html` avisa con SweetAlert *antes* de enviar el formulario si hay más de un curso tildado para `cargar_tareas`/`cargar_estudiantes`/`cargar_ultimo_acceso`; (2) `dashboard()` rechaza con un `ValueError` esas mismas acciones si `len(selected_ids) != 1` — la validación real, por si llega un POST armado a mano saltándose el JS |
| C12 | **`estudiantes()` sobrescribía `estudiantes.json` entero, sin el candado de profesor que sí tiene `tareas()`.** `tareas()` (`services/utils/run_scraping.py:49-106`) guarda un marcador `{"profesor": id}` como primer elemento del JSON: si el `profesor_id` de la corrida actual coincide, conserva/mergea lo de otros cursos del mismo profesor; si no coincide (otro usuario), descarta todo y arranca de cero. `estudiantes()` no tenía ningún chequeo equivalente: llamaba a `exportarjson.save_estudiantes(estudiantes_resultado)` con *solo* el resultado de la corrida actual | `services/utils/run_scraping.py` (función `estudiantes()`), `services/data_utils/cargarjson.py` | ✅ Corregido (2026-10-23): portado a `estudiantes()` el mismo patrón de marcador + merge que ya tenía `tareas()` (acá la clave de merge es el `id` de tarea, no `asignatura`, porque cada entrada de `estudiantes.json` es por-tarea). De paso se arregló `cargar_estudiantes()`, que no manejaba archivo inexistente/corrupto (a diferencia de `cargar_tareas()`) y hubiera roto el merge en la primera extracción de un VPS nuevo. **Importante — esto es defensa en profundidad, no el único mecanismo:** al revisar el código vigente se confirmó que `cargar_tareas`/`cargar_estudiantes`/`cargar_ultimo_acceso` ya ejecutan extracción **e importación** dentro de la misma función (`run_cargar_tareas_web`/`run_cargar_estudiantes_web`/`run_cargar_ultimo_acceso_web`), bajo un único `try/finally` que retiene el candado de `extraction_lock` hasta que *todo* termina (`web/views.py:704-934`) — no solo durante el scraping. Eso ya cerraba el caso principal (nadie más puede extraer mientras el actual no terminó de importar); el marcador de esta fila cubre lo que ese candado no cubre: si la extracción tiene éxito pero el *import* falla a mitad de camino, el candado ya se liberó con datos sin importar en el JSON |
| C13 | **"Guardar cambios" del modal de asignación perdía el listener del spinner de extracción.** El modal (`#modalAsignacion`) tenía su propio `<form>` aparte de `#formAcciones`, con submit normal: al guardar, recargaba la página entera (Post-Redirect-Get). Eso reinicia todo el `<script>` de `dashboard.html` desde cero, y si algo fallaba al reconstruirlo (se vio un `Uncaught SyntaxError` en la consola del navegador, pero no se logró aislar su causa exacta), ningún listener volvía a engancharse — incluido el de `#formAcciones` que muestra el spinner. Reproducido en 2 laptops distintas con los mismos pasos: abrir "Revisar asignación" → "Guardar cambios" → cualquier botón de extracción después hacía un submit nativo del navegador (se veía como `302` en el log en vez del `200` JSON esperado) en lugar de pasar por `fetch()`, sin mostrar spinner ni sondear el progreso | `web/templates/web/dashboard.html`, `web/views.py:dashboard` | ✅ Corregido (2026-10-29): "Revisar asignación" y "Guardar cambios" pasan a `fetch()`, igual que "1"–"4" — la vista ya devolvía JSON por ese camino para esas acciones, solo le faltaba incluir `asignacion_detalle`/`categorias_peso` en la respuesta para poder pintar el modal en JS sin ningún GET de por medio. Ninguno de los dos vuelve a navegar la página, así que el script nunca se reinicia y el bug deja de poder pasar, sin depender de haber encontrado la causa exacta del `SyntaxError` original |

**Antes/después de C13** — el cambio central fue mover "Guardar cambios" de un `<form>` con submit normal a uno interceptado por `fetch()`, y que el backend entregara el contenido del modal como JSON en vez de HTML server-rendered:

```html
<!-- ANTES: web/templates/web/dashboard.html -->
<form method="post" class="modal-form">
    {% csrf_token %}
    <input type="hidden" name="action" value="guardar_asignacion_manual" />
    {% for cid in selected_ids %}<input type="hidden" name="courses" value="{{ cid }}" />{% endfor %}
    ...
</form>
<!-- submit nativo -> recarga TODA la página, reinicia el <script> entero -->
```

```html
<!-- DESPUÉS -->
<form id="formAsignacionManual" class="modal-form">...</form>
```
```javascript
formAsignacionManual.addEventListener('submit', function (ev) {
    ev.preventDefault();  // nunca navega
    var datos = new FormData(formAsignacionManual);
    datos.set('action', 'guardar_asignacion_manual');
    cursosDelModal.forEach(function (id) { datos.append('courses', id); });
    fetch(window.location.pathname, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrftoken },
        body: datos,
    }).then(function (r) { return r.json(); }).then(function (data) {
        mostrarResultado(data.action_result);
        pintarAsignacion(data.asignacion_detalle, data.categorias_peso);  // repinta sin recargar
    });
});
```

```python
# ANTES: web/views.py::dashboard, rama X-Requested-With
return JsonResponse({
    'action_result': action_result,
    'error': error,
    'abrir_modal_asignacion': bool(abrir_modal_asignacion and not error),
})
```
```python
# DESPUÉS
respuesta = {
    'action_result': action_result, 'error': error, 'error_link': error_link,
    'abrir_modal_asignacion': bool(abrir_modal_asignacion and not error),
}
if abrir_modal_asignacion and not error:
    respuesta['asignacion_detalle'] = construir_asignacion_detalle(selected_ids)
    respuesta['categorias_peso'] = [{'key': c, 'label': CATEGORIA_LABELS[c]} for c in CATEGORIAS_PESO]
return JsonResponse(respuesta)
```

### Importantes

- `Profesor.moodle_id` **ya es** el `moodle_userid` que el plan proponía agregar — mismo namespace que `Estudiante.moodle_userid`. No agregar un tercer campo.
- Una persona con doble rol genera dos filas (una en `Profesor`, otra en `Estudiante`) con el mismo número de Moodle, sin constraint que lo detecte.
- **4 reglas distintas** de "¿qué Profesor soy yo?" en `web/views.py` (`:63-71` con fallback `icontains` que puede dar acceso a materias ajenas, `:85`, `:112`, `:730`) — **sin tocar todavía**, sigue pendiente unificarlas por `moodle_userid` (D1).
- **N+1 en `/resumen/`**: `web/views.py:439` pone `select_related` y `:455` lo pisa; ~4000 queries con 40 materias / 2000 entregas.
- `except Exception: pass` cubriendo 116 líneas de cálculo de KPIs (`web/views.py:385-501`).
- ✅ `ClientTimeout` agregado (30s) en `tareas.py` y `detallesprofesores.py`.
- ✅ `config.SESSKEY` ya no es variable de módulo mutable — vive en `MoodleSession.sesskey`, por instancia (una por request/job).
- `services/imports/estudiantes.py`: emails repetidos de Moodle → `IntegrityError` silencioso (`Estudiante.email` es `unique`); `import_all_data` igual reporta "completada exitosamente" — sin tocar.
- `import_all_data` nunca importa profesores (solo tareas y estudiantes) — sin tocar.
- ✅ `range(1, 13)` hardcodeado en `tareas.py:73` → ahora detecta el número real de secciones leyendo la página del curso (`detectar_num_secciones`), con `12` como piso si no se puede detectar.
- ✅ `print("... ✔")` en `services/data_utils/{cargarjson,exportarjson}.py` rompía con `UnicodeEncodeError` en consolas Windows con codepage `cp1252` (no en Render, que es Linux/UTF-8, pero sí al correr local) — se sacó el carácter.
- Documentos de junio (`README` viejo, `PROYECTO_COMPLETADO.md`, `TAREAS_COMPLETADAS.md`) contradicen el código: p. ej. afirmaban "las cookies NUNCA se persisten en DB" (falso, corregido ahora con `SESSION_ENGINE = signed_cookies`) y `actividades = Tarea.objects.count()` (está filtrado).
- ✅ (10-15) El filtro de rol "estudiante"/"todos" del dashboard (`filter_courses_by_role`, `web/views.py`) no tenía ninguna relación real con el usuario logueado: calculaba "estudiante" como "cualquier materia de toda la BD sin profesor asignado", heurística sin ningún vínculo con quién inició sesión (a diferencia de "docente", que sí usaba `Materia.profesores` real y por eso andaba bien). Corregido para usar `AccesoCurso` (§1) y el `moodle_id` real del profesor logueado — depende de que ya se haya corrido "3b. Extraer último acceso" + su importador para esas materias.
- `services/utils/run_scraping.py::run_obtener_categorias/obtener_carreras/obtener_Linkcarreras` **todavía** instancian `MoodleSession()` sin cookie (leen el fallback `config.COOKIES` del `.env`) — es la misma clase de bug que D1b ya corrigió para tareas/estudiantes. La acción web `extraer_carreras` (C9) no pasa por ahí: la vista arma su propio `MoodleSession(cookie=...)` y llama directo a `scraping/scrapers/carreras.py`. Si alguien usa el management command CLI (`extraer_categorias`/`extraer_carreras`/`extraer_linkcarreras`) en vez del botón, sigue dependiendo de `MOODLE_SESSION_COOKIE` en `.env` — sin tocar.
- **Gunicorn no tiene `--timeout` seteado en el `Procfile`** → default de 30s. Cualquier acción que llame a Moodle de verdad (`extraer_carreras`, `extraer_tareas`, `estudiantes`) corre síncrona dentro del request y puede superar ese límite fácilmente (la sola cadena de `extraer_carreras` hace 8-15+ POST secuenciales con `sleep(1.5-3.5s)` entre páginas) — el worker muere con "WORKER TIMEOUT" sin importar el hosting (Render, VPS, el que sea). Subir `--timeout` es un parche; la solución de fondo sigue siendo sacar la extracción del request HTTP (Bloque 2, cola/worker separado).

### Contexto no verificable sin ejecutar

- Nada se probó contra el Moodle real de TECBA ni contra un hosting real.
- `collectstatic` en el build del hosting: con `CompressedManifestStaticFilesStorage`, si no corre en el build, todo `{% static %}` lanza 500.

### Puntos a verificar (actualizado 2026-10-01)

- [x] **"Extraer carreras" contra Moodle real** — confirmado en Postgres local: 41 facultad/carrera/nivel, 831 materias en `linkcarreras.json`, importadas como 6 Facultad / 12 Carrera / 9 Nivel / 779 Materia / 157 Profesor (759 materias con profesor enlazado).
- [ ] **"Extraer tareas del curso" y "Extraer estudiantes" contra Moodle real** — corregido el bug de C8 y simulado con un stub, pero todavía no ejecutado de punta a punta contra el Moodle real de TECBA.
- [ ] **Aplicar la corrección de `Materia.moodle_url` (C8) en Render** (`centralizador_db2`) — solo se corrigió en la base local; Render sigue con las URLs viejas hasta que se repita la corrección ahí o se vuelva a poblar desde un dump ya corregido.
- [ ] **Repoblar Render (`centralizador_db2`) con la jerarquía nueva de carreras** — Render todavía tiene el dataset viejo (343 materias, con una Facultad `"Importadas"` de un import previo con `services/data_utils/`); la base local ya quedó más limpia (779 materias, sin esa Facultad ficticia, orden de import corregido). Decidir si se re-pobla Render igual o se espera al hosting definitivo (D3).
- [ ] **Auditar las migraciones `0012_profesor_user` y `0013_tarea_descripcion_tarea_url_entrega`** — agregan `Profesor.user` (OneToOne a `auth.User`) y campos nuevos a `Tarea`; se hicieron fuera de este historial de auditoría y `get_current_profesor`/`register_view` ya dependen de `Profesor.user`, pero no se revisó si rompen algo de lo documentado en §5/§6.
- [ ] **Confirmar visualmente en navegador** la paleta nueva (dorado + violeta), el sidebar oculto antes de login, el autocompletado de `/register/` y el layout responsive — todo se verificó con `manage.py check` y el test client de Django, no mirando la página real.
- [ ] **Probar el candado cross-user con una segunda cuenta de docente real** (no simulada) para confirmar el mensaje de "extracción en curso" y que el botón de emergencia la libera.
- [ ] **Setear `--timeout` en gunicorn** (o mover la extracción a un worker separado) antes de probar `extraer_carreras`/`extraer_tareas`/`estudiantes` en cualquier hosting real — ver bullet de Gunicorn en "Importantes".

---

## 7. Orden de trabajo (borrador, se refina con §8)

**Bloque 0 — antes de cualquier cosa de Fase 2:**
1. ⚠️ Sacar `gatfh/config_runtime.json` del repo — agregado a `.gitignore` y ya no se
   reescribe; falta el `git rm --cached` (lo hace el usuario) + decidir rotación del sesskey.
2. ✅ Aplicado `login_required`. Falta la segunda mitad: filtrar materias/docentes/estudiantes
   por usuario (no solo exigir login).
3. ✅ `gatfh/config.py:9` → `os.path.join(BASE_DIR, "data", "raw")` + los 8 literales de
   `services/imports/` ahora usan `config.DATA_DIR`.
4. ✅ Arreglado el crash de `services/imports/estudiantes.py:8` (`ArchivoEntrega` no existía) —
   se omite el guardado de adjuntos por estudiante hasta que se defina ese modelo.

**Bloque 1 — integridad de datos:**
5. ✅ Validado en `tareas.py` (y `session.py`) que la respuesta no sea la página de login (C4).
6. ✅ `break` → `continue` en `detallesprofesores.py:98` (C5).
7. ✅ `ClientTimeout(total=30)` en los `ClientSession` de `tareas.py` y `detallesprofesores.py`;
   `return_exceptions=True` en sus `gather`.
8. ✅ `range(1,13)` dinámico en `tareas.py:73` vía `detectar_num_secciones`.
9. ⛔ Sin tocar: borrar `services/data_utils/`, migrar el dashboard a `services/imports/`,
   normalizar la Facultad `"Importadas"`.

**Candado entre usuarios (no estaba en el Bloque 0/1 original, se resolvió junto con esto):**
`web/views.py:dashboard` llamaba `asyncio.run(...)` directo en el request con
`config.SESSKEY`/`config.COOKIES` globales compartidos — con 2+ usuarios concurrentes, el
sesskey de uno se le podía mostrar a otro a mitad de scraping. Resuelto con
`services/utils/extraction_lock.py` (candado en Postgres, timeout de 2 min) + botón de
emergencia "Detener extracción" (`POST /extraccion/detener/`), sin tocar hosting ni agregar
Celery/Redis. `MoodleSession` ahora recibe el cookie por parámetro en vez de leer
`config.COOKIES` global (D1b).

**Pipeline de extracción incompleto (encontrado al probar el candado en producción, no estaba
documentado):** faltaba el paso que trae las tareas de cada curso antes de "Normalizar", y el
campo `Materia.moodle_url` del que dependía ese paso estaba mal poblado desde siempre (ver C8).
Se agregó la acción `extraer_tareas` (botón "1. Extraer tareas del curso" en `/extraccion/`) y
se corrigió `import_to_db.py` para que tome la URL real del curso y se autocorrija en cada
corrida de "Normalizar". Corregido en la BD local; **pendiente en Render**.

**Interfaz (pedido explícito, no estaba en el Bloque 0/1 original):** sidebar oculto antes de
login, autocompletado de nombre de docente en `/register/`, paleta dorado+violeta, layout
responsive, y el cuadro para pegar la cookie de Moodle directo en `/extraccion/`
(`SESSION_ENGINE = signed_cookies`, nunca toca Postgres).

**Bloque 2 — solo después:** hosting real → extensión de navegador → rol gestor.

---

## 8. Roadmap

El plan de Fase 2 detallado está en [`PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md), **en
re-ordenamiento** para reflejar las decisiones D1–D4 de §5 (muere la sección 5 de cifrado;
la extensión de navegador pasa de "fase posterior" a núcleo; se agrega la migración de
hosting; se evalúa si la cola en Postgres sigue siendo necesaria con extracción on-demand).

---

## 9. Historial de documentación

| Archivo | Estado |
|---|---|
| `README.md` (este) | Punto de verdad del estado |
| `PLAN_DESARROLLO.md` | Roadmap de Fase 2 (en re-ordenamiento) |
| `deploy/README.md` | Guía operativa del VPS (levantar, redeploy, backups) — ver §10 |
| `archivo/PROYECTO_COMPLETADO.md` | Archivado — junio 2026, avance inflado |
| `archivo/TAREAS_COMPLETADAS.md` | Archivado — junio 2026, matriz de requisitos desactualizada |
| `archivo/QUICKSTART.md` | Archivado — junio 2026, comandos y rutas incorrectos |

---

## 10. Deploy en producción (VPS)

Corriendo en un VPS compartido (Contabo) junto a otros 3 proyectos del grupo, vía Docker
Compose + un proxy Caddy compartido que maneja HTTPS para los 4. Guía operativa completa
(cómo levantarlo, redeploy, backups, troubleshooting) en [`deploy/README.md`](deploy/README.md).

- **URL:** `https://centralizador-tecba.duckdns.org`
- **Servicios:** `web` (Django + gunicorn, 2 workers — ver nota sobre el candado en §1),
  `db` (Postgres 17), `respaldos` (backup diario automático, 14 días / 4 semanales / 3
  mensuales, fuera de Docker en `deploy/respaldos/`)
- **Aislamiento:** ningún servicio de Centralizador publica un puerto al mundo salvo el
  Caddy compartido (80/443). `db` sí tiene un puerto en `127.0.0.1:5432` — solo alcanzable
  desde el propio VPS, pensado para conectar un cliente como DBeaver por túnel SSH.
- **Deploy automático:** `.github/workflows/deploy-vps.yml` ya está en el repo (hace
  `git pull` + `docker compose up -d --build` en cada push a `main`), pero **todavía no
  está activado** — falta generar la llave SSH restringida en el VPS y cargar los secrets
  (`VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY`) y la variable `VPS_DEPLOY_ACTIVO` en GitHub
  (detalle en `deploy/README.md`, sección 4). Hasta entonces, el redeploy es manual:
  `git pull --ff-only && docker compose up -d` en el VPS.
- **Render:** abandonado como ruta de deploy (D3, §5); el `Procfile` se mantiene en el
  repo pero no es el camino real hoy.
- **Seed de datos:** `data/raw/categorias.json`/`carreras.json`/`linkcarreras.json` se
  versionan a propósito (excepción en `.gitignore`) para poder importar la jerarquía de
  carreras en un deploy nuevo sin volver a correr "Extraer carreras" contra Moodle — no
  traen datos de estudiantes.

---

## 11. Predicciones — modelo de riesgo (Random Forest)

**Estado: en progreso, iniciado 2026-10-14.** `/predicciones/` sigue siendo placeholder
(§1); esto es el trabajo de base para dejar de serlo. Elegido Random Forest sobre
XGBoost/K-Means (ver 2.2.9.1 del Marco Conceptual de la tesis). Entrenamiento en Google
Colab; el modelo entrenado (`.joblib`) se va a versionar en el repo para que el deploy en
Docker lo sirva sin infraestructura extra.

### Decisión de diseño: qué predice y de dónde sale la etiqueta

No existe en la base ningún campo histórico de "en riesgo"/"aprobó"/"reprobó" — hay que
derivarlo. Unidad de observación elegida: **una fila por `(Estudiante, Materia,
parcial)`** ya cerrado (no por estudiante solo, para tener más filas y porque el riesgo
es específico a una materia). Label: nota ponderada del parcial (misma fórmula que ya usa
"Generar Excel", ver abajo) comparada contra la nota mínima de aprobación.

- **Nota de aprobación:** 61/100 (confirmado por el usuario, TECBA). **No quedó
  hardcodeada** — es configurable, porque así lo pidió el usuario explícitamente para
  poder ajustarla desde el panel de Predicciones más adelante.
- **Features candidatas** (calculadas con datos *del propio parcial*, nunca posteriores,
  para no "ver el futuro"): % de tareas sin entregar, % ya calificadas, días de atraso
  promedio, cantidad de entregas atrasadas.
- **Candidata nueva, todavía no integrada (10-15):** días desde el último acceso más
  reciente del estudiante a *cualquiera* de sus materias, usando `AccesoCurso` (§1) — si
  supera ~1 mes, señal de posible abandono. Requiere que "3b. Extraer último acceso" ya se
  haya corrido para esas materias; `exportar_dataset_ml` todavía no la calcula.
- **Advertencia de volumen de datos (confirmada por el usuario):** hoy hay ~80 entregas
  calificadas, de 2 cursos del año pasado. Es muy poco para un Random Forest confiable —
  el plan es dejar el pipeline listo y correrlo de nuevo a medida que más profesores usen
  el sistema, no asumir que ya hay suficiente para entrenar en serio.

### Lo que ya se construyó (verificado contra el código)

| Pieza | Qué hace |
|---|---|
| `ConfiguracionInstitucional` (modelo + migración `0018`) | Fila única (mismo patrón que `TrabajoExtraccion`, pk=1) con `nota_aprobacion` (default 61). La usa tanto el entrenamiento como, a futuro, el panel de Predicciones en producción. |
| `calcular_total_parcial()` en `services/data_utils/run_export.py` | Extraída de `generar_excel()` (antes era código inline) para que la etiqueta del dataset de entrenamiento use **la misma fórmula** que ya ve el profesor en el Excel, en vez de una paralela que podría divergir. |
| `python manage.py exportar_dataset_ml` (nuevo comando) | Arma `data/ml/dataset_ml.csv` (gitignoreado — trae `estudiante_id` real) con una fila por `(estudiante, materia, parcial)` cerrado: features + `nota_parcial` + `en_riesgo`. Reusa `parse_date_string()` de `web/views.py` para los días de atraso en vez de reimplementar el parseo de fechas en texto libre. Informa por consola cuántas materias se saltearon y por qué (sin profesor enlazado / sin `PesosCategorias`-`FechasParciales` en `/configuracion/` / sin entregas tipo `assign`) — importante porque con tan pocos datos es más probable terminar en 0 filas que en un dataset usable, y sin ese desglose no hay forma de saber por qué. |

**Pendiente de ejecutar** (verificado 10-15: la migración `0018` ya está aplicada, pero
`data/ml/` sigue vacío — `exportar_dataset_ml` nunca se corrió): `python manage.py
exportar_dataset_ml`, y confirmar cuántas filas salen antes de seguir con el notebook de
Colab. Es el siguiente paso concreto y accionable de esta sección.

### Lo que falta (no construido todavía)

1. **Notebook de Colab**: lee `dataset_ml.csv`, entrena `RandomForestClassifier
   (class_weight='balanced')`, evalúa con precision/recall por clase (no accuracy sola —
   con pocos casos de "en riesgo", accuracy engaña), guarda con `joblib.dump`.
2. **Llevar el modelo a Docker**: `.joblib` versionado en el repo (ej.
   `ml/models/riesgo_v1.joblib`), entra al build con el `COPY . .` del `Dockerfile` de
   `deploy/web/` sin infraestructura extra. Hay que fijar la versión de `scikit-learn` en
   `requirements.txt` igual a la usada en Colab, o el `.joblib` puede no cargar.
3. **Panel de configuración en `/predicciones/`** — importante separar dos cosas que no
   son lo mismo: la configuración de *entrenamiento* (hiperparámetros de Random Forest)
   vive en Colab, no en la web — no tiene sentido exponerla en producción porque cambiarla
   implica reentrenar, no solo re-evaluar. Lo que sí va en el panel web, porque es
   configuración de *inferencia* sobre un modelo ya entrenado:
   - Umbral de aprobación (ya armado, `ConfiguracionInstitucional.nota_aprobacion`)
   - Bandas de riesgo (bajo/medio/alto) por probabilidad de la predicción
   - Selector de versión de modelo, si se suben reentrenos periódicos
   - Botón "Recalcular predicciones" explícito (no se corre en cada visita a la página —
     mismo patrón que ya usa Extracción, no un cálculo síncrono en cada GET)
