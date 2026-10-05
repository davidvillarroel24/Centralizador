import json
from pathlib import Path

from gatfh import config
from data.models import Facultad, Carrera


def importar_carreras():

    ruta = Path(config.DATA_DIR) / "linkcarreras.json"

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)

    carreras_unicas = {}

    for item in datos:

        nombre_facultad = item.get("facultad")
        nombre_carrera = item.get("carrera")

        if not nombre_facultad or not nombre_carrera:
            continue

        nombre_facultad = nombre_facultad.strip()
        nombre_carrera = nombre_carrera.strip()

        try:
            facultad = Facultad.objects.get(
                nombre=nombre_facultad
            )

        except Facultad.DoesNotExist:
            continue

        clave = f"{facultad.id}_{nombre_carrera}"

        if clave not in carreras_unicas:

            carreras_unicas[clave] = Carrera(
                facultad=facultad,
                nombre=nombre_carrera
            )

    Carrera.objects.bulk_create(
        carreras_unicas.values(),
        ignore_conflicts=True
    )

    print(f"Carreras importadas: {len(carreras_unicas)}")

    return len(carreras_unicas)
