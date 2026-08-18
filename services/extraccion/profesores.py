import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_profesores():
    profesores=run_scraping.profesores()
    exportarjson.save_profesores(profesores)
