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
from scraping.scrapers.asignartareas import  editar_tareas_interactivamente
from scraping.scrapers.asignartareas import  generar_config_final
from scraping.scrapers.normalizar_est import transformar_estudiantes
from scraping.scrapers.carreras import extraer_categorias
from scraping.scrapers.carreras import obtener_categorias
from scraping.scrapers.carreras import  cargar_todo
from scraping.scrapers.carreras import procesar_datos


from scraping.scrapers.session import MoodleSession



from services.data_utils import cargarjson
from gatfh import config

from services.utils.timing import medir_tiempo

def scraping():
    moodle = MoodleSession()
    moodle.get()
    
    print("Scrapping OK",config.SESSKEY)

@medir_tiempo
def getsession():
    moodle = MoodleSession()
    config.SESSKEY=moodle.get_sesskey()
    print("Scrapping OK",config.SESSKEY)

@medir_tiempo
def cursos():
    moodle = MoodleSession()
    cursos=obtener_cursos(moodle)
    print("Cursos OK",cursos)
    return cursos

def tareas():
    moodle = MoodleSession()
    cursos = cargarjson.cargar_cursos()

    tareas = asyncio.run(
        obtener_tareas_async(moodle, cursos)
    )
    
    print("Tareas OK",tareas)
    return tareas

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

@medir_tiempo
def estudiantes():
    moodle = MoodleSession()

    cursos = cargarjson.cargar_cursos()
    tareas = cargarjson.cargar_tareas()

    curso_seleccionado = seleccionar_curso(cursos)

    tareas_filtradas = filtrar_tareas_por_curso(tareas, curso_seleccionado)

    estudiantes = asyncio.run(
        obtener_tareas_docente_async(moodle, tareas_filtradas)
    )
    return estudiantes


def seleccionar_curso(cursos):
    print("\n📚 Selecciona un curso:\n")

    for i, c in enumerate(cursos, 1):
        print(f"{i}. {c['asignatura']}")

    while True:
        try:
            opcion = int(input("\nIngrese el número del curso: "))
            if 1 <= opcion <= len(cursos):
                return cursos[opcion - 1]
            else:
                print("Opción inválida")
        except ValueError:
            print("Ingrese un número válido")

def filtrar_tareas_por_curso(tareas, curso):
    return [t for t in tareas if t["asignatura"] == curso["asignatura"]]

@medir_tiempo
def normalizado():
    cursos = cargarjson.cargar_cursos()
    tareas = cargarjson.cargar_tareas()

    curso_seleccionado = seleccionar_curso(cursos)

    tareas_filtradas = filtrar_tareas_por_curso(tareas, curso_seleccionado)

    normalizado =extraer_tareas_planas(tareas_filtradas)

    return normalizado

@medir_tiempo
def asignacion_tareas():
    config_base = cargarjson.cargar_fechas()
    tareas = cargarjson.cargar_normalizacion()

    asignacion = auto_asignar_tareas(tareas, config_base["rangos_parciales"])
    asignacion_ordenados=mostrar_resumen_tareas(asignacion)
    asignaciones_final = editar_tareas_interactivamente(asignacion_ordenados)
    config_final, errores = generar_config_final(asignaciones_final, config_base)
    return config_final


@medir_tiempo
def transformar_calificacion():
    estudiantes=cargarjson.cargar_estudiantes()
    notas_estudiantes=transformar_estudiantes(estudiantes)
    return notas_estudiantes

@medir_tiempo
def run_obtener_categorias():
    moodle=MoodleSession()
    pagina = obtener_categorias(moodle)
    html=extraer_categorias(pagina)
    #with open("categorias_ajax.html", "w", encoding="utf-8") as f:
    #    f.write(str(html))
    return html

@medir_tiempo
def obtener_carreras():    
    categorias=cargarjson.cargar_categorias()    
    moodle=MoodleSession()    
    html = cargar_todo(moodle,categorias)    
    return html

    #with open("categorias_ajax.html", "w", encoding="utf-8") as f:
    #    f.write(str(html))

@medir_tiempo
def obtener_Linkcarreras():    
    carreras=cargarjson.cargar_carreras() 
    html = procesar_datos(carreras)    
    return html


    
