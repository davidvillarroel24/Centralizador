import json
import re
from pathlib import Path

from gatfh import config
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

    Moodle no usa un unico formato para el encabezado (todo lo que va antes del
    sigla-nombre): ademas del viejo "GESTION/GRUPO-TURNO" tambien aparece
    "GESTION-GRUPO-TURNO" (sin la primera barra) y, en cursos de intersemestral,
    un marcador de periodo en numeros romanos antes o en medio ("II-2026-GB-TM",
    "2025-II-G2-TM"). Si se asumia que la barra "/" dividia siempre en 3 partes
    fijas, estos formatos nuevos tiraban un IndexError (atrapado por el except de
    mas abajo) y la materia se saltaba en silencio - nunca llegaba a la base,
    aunque linkcarreras.json si la tuviera (confirmado 2026-10-22 con las
    materias 2026 de Sharon Sarabia). Por eso ahora se parte solo por la ULTIMA
    barra (el sigla-nombre nunca lleva barras) y el encabezado se tokeniza por
    "/" o "-" sin asumir una cantidad fija de partes.
    """

    try:

        encabezado, _sep, resto = texto.rpartition("/")

        if not resto:
            return None

        tokens = [t for t in re.split(r'[/-]', encabezado) if t]

        # Marcador de periodo ("I"/"II"/"III", intersemestral) - Materia no tiene
        # columna para esto, se descarta sin afectar el resto del parseo.
        tokens = [t for t in tokens if not re.fullmatch(r'I{1,3}|IV', t)]

        gestion = None
        for i, t in enumerate(tokens):
            if re.fullmatch(r'\d{4}', t):
                gestion = int(t)
                del tokens[i]
                break

        if gestion is None or len(tokens) < 2:
            return None

        grupo, turno = tokens[0], tokens[1]

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

    ruta = Path(config.DATA_DIR) / "linkcarreras.json"

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

    return materias_creadas
