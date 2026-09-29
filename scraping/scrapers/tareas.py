#Funciones para obtener tareas de un curso.
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from gatfh import config
import random

from urllib.parse import urlparse, parse_qs

semaphore = asyncio.Semaphore(5)
CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class SesionExpiradaError(Exception):
    """La cookie de Moodle vencio: la respuesta es la pagina de login, no el curso (C4)."""


async def fetch_section(session, course_url, Nsec, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        raise asyncio.CancelledError()

    seccion = f"&section={Nsec}"
    async with semaphore:
        if stop_event is not None and stop_event.is_set():
            raise asyncio.CancelledError()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        async with session.get(f"{course_url}{seccion}") as resp:
            text = await resp.text()
            # Moodle responde 200 con la pagina de login cuando la cookie vencio; sin este
            # chequeo esa pagina se parsea como si fuera el curso y se guardan datos basura (C4).
            if "/login/" in str(resp.url):
                raise SesionExpiradaError(
                    "La sesión de Moodle expiró (la cookie ya no es válida)."
                )
        soup = BeautifulSoup(text, "html.parser")

    tituloUnidad = soup.title.string.split("|")
    detalle = []
    for li in soup.find_all("li", class_="activity-wrapper"):
        link = li.find("a", class_="aalink")
        if not link:
            continue
        url = link.get("href")        
        parsed = urlparse(url)
        tarea_id = int(parse_qs(parsed.query)['id'][0])
        span = link.find("span", class_="instancename")
        titulo = span.get_text(strip=True).replace(" Tarea", "") if span else None
        TIPOS = [
            "Tarea",
            "URL",
            "Foro",
            "Archivo",
            "Cuestionario",
            "Página",
            "Etiqueta",
        ]

        if titulo:
            for tipo in TIPOS:
                if titulo.endswith(tipo):
                    titulo = titulo[:-len(tipo)].strip()
                    break
                
        # Fechas
        apertura, cierre = None, None
        fechas = li.find("div", {"data-region": "activity-dates"})
        if fechas:
            apertura_tag = fechas.find("strong", string="Apertura:")
            cierre_tag = fechas.find("strong", string="Cierre:")
            if apertura_tag:
                apertura = apertura_tag.next_sibling.strip()
            if cierre_tag:
                cierre = cierre_tag.next_sibling.strip()

        if titulo and url:
            detalle.append({"id":tarea_id,"Titulo": titulo,"apertura": apertura,"cierre": cierre, "url": url})
    return {"unidad": tituloUnidad[0][6:], "contenido": detalle}

async def detectar_num_secciones(session, course_url, minimo=12):
    """Detecta cuantas secciones/unidades tiene realmente el curso leyendo su pagina
    principal, en vez de asumir un numero fijo (antes hardcodeado en 12 - C3/seccion 7 del
    plan). Si no se puede detectar ninguna, cae al minimo anterior para no romper cursos
    con una estructura de pagina distinta."""
    async with session.get(course_url) as resp:
        text = await resp.text()
        if "/login/" in str(resp.url):
            raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
    soup = BeautifulSoup(text, "html.parser")
    numeros = []
    for elemento in soup.find_all(id=re.compile(r"^section-\d+$")):
        try:
            numeros.append(int(elemento["id"].split("-")[1]))
        except (IndexError, ValueError):
            continue
    return max(numeros) if numeros else minimo


async def obtener_tareas_async(moodle, courses, stop_event=None):

    tareas = []
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for c in courses:
            if stop_event is not None and stop_event.is_set():
                break
            course_url = c["url"]
            asignatura = c["asignatura"]
            print("Extrayendo secciones de:", asignatura)

            num_secciones = await detectar_num_secciones(session, course_url)

            results = await asyncio.gather(*[
                fetch_section(session, course_url, Nsec, stop_event)
                for Nsec in range(1, num_secciones + 1)
            ], return_exceptions=True)
            errores = [r for r in results if isinstance(r, SesionExpiradaError)]
            if errores:
                raise errores[0]
            results = [r for r in results if not isinstance(r, BaseException)]
            tareas.append({
                "asignatura": asignatura,
                "tareas": results
            })
    return tareas
