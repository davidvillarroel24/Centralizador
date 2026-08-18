import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

semaphore = asyncio.Semaphore(5)

async def fetch(session, url):
    
    """Descarga HTML con aiohttp"""
    async with semaphore:
        async with session.get(url) as resp:
            return await resp.text()

async def obtener_tareas_docente_async(moodle, tareas):
    resultados = []
    #tareas=tareas[1][tareas[]]
    #print(tareas)
    #continuar= input("Detener: ")
    cookies = moodle.session.cookies.get_dict()
    print(cookies)

    #return

    async with aiohttp.ClientSession(cookies=cookies) as session:
        #print(session)
        #return
        tasks = []
        #contador=1
        for t in tareas:
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
                                t1["Titulo"]
                            )
                        )
            #if contador==1: break
            #continuar= input("Detener: ")

        data = await asyncio.gather(*tasks)
        resultados.extend(data)

    return resultados

async def procesar_tarea_docente(session, url, unidad, titulo):

    query = urlparse(url).query

    id_tarea = parse_qs(query).get("id", [None])[0]

    html = await fetch(session, url)

    soup = BeautifulSoup(html, "html.parser")

    data = []

    #tabla = soup.find("table", class_="generaltable")
    tabla = soup.select_one("table.generaltable")

    if not tabla:
        print("No se encontró tabla, guardando HTML para debug...")
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        return {
            "id":id_tarea,
            "unidad": unidad,
            "titulo": titulo,
            "estudiantes": []
        }

    filas = tabla.find("tbody").find_all("tr")

    for fila in filas:
        try:
            celdas = fila.find_all("td")

            # USER ID
            checkbox = fila.find("input", {"name": "selectedusers"})
            userid = checkbox["value"] if checkbox else None

            # MAPEO POR ÍNDICE (según orden típico de Moodle)
            #nombre = celdas[1].get_text(strip=True) if len(celdas) > 1 else None
            #apellido = celdas[2].get_text(strip=True) if len(celdas) > 2 else None
            nombre = celdas[2].get_text(strip=True) if len(celdas) > 2 else None
            if not nombre or not userid:
                print("⛔ Fin real de datos")
                break

            email = celdas[3].get_text(strip=True) if len(celdas) > 3 else None
            #estado = fila.find("div", class_="submissionstatussubmitted")
            estado_div = fila.find("td", class_="cell c4")  # columna estado (puede variar)
            #estado = estado.get_text(strip=True) if estado else None
            estado = None
            if estado_div:
                estado = estado_div.get_text(" ", strip=True)

            calificacion = celdas[5].get_text(strip=True) if len(celdas) > 5 else None

            ultima_mod_entrega = celdas[7].get_text(strip=True) if len(celdas) > 7 else None
            archivos = []
            archivo_urls = []

            if len(celdas) > 8:
                celda_archivos = celdas[8]

                links = celda_archivos.find_all("a")

                for link in links:
                    nombre_archivo = link.get_text(strip=True)
                    url = link.get("href")

                    archivos.append(nombre_archivo)
                    archivo_urls.append(url)
            comentarios_entrega = celdas[9].get_text(strip=True) if len(celdas) > 9 else None

            ultima_mod_calificacion = celdas[10].get_text(strip=True) if len(celdas) > 10 else None
            comentarios_feedback = celdas[11].get_text(strip=True) if len(celdas) > 11 else None
            calificacion_final = celdas[12].get_text(strip=True) if len(celdas) > 12 else None

            # LINK CALIFICAR
            calificar_tag = fila.find("a", class_="btn")
            link_calificar = calificar_tag["href"] if calificar_tag else None

            data.append({
                "userid": userid,
                "nombre": nombre,
                #"apellido": apellido,
                "email": email,
                "estado": estado,
                "calificacion": calificacion,
                "ultima_mod_entrega": ultima_mod_entrega,
                "archivos": archivos,
                "archivosurl":archivo_urls,
                "comentarios_entrega": comentarios_entrega,
                "ultima_mod_calificacion": ultima_mod_calificacion,
                "comentarios_feedback": comentarios_feedback,
                "calificacion_final": calificacion_final,
                "link_calificar": link_calificar
            })

        except Exception as e:
            print("Error procesando fila:", e)
            continue

    return {
        "id":id_tarea,
        "unidad": unidad,
        "titulo": titulo,
        "estudiantes": data
    }
