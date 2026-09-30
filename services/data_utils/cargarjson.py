# pipeline/cargarjson.py
import json
from gatfh import config

def cargar_cursos():
    try:
        with open(config.JSON_CURSOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando cursos: {e}")

def cargar_tareas():
    try:
        with open(config.JSON_TAREAS, "r", encoding="utf-8") as f:
            data = json.load(f)

        print("Tareas cargadas")
        return data

    except FileNotFoundError:
        print("No existe el archivo tareas.json")
        return []

    except json.JSONDecodeError:
        print("Error: JSON corrupto")
        return []

    except Exception as e:
        raise Exception(f"Error cargando tareas: {e}")
    
def cargar_detalle():
    try:
        with open(config.JSON_DETALLES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando cursos: {e}")
    
    
def cargar_fechas():
    try:
        with open(config.JSON_CONFIG_TAREAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando fechas: {e}")
    
def cargar_normalizacion():
    try:
        with open(config.JSON_NORMALIZACION, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando normalizacion: {e}")
    
def cargar_estudiantes():
    try:
        with open(config.JSON_ESTUDIANTES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando estudiante: {e}")
    
    
def cargar_asignaciones():
    try:
        with open(config.JSON_ASIGNACION, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando estudiante: {e}")


def cargar_categorias():
    try:
        with open(config.JSON_CATEGORIAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando categorias: {e}")
    

def cargar_carreras():
    try:
        with open(config.JSON_CARRERAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error cargando estudiante: {e}")
