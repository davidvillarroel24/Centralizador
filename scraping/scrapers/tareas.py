#Funciones para obtener tareas de un curso.
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from gatfh import config
import random

from urllib.parse import urlparse, parse_qs

semaphore = asyncio.Semaphore(5)

async def fetch_section(session, course_url, Nsec):
    seccion = f"&section={Nsec}"
    async with semaphore:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        async with session.get(f"{course_url}{seccion}") as resp:
            text = await resp.text()
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

async def obtener_tareas_async(moodle,courses):
        
    tareas = []    
    cookies = moodle.session.cookies.get_dict()
    async with aiohttp.ClientSession(cookies=cookies) as session:
        for c in courses:
            course_url = c["url"]
            asignatura = c["asignatura"]
            print("Extrayendo secciones de:", asignatura)

            results = await asyncio.gather(*[
                fetch_section(session, course_url, Nsec) for Nsec in range(1, 13)
            ])
            tareas.append({
                "asignatura": asignatura,
                "tareas": results
            })
            #print(tareas)
            #señal=input("enter para continuar con")
    return tareas
