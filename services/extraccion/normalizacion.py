import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_normalizado():
    normalizado=run_scraping.normalizado()
    exportarjson.save_normalizacion(normalizado)
