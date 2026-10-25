import aiohttp
import asyncio
from bs4 import BeautifulSoup
import random


from urllib.parse import urlparse, parse_qs

from .tareas import SesionExpiradaError


async def fetch(session, url, semaphore):
    """Descarga HTML con aiohttp"""
    async with semaphore:
        await asyncio.sleep(random.uniform(0.5, 1.2))
        async with session.get(url) as resp:
            text = await resp.text()
            # Moodle responde 200 con la pagina de login cuando la cookie vencio en vez de
            # cualquier error HTTP - sin este chequeo esa pagina se parseaba como si fuera
            # la tarea (sin encontrar nada, "Detalle"/"Archivos" vacios) en vez de avisar
            # que habia que volver a capturar la cookie. Mismo bug/arreglo que tareas.py
            # (C4) y participantes.py, ahora tambien aca.
            if "/login/" in str(resp.url):
                raise SesionExpiradaError("La sesión de Moodle expiró (la cookie ya no es válida).")
            return text

async def obtener_detalle_tarea_async(moodle, tareas, stop_event=None):
    """`tareas` ya viene filtrada a solo tipo 'assign' por quien llama (ver
    run_scraping.detalle_tarea, que la arma desde la base de datos) - antes esta función
    repetía esa clasificación a mano con `"/assign/view" in url`, una segunda fuente de
    verdad para algo que Tarea.tipo ya resuelve de forma confiable."""
    detalles = []

    # Creado adentro de esta función (que siempre corre vía asyncio.run(), ver
    # run_scraping.detalle_tarea) en vez de a nivel de módulo: un Semaphore queda "atado"
    # al primer event loop donde tiene que esperar turno (asyncio.mixins._LoopBoundMixin).
    # Si viviera a nivel de módulo, sobreviviría al cierre de ESE loop (asyncio.run() lo
    # cierra al terminar) y la siguiente corrida - mismo proceso de gunicorn/runserver,
    # módulo ya importado - reventaria con "RuntimeError: ... is bound to a different
    # event loop" apenas se agotara el cupo inicial del semáforo (confirmado 2026-10-25:
    # exactamente 5 tareas pasaban antes de que todo lo demás fallara, igual al cupo de
    # Semaphore(5)). Creándolo acá, cada asyncio.run() nuevo arranca con un semáforo nuevo,
    # atado a SU PROPIO loop.
    semaphore = asyncio.Semaphore(5)

    cookies = moodle.session.cookies.get_dict()

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = []

        for t in tareas:
            if stop_event is not None and stop_event.is_set():
                break
            print("\nExtrayendo la asignatura:", t["asignatura"])
            if stop_event is not None:
                stop_event.set_paso(f"Extrayendo detalle de tareas de la materia: {t['asignatura']}")
            for t0 in t['tareas']:
                print("Extrayendo la unidad:", t0["unidad"])
                for t1 in t0['contenido']:
                    titulotarea = t1["Titulo"]
                    tarea_url = t1["url"] + "&action=editsubmission"
                    # lanzamos la petición en paralelo
                    tasks.append(procesar_tarea(session, tarea_url, t0["unidad"], titulotarea, t1["url"], semaphore))

        # Esperar a que terminen todas las tareas concurrentes
        resultados = await asyncio.gather(*tasks, return_exceptions=True)
        errores_sesion = [r for r in resultados if isinstance(r, SesionExpiradaError)]
        if errores_sesion:
            raise errores_sesion[0]
        detalles.extend(item for item in resultados if not isinstance(item, BaseException))

    return detalles


async def procesar_tarea(session, tarea_url, unidad, titulotarea, fallback_url, semaphore):
    """Procesa una tarea individual y devuelve su detalle. Atrapa sus propios errores (en
    vez de dejarlos subir a asyncio.gather(..., return_exceptions=True), que los filtra en
    silencio) para que una tarea que falla (red, permiso, HTML inesperado) quede igual en
    detalle.json con el motivo, en vez de desaparecer de la lista sin dejar rastro - asi se
    puede diferenciar "no encontró nada en el HTML" de "nunca llegó a pedirlo"."""
    try:
        html = await fetch(session, tarea_url, semaphore)
        soup = BeautifulSoup(html, "html.parser")

        parsed = urlparse(fallback_url)
        detalle_id = int(parse_qs(parsed.query)['id'][0])
    except SesionExpiradaError:
        # No se guarda como error de ESTA tarea puntual: corta todo el lote (ver
        # obtener_detalle_tarea_async) en vez de seguir pidiendo el resto con una cookie
        # que ya sabemos que no sirve.
        raise
    except Exception as exc:
        return {
            "id": None,
            "unidad": unidad,
            "titulo": titulotarea,
            "descripcion": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    descripcion_dict = {
        "Detalle": None,
        "url": None,
        "Archivos": [],
        # "html" deshabilitado (ver mas abajo) - era temporal, para diagnosticar por que
        # salia vacio con una cuenta docente. Ya cumplio su proposito (confirmado: cookie
        # vencida, no un problema de "&action=editsubmission"). Descomentar las 2 lineas
        # marcadas si hace falta volver a inspeccionar el HTML crudo.
        # "html": None,
    }

    desc_div = soup.find("div", class_="activity-description")
    desc_over = soup.find("div", class_="no-overflow")

    # fallback si no encontró descripción
    if desc_over is None:
        html = await fetch(session, fallback_url, semaphore)
        soup = BeautifulSoup(html, "html.parser")
        desc_div = soup.find("div", class_="activity-description")
        desc_over = soup.find("div", class_="no-overflow")

    # descripcion_dict["html"] = html

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
