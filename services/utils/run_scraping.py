import asyncio

from scraping.scrapers.cursos import obtener_cursos
from scraping.scrapers.tareas import obtener_tareas_async
from scraping.scrapers.detalles import obtener_detalle_tarea_async
from scraping.scrapers.calificaciones import obtener_calificaciones_async
from scraping.scrapers.profesores import obtener_profesores_async
from scraping.scrapers.detallesprofesores import obtener_tareas_docente_async
from scraping.scrapers.normalizacion import extraer_tareas_planas
from scraping.scrapers.asignartareas import  auto_asignar_tareas
from scraping.scrapers.asignartareas import  mostrar_resumen_tareas
from scraping.scrapers.asignartareas import  generar_config_final
from scraping.scrapers.normalizar_est import transformar_estudiantes
from scraping.scrapers.carreras import extraer_categorias
from scraping.scrapers.carreras import obtener_categorias
from scraping.scrapers.carreras import  cargar_todo
from scraping.scrapers.carreras import procesar_datos


from scraping.scrapers.session import MoodleSession



from services.data_utils import cargarjson, exportarjson
from services.utils import conexiondb
from gatfh import config

from services.utils.timing import medir_tiempo

def scraping():
    moodle = MoodleSession()
    moodle.get()

    print("Scrapping OK", moodle.sesskey)

@medir_tiempo
def getsession():
    moodle = MoodleSession()
    sesskey = moodle.get_sesskey()
    print("Scrapping OK", sesskey)

@medir_tiempo
def cursos():
    moodle = MoodleSession()
    cursos=obtener_cursos(moodle)
    print("Cursos OK",cursos)
    return cursos

def tareas(ids, cookie=None, stop_event=None):
    """Unico lugar donde vive la extraccion de tareas: tanto el boton web
    ("1. Extraer tareas del curso", via run_extraer_tareas_web en web/views.py) como el
    comando CLI (python manage.py extraer_tareas <id> [<id> ...]) pasan por aca, para que
    un print() puesto en esta funcion se vea sin importar desde donde se dispare.

    Extrae solo los cursos (Materia.id) que se le pasen, nunca todos: con 779 materias
    cargadas, correr esto sin filtrar intentaria extraer cursos de carreras ajenas al
    usuario (no es docente en todas) y, para un gestor con varias materias a cargo,
    tardaria muchisimo - sobre todo porque todavia no existe un boton para cancelar una
    extraccion disparada por el camino CLI (el candado de extraction_lock solo protege al
    boton web). Antes leia TODO cursos.json (data/raw/, un archivo de staging del flujo
    viejo); ahora usa conexiondb.cargar_cursos_por_id(ids), que lee Materia directo de
    Postgres, filtrado.

    `cookie`: se pasa explicito a MoodleSession, nunca se lee de config.COOKIES global
    (D1b). Si se llama sin cookie (uso CLI suelto), MoodleSession cae al fallback de
    MOODLE_SESSION_COOKIE en .env - ver el docstring de MoodleSession.__init__.
    """
    if not ids:
        raise ValueError('Debes indicar al menos un id de curso (Materia.id) para extraer sus tareas.')

    cursos = conexiondb.cargar_cursos_por_id(ids)
    print("Cursos a extraer:", cursos)
    if not cursos:
        raise ValueError(f'No se encontró ninguna Materia con esos ids: {ids}')

    moodle = MoodleSession(cookie=cookie)

    # Se conserva lo ya extraido de otros cursos y se reemplaza solo lo de los
    # seleccionados, para poder correr esta accion curso por curso sin perder el resto.
    asignaturas_seleccionadas = {c.get('asignatura') for c in cursos}
    tareas_previas = [
        t for t in cargarjson.cargar_tareas()
        if t.get('asignatura') not in asignaturas_seleccionadas
    ]

    tareas_nuevas = asyncio.run(
        obtener_tareas_async(moodle, cursos, stop_event)
    )
    detenido = stop_event is not None and stop_event.is_set()

    exportarjson.save_tareas(tareas_previas + tareas_nuevas)

    print("Tareas OK", tareas_nuevas)
    return tareas_nuevas, detenido

def detalle_tarea():
    moodle = MoodleSession()
    tareas=cargarjson.cargar_tareas()

    detalle = asyncio.run(
        obtener_detalle_tarea_async(moodle, tareas)
    )    
    print("Detalles OK",tareas)
    return detalle

