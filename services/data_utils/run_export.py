from collections import defaultdict
from io import BytesIO

import pandas as pd

from services.utils.timing import medir_tiempo
from data.models import Entrega, PesosCategorias

CATEGORIAS_PESO = ['mitek', 'etek', 'training', 'designlab', 'examen']


def calcular_nota_categoria(entregas_est, parcial_num, cat, peso):
    """Nota de una sola categoria (Mi-Tek/E-Tek/Training/Design Lab/Examen) dentro de un
    parcial, ya en la escala de su peso.

    `nota`/`nota_maxima` de cada tarea vienen tal cual las puso el docente en Moodle, que
    no son consistentes entre si (algunos ponderan sobre 100, otros sobre el puntaje de la
    tarea, otros a eleccion libre) - por eso cada tarea se normaliza individualmente antes
    de combinarla: `peso_categoria * (nota / nota_maxima)` da la "nota real" de esa tarea
    ya en la escala del peso de su categoria. Las normalizadas de una misma categoria se
    suman y se dividen entre el **total de tareas de esa categoria en el parcial** (no
    solo las que ya tienen nota) - una tarea sin calificar cuenta en el denominador y
    aporta 0 al numerador, en vez de excluirse del promedio (que inflaria la nota de un
    estudiante con pocas entregas calificadas, como si lo no calificado no existiera).
    Una categoria sin ninguna tarea asignada en ese parcial devuelve 0."""
    entregas_cat = [
        e for e in entregas_est
        if e.tarea.parcial == parcial_num and e.tarea.categoria == cat
    ]
    if not entregas_cat:
        return 0  # sin tareas de esta categoria en el parcial: no aporta
    suma_normalizada = sum(
        float(e.nota) / float(e.nota_maxima) * peso
        for e in entregas_cat
        if e.nota is not None and e.nota_maxima
    )
    # Entre TODAS las tareas de la categoria, calificadas o no - una sin calificar cuenta
    # en el denominador y aporta 0, no se excluye del promedio.
    return suma_normalizada / len(entregas_cat)


def calcular_total_parcial(entregas_est, parcial_num, pesos):
    """Nota de un estudiante en un parcial: suma de `calcular_nota_categoria` sobre las 5
    categorias (Mi-Tek/E-Tek/Training/Design Lab/Examen) con los pesos del profesor
    (PesosCategorias). No se re-normaliza sobre las categorias presentes - si `pesos` suma
    100, el resultado queda "sobre 100" solo cuando las 5 categorias tienen tareas ese
    parcial.

    Extraida de `generar_excel` para que el dataset de entrenamiento del modelo de
    riesgo (`exportar_dataset_ml`) etiquete cada fila con la misma nota que el profesor
    ya ve en el Excel, en vez de una formula paralela que podria divergir."""
    return sum(
        calcular_nota_categoria(entregas_est, parcial_num, cat, pesos.get(cat, 0))
        for cat in CATEGORIAS_PESO
    )


def _filas_de_materia(entregas_est_por_estudiante, pesos):
    """[{"nombre", "P1_mitek", ..., "final"}, ...] para UNA materia - extraida de
    generar_excel para poder armar un archivo por materia en vez de uno solo mezclado
    (decisión 2026-11-27: con más de un curso tildado, un mismo estudiante inscrito en
    varios mezclaba sus notas de todos en una sola fila, sin poder saber de qué curso era
    cada una)."""
    filas = []
    for estudiante, entregas_est in entregas_est_por_estudiante.items():
        fila = {"nombre": estudiante.nombre}
        parciales_totales = []

        for parcial_num in range(1, 5):
            for cat in CATEGORIAS_PESO:
                valor = calcular_nota_categoria(entregas_est, parcial_num, cat, pesos.get(cat, 0))
                fila[f"P{parcial_num}_{cat}"] = round(valor, 2)

            total_parcial = calcular_total_parcial(entregas_est, parcial_num, pesos)
            fila[f"P{parcial_num}_total"] = round(total_parcial, 2)
            parciales_totales.append(total_parcial)

        fila["final"] = round(sum(parciales_totales) / len(parciales_totales), 2) if parciales_totales else 0
        filas.append(fila)

    filas.sort(key=lambda f: f['nombre'])
    return filas


@medir_tiempo
def generar_excel(ids, profesor):
    """Genera UN Excel por cada curso seleccionado (`ids`, Materia.id) - antes era un solo
    archivo con todos los cursos mezclados (una columna "materia" para distinguirlos); con
    más de un curso tildado a la vez eso resultaba confuso para abrir/revisar, así que ahora
    cada materia es su propio archivo (decisión 2026-11-27). Usa los pesos por categoría del
    `profesor` logueado (PesosCategorias).

    Requiere que "Importar estudiantes" (Entrega.nota/nota_maxima) e "Importar asignación"
    (Tarea.categoria/Tarea.parcial) ya hayan corrido para estos cursos.

    Devuelve [(materia, cantidad_de_filas, buffer_xlsx), ...] - una entrada por cada materia
    de `ids` que tenga al menos una entrega de tipo 'assign' (las que no, no generan archivo
    vacío)."""
    pesos_row = PesosCategorias.objects.filter(profesor=profesor).first()
    pesos = {cat: getattr(pesos_row, cat, 0) if pesos_row else 0 for cat in CATEGORIAS_PESO}

    entregas = (
        Entrega.objects.filter(tarea__tipo='assign', tarea__unidad__materia_id__in=ids)
        .select_related('tarea__unidad__materia', 'estudiante')
    )

    materias_por_id = {}
    por_materia_estudiante = defaultdict(lambda: defaultdict(list))
    for entrega in entregas:
        materia = entrega.tarea.unidad.materia
        materias_por_id[materia.id] = materia
        por_materia_estudiante[materia.id][entrega.estudiante].append(entrega)

    # Se recorre `ids` (no las claves de por_materia_estudiante) para mantener el orden en
    # que el usuario tildó los cursos.
    resultados = []
    for materia_id in ids:
        entregas_est_por_estudiante = por_materia_estudiante.get(materia_id)
        if not entregas_est_por_estudiante:
            continue
        materia = materias_por_id[materia_id]
        filas = _filas_de_materia(entregas_est_por_estudiante, pesos)

        buffer = BytesIO()
        pd.DataFrame(filas).to_excel(buffer, index=False)
        buffer.seek(0)
        resultados.append((materia, len(filas), buffer))

    total_filas = sum(cantidad for _materia, cantidad, _buffer in resultados)
    print(f"✅ Excel generado: {len(resultados)} archivo(s), {total_filas} fila(s) en total")
    return resultados
