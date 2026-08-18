import aiohttp
import asyncio
from bs4 import BeautifulSoup
import random

semaphore = asyncio.Semaphore(5)

async def fetch(session, url):
    """Descarga HTML con aiohttp"""
    async with semaphore:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        async with session.get(url) as resp:
            return await resp.text()

async def obtener_calificaciones_async(moodle,grade_url):
    resultado = []

    cookies = moodle.session.cookies.get_dict()

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = []

        for grade1 in grade_url:
            print("\nExtrayendo calificaciones de:", grade1["asignatura"], "\n")
            for grade in grade1["tareas"]:
                print("Extrayendo calificaciones de la unidad:", grade["unidad"])
                contenido = grade["contenido"]

                for tarea in contenido:
                    if "/assign/view" in tarea["url"]:
                        # cada tarea se procesa en paralelo
                        tasks.append(
                            procesar_calificacion(session, tarea["url"], grade["unidad"], tarea["Titulo"])
                        )

        # Ejecutamos todas las descargas concurrentemente
        resultados = await asyncio.gather(*tasks)
        resultado.extend(resultados)

    return resultado


async def procesar_calificacion(session, url, unidad, titulo):
    """Procesa la calificación de una tarea"""
    html = await fetch(session, url)
    soup = BeautifulSoup(html, "html.parser")

    # ---------- TABLA DE MI TRABAJO ----------
    trabajo_dict = {
        "Estado de la entrega": None,
        "Estado de la calificación": None,
        "Tiempo restante": None,
        "Última modificación": None,
        "Archivos enviados": [],
        "Comentarios de la entrega": None
    }

    trabajo_table = soup.find("div", class_="submissionstatustable")
    if trabajo_table:
        rows = trabajo_table.find_all("tr")
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = th.get_text(strip=True)
            val = td.get_text(" ", strip=True).replace("\xa0", " ")

            if key == "Archivos enviados":
                files = []
                for a in td.find_all("a", href=True):
                    nombre = a.get_text(strip=True)
                    url = a["href"]
                    files.append({"archivo": nombre, "url": url})
                trabajo_dict["Archivos enviados"] = files
            elif key == "Comentarios de la entrega":
                if "Comentarios (0)" in val:
                    trabajo_dict[key] = "Comentarios (0)"
                else:
                    comentario = td.get_text(" ", strip=True)
                    trabajo_dict[key] = comentario
            else:
                trabajo_dict[key] = val

    # ---------- TABLA DE NOTAS ----------
    nota_dict = {
        "Calificación": None,
        "Calificado sobre": None,
        "Calificado por": None,
        "Comentarios de retroalimentación": None
    }

    feedback_div = soup.find("div", class_="feedback")
    if feedback_div:
        rows = feedback_div.find_all("tr")
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = th.get_text(strip=True)
            val = td.get_text(" ", strip=True).replace("\xa0", " ")

            if key == "Calificado por":
                docente = td.get_text(" ", strip=True)
                nota_dict["Calificado por"] = docente
            elif key == "Comentarios de retroalimentación":
                comentario = td.get_text(" ", strip=True)
                nota_dict["Comentarios de retroalimentación"] = comentario
            else:
                nota_dict[key] = val

    return {
        "unidad": unidad,
        "titulo": titulo,
        "TrabEntregado": trabajo_dict,
        "Calificacion": nota_dict
    }
