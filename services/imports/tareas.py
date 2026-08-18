import json
import re

from data.models import Materia, Unidad, Tarea


def importar_tareas():

    with open("data/raw/tareas.json", "r", encoding="utf-8") as file:

        data = json.load(file)

    tareas_creadas = 0

    for item in data:

        nombre_materia = item.get("asignatura")

        materia = Materia.objects.filter(
            moodle_nombre=nombre_materia
        ).first()

        if not materia:

            print(f"❌ Materia no encontrada: {nombre_materia}")

            continue

        for tarea_data in item.get("tareas", []):

            nombre_unidad = tarea_data.get("unidad")

            unidad, _ = Unidad.objects.get_or_create(
                materia=materia,
                nombre=nombre_unidad
            )

            for contenido in tarea_data.get("contenido", []):

                moodle_id = contenido.get("id")

                titulo_completo = contenido.get("Titulo", "")

                titulo, tipo = separar_tipo(titulo_completo)

                _, created = Tarea.objects.get_or_create(

                    moodle_id=moodle_id,

                    defaults={

                        "unidad": unidad,

                        "titulo": titulo,

                        "tipo": tipo,

                        "apertura": contenido.get("apertura"),

                        "cierre": contenido.get("cierre"),

                        "url": contenido.get("url"),
                    }
                )

                if created:

                    tareas_creadas += 1

    print(f"✅ Tareas creadas: {tareas_creadas}")


def separar_tipo(texto):

    tipos = [
        "Tarea",
        "URL",
        "Foro",
        "Archivo",
        "Quiz",
    ]

    for tipo in tipos:

        if texto.endswith(tipo):

            titulo = texto.replace(tipo, "").strip()

            return titulo, tipo

    return texto, "Otro"
