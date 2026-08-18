# Centralizador Académico - Plataforma de Monitoreo Docente

## 📋 Resumen Ejecutivo

**Centralizador Académico** es una plataforma de monitoreo y analytics para docentes construida en **Django + Bootstrap + Chart.js**, diseñada para transformar datos de Moodle en inteligencia académica. Permite supervisar indicadores de desempeño, detectar alertas, y apoyo para la toma de decisiones en tiempo real.

**Estado**: ✅ MVP Completado (ver tabla de tareas más abajo)

---

## 🎯 Objetivos Logrados

### ✅ Completado (Fase 1)

| Módulo | Tarea | Estado |
|--------|-------|--------|
| **Arquitectura** | Menú lateral responsivo (8 módulos) | ✅ |
| **Resumen** | Dashboard KPI (8 indicadores) | ✅ |
| **Resumen** | Gráficos Chart.js (Doughnut + Bar) | ✅ |
| **Resumen** | Alertas críticas integradas | ✅ |
| **Materias** | Lista de materias desde DB | ✅ |
| **Docentes** | Lista de docentes desde DB | ✅ |
| **Estudiantes** | Lista de estudiantes desde DB | ✅ |
| **Alertas** | Reglas: sin actividades, sin cierre, sobrecarga | ✅ |
| **Extracción** | Recuperación manual de cookie MoodleSession | ✅ |
| **Extracción** | UI con instrucciones visuales paso a paso | ✅ |
| **Extracción** | Almacenamiento en sesión (seguro/temporal) | ✅ |
| **Parseo** | Soporte múltiples formatos de fecha + dateutil | ✅ |
| **Importación** | Comando: `python manage.py import_json_to_db` (tareas) | ✅ |
| **Importación** | Comando: `python manage.py import_estudiantes_to_db` | ✅ |
| **Importación** | Comando: `python manage.py import_all_data` | ✅ |
| **Predicciones** | Estructura placeholder para ML | ✅ |
| **Reportes** | Plantilla placeholder + filtros UI | ✅ |
| **Configuración** | Panel placeholder con parámetros | ✅ |

### 🔄 Parcialmente Completado (Mejoras Futuras)

| Módulo | Tarea | Estado | Notas |
|--------|-------|--------|-------|
| **Materias** | Estado de cumplimiento (%) | ⏳ | Requiere cálculo de tareas completadas |
| **Materias** | Fechas de parciales + semáforo | ⏳ | Depende de migración `config_tareas.json` |
| **Docentes** | Indicadores de cumplimiento real | ⏳ | Requiere agregación por profesor |
| **Estudiantes** | Análisis semanal de carga | ⏳ | Requiere agrupar entregas por fecha |
| **Predicciones** | ML: Riesgo de retraso/sobrecarga | ⏳ | Estructura lista, pendiente algorítmica |
| **Reportes** | Filtros funcionales + Excel dinámico | ⏳ | Integración con `exportarjson.py` |
| **Configuración** | Gestión de categorías/parciales en UI | ⏳ | Requiere endpoints CRUD |

### ❌ No Iniciado

- **Auto-retry automático** de extracción (solo manual + reintentar explícitamente)
- **Websockets/tiempo real** para actualizaciones en vivo

---

## 🏗️ Arquitectura del Sistema

