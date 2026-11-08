import re

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

from .participantes import ultima_pagina
from .tareas import SesionExpiradaError

CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)

async def fetch(session, url, semaphore):

    """Descarga HTML con aiohttp"""
    async with semaphore:
        async with session.get(url) as resp:
            text = await resp.text()
            # Moodle responde 200 con la pagina de login cuando la cookie vencio - sin este
            # chequeo esa pagina se parseaba como si fuera la planilla de calificacion (sin
            # encontrar ninguna fila, 0 estudiantes) en vez de avisar que hay que volver a
            # capturar la cookie. Mismo bug/arreglo que tareas.py (C4), participantes.py y
            # detalles.py.
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
            return text

async def obtener_tareas_docente_async(moodle, tareas, stop_event=None):
    """Semaphore creado aca (no a nivel de modulo) - ver el comentario equivalente en
    scraping/scrapers/tareas.py::obtener_tareas_async, mismo bug (2026-10-25)."""
    semaphore = asyncio.Semaphore(5)
    resultados = []
    cookies = moodle.session.cookies.get_dict()

    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        tasks = []
        for t in tareas:
            if stop_event is not None and stop_event.is_set():
                break
            print("\nAsignatura:", t["asignatura"])
            for t0 in t['tareas']:
                print("Unidad:", t0["unidad"])
                for t1 in t0['contenido']:

                    if "/assign/view" in t1["url"]:
                        grading_url = t1["url"] + "&action=grading&perpage=100"
                        print(t0["unidad"],grading_url)
                        tasks.append(
                            procesar_tarea_docente(
                                session,
                                grading_url,
                                t0["unidad"],
                                t1["Titulo"],
                                semaphore,
                                stop_event
                            )
                        )

        data = await asyncio.gather(*tasks, return_exceptions=True)
        errores_sesion = [r for r in data if isinstance(r, SesionExpiradaError)]
        if errores_sesion:
            raise errores_sesion[0]
        resultados.extend(item for item in data if not isinstance(item, BaseException))

    return resultados

# Orden de columnas de la planilla de calificacion vista por un docente del curso: la
# posicion en esta lista es su cN (c0 = seleccionar, c1 = imagen, c2 = nombre...). Es la
# que se leia siempre.
ORDEN_DOCENTE = [
    "seleccionar", "imagen", "nombre", "email", "estado", "calificacion", "editar",
    "ultima_mod_entrega", "archivos", "comentarios_entrega", "ultima_mod_calificacion",
    "comentarios_feedback", "calificacion_final",
]
# Un Decano ve la misma planilla sin correo (c3 del docente), "editar" (c6) NI "seleccionar"
# (c0): esas tres columnas no existen (confirmado 2026-11-08 probando con una cuenta Decano
# real) y el resto se corre, quedando c0..c9. Antes se asumia que "seleccionar" si estaba
# (10 columnas reales contra las 11 que se esperaban), lo que corria todo un lugar y hacia
# que cada entrega se descartara por no encontrar userid (ver _columnas_de).
ORDEN_DECANO = [c for c in ORDEN_DOCENTE if c not in ("seleccionar", "email", "editar")]

# Se elige por cuantas columnas trae la fila (lo que la cuenta ve), nunca por el texto de
# los encabezados.
ORDEN_POR_CANTIDAD = {len(ORDEN_DOCENTE): ORDEN_DOCENTE, len(ORDEN_DECANO): ORDEN_DECANO}


def _columnas_de(fila):
    """{campo: indice cN} segun la cantidad de celdas de la fila: 13 -> docente, 10 ->
    decano. Un campo que esa planilla no tiene (ej. email o seleccionar para el decano)
    queda en None."""
    total = len(fila.find_all(["td", "th"], recursive=False))
    orden = ORDEN_POR_CANTIDAD.get(total)
    if orden is None:
        # No se adivina en silencio: se usa la del docente (la de siempre) y queda el aviso
        # en el log para agregar la nueva disposicion si Moodle cambia la tabla.
        print(f"[entregas] fila con {total} columnas (se esperaban {len(ORDEN_DOCENTE)} o "
              f"{len(ORDEN_DECANO)}) - revisar ORDEN_* en detallesprofesores.py")
        orden = ORDEN_DOCENTE
    return {campo: (orden.index(campo) if campo in orden else None) for campo in ORDEN_DOCENTE}


