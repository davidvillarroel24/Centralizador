import json
from pathlib import Path

from gatfh import config
from data.models import (
    Tarea,
    Estudiante,
    Entrega,
)

RUTA_JSON = str(Path(config.DATA_DIR) / "estudiantes.json")


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

            # BUG (encontrado 2026-11-05): un Decano ve esta misma planilla sin columna de
            # correo (detallesprofesores.py::ORDEN_DECANO), asi que "email" puede venir None,
            # "" o faltar directamente - nunca se asume que esta. Se normaliza todo eso a
            # None (nunca "", que con unique=True chocaria entre dos estudiantes sin correo
            # todavia) para guardar "no tengo el dato" de forma explicita.
            nombre = est.get("nombre") or ""
            email = (est.get("email") or "").strip() or None

            estudiante, creado = Estudiante.objects.get_or_create(
                moodle_userid=int(est["userid"]),
                defaults={"nombre": nombre, "email": email}
            )

            if not creado:
                # get_or_create() solo usa "defaults" al crear - si el estudiante ya
                # existia (por ej. lo creo un Decano sin correo), una extraccion posterior
                # de un Docente con el correo real antes se perdia en silencio. Se
                # actualiza aca, y solo con datos no vacios: nunca se pisa un nombre/correo
                # ya guardado con uno en blanco.
                cambios = []
                if nombre and estudiante.nombre != nombre:
                    estudiante.nombre = nombre
                    cambios.append("nombre")
                if email and estudiante.email != email:
                    estudiante.email = email
                    cambios.append("email")
                if cambios:
                    estudiante.save(update_fields=cambios)

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

            # Nota: el JSON trae "archivos"/"archivosurl" por entrega, pero no existe un
            # modelo ArchivoEntrega (solo ArchivoTarea, a nivel de tarea) - se omite el
            # guardado de adjuntos por estudiante hasta que se defina ese modelo.

            total_entregas += 1

    print(f"✅ Entregas importadas: {total_entregas}")
