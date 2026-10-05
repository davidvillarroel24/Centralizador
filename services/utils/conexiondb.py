"""Reemplazo de services/data_utils/cargarjson para los datos que ya viven en Postgres.

cargarjson.cargar_cursos() lee data/raw/cursos.json, un archivo de staging que viene del
flujo viejo (scraping --cursos -> JSON) y que hoy está desactualizado o ni existe: los
cursos reales ya se cargan a la tabla Materia vía "0. Extraer carreras" + los botones de
importación (ver README §3.1). Las funciones de acá devuelven la misma forma de dict
({'id', 'asignatura', 'url'}) que cargarjson.cargar_cursos() y que load_courses() en
web/views.py, para poder enchufarse donde antes se usaba el JSON sin tocar el resto del
pipeline.
"""

from data.models import Materia


def cargar_cursos():
    """Todas las materias cargadas en la base (hoy, 779). Sirve para LISTAR/elegir
    cursos (por ejemplo para mostrar IDs disponibles en un comando CLI) - NO USAR esto
    para disparar una extraccion real contra Moodle: un usuario no es docente en todas
    las carreras, y un gestor con varias materias a cargo tardaria muchisimo si esto
    arranca una extraccion de los 779 cursos de una. Para extraer, usar siempre
    cargar_cursos_por_id(ids) con los cursos que el usuario selecciono de verdad."""
    return [
        {
            'id': materia.id,
            'asignatura': materia.moodle_nombre,
            'url': materia.moodle_url,
        }
        for materia in Materia.objects.order_by('nombre')
    ]


def cargar_cursos_por_id(ids):
    """Igual que cargar_cursos(), filtrado por una lista de Materia.id. Pensado para
    cuando el llamador (CLI o vista) ya sabe qué cursos quiere, en vez de traer todos."""
    if not ids:
        return []
    return [
        {
            'id': materia.id,
            'asignatura': materia.moodle_nombre,
            'url': materia.moodle_url,
        }
        for materia in Materia.objects.filter(id__in=ids).order_by('nombre')
    ]
