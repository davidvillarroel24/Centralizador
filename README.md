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

## 1. Estado real (actualizado 2026-10-01)

Lo que la Fase 1 dejó **realmente** funcionando, verificado contra el código —
no contra los documentos de junio, que inflaban el avance.

| Módulo | Estado | Detalle |
|---|---|---|
| Routing + sidebar (8 módulos) | ✅ Funciona | `web/urls.py`, `web/templates/web/base.html` |
| Autenticación | ✅ `login_required` aplicado | Todas las vistas salvo login/register/logout exigen sesión (C2 resuelto, `LOGIN_URL` en `settings.py`). `register` sigue exigiendo que el usuario coincida con un `Profesor.nombre`. |
| Resumen (KPIs + Chart.js) | ⚠️ Frágil | Renderiza, pero el cálculo está envuelto en `except: pass` (una BD vacía muestra ceros indistinguibles de "sin alertas"); N+1 (~4000 queries medidos); "actividades" cuenta solo tareas cuyo título contiene `"Examen"`/`"tek"`, no todas |
| Materias / Docentes / Estudiantes | ⚠️ Listado básico | Consultas con algunas anotaciones; quedan `print()` de depuración en el código |
| Alertas | ⚠️ Parcial | 3 reglas efectivas (el README de junio decía 5): materias sin actividades, tareas sin cierre, sobrecarga >8 pendientes. "Sobrecarga" tiene **dos definiciones incompatibles** en `web/views.py` (≥3 el mismo día para el KPI, >8 pendientes para alertas) |
| Extracción (`/extraccion/`) | ✅ Pipeline completo + candado | POST dispara 6 acciones en orden: `extraer_carreras` (**nuevo**, ver C9) → `extraer_tareas` (ver C8) → `normalizado` → `asignacion` → `estudiantes` → `transformar`. Las tres que llaman a Moodle de verdad (`extraer_carreras`, `extraer_tareas`, `estudiantes`) pasan el cookie de `request.session['MoodleSession']` a `MoodleSession(cookie=...)` y por el candado global (`services/utils/extraction_lock.py`, `data.TrabajoExtraccion`) que serializa entre usuarios distintos, con timeout de 2 min y botón "Detener extracción" (`POST /extraccion/detener/`). Probado contra el Moodle real de TECBA en local (Postgres propio, sin Render): `extraer_carreras` trajo 779 materias / 157 profesores reales. **`extraer_tareas`/`estudiantes` contra Moodle real siguen sin confirmarse.** |
| Cookie de Moodle | ✅ Nunca toca la BD | Se pega directo en `/extraccion/` (cuadro nuevo, se opaca al guardar). Vive en `request.session`, y `SESSION_ENGINE` se cambió a `signed_cookies` (`gatfh/settings.py`): la sesión completa (incluida la cookie) queda en una cookie firmada del navegador, nunca en `django_session` de Postgres. El flujo viejo (`/session-cookie/`, `session_recovery.html`) sigue existiendo como fallback pero ya no es el camino principal. |
| Predicciones / Reportes / Configuración | ⛔ Placeholder | Solo renderizan un mensaje fijo |
| Importadores | ⚠️ Duplicados | Ver §4. Existen dos subsistemas (`services/data_utils/` y `services/imports/`) que escriben las mismas tablas con semánticas distintas |
| Base de datos | ✅ Postgres | `DATABASE_URL` vía `dj-database-url`, fallback a SQLite. Migraciones `0001`–`0013` (`0012`/`0013` agregan `Profesor.user` y `Tarea.descripcion`/`url_entrega` — hechas fuera de esta auditoría, sin revisar todavía) |
| Preparación de deploy | ✅ Local, ⛔ sin probar | `Procfile`, `requirements.txt`, `.python-version`, `whitenoise`, hardening de producción condicionado a `DEBUG=False`. Nunca se desplegó en ninguna plataforma |
| Interfaz (paleta / responsive) | ✅ Hecho | Paleta cambiada de naranja→azul→dorado+violeta ("Protoss"); sidebar oculto antes de login; autocompletado de nombre de docente en `/register/` (`<datalist>`); tablas/gráficos/sidebar responsive (breakpoints en `sidebar.css`/`dashboard.css`). Verificado con Django test client + `manage.py check`, no visualmente en navegador real. |

**Fase 2 (multiusuario): 0 % en código.** Lo hecho hasta ahora es infraestructura
(lectura de `.env`, Postgres, preparación para hosting).

---

## 2. Stack y estructura

- **Python 3.14** · **Django 6.0.5** · **PostgreSQL** (SQLite como fallback local)
- `aiohttp` + `beautifulsoup4` para el scraping · `requests` para la sesión
- `pandas` + `openpyxl` para exportar Excel · `Chart.js` (CDN) en el front

```
gatfh/            Configuración Django (settings, urls, config.py, wsgi)
data/             Modelos: Profesor, Facultad, Carrera, Nivel, Materia, Unidad,
                  Tarea, Estudiante, Entrega, ArchivoTarea  + migraciones
web/              Vistas, templates, estáticos (el front completo)
scraping/scrapers/ Scrapers de Moodle (session, tareas, calificaciones, profesores,
                  carreras, detallesprofesores, normalización, asignartareas)
services/
  imports/        Importadores JSON→DB por entidad (8 comandos importar_*)  ← canónico (§3, decisión 2)
  data_utils/     Importadores antiguos (a eliminar — §3, decisión 2)
  extraccion/     Wrappers finos sobre los scrapers
  management/commands/  Comandos de extracción (extraer_*), importación (importar_*)
                  y `crear_admin` (seed del admin de prueba, ver §3)
  utils/          run_scraping, timing
data/raw/         Staging JSON de la extracción (gitignoreado — datos reales de personas)
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
| `archivo/PROYECTO_COMPLETADO.md` | Archivado — junio 2026, avance inflado |
| `archivo/TAREAS_COMPLETADAS.md` | Archivado — junio 2026, matriz de requisitos desactualizada |
| `archivo/QUICKSTART.md` | Archivado — junio 2026, comandos y rutas incorrectos |
