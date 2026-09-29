import json
from pathlib import Path

from gatfh import config
from data.models import Facultad


def importar_facultades():

    ruta = Path(config.DATA_DIR) / "linkcarreras.json"

    with open(ruta, "r", encoding="utf-8") as f:
        carreras = json.load(f)

    facultades_unicas = {}

    for carrera in carreras:

        nombre_facultad = carrera.get("facultad")

        if not nombre_facultad:
            continue

        nombre_facultad = nombre_facultad.strip()

        if nombre_facultad not in facultades_unicas:

            facultades_unicas[nombre_facultad] = Facultad(
                nombre=nombre_facultad
            )

    Facultad.objects.bulk_create(
        facultades_unicas.values(),
        ignore_conflicts=True
    )

    print(f"Facultades importadas: {len(facultades_unicas)}")
