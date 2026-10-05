import json
from pathlib import Path

from gatfh import config
from data.models import Nivel


def importar_niveles():

    ruta = Path(config.DATA_DIR) / "linkcarreras.json"

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)

    niveles_unicos = {}

    for item in datos:

        nombre_nivel = item.get("nivel")

        if not nombre_nivel:
            continue

        nombre_nivel = nombre_nivel.strip()

        if nombre_nivel not in niveles_unicos:

            niveles_unicos[nombre_nivel] = Nivel(
                nombre=nombre_nivel
            )

    Nivel.objects.bulk_create(
        niveles_unicos.values(),
        ignore_conflicts=True
    )

    print(f"Niveles importados: {len(niveles_unicos)}")

    return len(niveles_unicos)
