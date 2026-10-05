from services.utils import run_scraping


def extract_categorias(cookie=None):
    # run_scraping.run_obtener_categorias() ya guarda en categorias.json.
    return run_scraping.run_obtener_categorias(cookie=cookie)
