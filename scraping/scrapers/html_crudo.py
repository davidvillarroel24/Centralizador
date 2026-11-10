"""Descarga el HTML crudo de Moodle que cada extraccion visitaria, SIN parsear ni importar
nada - ni un archivo json, ni la base de datos. Pensado para cuando la pagina real no
coincide con lo que el parser espera (ej. el bug de columnas del Decano en
detallesprofesores.py, confirmado 2026-11-08: sin esto, para ver la tabla real hacia falta
pedirle a alguien con esa cuenta que probara en vivo y describiera lo que veia). Un
administrador lo usa para bajar un .zip con esas paginas y revisarlas directamente.

No persigue paginacion completa (la planilla de calificacion o la de participantes pueden
traer varias paginas): alcanza con la primera pagina de cada una para ver la estructura
real de columnas, que es lo unico que este debug necesita.
"""
import re

import aiohttp
import asyncio

from .session import MoodleSession
from .tareas import SesionExpiradaError, detectar_num_secciones
from .participantes import PERPAGE_MINIMO
from services.utils import conexiondb
from data.models import Tarea

CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def _fetch(session, url, semaphore):
    async with semaphore:
        async with session.get(url) as resp:
            text = await resp.text()
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
            return text


def _nombre_archivo(*partes):
    """Nombre de archivo seguro para el .zip a partir de textos libres (nombre de
    materia/tarea, que puede traer "/", espacios, acentos, etc.)."""
    texto = "_".join(str(p) for p in partes if p)
    texto = re.sub(r"[^\w.-]+", "_", texto).strip("_")
    return f"{texto[:150]}.html"


def _tareas_filtradas_por_materia(ids):
    """Mismo armado que run_scraping.detalle_tarea()/estudiantes(): Tarea tipo 'assign' de
    los cursos seleccionados, agrupada por materia/unidad."""
    tareas_qs = (
        Tarea.objects.filter(tipo='assign', unidad__materia_id__in=ids)
        .select_related('unidad__materia')
        .order_by('unidad__materia_id', 'unidad_id')
    )
    por_materia = {}
    for t in tareas_qs:
        materia = t.unidad.materia
        entrada = por_materia.setdefault(materia.id, {'asignatura': materia.moodle_nombre, 'tareas': {}})
        unidad_entrada = entrada['tareas'].setdefault(t.unidad_id, {'unidad': t.unidad.nombre, 'contenido': []})
        unidad_entrada['contenido'].append({'Titulo': t.titulo, 'url': t.url})
    return [
        {'asignatura': e['asignatura'], 'tareas': list(e['tareas'].values())}
        for e in por_materia.values()
    ]


async def _descargar_tareas(moodle, cursos, stop_event=None):
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for c in cursos:
            if stop_event is not None and stop_event.is_set():
                break
            course_url = c["url"]
            asignatura = c["asignatura"]
            paginas[_nombre_archivo(asignatura, "curso")] = await _fetch(session, course_url, semaphore)
            num_secciones = await detectar_num_secciones(session, course_url)
            for n in range(1, num_secciones + 1):
                if stop_event is not None and stop_event.is_set():
                    break
                paginas[_nombre_archivo(asignatura, "seccion", n)] = await _fetch(
                    session, f"{course_url}&section={n}", semaphore
                )
    return paginas


async def _descargar_detalle(moodle, tareas_filtradas, stop_event=None):
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for t in tareas_filtradas:
            if stop_event is not None and stop_event.is_set():
                break
            for t0 in t['tareas']:
                for t1 in t0['contenido']:
                    url = t1["url"] + "&action=editsubmission"
                    nombre = _nombre_archivo(t["asignatura"], t0["unidad"], t1["Titulo"])
                    paginas[nombre] = await _fetch(session, url, semaphore)
    return paginas


async def _descargar_grading(moodle, tareas_filtradas, stop_event=None):
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for t in tareas_filtradas:
            if stop_event is not None and stop_event.is_set():
                break
            for t0 in t['tareas']:
                for t1 in t0['contenido']:
                    if "/assign/view" not in t1["url"]:
                        continue
                    url = t1["url"] + "&action=grading&perpage=100"
                    nombre = _nombre_archivo(t["asignatura"], t0["unidad"], t1["Titulo"], "planilla")
                    paginas[nombre] = await _fetch(session, url, semaphore)
    return paginas


async def _descargar_participantes(moodle, cursos, stop_event=None):
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for c in cursos:
            if stop_event is not None and stop_event.is_set():
                break
            m = re.search(r"[?&]id=(\d+)", c.get("url", ""))
            if not m:
                continue
            moodle_course_id = m.group(1)
            url = f"{moodle.base_url}/user/index.php?id={moodle_course_id}&perpage={PERPAGE_MINIMO}"
            nombre = _nombre_archivo(c.get("asignatura"), "participantes")
            paginas[nombre] = await _fetch(session, url, semaphore)
    return paginas


def _cursos_o_falla(ids):
    cursos = conexiondb.cargar_cursos_por_id(ids)
    if not cursos:
        raise ValueError(f'No se encontró ninguna Materia con esos ids: {ids}')
    return cursos


def _tareas_o_falla(ids):
    tareas_filtradas = _tareas_filtradas_por_materia(ids)
    if not tareas_filtradas:
        raise ValueError(
            'No se encontraron tareas (tipo assign) importadas para los cursos '
            'seleccionados. Corré primero "1. Extraer, asignar e importar tareas" para '
            'esos mismos cursos.'
        )
    return tareas_filtradas


def descargar_html_tareas(ids, cookie=None, stop_event=None):
    """Paginas que visita '1. Extraer tareas': la pagina del curso y cada seccion."""
    cursos = _cursos_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_tareas(moodle, cursos, stop_event))


def descargar_html_detalle(ids, cookie=None, stop_event=None):
    """Paginas que visita '2. Extraer detalle de tareas': una por tarea tipo assign."""
    tareas_filtradas = _tareas_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_detalle(moodle, tareas_filtradas, stop_event))


def descargar_html_estudiantes(ids, cookie=None, stop_event=None):
    """Paginas que visita '3. Extraer estudiantes': la planilla de calificacion (primera
    pagina) de cada tarea tipo assign - la misma que detallesprofesores.py parsea."""
    tareas_filtradas = _tareas_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_grading(moodle, tareas_filtradas, stop_event))


def descargar_html_ultimo_acceso(ids, cookie=None, stop_event=None):
    """Paginas que visita '4. Extraer ultimo acceso': la tabla de participantes (primera
    pagina) de cada curso."""
    cursos = _cursos_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_participantes(moodle, cursos, stop_event))
