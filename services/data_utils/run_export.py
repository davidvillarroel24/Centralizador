from collections import defaultdict

import pandas as pd

from services.utils.timing import medir_tiempo
from data.models import Entrega, PesosCategorias

CATEGORIAS_PESO = ['mitek', 'etek', 'training', 'designlab', 'examen']


@medir_tiempo
def generar_excel(ids, profesor, archivo="notas.xlsx"):
    """Genera notas.xlsx directo de la base de datos (Entrega/Tarea/Estudiante), filtrado
    por los cursos seleccionados (`ids`, Materia.id) y usando los pesos por categoria del
    `profesor` logueado (PesosCategorias). Reemplaza al pipeline viejo, que leia
    estudiantes.json + asignacion.json completos sin filtrar por seleccion - mezclaba
    cursos de cualquier extraccion anterior en el mismo Excel.

    Requiere que "Importar estudiantes" (Entrega.nota/nota_maxima) e "Importar asignación"
    (Tarea.categoria/Tarea.parcial) ya hayan corrido para estos cursos."""
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
            total_parcial = 0

            for cat in CATEGORIAS_PESO:
                peso = pesos.get(cat, 0)
                notas_categoria = [
                    float(e.nota) / float(e.nota_maxima) * peso
                    for e in entregas_est
                    if e.tarea.parcial == parcial_num
                    and e.tarea.categoria == cat
                    and e.nota is not None
                    and e.nota_maxima
                ]
                valor = sum(notas_categoria) / len(notas_categoria) if notas_categoria else 0
                fila[f"P{parcial_num}_{cat}"] = round(valor, 2)
                total_parcial += valor

            fila[f"P{parcial_num}_total"] = round(total_parcial, 2)
            parciales_totales.append(total_parcial)

        fila["final"] = round(sum(parciales_totales) / len(parciales_totales), 2) if parciales_totales else 0
        filas.append(fila)

    df = pd.DataFrame(filas)
    df.to_excel(archivo, index=False)

    print(f"✅ Excel generado: {archivo} ({len(filas)} estudiante(s))")
    return len(filas)
