import json
from pathlib import Path

from gatfh import config
from data.models import (
    Tarea,
    ArchivoTarea
)


RUTA_JSON = str(Path(config.DATA_DIR) / "detalle.json")


def importar_detalles_tareas():

    with open(RUTA_JSON, "r", encoding="utf-8") as f:
        datos = json.load(f)

    total = 0

    for item in datos:

        moodle_id = item.get("id")

        if not moodle_id:
            continue

        try:

            tarea = Tarea.objects.get(
                moodle_id=int(moodle_id)
            )

        except Tarea.DoesNotExist:

            print(f"❌ No existe tarea moodle_id={moodle_id}")
            continue

        descripcion = item.get("descripcion", {})

        tarea.descripcion = descripcion.get(
            "Detalle"
        )

        tarea.url_entrega = descripcion.get(
            "url"
        )

        tarea.save()

        archivos = descripcion.get(
            "Archivos",
            []
        )

        for archivo in archivos:

            ArchivoTarea.objects.update_or_create(

                tarea=tarea,

                nombre=archivo.get(
                    "archivo"
                ),

                defaults={

                    "url": archivo.get(
                        "url"
                    ),

                    "fecha": archivo.get(
                        "fecha"
                    )
                }
            )

        total += 1

    print(f"✅ Detalles importados: {total}")
