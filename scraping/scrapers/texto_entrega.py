"""Bajar aparte la página completa de cada "Texto en línea" que la planilla de
calificación muestra truncado (con el link de la lupa "Ver entrega", identificable por
plugin=onlinetext en el href) - módulo independiente para no tocar detallesprofesores.py
ni html_crudo.py mientras se confirma cómo luce esa página real (ver auditoría
2026-11-20). Se encadena desde fuera (ver run_scraping.descargar_html_estudiantes).
"""
import re

import aiohttp
import asyncio
from bs4 import BeautifulSoup

CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=30)


def links_texto_en_linea(html_planilla):
    """[{'userid': ..., 'url': ...}, ...] por cada link "Ver entrega" de texto en línea
    (plugin=onlinetext) que haya en una página de planilla de calificación ya descargada.
    Se busca por el href, no por texto/clase visual, igual criterio que
    detallesprofesores.py usa para las columnas - lo único estable entre cuentas/roles."""
    soup = BeautifulSoup(html_planilla, "html.parser")
    enlaces = []
    for a in soup.select('a[href*="plugin=onlinetext"][href*="action=viewpluginassignsubmission"]'):
        href = a["href"]
        m = re.search(r"[?&]gid=(\d+)", href)
        enlaces.append({"userid": m.group(1) if m else None, "url": href})
    return enlaces


async def _fetch(session, url, semaphore):
    async with semaphore:
        async with session.get(url) as resp:
            return await resp.text()


def extraer_texto_completo(html_pagina_completa):
    """Texto íntegro de la página "Ver entrega" (plugin=onlinetext). Confirmado contra un
    caso real (2026-11-20): la planilla de calificación trunca el texto en línea cuando es
    largo (ej. corta una URL a mitad), pero esta página aparte siempre trae el contenido
    completo, dentro de div.submissionfull .no-overflow. separador="\\n" por el mismo
    motivo que en detallesprofesores.py: el texto trae varios <p>/<a> y sin separador
    quedan pegados sin espacio."""
    soup = BeautifulSoup(html_pagina_completa, "html.parser")
    contenedor = soup.select_one("div.submissionfull .no-overflow")
    if not contenedor:
        return None
    return contenedor.get_text("\n", strip=True)


async def completar_truncados(fetch_fn, entregas):
    """Reemplaza, en `entregas` (ya parseadas por detallesprofesores.parsear_entregas), el
    texto_en_linea por el texto COMPLETO de la página dedicada de cada una que traiga
    `texto_en_linea_url` - la planilla de calificación trunca ese texto cuando es largo,
    esta página aparte no. Se usa la URL que ya quedó guardada por fila al parsear (nunca
    se cruza por ids de la URL: el "gid" de Moodle no es el userid del estudiante -
    confirmado 2026-11-20 con un caso real donde no coincidían). `fetch_fn(url)` es
    provisto por quien llama (ver detallesprofesores.procesar_tarea_docente), para reusar
    su misma sesión/semáforo y la detección de sesión vencida que ya tiene `fetch` ahí."""

    async def _resolver(entrega):
        url = entrega.get("texto_en_linea_url")
        if not url:
            return
        texto_completo = extraer_texto_completo(await fetch_fn(url))
        if texto_completo:
            entrega["texto_en_linea"] = texto_completo

    await asyncio.gather(*(_resolver(e) for e in entregas if e.get("texto_en_linea")))


async def descargar_paginas_completas(moodle, html_planillas, stop_event=None):
    """html_planillas: {nombre_archivo: html} de planillas de calificación ya descargadas
    (ver html_crudo.py._descargar_grading). Devuelve un dict nuevo {nombre_archivo: html}
    con la página completa de cada "Ver entrega" de texto en línea encontrado en ellas,
    listo para fusionar con el resultado original (dict.update) sin modificarlo."""
    semaphore = asyncio.Semaphore(5)
    paginas = {}
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies, timeout=CLIENT_TIMEOUT) as session:
        for nombre, html in html_planillas.items():
            if stop_event is not None and stop_event.is_set():
                break
            for enlace in links_texto_en_linea(html):
                sufijo = enlace["userid"] or "sinid"
                nuevo_nombre = nombre.replace(".html", f"__texto_{sufijo}.html")
                paginas[nuevo_nombre] = await _fetch(session, enlace["url"], semaphore)
    return paginas
