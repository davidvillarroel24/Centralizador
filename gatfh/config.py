import os
from dotenv import load_dotenv

# Carpeta base del proyecto (moodle_app)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Carpeta donde se guardan CSV y BD
DATA_DIR = os.path.join(BASE_DIR, "data\\raw")
CONFIG_DIR = os.path.join(BASE_DIR, "gatfh")

# Asegurar que la carpeta exista
os.makedirs(DATA_DIR, exist_ok=True)

# Archivos CSV
CSV_CURSOS = os.path.join(DATA_DIR, "cursos.csv")
CSV_DETALLES = os.path.join(DATA_DIR, "detalles.csv")
CSV_PROFESORES = os.path.join(DATA_DIR, "profesores.csv")
CSV_CALIFICACIONES = os.path.join(DATA_DIR, "calificaciones.csv")
CSV_TAREAS = os.path.join(DATA_DIR, "tareas.csv")
CSV_UNIDADES = os.path.join(DATA_DIR, "unidades.csv")
CSV_ARCHIVOS_DETALLES = os.path.join(DATA_DIR, "archivos_detalles.csv")
CSV_ARCHIVOS_CALIFICACIONES = os.path.join(DATA_DIR, "archivos_calificaciones.csv")
CSV_TAREAS_DOCENTES = os.path.join(DATA_DIR, "tareas_docente.csv")
CSV_ESTUDIANTES = os.path.join(DATA_DIR, "estudiantes.csv")

# Archivos JSON
JSON_SESSKEY= os.path.join(CONFIG_DIR, "config_runtime.json")

JSON_CURSOS = os.path.join(DATA_DIR, "cursos.json")
JSON_TAREAS = os.path.join(DATA_DIR, "tareas.json")
JSON_DETALLES= os.path.join(DATA_DIR, "detalle.json")
JSON_CALIFICACION= os.path.join(DATA_DIR, "calificacion.json")
JSON_PROFESORES= os.path.join(DATA_DIR, "profesores.json")
JSON_ESTUDIANTES= os.path.join(DATA_DIR, "estudiantes.json")
JSON_NORMALIZACION= os.path.join(DATA_DIR, "normalizacion.json")
JSON_ASIGNACION= os.path.join(DATA_DIR, "asignacion.json")
JSON_NOTAS_EST= os.path.join(DATA_DIR, "notas_est.json")
JSON_CATEGORIAS= os.path.join(DATA_DIR, "categorias.json")
JSON_CARRERAS= os.path.join(DATA_DIR, "carreras.json")
JSON_LINKCARRERAS= os.path.join(DATA_DIR, "linkcarreras.json")

JSON_AJAX= os.path.join(CONFIG_DIR, "sesskey.json")
JSON_CONFIG_TAREAS=os.path.join(CONFIG_DIR, "config_tareas.json")

# Base de datos SQLite
DB_PATH = os.path.join(DATA_DIR, "moodle_relacional.db")

# Base URL
BASE_URL = os.environ.get("MOODLE_BASE_URL", "https://moodle-108854-0.cloudclusters.net")

# Cookie de sesion activa (temporal, hasta que las credenciales se guarden por usuario
# en la base de datos - ver PLAN_DESARROLLO.md seccion 5). Se lee desde .env, nunca
# se hardcodea un valor real aqui.
COOKIES = {
    "MoodleSession": os.environ.get("MOODLE_SESSION_COOKIE", "")
}

# Este valor se actualizará dinámicamente
SESSKEY = None
