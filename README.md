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

## 1. Estado real (2026-08-30)

Lo que la Fase 1 dejó **realmente** funcionando, verificado contra el código —
no contra los documentos de junio, que inflaban el avance.

| Módulo | Estado | Detalle |
|---|---|---|
| Routing + sidebar (8 módulos) | ✅ Funciona | `web/urls.py`, `web/templates/web/base.html` |
| Autenticación | ⚠️ Incompleta | Vistas `login`/`register`/`logout` existen; `register` exige que el usuario coincida con un `Profesor.nombre`. **`login_required` está importado pero no se aplica a ninguna vista — todas las páginas son públicas.** |
| Resumen (KPIs + Chart.js) | ⚠️ Frágil | Renderiza, pero el cálculo está envuelto en `except: pass` (una BD vacía muestra ceros indistinguibles de "sin alertas"); N+1 (~4000 queries medidos); "actividades" cuenta solo tareas cuyo título contiene `"Examen"`/`"tek"`, no todas |
| Materias / Docentes / Estudiantes | ⚠️ Listado básico | Consultas con algunas anotaciones; quedan `print()` de depuración en el código |
| Alertas | ⚠️ Parcial | 3 reglas efectivas (el README de junio decía 5): materias sin actividades, tareas sin cierre, sobrecarga >8 pendientes. "Sobrecarga" tiene **dos definiciones incompatibles** en `web/views.py` (≥3 el mismo día para el KPI, >8 pendientes para alertas) |
| Extracción (`/extraccion/`) | ⚠️ Con bugs | POST dispara `normalizado`/`asignacion`/`estudiantes`/`transformar`. `MoodleSession()` lee `config.COOKIES` (del `.env`), **no** `request.session['MoodleSession']` → el flujo de "recuperar cookie" desde la web no llega al scraper |
| Recuperación de cookie | ⚠️ Rota parcialmente | Guarda `request.session['MoodleSession']` + un `make_password()` de la cookie en `Profesor.moodle_session_hash` que **nadie lee**. El redirect apunta a `/web/session-cookie/` pero la ruta real es `/session-cookie/` → 404 |
| Predicciones / Reportes / Configuración | ⛔ Placeholder | Solo renderizan un mensaje fijo |
| Importadores | ⚠️ Duplicados | Ver §4. Existen dos subsistemas (`services/data_utils/` y `services/imports/`) que escriben las mismas tablas con semánticas distintas |
| Base de datos | ✅ Postgres | `DATABASE_URL` vía `dj-database-url`, fallback a SQLite. Migraciones `0001`–`0010` |
| Preparación de deploy | ✅ Local, ⛔ sin probar | `Procfile`, `requirements.txt`, `.python-version`, `whitenoise`, hardening de producción condicionado a `DEBUG=False`. Nunca se desplegó en ninguna plataforma |

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
  management/commands/  Comandos de extracción (extraer_*) e importación
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

python manage.py migrate
# Importar datos desde data/raw/*.json (ver nota sobre importadores en §4):
python manage.py importar_facultades
python manage.py importar_carreras
python manage.py importar_niveles
python manage.py importar_materias
python manage.py importar_profesores
python manage.py importar_tareas
python manage.py importar_detalles_tareas
python manage.py importar_estudiantes