```
Centralizador Académico
│
├── 📦 Módulo Web (Django)
│   ├── URLs (web/urls.py)
│   │   ├── / → dashboard (extracción)
│   │   ├── /resumen/ → KPIs + gráficos
│   │   ├── /materias/ → listado
│   │   ├── /docentes/ → listado
│   │   ├── /estudiantes/ → listado
│   │   ├── /alertas/ → reglas críticas
│   │   ├── /session-cookie/ → recuperación manual
│   │   ├── /predicciones/ → ML placeholder
│   │   ├── /reportes/ → filtros + Excel
│   │   └── /configuracion/ → parámetros
│   │
│   ├── Vistas (web/views.py)
│   │   ├── dashboard() → extracción + UI selección
│   │   ├── resumen() → KPIs + chart data JSON
│   │   ├── materias_view() → Materia.objects.all()
│   │   ├── docentes_view() → Profesor.objects.all()
│   │   ├── estudiantes_view() → Estudiante.objects.all()
│   │   ├── alertas_view() → reglas de alertas
│   │   ├── cookie_recovery_view() → sesión cookie
│   │   ├── predicciones_view() → placeholder
│   │   ├── reportes_view() → placeholder
│   │   └── configuracion_view() → placeholder
│   │
│   ├── Templates (web/templates/web/)
│   │   ├── base.html (sidebar + layout responsivo)
│   │   ├── resumen.html (KPI cards + Chart.js)
│   │   ├── alertas.html (lista de alertas)
│   │   ├── session_recovery.html (instrucciones cookie)
│   │   ├── [materias|docentes|estudiantes].html (listados)
│   │   └── [predicciones|reportes|configuracion].html (placeholders)
│   │
│   └── Estáticos (web/static/web/)
│       └── sidebar.css (grid + card styling)
│
├── 🗄️ Modelos de Base de Datos (data/models.py)
│   ├── Profesor (moodle_id, nombre, URL)
│   ├── Facultad (nombre)
│   ├── Carrera (facultad, nombre)
│   ├── Nivel (nombre)
│   ├── Materia (gestion, grupo, sigla, nombre, moodle_*, carrera, nivel, profesores)
│   ├── Unidad (materia, nombre)
│   ├── Tarea (unidad, moodle_id, titulo, tipo, apertura, cierre, url)
│   ├── Estudiante (moodle_userid, nombre, email)
│   ├── Entrega (tarea, estudiante, estado, calificacion, ultimas_mods, comentarios)
│   └── ArchivoTarea (tarea, nombre, url, fecha)
│
├── 🔄 Servicios de Importación (services/data_utils/)
│   ├── import_to_db.py → Tareas JSON → DB
│   ├── import_estudiantes_to_db.py → Estudiantes/Entregas JSON → DB
│   └── Management Commands
│       ├── python manage.py import_json_to_db
│       ├── python manage.py import_estudiantes_to_db
│       └── python manage.py import_all_data
│
├── 🕷️ Scrapers Moodle (scraping/scrapers/)
│   ├── session.py → MoodleSession (gestión de sesskey + cookies)
│   ├── tareas.py → extrae tareas async
│   ├── calificaciones.py → extrae entregas + calificaciones
│   ├── profesores.py → lista de docentes
│   ├── normalizacion.py → normaliza estructura
│   ├── asignartareas.py → asignación de parciales
│   └── detalles[profesores].py → detalles por docente
│
├── 📊 Extracción y Transformación (services/extraccion/)
│   ├── scrap.py → orquestador async
│   ├── trasformar.py → genera Excel
│   └── session.py → gestión de sesión
│
└── ⚙️ Configuración Global (gatfh/)
    ├── settings.py → apps, middleware, DB
    ├── config.py → rutas JSON, SESSKEY Moodle
    ├── config_tareas.json → rangos parciales
    └── config_runtime.json → parámetros runtime
```

---

## 📊 Indicadores KPI (Módulo Resumen)

**Vista**: `/web/resumen/`

### Tarjetas de Indicadores
```
┌─────────────────────────────────────────────────┐
│ 📚 Materias:        12  │ 👨‍🏫 Docentes:        8   │
│ 👨‍🎓 Estudiantes:    245  │ 📋 Actividades:    1234 │
│ ⏳ Pendientes:      45   │ ⚠️ Retraso:         3   │
│ 🔴 Sobrecarga:       2   │ 🔄 Última sync:    5m  │
└─────────────────────────────────────────────────┘
```

