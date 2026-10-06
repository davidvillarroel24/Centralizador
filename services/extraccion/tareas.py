from services.utils import run_scraping


def extraer_tareas(ids, profesor_id=None):
    # run_scraping.tareas() ya guarda en tareas.json (fusionado con lo de otros cursos
    # del mismo profesor_id, o descartado si pertenece a otro); no volver a llamar
    # exportarjson.save_tareas() aca, pisaria ese merge.
    tareas_nuevas, detenido = run_scraping.tareas(ids, profesor_id=profesor_id)
    return tareas_nuevas, detenido
