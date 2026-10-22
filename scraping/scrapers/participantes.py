#Extrae el padron de inscritos (estudiantes y profesores) de un curso, con su ultimo
#acceso, via /user/index.php?id=<curso> - a diferencia de obtener_tareas_docente_async
#(detallesprofesores.py), que solo ve a quien entrego ALGO en una tarea, esto trae a
#TODOS los inscritos, incluyendo a quien nunca entrego nada.
import re

import aiohttp
import asyncio
from bs4 import BeautifulSoup

from .tareas import SesionExpiradaError

semaphore = asyncio.Semaphore(5)
CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Piso acordado: de sobra para cualquier curso de TECBA, sin inflar el HTML de mas (Moodle
# arma la lista de accesibilidad aria-controls de cada encabezado con este numero, no con
# la cantidad real de filas - pedir de mas solo hincha el archivo sin necesidad). Un admin
# puede subirlo si hiciera falta, pero nunca baja de esto.
PERPAGE_MINIMO = 300


def _mapear_columnas(soup):
    """{indice_c: texto_header} a partir de <th class="header cN"> - las columnas reales
    cambian segun el permiso de quien tiene la cookie (ver conversacion: un profesor sin
    permiso de edicion ve menos columnas que uno con permiso completo), asi que no se
    puede asumir un indice fijo."""
    columnas = {}
    for th in soup.select('table#participants thead th[class*="header c"]'):
        m = re.search(r"\bc(\d+)\b", " ".join(th.get("class", [])))
        if not m:
            continue
        columnas[int(m.group(1))] = th.get_text(" ", strip=True).lower()
    return columnas


def _encontrar_indice(columnas, *palabras_clave):
    for indice, texto in columnas.items():
        if any(p in texto for p in palabras_clave):
            return indice
    return None


def parsear_participantes(html, materia_id):
    """Una fila de la tabla -> un dict. Campos opcionales (roles, ultimo_acceso, fechas de
    matricula) quedan en None/[] cuando la cuenta que extrajo no tiene permiso para verlos
    - confirmado con cursos reales que algunas cuentas ven una tabla reducida."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="participants")
    if not tabla:
        return []

    columnas = _mapear_columnas(soup)
    col_roles = _encontrar_indice(columnas, "rol")
    col_acceso = _encontrar_indice(columnas, "último acceso", "ultimo acceso")

    participantes = []
    cuerpo = tabla.find("tbody")
    if not cuerpo:
        return []

    for fila in cuerpo.find_all("tr", recursive=False):
        link_usuario = fila.select_one('th a[href*="/user/view.php"]')
        if not link_usuario:
            continue
        m = re.search(r"[?&]id=(\d+)", link_usuario.get("href", ""))
        if not m:
            continue
        moodle_userid = int(m.group(1))
        nombre = link_usuario.get_text(strip=True)

        email = None
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", fila.get_text(" "))
        if email_match:
            email = email_match.group(0)

        roles = []
        widget_rol = fila.select_one('span[data-itemtype="user_roles"]')
        if widget_rol:
            enlace = widget_rol.select_one("a.quickeditlink")
            if enlace:
                roles = [t.strip() for t in enlace.get_text("\n").split("\n") if t.strip()]
        elif col_roles is not None:
            celda = fila.select_one(f"td.cell.c{col_roles}")
            if celda:
                roles = [t.strip() for t in celda.get_text(",").split(",") if t.strip()]

        ultimo_acceso = None
        if col_acceso is not None:
            celda = fila.select_one(f"td.cell.c{col_acceso}")
            if celda:
                ultimo_acceso = celda.get_text(strip=True)

        fecha_inicio_matricula = None
        fecha_matriculacion = None
        div_estatus = fila.select_one("div[data-timestart]")
        if div_estatus:
            fecha_inicio_matricula = div_estatus.get("data-timestart") or None
            fecha_matriculacion = div_estatus.get("data-timeenrolled") or None

        participantes.append({
            "materia_id": materia_id,
            "moodle_userid": moodle_userid,
            "nombre": nombre,
            "email": email,
            "roles": roles,
            "ultimo_acceso": ultimo_acceso,
            "fecha_inicio_matricula": fecha_inicio_matricula,
            "fecha_matriculacion": fecha_matriculacion,
        })

    return participantes


def _buscar_siguiente_pagina(html):
    """Links reales de paginacion (page=N en un <a class="page-link">), descartando la
    barra A-Z de nombres (tifirst=/tilast=, que tambien usa class="page-link"). Con
    perpage >= PERPAGE_MINIMO no deberia aparecer nunca en TECBA, pero si algun curso
    tiene mas inscritos que eso, esto trae el resto."""
    soup = BeautifulSoup(html, "html.parser")
    paginas = {}
    for a in soup.select('nav[aria-label] a.page-link[href]'):
        href = a.get("href", "")
        if "tifirst=" in href or "tilast=" in href or href == "#":
            continue
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            paginas[int(m.group(1))] = href
    return paginas


async def fetch_participantes_curso(session, url_base, materia_id, perpage, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        raise asyncio.CancelledError()

    async with semaphore:
        if stop_event is not None and stop_event.is_set():
            raise asyncio.CancelledError()
        url = f"{url_base}&perpage={perpage}"
        print(f"[participantes] GET {url}")
        async with session.get(url) as resp:
            html = await resp.text()
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")

    participantes = parsear_participantes(html, materia_id)
    print(f"[participantes] materia_id={materia_id}: {len(participantes)} fila(s) en la primera pagina")

    paginas = _buscar_siguiente_pagina(html)
    if paginas:
        print(f"[participantes] materia_id={materia_id}: paginacion detectada ({len(paginas)} pagina(s) mas) - perpage={perpage} no alcanzo")

    for num_pagina, href in paginas.items():
        if stop_event is not None and stop_event.is_set():
            break
        print(f"[participantes] GET (pagina {num_pagina}) {href}")
        async with semaphore:
            async with session.get(href) as resp2:
                html2 = await resp2.text()
                if "/login/" in str(resp2.url):
                    raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
        nuevos = parsear_participantes(html2, materia_id)
        print(f"[participantes] materia_id={materia_id}: +{len(nuevos)} fila(s) de la pagina {num_pagina}")
        participantes.extend(nuevos)

    return participantes


async def obtener_participantes_async(moodle, cursos, stop_event=None, perpage=PERPAGE_MINIMO):
    """cursos: lista de dicts {'id': Materia.id, 'url': url de .../course/view.php?id=N}
    (el shape que ya devuelve conexiondb.cargar_cursos_por_id)."""
    perpage = max(perpage, PERPAGE_MINIMO)
    resultados = []
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for curso in cursos:
            if stop_event is not None and stop_event.is_set():
                break
            m = re.search(r"[?&]id=(\d+)", curso.get("url", ""))
            if not m:
                print(f"  No se pudo sacar el id de Moodle de {curso.get('url')!r}, se salta.")
                continue
            moodle_course_id = m.group(1)
            url_base = f"{moodle.base_url}/user/index.php?id={moodle_course_id}"
            print(f"[participantes] === Materia.id={curso['id']} ({curso.get('asignatura')}) -> curso Moodle id={moodle_course_id} ===")
            if stop_event is not None:
                stop_event.set_paso(f"Extrayendo último acceso de la materia: {curso.get('asignatura')}")
            participantes = await fetch_participantes_curso(
                session, url_base, curso["id"], perpage, stop_event
            )
            print(f"[participantes] Materia.id={curso['id']}: {len(participantes)} participante(s) en total")
            resultados.extend(participantes)
    return resultados
