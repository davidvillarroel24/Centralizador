import json
from pathlib import Path

from data.models import (
    Tarea,
    Estudiante,
    Entrega,
    ArchivoEntrega
)

RUTA_JSON = "data/raw/estudiantes.json"


def importar_estudiantes():

    with open(RUTA_JSON, "r", encoding="utf-8") as f:
        datos = json.load(f)

    total_entregas = 0

    for item in datos:

        moodle_id = item.get("id")

        if not moodle_id:

            print("❌ Tarea sin ID")
            continue

        try:

            tarea = Tarea.objects.get(
                moodle_id=int(moodle_id)
            )

        except Tarea.DoesNotExist:

            print(f"❌ Tarea no encontrada con moodle_id: {moodle_id}")
            continue

        estudiantes = item.get("estudiantes", [])

        for est in estudiantes:

            estudiante, _ = Estudiante.objects.get_or_create(
                moodle_userid=int(est["userid"]),
                defaults={
                    "nombre": est.get("nombre", ""),
                    "email": est.get("email", "")
                }
            )

            entrega, _ = Entrega.objects.update_or_create(
                tarea=tarea,
                estudiante=estudiante,
                defaults={

                    "estado": est.get("estado"),

                    "calificacion": est.get(
                        "calificacion"
                    ),

                    "ultima_mod_entrega": est.get(
                        "ultima_mod_entrega"
                    ),

                    "ultima_mod_calificacion": est.get(
                        "ultima_mod_calificacion"
                    ),

                    "comentarios_entrega": est.get(
                        "comentarios_entrega"
                    ),

                    "comentarios_feedback": est.get(
                        "comentarios_feedback"
                    ),

                    "calificacion_final": est.get(
                        "calificacion_final"
                    ),

                    "link_calificar": est.get(
                        "link_calificar"
                    )
                }
            )

            archivos = est.get("archivos", [])
            urls = est.get("archivosurl", [])

            for nombre, url in zip(archivos, urls):

                ArchivoEntrega.objects.update_or_create(

                    entrega=entrega,

                    nombre=nombre,

                    defaults={
                        "url": url
                    }
                )

            total_entregas += 1

    print(f"✅ Entregas importadas: {total_entregas}")
