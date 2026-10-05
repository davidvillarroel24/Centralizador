from services.utils import run_scraping


def extraer_tareas(ids):
    # run_scraping.tareas() ya guarda en tareas.json (fusionado con lo de otros cursos);
    # no volver a llamar exportarjson.save_tareas() aca, pisaria ese merge.
    tareas_nuevas, detenido = run_scraping.tareas(ids)
    return tareas_nuevas, detenido
