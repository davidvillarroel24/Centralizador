import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_detalle():
    detalle=run_scraping.detalle_tarea()
    exportarjson.save_detalles(detalle)
    
