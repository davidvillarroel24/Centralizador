from services.utils import run_scraping


def extraer_estudiantes(ids, profesor_id=None):
    # run_scraping.estudiantes() ya guarda en estudiantes.json; no volver a guardar aca.
    # Exige profesor_id con PesosCategorias guardado (candado de validacion previa).
    return run_scraping.estudiantes(ids, profesor_id=profesor_id)
