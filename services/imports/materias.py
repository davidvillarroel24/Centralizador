import json
import re
from pathlib import Path

from data.models import (
    Carrera,
    Nivel,
    Profesor,
    Materia
)


def parsear_materia(texto):

    """
    Convierte:
    2025/G2-TN/SIS-BDD-208-Base de Datos I

    en:
    gestion, grupo, turno, sigla, nombre
    """

    try:

        partes = texto.split("/")

        gestion_texto = partes[0]

        match_gestion = re.search(r'(\d{4})', gestion_texto)

        if not match_gestion:
            return None

        gestion = int(match_gestion.group(1))

        codigo = partes[1]

        resto = partes[2]

        codigo_partes = codigo.split("-")

        grupo = codigo_partes[0]
        turno = codigo_partes[1]

        match = re.match(
            r'^([A-Z]+(?:-[A-Z]+)?-\d+)-(.*)$',
            resto
        )

        if not match:
            return None

        sigla = match.group(1).strip()
        nombre = match.group(2).strip()

        return {
            "gestion": gestion,
            "grupo": grupo,
            "turno": turno,
            "sigla": sigla,
            "nombre": nombre
        }

    except Exception:

        return None


def importar_materias():

    ruta = Path("data/raw/linkcarreras.json")

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)

    materias_creadas = 0

    for item in datos:

        nombre_carrera = item.get("carrera")
        nombre_nivel = item.get("nivel")

        if not nombre_carrera:
            continue

        try:
            carrera = Carrera.objects.get(
                nombre=nombre_carrera.strip()
            )

        except Carrera.DoesNotExist:
            continue

        nivel = None

        if nombre_nivel:

            nivel = Nivel.objects.filter(
                nombre=nombre_nivel.strip()
            ).first()

        materias = item.get("materias") or []

        for materia_json in materias:

            moodle_nombre = materia_json.get("materia")

            if not moodle_nombre:
                continue

            datos_parseados = parsear_materia(
                moodle_nombre
            )

            if not datos_parseados:
                continue

            materia, creada = Materia.objects.get_or_create(

                moodle_nombre=moodle_nombre,

                defaults={

                    "gestion": datos_parseados["gestion"],
                    "grupo": datos_parseados["grupo"],
                    "turno": datos_parseados["turno"],
                    "sigla": datos_parseados["sigla"],
                    "nombre": datos_parseados["nombre"],

                    "moodle_url": materia_json.get("url", ""),

                    "carrera": carrera,
                    "nivel": nivel
                }
            )

            if creada:
                materias_creadas += 1

            # Profesores
            profesores = materia_json.get("profesor") or []

            for profesor_json in profesores:

                moodle_id = profesor_json.get("id")

                if not moodle_id:
                    continue

                profesor = Profesor.objects.filter(
                    moodle_id=int(moodle_id)
                ).first()

                if profesor:
                    materia.profesores.add(profesor)

    print(f"Materias creadas: {materias_creadas}")
