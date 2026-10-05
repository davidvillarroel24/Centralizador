from services.utils import run_scraping


def extraer_carreras(cookie=None):
    # run_scraping.obtener_carreras() ya guarda en carreras.json.
    return run_scraping.obtener_carreras(cookie=cookie)
