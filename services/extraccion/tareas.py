import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_tareas():
    tareas =run_scraping.tareas()
    exportarjson.save_tareas(tareas)