### Fuentes de Datos
- **Materias**: `SELECT COUNT(*) FROM data_materia`
- **Docentes**: `SELECT COUNT(*) FROM data_profesor`
- **Estudiantes**: `SELECT COUNT(*) FROM data_estudiante`
- **Actividades**: `SELECT COUNT(*) FROM data_tarea`
- **Pendientes**: `SELECT COUNT(*) FROM data_entrega WHERE calificacion IS NULL OR calificacion = ''`
- **Retraso**: Detección de fechas pasadas en `tarea.cierre` (parseo robusto múltiples formatos)
- **Sobrecarga**: Estudiantes con >8 entregas pendientes
- **Última Sync**: `MAX(mtime)` de archivos JSON

### Gráficos
1. **Doughnut (Actividades)**
   - Labels: `['Pendientes', 'Calificadas']`
   - Data: `[pendientes_count, (total - pendientes)]`
   - Colores: Rosa + Azul

2. **Bar (Tareas por Materia)**
   - Top 8 materias por cantidad de tareas
   - Ordenado descendente
   - Color: Teal

---

## 🚨 Sistema de Alertas

**Vista**: `/web/alertas/`

### Reglas Implementadas

| Alerta | Condición | Severidad |
|--------|-----------|-----------|
| Materias sin actividades | `Materia.tareas.count() == 0` | ⚠️ Media |
| Tareas sin fecha de cierre | `Tarea.cierre IS NULL` | ⚠️ Media |
| Parciales no configurados | `config_tareas.rangos_parciales` vacío | ⚠️ Media |
| Sobrecarga de estudiantes | Estudiante con >8 entregas pendientes | 🔴 Alta |
| Retrasos detectados | `Tarea.cierre < HOY` | 🔴 Alta |

### Ejemplo de Respuesta API (JSON)
```json
{
  "materias_sin_actividades": [
    {"id": 5, "nombre": "Cálculo I"},
    {"id": 12, "nombre": "Física"}
  ],
  "tareas_sin_cierre": [
    {"moodle_id": 1842, "titulo": "Avance de Clase"}
  ],
  "estudiantes_sobrecarga": [
    {"estudiante__nombre": "Alex Mamani", "pendientes": 12}
  ]
}
```

---

## 🔐 Recuperación de Sesión Moodle

### Flujo (Sin Auto-Retry)

```
Usuario intenta extraer
         ↓
¿Cookie válida?
  ├─ NO → Error capturado
  │       ↓
  │       Redirige a /web/session-cookie/?error=...
  │       ↓
  │       UI muestra instrucciones paso a paso
  │       ├─ Abre Moodle en navegador
  │       ├─ F12 → Application → Cookies
  │       ├─ Busca "MoodleSession"
  │       ├─ Copia valor
  │       ├─ Pega en textarea
  │       └─ Click "Guardar y continuar"
  │       ↓
  │       `request.session['MoodleSession'] = valor`
  │       ↓
  │       Usuario vuelve manualmente a /web/dashboard/
  │       ↓
  │       Reintenta acción con nueva sesión
  │
  └─ SÍ → Procede normalmente
```

### Código de Integración

```python
# En web/views.py
def handle_session_error(request, error_msg, next_url='/web/'):
    """Redirige con parámetros de error y URL de retorno."""
    params = urlencode({'error': error_msg, 'next': next_url})
    return redirect(f'/web/session-cookie/?{params}')

# En dashboard()
except Exception as exc:
    error_str = str(exc)
    if any(word in error_str.lower() for word in ['cookie', 'sesión', 'session']):
        return handle_session_error(request, error_str, next_url=request.path)
```

---

## 📈 Flujo de Importación de Datos

### Step 1: Extracción desde Moodle
```
scraping/scrapers/tareas.py (async, Semaphore(5))
  └─ Genera data/raw/tareas.json
     └─ Genera data/raw/estudiantes.json
        └─ Genera data/raw/calificacion.json
```

