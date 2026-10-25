from services.utils import run_scraping


def extraer_detalle(ids):
    # run_scraping.detalle_tarea() ya guarda en detalle.json; no volver a guardar aca.
    return run_scraping.detalle_tarea(ids)