python manage.py runserver   # http://localhost:8000/
```

`.env` nunca se commitea. Si `DATABASE_URL` no está definida, el proyecto usa SQLite
automáticamente.

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

| # | Problema | Ubicación |
|---|---|---|
| C1 | **Secreto en el repo:** `gatfh/config_runtime.json` está trackeado y contiene un `SESSKEY` de Moodle. No está en `.gitignore`. `session.py` lo reescribe en cada scrape | `gatfh/config_runtime.json`, commit `cbe258a` |
| C2 | **Ninguna vista exige autenticación.** `login_required` importado y nunca aplicado. `/resumen/`, `/materias/`, etc. devuelven 200 anónimo con datos reales; `POST /extraccion/` anónimo dispara scraping. El `role` se toma de `request.GET` | `web/views.py` |
| C3 | **`data\raw` con backslash literal** rompe en Linux (Render/VPS): produce un directorio llamado `data\raw`. `services/imports/` usa `data/raw/` → dos rutas distintas | `gatfh/config.py:9` + 8 literales en `services/imports/` |
| C4 | **Cookie vencida = scrape "exitoso" contaminante.** Moodle devuelve 200 con la página de login; el scraper la parsea como si fuera el curso y mete unidades fantasma en la BD sin lanzar excepción | `scraping/scrapers/tareas.py:16-20` |
| C5 | **Se pierden estudiantes** (solo con stdout UTF-8, o sea en Linux): una fila sin nombre hace `break` en vez de `continue` y descarta al resto de la tabla | `scraping/scrapers/detallesprofesores.py:96-98` |
| C6 | **Dos subsistemas de importación** escribiendo las mismas tablas con semánticas incompatibles; el que corre primero gana. `services/imports/estudiantes.py:8` importa `ArchivoEntrega` (inexistente) → ese comando no arranca | `services/data_utils/` vs `services/imports/` |
| C7 | **La sección 4 del plan parte de una premisa falsa:** `procesar_profesor` NO puebla `Materia.profesores` (escribe un JSON que nadie lee). La M2M la puebla `carreras.py` → `linkcarreras.json` | `scraping/scrapers/profesores.py` |

### Importantes

- `Profesor.moodle_id` **ya es** el `moodle_userid` que el plan proponía agregar — mismo namespace que `Estudiante.moodle_userid`. No agregar un tercer campo.
- Una persona con doble rol genera dos filas (una en `Profesor`, otra en `Estudiante`) con el mismo número de Moodle, sin constraint que lo detecte.
- **4 reglas distintas** de "¿qué Profesor soy yo?" en `web/views.py` (`:63-71` con fallback `icontains` que puede dar acceso a materias ajenas, `:85`, `:112`, `:730`).
- **N+1 en `/resumen/`**: `web/views.py:439` pone `select_related` y `:455` lo pisa; ~4000 queries con 40 materias / 2000 entregas.
- `except Exception: pass` cubriendo 116 líneas de cálculo de KPIs (`web/views.py:385-501`).
- Sin `ClientTimeout` en los `aiohttp.ClientSession` (aiohttp aplica 300 s por defecto; 3× el timeout de un proxy típico).
- `config.SESSKEY` es variable de módulo mutable → con 2+ workers, el sesskey de un usuario se le puede mostrar a otro.
- `services/imports/estudiantes.py`: emails repetidos de Moodle → `IntegrityError` silencioso (`Estudiante.email` es `unique`); `import_all_data` igual reporta "completada exitosamente".
- `import_all_data` nunca importa profesores (solo tareas y estudiantes).
- Documentos de junio (`README` viejo, `PROYECTO_COMPLETADO.md`, `TAREAS_COMPLETADAS.md`) contradicen el código: p. ej. afirmaban "las cookies NUNCA se persisten en DB" (falso) y `actividades = Tarea.objects.count()` (está filtrado).

### Contexto no verificable sin ejecutar

- Nada se probó contra el Moodle real de TECBA ni contra un hosting real.
- No hay `.env` ni `data/raw/` en disco → los conteos "16 materias / 669 tareas / 288 entregas" del plan no se pudieron confirmar.
- `collectstatic` en el build del hosting: con `CompressedManifestStaticFilesStorage`, si no corre en el build, todo `{% static %}` lanza 500.

---

## 7. Orden de trabajo (borrador, se refina con §8)

**Bloque 0 — antes de cualquier cosa de Fase 2:**
1. Sacar `gatfh/config_runtime.json` del repo (`git rm --cached` + `.gitignore`); decidir rotación del sesskey y si el repo sigue público.
2. Aplicar `login_required` + filtrar materias/docentes/estudiantes por usuario.
3. `gatfh/config.py:9` → `os.path.join(BASE_DIR, "data", "raw")` + los 8 literales de `services/imports/`.
4. Arreglar `services/imports/estudiantes.py:8` (`ArchivoEntrega`).

**Bloque 1 — integridad de datos:**
5. Validar en `tareas.py` que la respuesta no sea la página de login (C4).
6. `break` → `continue` en `detallesprofesores.py:98` (C5).
7. `ClientTimeout` + `return_exceptions=True` en los `ClientSession`/`gather`.
8. `range(1,13)` dinámico en `tareas.py:73` (verificar primero si alguna materia supera 12 secciones).
9. Borrar `services/data_utils/`, migrar el dashboard a `services/imports/`, normalizar la Facultad `"Importadas"`.

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
