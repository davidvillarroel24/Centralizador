import asyncio
from services.utils import run_scraping
from services.data_utils import run_export
from services.data_utils  import exportarjson

def extraer_transformar():
    notas_est=run_scraping.transformar_calificacion()   
    exportarjson.save_notas_est(notas_est)
    run_export.generar_excel(notas_est)