### Step 2: Importación a Base de Datos
```bash
python manage.py import_all_data
  ├─ import_tareas_from_json()
  │  └─ Crea Materia, Unidad, Tarea desde tareas.json
  │
  └─ import_estudiantes_from_json()
     └─ Crea Estudiante, Entrega desde estudiantes.json
```

### Step 3: Validación de Datos
- **Tareas**: Únicas por `moodle_id`
- **Estudiantes**: Únicas por `moodle_userid` y `email`
- **Entregas**: Unique constraint `(tarea, estudiante)`
- **Parseo de fechas**: `try_parse_date()` soporta:
  - ISO: `2025-04-11T15:30:00`
  - ES: `11/04/2025`, `11-04-2025`
  - Texto: `"viernes, 11 de abril de 2025, 00:00"`
  - Fallback: `dateutil.parser.parse()`

---

## 🔧 Setup e Instalación

### Requisitos Previos
- Python 3.9+
- Django 6.0+
- SQLite3 (o PostgreSQL)
- pip

### 1. Instalación de Dependencias
```bash
cd "c:\Users\BRSolid\Desktop\Tecba 2026\Taller\Centralizador"

# Crear entorno virtual
python -m venv venv
.\venv\Scripts\activate

# Instalar dependencias
pip install django requests aiohttp beautifulsoup4 openpyxl dateutil
```

### 2. Configuración de Base de Datos
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Importar Datos Iniciales
```bash
# Desde archivos JSON existentes
python manage.py import_all_data

# O paso a paso
python manage.py import_json_to_db
python manage.py import_estudiantes_to_db
```

### 4. Iniciar Servidor
```bash
python manage.py runserver
# Accede a http://localhost:8000/web/
```

---

## 📋 Módulos Detallados

### 1️⃣ RESUMEN (Dashboard Ejecutivo)
**URL**: `/web/resumen/`

✅ **Implementado**:
- 8 tarjetas KPI con conteos desde DB
- 2 gráficos Chart.js (Doughnut + Bar)
- Parseo robusto de fechas
- Alertas resumidas en tarjeta

⏳ **Mejoras futuras**:
- Gráficos interactivos (filtrar por carrera/docente)
- Sparklines de tendencias
- Notificaciones push

---

### 2️⃣ MATERIAS
**URL**: `/web/materias/`

✅ **Implementado**:
- Lista paginable de materias desde `Materia.objects.all()`
- Datos: ID, nombre, sigla, gestion, carrera, nivel

⏳ **Pendiente**:
- Columna "Avance %" (tareas completadas / total)
- Semáforo (🟢 >70%, 🟡 40-70%, 🔴 <40%)
- Fechas de parciales desde `config_tareas.json`
- Hacer fila clickeable para ver detalles

---

### 3️⃣ DOCENTES
**URL**: `/web/docentes/`

✅ **Implementado**:
- Lista de docentes desde `Profesor.objects.all()`

⏳ **Pendiente**:
- Agregar columnas: "Materias", "Tareas registradas", "Pendientes", "% Cumplimiento"
- Hacer clickeable para ver detalle por docente
- Gráfico de carga por profesor

---

### 4️⃣ ESTUDIANTES
**URL**: `/web/estudiantes/`

✅ **Implementado**:
- Lista de estudiantes desde `Estudiante.objects.all()`

⏳ **Pendiente**:
- Columna "Carga académica" (entregas pendientes)
- Columna "Riesgo de sobrecarga" (indicador visual)
- Filtro por materia/carrera
- Link a detalle de entregas pendientes

---

### 5️⃣ ALERTAS
**URL**: `/web/alertas/`

✅ **Implementado**:
- Reglas: materias sin actividades, tareas sin cierre, sobrecarga estudiantil
- Listados detallados con IDs y nombres

⏳ **Pendiente**:
- Alertas por actividades fuera de cronograma
- Historial de alertas (timestamp)
- Exportar alertas a CSV

---

### 6️⃣ PREDICCIONES
**URL**: `/web/predicciones/`

