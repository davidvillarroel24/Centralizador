import json
from pathlib import Path

from gatfh import config
from data.models import Profesor


def importar_profesores():
    # Ruta del JSON
    ruta = Path(config.DATA_DIR) / "linkcarreras.json"

    with open(ruta, "r", encoding="utf-8") as f:
        carreras = json.load(f)

    profesores_unicos = {}

    # Recorrer carreras
    for carrera in carreras:

        # Obtener materias
        materias = carrera.get("materias") or []

        for materia in materias:

            # Obtener profesores
            profesores =  materia.get("profesor") or []
            
            for profesor in profesores:

                moodle_id = profesor.get("id")

                # Validar datos mínimos
                if not moodle_id:
                    continue

                # Evitar duplicados
                if moodle_id not in profesores_unicos:

                    profesores_unicos[moodle_id] = Profesor(
                        moodle_id=int(moodle_id),
                        nombre=profesor.get("nombre", "").strip(),
                        url=profesor.get("url", "")
                    )

    # Bulk create
    Profesor.objects.bulk_create(
        profesores_unicos.values(),
        ignore_conflicts=True
    )

    print(f"Profesores importados: {len(profesores_unicos)}")

    return len(profesores_unicos)
