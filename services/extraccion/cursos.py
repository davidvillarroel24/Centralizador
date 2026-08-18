import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_cursos():
    cursos=run_scraping.cursos()
    exportarjson.save_cursos(cursos)
