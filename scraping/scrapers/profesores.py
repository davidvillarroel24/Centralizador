import aiohttp
import asyncio
from bs4 import BeautifulSoup

async def fetch(session, url, semaphore):
    async with semaphore:
        async with session.get(url) as resp:
            return await resp.text()

async def obtener_profesores_async(moodle,course):
    """Semaphore creado aca (no a nivel de modulo) - ver el comentario equivalente en
    scraping/scrapers/tareas.py::obtener_tareas_async, mismo bug (2026-10-25)."""
    semaphore = asyncio.Semaphore(5)
    Profesores = []
    cookies = moodle.session.cookies.get_dict()

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = []
        for curso in course:
            print("Extrayendo profesor de:", curso["asignatura"])
            Urloriginal = curso["url"]
            direccioncurso = "/course/view"
            direccionUsuarios = "/user/index"
            urlprofesor = Urloriginal.replace(direccioncurso, direccionUsuarios)

            # cada curso se procesa en paralelo
            tasks.append(procesar_profesor(session, curso["asignatura"], urlprofesor, semaphore))

        resultados = await asyncio.gather(*tasks)
        Profesores.extend(resultados)

    return Profesores


async def procesar_profesor(session, asignatura, urlprofesor, semaphore):
    """Extrae el nombre del primer profesor en la página de participantes"""
    url = f"{urlprofesor}&perpage=100"
    html = await fetch(session, url, semaphore)
    soup = BeautifulSoup(html, "html.parser")

    profesor = None

    headers = soup.select("table#participants thead th")

    col_roles = None

    for i, th in enumerate(headers):
        texto = th.get_text(strip=True)
        if "Roles" in texto:
            col_roles = i
            break
        
    for fila in soup.select("table#participants tbody tr"):
        rol = fila.find("td", class_="c"+str(col_roles))
        if rol and "Profesor" in rol.get_text(strip=True):
            nombre = fila.find("th", class_="c1")
            if nombre:
                profesor = nombre.get_text(strip=True)
            break  # parar al encontrar el primero

    return {"curso": asignatura, "profesor": profesor}
