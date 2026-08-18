from urllib.parse import urlparse, parse_qs
import re

def parsear_calificacion(texto):
    if not texto:
        return None, None

    try:
        # Extrae números tipo "100,00 / 100,00"
        numeros = re.findall(r"[\d,]+", texto)

        if len(numeros) >= 2:
            nota = float(numeros[0].replace(",", "."))
            maximo = float(numeros[1].replace(",", "."))
            return nota, maximo

    except:
        pass

    return None, None


def extraer_id_desde_url(url):
    try:
        return int(parse_qs(urlparse(url).query)['id'][0])
    except:
        return None
    
def transformar_estudiantes(estudiantes_json):

    resultado = {}


    for item2 in estudiantes_json:
        for item in item2["estudiantes"]:

            userid = int(item["userid"])
            nombre = item["nombre"]

            # ID de tarea (desde link)
            tarea_id = extraer_id_desde_url(item.get("link_calificar", ""))

            nota, maximo = parsear_calificacion(item.get("calificacion_final"))

            if not tarea_id:
                continue

            if userid not in resultado:
                resultado[userid] = {
                    "userid": userid,
                    "nombre": nombre,
                    "tareas": []
                }

            resultado[userid]["tareas"].append({
                "id": tarea_id,
                "nota": nota,
                "max": maximo
            })

    return list(resultado.values())