def calificacion_tarea():
    moodle = MoodleSession()
    tareas=cargarjson.cargar_tareas()

    calificacion = asyncio.run(
        obtener_calificaciones_async(moodle, tareas)
    )    
    print("Detalles OK",calificacion)
    return calificacion

@medir_tiempo
def profesores():
    moodle = MoodleSession()    
    cursos = cargarjson.cargar_cursos()
    profesores = asyncio.run(
        obtener_profesores_async(moodle,cursos)
    )    
    print("Profesores OK",profesores)
    return profesores

def _cursos_seleccionados_o_falla(ids, para_que):
    """Resuelve ids de Materia -> cursos (dicts {id, asignatura, url}), o revienta con un
    mensaje claro. Nunca trae todos los cursos si `ids` viene vacio - eso es justo el bug
    que tenian estudiantes()/normalizado()/asignacion_tareas() antes de unificarse con
    tareas() (ver conexiondb.cargar_cursos())."""
    if not ids:
        raise ValueError(f'Debes indicar al menos un id de curso (Materia.id) para {para_que}.')
    cursos = conexiondb.cargar_cursos_por_id(ids)
    print("Cursos seleccionados:", cursos)
    if not cursos:
        raise ValueError(f'No se encontró ninguna Materia con esos ids: {ids}')
    return cursos


def estudiantes(ids, cookie=None, stop_event=None):
    """Unico lugar para extraer estudiantes/entregas: boton web (run_estudiantes_web en
    web/views.py) y CLI (python manage.py extraer_estudiantes <id> [<id> ...]) pasan por
    aca. Antes elegia el curso con seleccionar_curso(), un input() de consola bloqueante
    pensado para correrlo a mano uno por uno sin tener que pasarle todos los cursos - hoy
    esa seleccion se hace con ids de Materia explicitos, igual que tareas()."""
    cursos = _cursos_seleccionados_o_falla(ids, 'extraer sus estudiantes')

    asignaturas_seleccionadas = {c['asignatura'] for c in cursos}
    tareas_filtradas = [
        t for t in cargarjson.cargar_tareas()
        if t.get('asignatura') in asignaturas_seleccionadas
    ]
    if not tareas_filtradas:
        raise ValueError(
            'No se encontraron tareas para los cursos seleccionados. '
            'Corré primero "Extraer tareas del curso" para esos mismos ids.'
        )

    moodle = MoodleSession(cookie=cookie)
    estudiantes_resultado = []
    detenido = False

    for curso in tareas_filtradas:
        if stop_event is not None and stop_event.is_set():
            detenido = True
            break
        curso_estudiantes = asyncio.run(
            obtener_tareas_docente_async(moodle, [curso], stop_event)
        )
        estudiantes_resultado.extend(curso_estudiantes)

    exportarjson.save_estudiantes(estudiantes_resultado)

    print("Estudiantes OK", estudiantes_resultado)
    return estudiantes_resultado, detenido


def normalizado(ids):
    """Unico lugar para 'normalizar' (aplanar) las tareas ya extraidas de los cursos
    indicados: boton web (run_normalizado_web) y CLI (extraer_normalizado <id> ...) pasan
    por aca. Misma seleccion por ids que tareas()/estudiantes(), sin input() de consola."""
    cursos = _cursos_seleccionados_o_falla(ids, 'normalizar sus tareas')

    asignaturas_seleccionadas = {c['asignatura'] for c in cursos}
    tareas_filtradas = [
        t for t in cargarjson.cargar_tareas()
        if t.get('asignatura') in asignaturas_seleccionadas
    ]
    if not tareas_filtradas:
        raise ValueError(
            'No se encontraron tareas para los cursos seleccionados. '
            'Corré primero "Extraer tareas del curso" para esos mismos ids.'
        )

    normalizado_resultado = extraer_tareas_planas(tareas_filtradas)
    exportarjson.save_normalizacion(normalizado_resultado)

    print("Normalizado OK", normalizado_resultado)
    return normalizado_resultado


