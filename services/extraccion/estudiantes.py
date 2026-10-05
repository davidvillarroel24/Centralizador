from services.utils import run_scraping


def extraer_estudiantes(ids):
    # run_scraping.estudiantes() ya guarda en estudiantes.json; no volver a guardar aca.
    return run_scraping.estudiantes(ids)
