#Funciones para listar cursos.
from bs4 import BeautifulSoup
from gatfh.config import BASE_URL

import time
import random


def obtener_categorias(moodle_session):
    url = "/course/index.php"
    resp = moodle_session.get_category(url)

    html = str(resp)#.content  # o resp.content dependiendo de tu implementación

    # Guardar HTML para debug
    #with open("carreras_debug.html", "w", encoding="utf-8") as f:    
    #    f.write(html)

    return html


def extraer_categorias(html):
        
    soup = BeautifulSoup(html, "html.parser")

    categorias = []

    options = soup.select("select[name='jump'] option")
    
    for op in options:
        value = op.get("value")
        nombre = op.text.strip()

        if value and "categoryid=" in value:
            cat_id = value.split("categoryid=")[-1]

            categorias.append({
                "id": int(cat_id),
                "nombre": nombre
            })

    return categorias

def cargar_categoria_completa(moodle, url, categoria):

    categoria_id = categoria["id"]

    pagina = 0
    htmls = []

    while True:

        print(f"📄 Categoría {categoria_id} - página {pagina}")

        html = moodle.get_category(
            url,
            category_id=categoria_id,
            page=pagina
        )

        soup = BeautifulSoup(html, "html.parser")

        cursos = soup.select(".coursebox, .course-card-view")

        # si ya no hay cursos → terminar
        if not cursos:
            break

        htmls.append(html)

        # si vienen menos de 20 probablemente es la última
        if len(cursos) < 20:
            break

        pagina += 1

        time.sleep(random.uniform(1.5, 3.5))

    return {
        "categoria": categoria,
        "htmls": htmls
    }


def cargar_todo(moodle, categorias):

    url = "/course/index.php"

    resultados = []

    for cat in categorias:

        print(f"📂 Cargando categoría {cat['id']}")

        resultado = cargar_categoria_completa(
            moodle,
            url,
            cat
        )

        resultados.append(resultado)

    return resultados


def procesar_datos(categorias_html):

    resultado = []

    for item in categorias_html:

        nombre = item["categoria"]["nombre"]
        htmls = item["htmls"]

        # 🔥 FILTRO CLAVE
        if not es_categoria_final(nombre):
            continue

        facultad, carrera, nivel = parsear_nombre(nombre)

        materias = []

        # 🔥 recorrer todas las páginas
        for html in htmls:

            cursos = extraer_cursos(html)

            if cursos:
                materias.extend(cursos)

        # evitar categorías vacías
        if not materias:
            continue

        # 🔥 eliminar duplicados si Moodle repite cursos
        materias_unicas = []
        vistos = set()

        for materia in materias:

            clave = materia.get("url") or materia.get("nombre")

            if clave in vistos:
                continue

            vistos.add(clave)
            materias_unicas.append(materia)

        resultado.append({
            "facultad": facultad,
            "carrera": carrera,
            "nivel": nivel,
            "materias": materias_unicas
        })

    return resultado

def es_categoria_final(nombre):
    return (
        "SEMESTRE" in nombre.upper()
        or "AÑO" in nombre.upper()
    )

from bs4 import BeautifulSoup

def extraer_cursos(html):
    soup = BeautifulSoup(html, "html.parser")

    cursos = []
    vistos = set()

    # busca enlaces de cursos
    links = soup.find_all("a", href=lambda x: x and "course/view.php?id=" in x)

    for link in links:
        if link.text.strip()!="Go to the course":
            nombre = link.text.strip()
            url = link["href"]
            
        # evitar duplicados raros
        if not nombre:
            continue

        # 🔥 evitar duplicados
        if url in vistos:
            continue
        vistos.add(url)

        # intentar encontrar profesor cercano
        profesor = None

        parent = link.find_parent("div", class_="course-card-view")

        if parent:
            teacher_container = parent.find("div", class_="teachers") or parent.find("div", class_="teacher")

            if teacher_container:

                teacher_links = teacher_container.find_all("a")

                if teacher_links:

                    profesores = []

                    for t in teacher_links:

                        nombre_profesor = t.text.strip()
                        url_profesor = t.get("href")

                        profesor_id = None

                        # 🔥 extraer id del docente desde la URL
                        if url_profesor and "id=" in url_profesor:
                            profesor_id = url_profesor.split("id=")[1].split("&")[0]

                        profesores.append({
                            "id": profesor_id,
                            "nombre": nombre_profesor,
                            "url": url_profesor
                        })

                    profesor = profesores
        cursos.append({
            "materia": nombre,
            "profesor": profesor,
            "url": url
        })

    return cursos

def parsear_nombre(nombre):
    partes = nombre.split(" / ")

    facultad = partes[0] if len(partes) > 0 else None
    carrera = partes[1] if len(partes) > 1 else None
    nivel = partes[2] if len(partes) > 2 else None

    return facultad, carrera, nivel