def asignacion_tareas(ids=None, config_base=None):
    """Unico lugar para la asignacion automatica de tareas a periodos/parciales: boton web
    (run_asignacion_web) y CLI (extraer_asignacion) pasan por aca. Ya no pasa por
    editar_tareas_interactivamente() (edicion manual via input(), pensada para corregir a
    mano la asignacion automatica); el ajuste de fechas/rangos se hace en
    /configuracion/ (Profesor.config_tareas, por usuario).

    `config_base`: dict {'rangos_parciales': [...], 'pesos_default': {...}}. El boton web
    pasa el de Profesor.config_tareas del usuario logueado (cada profesor tiene el suyo,
    ver data.models.Profesor.config_tareas). Si se llama sin el (CLI suelto, sin nocion de
    "usuario actual"), cae al viejo gatfh/config_tareas.json como fallback compartido."""
    if config_base is None:
        config_base = cargarjson.cargar_fechas()
    tareas = cargarjson.cargar_normalizacion()
    warning = None

    if ids:
        tareas_filtradas = [t for t in tareas if t.get('curso_id') in ids]
        if tareas_filtradas:
            tareas = tareas_filtradas
        else:
            warning = 'No se encontró curso_id en normalización; usando todos los datos disponibles.'

    print("Tareas a asignar:", tareas)

    asignacion = auto_asignar_tareas(tareas, config_base.get('rangos_parciales', []))
    asignacion_ordenados = mostrar_resumen_tareas(asignacion)
    config_final, errores = generar_config_final(asignacion_ordenados, config_base)
    exportarjson.save_asignacion(config_final)

    print("Asignación OK", config_final)
    return asignacion, errores, warning


@medir_tiempo
def transformar_calificacion():
    estudiantes=cargarjson.cargar_estudiantes()
    notas_estudiantes=transformar_estudiantes(estudiantes)
    return notas_estudiantes

@medir_tiempo
def run_obtener_categorias(cookie=None):
    """Paso 1/3 de la jerarquia de carreras: lista las categorias de Moodle
    (/course/index.php). Guarda en categorias.json. `cookie` explicito (D1b); si se llama
    sin el (CLI suelto), MoodleSession cae al fallback de MOODLE_SESSION_COOKIE en .env."""
    moodle = MoodleSession(cookie=cookie)
    pagina = obtener_categorias(moodle)
    categorias = extraer_categorias(pagina)
    exportarjson.save_categorias(categorias)
    print("Categorias OK:", categorias)
    return categorias

@medir_tiempo
def obtener_carreras(cookie=None):
    """Paso 2/3: pagina cada categoria de categorias.json y trae el HTML crudo de sus
    cursos. Guarda en carreras.json."""
    categorias = cargarjson.cargar_categorias()
    moodle = MoodleSession(cookie=cookie)
    carreras_html = cargar_todo(moodle, categorias)
    exportarjson.save_carreras(carreras_html)
    print("Carreras OK:", len(carreras_html), "categoria(s) con HTML")
    return carreras_html

@medir_tiempo
def obtener_Linkcarreras():
    """Paso 3/3: parsea el HTML de carreras.json en la jerarquia Facultad/Carrera/Nivel/
    Materia(+profesor). Guarda en linkcarreras.json. No llama a Moodle, por eso no
    necesita cookie."""
    carreras_html = cargarjson.cargar_carreras()
    linkcarreras = procesar_datos(carreras_html)
    exportarjson.save_Linkcarreras(linkcarreras)
    print("Linkcarreras OK:", linkcarreras)
    return linkcarreras


def extraer_carreras_completo(cookie=None, stop_event=None):
    """Unico lugar para la cadena completa (categorias -> carreras -> linkcarreras):
    boton web ("0. Extraer carreras", via run_extraer_carreras_web en web/views.py) y CLI
    pasan por aca. Encadena los 3 pasos de arriba, cada uno con su propia responsabilidad
    (y su propio comando CLI suelto si se los quiere correr por separado:
    extraer_categorias / extraer_carreras / extraer_linkcarreras).

    No soporta cancelacion a mitad de camino (stop_event no se revisa entre categorias
    dentro de cargar_todo): son ~7 facultades, bastante mas rapido que extraer
    tareas/estudiantes."""
    categorias = run_obtener_categorias(cookie=cookie)
    carreras_html = obtener_carreras(cookie=cookie)
    linkcarreras = obtener_Linkcarreras()
    return categorias, carreras_html, linkcarreras


    
