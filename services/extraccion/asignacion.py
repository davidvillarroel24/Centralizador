from services.utils import run_scraping


def extraer_asignacion(ids=None):
    # run_scraping.asignacion_tareas() ya guarda en asignacion.json; no volver a guardar aca.
    return run_scraping.asignacion_tareas(ids)
