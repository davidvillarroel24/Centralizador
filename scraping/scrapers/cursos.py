#Funciones para listar cursos.
from bs4 import BeautifulSoup

def obtener_cursos(moodle_session):
    url = "/my/courses.php"
    resp = moodle_session.get_courses(url)
    data=resp

    cursos = []
    try:
        courses_list = data[0]["data"]["courses"]
        for c in courses_list:
            cursos.append({
                "asignatura": c["fullname"],
                "id":c['id'],
                "url": f"{moodle_session.base_url}/course/view.php?id={c['id']}"
            })
    except Exception as e:
        print("Error extrayendo cursos:", e)
        print("Respuesta completa:", data)
        print("VUELVA A EXTRAER EL SESSKEY")

    return cursos
