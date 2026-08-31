# 🚀 QUICKSTART - Centralizador Académico

**Duración estimada**: 10 minutos  
**Requisitos**: Python 3.9+, pip, SQLite3

---

## 1️⃣ Clonar / Posicionarse en el Proyecto

```powershell
cd "c:\Users\BRSolid\Desktop\Tecba 2026\Taller\Centralizador"
```

---

## 2️⃣ Crear Entorno Virtual e Instalar Dependencias

```powershell
# Crear entorno
python -m venv venv

# Activar
.\venv\Scripts\activate

# Instalar dependencias
pip install django requests aiohttp beautifulsoup4 openpyxl python-dateutil
```

---

## 3️⃣ Preparar Base de Datos

```powershell
# Crear migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate
```

---

## 4️⃣ Importar Datos desde JSON

```powershell
# Opción A: Importar todo de una vez
python manage.py import_all_data

# Opción B: Importar por etapas
python manage.py import_json_to_db
python manage.py import_estudiantes_to_db
```

**Salida esperada**:
```
Importando tareas desde JSON...
✓ Tareas: {'materias': 12, 'unidades': 45, 'tareas': 234, 'skipped': 0}
Importando estudiantes y entregas desde JSON...
✓ Estudiantes/Entregas: {'estudiantes': 245, 'entregas': 1234, 'skipped': 0, 'updated': 5}
✅ Importación completada exitosamente
```

---

## 5️⃣ Iniciar Servidor

```powershell
python manage.py runserver
```

**Salida esperada**:
```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

---

## 6️⃣ Acceder a la Plataforma

Abre tu navegador en:

```
http://localhost:8000/web/
```

### Navegación por módulos:

| Módulo | URL | Descripción |
|--------|-----|-------------|
| 🏠 Resumen | `/web/resumen/` | Dashboard con KPIs y gráficos |
| 📚 Materias | `/web/materias/` | Lista de materias monitoreadas |
| 👨‍🏫 Docentes | `/web/docentes/` | Lista de docentes |
| 👨‍🎓 Estudiantes | `/web/estudiantes/` | Lista de estudiantes |
| ⚠️ Alertas | `/web/alertas/` | Alertas académicas activas |
| 📈 Predicciones | `/web/predicciones/` | Análisis predictivo (ML) |
| 📄 Reportes | `/web/reportes/` | Generación y filtrado de reportes |
| ⚙️ Configuración | `/web/configuracion/` | Parámetros del sistema |

---

## 🔐 Recuperar Sesión (Si falla la extracción)

1. **Ir a**: `http://localhost:8000/web/session-cookie/`

2. **Seguir instrucciones**:
   - Abre Moodle en el navegador
   - Presiona `F12`
   - Ve a `Application` → `Cookies`
   - Busca `MoodleSession`
   - Copia el valor

3. **Pegar en el formulario** y click `Guardar y continuar`

4. **Reintentar manualmente** tu operación anterior

---

## 📊 Verificar Datos Importados

```powershell
# Abrir shell de Django
python manage.py shell

# Contar registros
>>> from data.models import *
>>> print(f"Materias: {Materia.objects.count()}")
>>> print(f"Docentes: {Profesor.objects.count()}")
>>> print(f"Estudiantes: {Estudiante.objects.count()}")
>>> print(f"Tareas: {Tarea.objects.count()}")
>>> print(f"Entregas: {Entrega.objects.count()}")
>>> exit()
```

**Salida esperada**:
```
Materias: 12
Docentes: 8
Estudiantes: 245
Tareas: 234
Entregas: 1234
```

---

## 🧪 Verificar Vistas

```powershell
python manage.py runserver 0.0.0.0:8000
```

Luego visita cada URL en tu navegador:

```bash
# Resumen con KPIs
curl http://localhost:8000/web/resumen/

# Alertas
curl http://localhost:8000/web/alertas/

# Materias
curl http://localhost:8000/web/materias/
```

---

## 🐛 Troubleshooting

### ❌ Error: "No such table"
```powershell
python manage.py migrate --run-syncdb
```

### ❌ Error: "ImportError: No module named 'django'"
```powershell
pip install -r requirements.txt
# O instalar manualmente:
pip install django requests aiohttp beautifulsoup4 openpyxl python-dateutil
```

### ❌ Error: "No se encuentra tareas.json"
```powershell
# Verificar que el archivo existe:
Test-Path "data\raw\tareas.json"

# Si no existe, crear con datos mínimos
Copy-Item "data\raw\tareas.json.backup" "data\raw\tareas.json"
```

### ❌ Gráficos no aparecen en Resumen
```
→ Abrir DevTools (F12)
→ Console tab
→ Buscar errores de Chart.js
→ Verificar que CDN está disponible: https://cdn.jsdelivr.net/npm/chart.js
```

---

## 📋 Flujo de Extracción (Dashboard)

1. **Ir a**: `http://localhost:8000/web/` (dashboard)

2. **Seleccionar cursos** a procesar

3. **Elegir acción**:
   - ✅ Normalizar tareas
   - ✅ Asignar parciales
   - ✅ Extraer estudiantes
   - ✅ Transformar a Excel

4. **Si falla**: Se redirige a `/web/session-cookie/` automáticamente

5. **Pegar cookie** y reintentar

---

## 📈 Próximos Pasos (Después de Setup)

### Para Docentes:
- [ ] Ver dashboard de resumen
- [ ] Revisar alertas por materia
- [ ] Explorar lista de estudiantes

### Para Administradores:
- [ ] Revisar parámetros de configuración
- [ ] Ejecutar importaciones de datos
- [ ] Generar reportes en Excel

### Para Desarrolladores:
- [ ] Revisar `README.md` para arquitectura completa
- [ ] Leer `TAREAS_COMPLETADAS.md` para estado del proyecto
- [ ] Implementar mejoras de Fase 2 (enriquecimiento de vistas)

---

## 📞 Ayuda Rápida

| Problema | Solución |
|----------|----------|
| Servidor no inicia | Verificar puerto 8000 disponible: `netstat -ano \| findstr :8000` |
| Datos no importan | Ejecutar `import_all_data` nuevamente |
| Cookie no funciona | Obtener nueva de Moodle y pegar en `/session-cookie/` |
| Gráficos vacíos | Asegurar que `Tarea.objects.count() > 0` |
| Alertas no aparecen | Verificar que hay datos en DB antes de acceder a `/alertas/` |

---

## 🎉 ¡Listo!

Una vez completados estos pasos, tienes una plataforma de monitoreo académico completamente funcional. 

**Explora cada módulo y revisa el README para detalles arquitectónicos.**

---

**Última actualización**: 2026-06-14
