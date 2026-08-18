import aiohttp
import asyncio
from bs4 import BeautifulSoup
import random


from urllib.parse import urlparse, parse_qs

semaphore = asyncio.Semaphore(5)

async def fetch(session, url):
    """Descarga HTML con aiohttp"""
    async with semaphore:
        await asyncio.sleep(random.uniform(0.5, 1.2))
        async with session.get(url) as resp:
            return await resp.text()

async def obtener_detalle_tarea_async(moodle,tareas):
    detalles = []

    cookies = moodle.session.cookies.get_dict()

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = []

        for t in tareas:        
            print("\nExtrayendo la asignatura:", t["asignatura"])
            for t0 in t['tareas']:
                print("Extrayendo la unidad:", t0["unidad"])
                for t1 in t0['contenido']:
                    titulotarea = t1["Titulo"]

                    if "/assign/view" in t1["url"]:
                        tarea_url = t1["url"] + "&action=editsubmission"
                        # lanzamos la petición en paralelo
                        tasks.append(procesar_tarea(session, tarea_url, t0["unidad"], titulotarea, t1["url"]))

        # Esperar a que terminen todas las tareas concurrentes
        resultados = await asyncio.gather(*tasks)
        detalles.extend(resultados)

    return detalles


async def procesar_tarea(session, tarea_url, unidad, titulotarea, fallback_url):
    """Procesa una tarea individual y devuelve su detalle"""
    html = await fetch(session, tarea_url)
    soup = BeautifulSoup(html, "html.parser")
    
    parsed = urlparse(fallback_url)
    detalle_id = int(parse_qs(parsed.query)['id'][0])

    descripcion_dict = {
        "Detalle": None,
        "url": None,
        "Archivos": []
    }

    desc_div = soup.find("div", class_="activity-description")
    desc_over = soup.find("div", class_="no-overflow")

    # fallback si no encontró descripción
    if desc_over is None:
        html = await fetch(session, fallback_url)
        soup = BeautifulSoup(html, "html.parser")
        desc_div = soup.find("div", class_="activity-description")
        desc_over = soup.find("div", class_="no-overflow")

    if desc_div:
        # --- 1) DETALLE ---
        textos = []
        for box in desc_div.find_all("div", class_="no-overflow"):
            textos.append(box.get_text(" ", strip=True))
        if textos:
            descripcion_dict["Detalle"] = "\n".join(textos)

        # --- 2) ARCHIVOS ---
        for file_div in desc_div.find_all("div", class_="fileuploadsubmission"):
            link = file_div.find("a", href=True)
            fecha = file_div.find_next("div", class_="fileuploadsubmissiontime")

            if link:
                descripcion_dict["Archivos"].append({
                    "archivo": link.get("title") or link.get_text(strip=True),
                    "url": link["href"],                    
                    "fecha": fecha.get_text(strip=True) if fecha else None
                })

        # --- 3) URL ---
        descripcion_dict["url"] = tarea_url

    return {
        "id":detalle_id,
        "unidad": unidad,
        "titulo": titulotarea,
        "descripcion": descripcion_dict
    }
