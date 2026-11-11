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
    """Algunos recursos ("Mostrar: Automático") redirigen directo al archivo en vez de a
    una pagina HTML intermedia - .text() sobre un PDF/imagen/etc. revienta con
    UnicodeDecodeError porque ni es texto ni esta en UTF-8 (encontrado 2026-11-10,
    intentando bajar el detalle de un curso con /mod/resource/ en modo automatico). Se
    detecta por content-type antes de decodificar, y se deja una nota en vez de la pagina -
    no hay HTML real que guardar, pero tampoco se quiere que la descarga entera se corte por
    una sola URL."""
    async with semaphore:
        async with session.get(url) as resp:
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
            tipo_contenido = resp.content_type or ''
            es_texto = tipo_contenido.startswith('text/') or 'html' in tipo_contenido or 'xml' in tipo_contenido
            if not es_texto:
                return f"<!-- No es una página HTML: content-type={tipo_contenido!r}, url={url} -->"
            try:
                return await resp.text()
            except UnicodeDecodeError:
                return await resp.text(errors='replace')


def _nombre_archivo(*partes):
    """Nombre de archivo seguro para el .zip a partir de textos libres (nombre de
    materia/tarea, que puede traer "/", espacios, acentos, etc.)."""
    texto = "_".join(str(p) for p in partes if p)
    texto = re.sub(r"[^\w.-]+", "_", texto).strip("_")
    return f"{texto[:150]}.html"


def _tareas_filtradas_por_materia(ids, tipos=None):
    """Mismo armado que run_scraping.detalle_tarea()/estudiantes(): Tarea de los cursos
    seleccionados, agrupada por materia/unidad. `tipos=None` trae todas (assign, url,
    resource, lo que haya) - para "2. Detalle de tareas" interesa ver TODO lo que un docente
    puede subir como material, no solo las assign (unica que filtraba antes)."""
    qs = Tarea.objects.filter(unidad__materia_id__in=ids)
    if tipos:
        qs = qs.filter(tipo__in=tipos)
    tareas_qs = qs.select_related('unidad__materia').order_by('unidad__materia_id', 'unidad_id')
    por_materia = {}
    for t in tareas_qs:
        materia = t.unidad.materia
        entrada = por_materia.setdefault(materia.id, {'asignatura': materia.moodle_nombre, 'tareas': {}})
        unidad_entrada = entrada['tareas'].setdefault(t.unidad_id, {'unidad': t.unidad.nombre, 'contenido': []})
        unidad_entrada['contenido'].append({'Titulo': t.titulo, 'url': t.url, 'tipo': t.tipo})
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
    """`&action=editsubmission` solo existe (y da permiso) para tareas tipo 'assign' - el
    resto (url, resource, lo que sea) se pide tal cual, con su URL normal de "ver la
    actividad"."""
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for t in tareas_filtradas:
            if stop_event is not None and stop_event.is_set():
                break
            for t0 in t['tareas']:
                for t1 in t0['contenido']:
                    tipo = t1.get('tipo') or 'assign'
                    url = t1["url"] + "&action=editsubmission" if tipo == 'assign' else t1["url"]
                    nombre = _nombre_archivo(t["asignatura"], t0["unidad"], t1["Titulo"], tipo)
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


def _tareas_o_falla(ids, tipos=None):
    tareas_filtradas = _tareas_filtradas_por_materia(ids, tipos=tipos)
    if not tareas_filtradas:
        detalle_tipos = f' (tipo {", ".join(tipos)})' if tipos else ''
        raise ValueError(
            f'No se encontraron tareas{detalle_tipos} importadas para los cursos '
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
    """Paginas que visita '2. Extraer detalle de tareas' - PERO sin limitarse a tipo
    assign: trae tambien url/resource/etc, para revisar como luce cada tipo de material
    (ej. el link de Drive adentro de un recurso tipo url) antes de decidir como extraerlo."""
    tareas_filtradas = _tareas_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_detalle(moodle, tareas_filtradas, stop_event))


def descargar_html_estudiantes(ids, cookie=None, stop_event=None):
    """Paginas que visita '3. Extraer estudiantes': la planilla de calificacion (primera
    pagina) de cada tarea tipo assign - la misma que detallesprofesores.py parsea."""
    tareas_filtradas = _tareas_o_falla(ids, tipos=['assign'])
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_grading(moodle, tareas_filtradas, stop_event))


def descargar_html_ultimo_acceso(ids, cookie=None, stop_event=None):
    """Paginas que visita '4. Extraer ultimo acceso': la tabla de participantes (primera
    pagina) de cada curso."""
    cursos = _cursos_o_falla(ids)
    moodle = MoodleSession(cookie=cookie)
    return asyncio.run(_descargar_participantes(moodle, cursos, stop_event))
