"""Material de apoyo subido por un docente como actividad tipo 'url' en Moodle (el campo
Tarea.tipo='url' es un catch-all en la BD para todo lo que no es 'assign': recursos de
enlace externo de verdad, archivos subidos, y tambien cuestionarios - que no tienen nada
que extraer). Para cada Tarea tipo 'url' se busca, en este orden:

1. El link externo (Drive, YouTube, lo que sea) que el docente puso - en un recurso tipo
   URL real esta en div.urlworkaround; en un recurso de archivo puede estar pegado como
   texto en la descripcion, que Moodle auto-convierte en <a> (confirmado 2026-11-10 con
   HTML real de varios cursos).
2. Si no hay link (o el que hay es un placeholder sin reemplazar, ej. "enlacedrive.com"),
   el archivo propio de Moodle - nombre + url directa, para poder previsualizarlo con el
   visor de siempre (ArchivoTarea) en vez de dejarlo vacio.

Nunca ambos a la vez: si el docente puso un link, es ese el material a compartir; el
archivo propio queda de respaldo solo cuando no hay ningun link usable.
"""
import re

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .tareas import SesionExpiradaError

CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Dominios de relleno que algunos docentes dejaron sin reemplazar al copiar la plantilla
# del recurso (confirmado en varios cursos - siempre el mismo texto, con o sin errores de
# tipeo en el esquema) - un link asi no sirve, se descarta igual que si no hubiera ninguno.
DOMINIOS_PLACEHOLDER = {"enlacedrive.com", "enlacedrieve.com"}


def _enlace_valido(href):
    if not href:
        return False
    try:
        partes = urlparse(href)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https"):
        return False
    dominio = partes.netloc.lower()
    if dominio.startswith("www."):
        dominio = dominio[4:]
    return dominio not in DOMINIOS_PLACEHOLDER


def _primer_enlace_externo(soup):
    for selector in ("div.urlworkaround", "div.activity-description"):
        contenedor = soup.select_one(selector)
        if not contenedor:
            continue
        a = contenedor.find("a", href=True)
        if a and _enlace_valido(a["href"]):
            return a["href"]
    return None


def _archivo_embebido(soup):
    """Sin link externo: el archivo propio, si la pagina lo muestra embebido (ej. una
    imagen con "Mostrar: Incrustado") - nombre + url directa del archivo en Moodle."""
    main = soup.find(attrs={"role": "main"})
    if not main:
        return None
    img = main.select_one(".resourcecontent img[src]")
    if img:
        return {"nombre": img.get("title") or img["src"].rsplit("/", 1)[-1], "url": img["src"]}
    link = main.select_one(".resourcecontent a[href]")
    if link:
        return {"nombre": link.get_text(strip=True) or link["href"].rsplit("/", 1)[-1], "url": link["href"]}
    return None


def _nombre_desde_content_disposition(resp, url):
    disposicion = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposicion)
    if m:
        return m.group(1)
    return url.rsplit("/", 1)[-1] or "archivo"


async def _fetch_material(session, url, semaphore):
    async with semaphore:
        async with session.get(url, allow_redirects=True) as resp:
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
            content_type = resp.content_type or ""
            es_html = content_type.startswith("text/") or "html" in content_type
            if not es_html:
                # "Mostrar: Automatico" en un recurso de archivo: esta URL YA es el
                # archivo (la redireccion ya se siguio sola), no hay pagina intermedia
                # que pedir ni descripcion que leer.
                return {
                    "enlace_externo": None,
                    "archivo": {
                        "nombre": _nombre_desde_content_disposition(resp, str(resp.url)),
                        "url": str(resp.url),
                    },
                }
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    enlace = _primer_enlace_externo(soup)
    archivo = None if enlace else _archivo_embebido(soup)
    return {"enlace_externo": enlace, "archivo": archivo}


async def _procesar_una(session, tarea, semaphore):
    try:
        resultado = await _fetch_material(session, tarea["url"], semaphore)
    except SesionExpiradaError:
        raise
    except Exception as exc:
        resultado = {"enlace_externo": None, "archivo": None, "error": f"{type(exc).__name__}: {exc}"}
    resultado["id"] = tarea["moodle_id"]
    return resultado


async def obtener_materiales_async(moodle, tareas, stop_event=None):
    """`tareas`: lista de dicts {'moodle_id', 'url'} (una por Tarea tipo 'url' a revisar).
    Semaphore creado aca (no a nivel de modulo) - mismo motivo que el resto de los
    scrapers: queda atado al event loop de ESTE asyncio.run()."""
    semaphore = asyncio.Semaphore(5)
    cookies = moodle.session.cookies.get_dict()
    resultados = []
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        tasks = []
        for t in tareas:
            if stop_event is not None and stop_event.is_set():
                break
            tasks.append(_procesar_una(session, t, semaphore))

        data = await asyncio.gather(*tasks, return_exceptions=True)
        errores_sesion = [r for r in data if isinstance(r, SesionExpiradaError)]
        if errores_sesion:
            raise errores_sesion[0]
        resultados.extend(item for item in data if not isinstance(item, BaseException))

    return resultados
