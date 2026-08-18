import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_carreras():                
    carreras=run_scraping.obtener_carreras()   
    exportarjson.save_carreras(carreras)