✅ **Implementado**:
- Estructura placeholder

⏳ **Implementar**:
- **Riesgo de retraso**: Estudiantes que históricamente entregan tarde
- **Riesgo de sobrecarga**: Proyección de entregas próximas
- **Tendencias**: Gráficos de progreso por semana
- Usar `dateutil` para agrupar entregas por semana/mes

**Algoritmo propuesto**:
```python
def predict_overload(student):
    """Predice riesgo de sobrecarga basado en entregas próximas."""
    now = datetime.now().date()
    proximas = Entrega.objects.filter(
        estudiante=student,
        tarea__cierre__gte=now,
        tarea__cierre__lte=now + timedelta(days=7)
    ).count()
    
    if proximas > 3:
        return {'riesgo': 'ALTO', 'entregas_proximas': proximas}
    elif proximas > 1:
        return {'riesgo': 'MEDIO', 'entregas_proximas': proximas}
    else:
        return {'riesgo': 'BAJO', 'entregas_proximas': proximas}
```

---

### 7️⃣ REPORTES
**URL**: `/web/reportes/`

✅ **Implementado**:
- Estructura placeholder
- Integración con `exportarjson.py` (Excel generado)

⏳ **Implementar**:
- Filtros funcionales:
  - Por Docente: `Profesor.objects.get(id=X).materias.all()`
  - Por Carrera: `Carrera.objects.get(id=X).materias.all()`
  - Por Materia: `Materia.objects.get(id=X).tareas.all()`
  - Por Gestión: `Materia.objects.filter(gestion=YYYY)`
  - Por Fecha: `Entrega.objects.filter(ultima_mod_entrega__range=[start, end])`

**Propuesta de modelo**:
```python
class ReportFilter:
    docente_id = None
    carrera_id = None
    materia_id = None
    gestion = None
    fecha_inicio = None
    fecha_fin = None
```

---

### 8️⃣ CONFIGURACIÓN
**URL**: `/web/configuracion/`

✅ **Implementado**:
- Estructura placeholder

⏳ **Implementar**:
- **Categorías de tareas**: CRUD para tipos de tarea (Práctica, Quiz, Proyecto)
- **Fechas de parciales**: UI para editar `config_tareas.json`
- **Parámetros de análisis**: Thresholds para alertas (e.g., sobrecarga >8)
- **Reglas de clasificación**: Mapeo Moodle → modelos internos

---

## 🔄 Ciclo de Vida de Datos

```
[Moodle] 
   ↓ (scraping async, Semaphore(5))
[tareas.json, estudiantes.json, calificacion.json]
   ↓ (python manage.py import_all_data)
[DB: Materia, Tarea, Estudiante, Entrega]
   ↓ (queries + cálculos KPI)
[KPIs en resumen]
   ↓ (Chart.js + JSON)
[Visualizaciones en navegador]
   ↓ (Alertas, análisis, reportes)
[Decisiones académicas]
```

---

## 🛡️ Consideraciones de Seguridad

### 1. **Manejo de Cookies Moodle**
- ✅ Se almacenan SOLO en `request.session` (server-side, encriptado)
- ❌ NUNCA se persisten en DB
- ❌ NUNCA se loguean en archivos
- ✅ Se limpian al cerrar sesión

### 2. **CSRF Protection**
- ✅ Django CSRF middleware activo
- ✅ Todos los forms incluyen `{% csrf_token %}`

### 3. **Acceso a Datos**
- ⏳ Falta: Restricción por rol (docente solo ve sus materias)
- ⏳ Falta: Auditoría de acceso

### 4. **Validación de Entrada**
- ✅ Parseo de IDs con `int()`
- ✅ Try/except en importadores

---

## 📦 Estructura de Archivos Modificados

