import json
from gatfh import config

def save_cursos(cursos):
    try:
        with open(config.JSON_CURSOS, "w", encoding="utf-8") as f:
            json.dump(cursos, f, indent=4, ensure_ascii=False)

        print("Cursos guardados en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")

def save_fechas(config_tareas):
    try:
        with open(config.JSON_CONFIG_TAREAS, "w", encoding="utf-8") as f:
            json.dump(config_tareas, f, indent=4, ensure_ascii=False)

        print("Config de parciales/pesos guardada")
    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")

def save_tareas(tareas):
    try:
        with open(config.JSON_TAREAS, "w", encoding="utf-8") as f:
            json.dump(tareas, f, indent=4, ensure_ascii=False)

        print("Tareas guardadas")
    except Exception as e:
        raise Exception(f"No se pudo guardar tareas: {e}")
    
def save_detalles(detalles):
    try:
        if not detalles:
            print("No hay detalles para guardar")
            return

        with open(config.JSON_DETALLES, "w", encoding="utf-8") as f:
            json.dump(detalles, f, indent=4, ensure_ascii=False)

        print(f"Detalles guardados ({len(detalles)} registros)")

    except Exception as e:
        raise Exception(f"No se pudo guardar detalles: {e}")

def save_calificacion(calificacion):
    try:
        if not calificacion:
            print("No hay calificaciones para guardar")
            return

        with open(config.JSON_CALIFICACION, "w", encoding="utf-8") as f:
            json.dump(calificacion, f, indent=4, ensure_ascii=False)

        print(f"Calificaciones guardados ({len(calificacion)} registros)")

    except Exception as e:
        raise Exception(f"No se pudo guardar calificaciones: {e}")

def save_profesores(profesores):
    try:
        if not profesores:
            print("No hay profesores para guardar")
            return

        with open(config.JSON_PROFESORES, "w", encoding="utf-8") as f:
            json.dump(profesores, f, indent=4, ensure_ascii=False)

        print(f"Profesores guardados ({len(profesores)} registros)")

    except Exception as e:
        raise Exception(f"No se pudo guardar profesores: {e}")
    
def save_estudiantes(estudiantes):
    try:
        if not estudiantes:
            print("No hay estudiantes para guardar")
            return

        with open(config.JSON_ESTUDIANTES, "w", encoding="utf-8") as f:
            json.dump(estudiantes, f, indent=4, ensure_ascii=False)

        print(f"Estudiantes guardados ({len(estudiantes)} registros)")

    except Exception as e:
        raise Exception(f"No se pudo guardar estudiantes: {e}")
    
def save_sesskey(sesskey):
    try:
        with open(config.JSON_AJAX, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Ajax guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
    
def save_normalizacion(sesskey):
    try:
        with open(config.JSON_NORMALIZACION, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Normalizacion guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
    
def save_asignacion(sesskey):
    try:
        with open(config.JSON_ASIGNACION, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Asignacion de tareas guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")

def save_notas_est(sesskey):
    try:
        with open(config.JSON_NOTAS_EST, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Notas de tareas guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
    
def save_categorias(sesskey):
    try:
        with open(config.JSON_CATEGORIAS, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Categorias guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
    
def save_carreras(sesskey):
    try:
        with open(config.JSON_CARRERAS, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Carreras guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
    
def save_Linkcarreras(sesskey):
    try:
        with open(config.JSON_LINKCARRERAS, "w", encoding="utf-8") as f:
            json.dump(sesskey, f, indent=4, ensure_ascii=False)

        print("Carreras guardado en JSON")

    except Exception as e:
        raise Exception(f"No se pudo guardar: {e}")
