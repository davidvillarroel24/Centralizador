import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson


def extract_categorias():
    categorias=run_scraping.run_obtener_categorias()   
    exportarjson.save_categorias(categorias)