```
web/
├── urls.py ✅ (8 rutas nuevas)
├── views.py ✅ (8 vistas + helper functions)
├── templates/web/
│   ├── base.html ✅ (layout con sidebar)
│   ├── resumen.html ✅ (KPIs + Chart.js)
│   ├── alertas.html ✅ (lista detallada)
│   ├── session_recovery.html ✅ (cookie recovery UI)
│   ├── materias.html ✅ (lista)
│   ├── docentes.html ✅ (lista)
│   ├── estudiantes.html ✅ (lista)
│   ├── predicciones.html ✅ (placeholder)
│   ├── reportes.html ✅ (placeholder)
│   └── configuracion.html ✅ (placeholder)
├── static/web/
│   └── sidebar.css ✅ (grid + KPI cards)

services/
├── data_utils/
│   ├── import_to_db.py ✅
│   └── import_estudiantes_to_db.py ✅
└── management/commands/
    ├── import_json_to_db.py ✅
    ├── import_estudiantes_to_db.py ✅
    └── import_all_data.py ✅
```

---

## 🧪 Testing

### Verificar Instalación
```bash
# Contar registros
python manage.py shell
>>> from data.models import *
>>> Materia.objects.count()  # Debería ser > 0 después de import
>>> Entrega.objects.count()
```

### Verificar Vistas
```bash
# Acceder a cada módulo
GET http://localhost:8000/web/resumen/
GET http://localhost:8000/web/materias/
GET http://localhost:8000/web/alertas/
```

### Probar Recuperación de Cookie
```
1. Ir a http://localhost:8000/web/session-cookie/
2. Pegar un valor dummy en textarea
3. Click "Guardar y continuar"
4. Verificar session: request.session['MoodleSession'] existe
```

---

## 📞 Support & Troubleshooting

### Error: "ModuleNotFoundError: No module named 'django'"
```bash
pip install django
```

### Error: "No se encuentra tareas.json"
```bash
# Ejecutar extracción primero
python web/dashboard → seleccionar curso → "Normalizar"
# O cargar datos de respaldo
cp data/raw/tareas.json gatfh/tareas.json
```

### Error: "Cookie inválida para Moodle"
```
→ /web/session-cookie/?error=La%20sesión%20expiró
→ Seguir instrucciones visuales
→ Obtener nueva cookie del navegador
→ Pegar y guardar
→ Reintentar extracción manualmente
```

### Gráficos no aparecen
```
✓ Verificar que Chart.js CDN está disponible
✓ Verificar que context['chart_kpis_json'] tiene datos válidos
✓ Abrir DevTools → Console para errores JS
```

---

## 📚 Referencias

- [Django Documentation](https://docs.djangoproject.com/)
- [Chart.js](https://www.chartjs.org/)
- [Bootstrap 5](https://getbootstrap.com/docs/5.0/)
- [Moodle Web Services API](https://docs.moodle.org/401/en/Web_services_API)

---

## 📝 Notas de Desarrollo

### Próximas Prioritarias
1. **Metricas por Docente**: Agregar columnas en docentes.html
2. **Filtros en Reportes**: Implementar form + queryset dinámico
3. **ML Predicciones**: Usar regresión simple para tendencias
4. **Tiempo Real**: Considerar Channels + WebSocket para actualizaciones

### Decisiones Arquitectónicas
- ✅ Uso de ORM Django (vs SQL raw): Seguridad + mantenibilidad
- ✅ JSON files como staging (vs directo DB): Auditabilidad + reversibilidad
- ✅ Session-only cookies (vs DB): Seguridad temporal
- ❌ NO auto-retry: Simplifica debugging, requiere acción explícita

### Deuda Técnica
- [ ] Tests unitarios en `web/tests.py`
- [ ] Integración CI/CD
- [ ] Logging centralizado
- [ ] Restricción de acceso por rol

---

## 👥 Contribuyentes

- **Versión**: 1.0 (MVP)
- **Fecha**: Junio 2026
- **Arquitecto**: Senior Django Engineer

---

**Última actualización**: 2026-06-14