def parsear_entregas(html):
    """Filas de UNA pagina de la planilla de calificacion -> lista de dicts, o None si la
    pagina no trae la tabla."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.select_one("table.generaltable")
    if not tabla or not tabla.find("tbody"):
        return None

    data = []

    for fila in tabla.find("tbody").find_all("tr"):
        try:
            columnas = _columnas_de(fila)

            def celda_de(campo):
                indice = columnas[campo]
                return fila.select_one(f"td.cell.c{indice}") if indice is not None else None

            def texto(campo, separador=""):
                celda = celda_de(campo)
                return celda.get_text(separador, strip=True) if celda else None

            # El id sale del checkbox, como siempre; si la cuenta no lo tiene, del link al
            # perfil del estudiante en la celda del nombre.
            checkbox = fila.find("input", {"name": "selectedusers"})
            userid = checkbox["value"] if checkbox else None
            if not userid:
                celda_nombre = celda_de("nombre")
                link_perfil = celda_nombre.select_one('a[href*="/user/view.php"]') if celda_nombre else None
                m = re.search(r"[?&]id=(\d+)", link_perfil.get("href", "")) if link_perfil else None
                userid = m.group(1) if m else None
            nombre = texto("nombre")
            if not nombre or not userid:
                # Fila sin nombre/userid (fila de encabezado, separador, etc.): se omite
                # esta fila puntual, pero se sigue procesando el resto de la tabla (C5).
                continue

            archivos = []
            archivo_urls = []
            celda_archivos = celda_de("archivos")
            if celda_archivos:
                for link in celda_archivos.find_all("a"):
                    archivos.append(link.get_text(strip=True))
                    archivo_urls.append(link.get("href"))

            # LINK CALIFICAR
            calificar_tag = fila.find("a", class_="btn")
            link_calificar = calificar_tag["href"] if calificar_tag else None

            data.append({
                "userid": userid,
                "nombre": nombre,
                "email": texto("email"),
                "estado": texto("estado", " "),
                "calificacion": texto("calificacion"),
                "ultima_mod_entrega": texto("ultima_mod_entrega"),
                "archivos": archivos,
                "archivosurl": archivo_urls,
                "comentarios_entrega": texto("comentarios_entrega"),
                "ultima_mod_calificacion": texto("ultima_mod_calificacion"),
                "comentarios_feedback": texto("comentarios_feedback"),
                "calificacion_final": texto("calificacion_final"),
                "link_calificar": link_calificar
            })

        except Exception as e:
            print("Error procesando fila:", e)
            continue

    return data


async def procesar_tarea_docente(session, url, unidad, titulo, semaphore, stop_event=None):

    if stop_event is not None and stop_event.is_set():
        raise asyncio.CancelledError()

    query = urlparse(url).query

    id_tarea = parse_qs(query).get("id", [None])[0]

    html = await fetch(session, url, semaphore)

    data = parsear_entregas(html)

    if data is None:
        print("No se encontró tabla, guardando HTML para debug...")
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(html)

        return {
            "id":id_tarea,
            "unidad": unidad,
            "titulo": titulo,
            "estudiantes": []
        }

    # Moodle ignora el &perpage=100 de la URL en esta planilla: usa la preferencia guardada
    # de la cuenta (10 por defecto) - un curso de 42 traia solo los primeros 10.
    ultima = ultima_pagina(html)
    for pagina in range(1, ultima + 1):
        if stop_event is not None and stop_event.is_set():
            raise asyncio.CancelledError()
        data.extend(parsear_entregas(await fetch(session, f"{url}&page={pagina}", semaphore)) or [])

    # Por si una pagina se repite (alguien entrego mientras se extraia y la lista se corrio).
    vistos = set()
    data = [e for e in data if not (e["userid"] in vistos or vistos.add(e["userid"]))]

    if ultima:
        print(f"[entregas] tarea {id_tarea}: {ultima + 1} pagina(s), {len(data)} estudiante(s)")

    return {
        "id":id_tarea,
        "unidad": unidad,
        "titulo": titulo,
        "estudiantes": data
    }
