from collections import defaultdict

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


@medir_tiempo
def generar_excel(ids, profesor, archivo=None):
    """Genera el Excel directo de la base de datos (Entrega/Tarea/Estudiante), filtrado
    por los cursos seleccionados (`ids`, Materia.id) y usando los pesos por categoria del
    `profesor` logueado (PesosCategorias). Reemplaza al pipeline viejo, que leia
    estudiantes.json + asignacion.json completos sin filtrar por seleccion - mezclaba
    cursos de cualquier extraccion anterior en el mismo Excel.

    `archivo`: ruta en disco, un buffer tipo BytesIO (pandas acepta ambos por igual - lo
    usa el boton web para armar la descarga directa sin tocar el disco), o None para
    guardar en un archivo propio por profesor (notas_profesor_<id>.xlsx) y evitar que dos
    profesores se pisen el mismo "notas.xlsx" compartido, como pasaba antes.

    Requiere que "Importar estudiantes" (Entrega.nota/nota_maxima) e "Importar asignación"
    (Tarea.categoria/Tarea.parcial) ya hayan corrido para estos cursos.

    Devuelve (cantidad_de_filas, archivo)."""
    if archivo is None:
        archivo = f"notas_profesor_{profesor.id}.xlsx"

    pesos_row = PesosCategorias.objects.filter(profesor=profesor).first()
    pesos = {cat: getattr(pesos_row, cat, 0) if pesos_row else 0 for cat in CATEGORIAS_PESO}

    entregas = (
        Entrega.objects.filter(tarea__tipo='assign', tarea__unidad__materia_id__in=ids)
        .select_related('tarea', 'estudiante')
    )

    por_estudiante = defaultdict(list)
    for entrega in entregas:
        por_estudiante[entrega.estudiante].append(entrega)

    filas = []
    for estudiante, entregas_est in por_estudiante.items():
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

    df = pd.DataFrame(filas)
    df.to_excel(archivo, index=False)
    if hasattr(archivo, "seek"):
        archivo.seek(0)

    print(f"✅ Excel generado: {archivo} ({len(filas)} estudiante(s))")
    return len(filas), archivo
