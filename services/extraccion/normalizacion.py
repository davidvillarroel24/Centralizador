from services.utils import run_scraping


def extraer_normalizado(ids):
    # run_scraping.normalizado() ya guarda en normalizacion.json; no volver a guardar aca.
    return run_scraping.normalizado(ids)
