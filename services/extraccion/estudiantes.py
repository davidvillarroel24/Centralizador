import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_estudiantes():
    estudiantes=run_scraping.estudiantes()
    exportarjson.save_estudiantes(estudiantes)
