from datetime import date

from django.core.management.base import BaseCommand

from data.models import ConfiguracionInstitucional, Entrega, FechasParciales, Materia, PesosCategorias
from gatfh import config
from services.data_utils.run_export import CATEGORIAS_PESO, calcular_total_parcial
from web.views import parse_date_string

import csv


class Command(BaseCommand):
    help = (
        "Exporta data/ml/dataset_ml.csv: una fila por (estudiante, materia, parcial) "
        "ya cerrado, con features de comportamiento durante el parcial y la nota "
        "ponderada como columna de referencia. Insumo para entrenar en Colab el modelo "
        "de riesgo (Random Forest) de la seccion Predicciones."
    )

    def handle(self, *args, **kwargs):
        hoy = date.today()
        nota_aprobacion = float(ConfiguracionInstitucional.actual().nota_aprobacion)

        filas = []
        # Diagnostico: con pocos datos reales (ver README §1), es mas probable terminar
        # con 0 filas que con un dataset usable - sin esto, no hay forma de saber si el
        # motivo fue "faltan pesos/fechas en /configuracion/" o "no hay entregas todavia".
        materias_sin_profesor = materias_sin_config = materias_sin_entregas = 0
        materias = Materia.objects.select_related('carrera').prefetch_related('profesores')

        for materia in materias:
            # Una materia puede tener varios profesores (M2M); por ahora se toma la
            # config del primero. Si en el futuro una materia tiene profesores con
            # pesos distintos, esto queda como aproximacion a revisar.
            profesor = materia.profesores.first()
            if profesor is None:
                materias_sin_profesor += 1
                continue
            pesos_row = PesosCategorias.objects.filter(profesor=profesor).first()
            fechas_row = FechasParciales.objects.filter(profesor=profesor).first()
            if pesos_row is None or fechas_row is None:
                materias_sin_config += 1
                continue
            pesos = {cat: getattr(pesos_row, cat, 0) for cat in CATEGORIAS_PESO}

            entregas = list(
                Entrega.objects
                .filter(tarea__tipo='assign', tarea__unidad__materia=materia)
                .select_related('tarea', 'estudiante')
            )
            if not entregas:
                materias_sin_entregas += 1
                continue

            por_estudiante = {}
            for entrega in entregas:
                por_estudiante.setdefault(entrega.estudiante_id, []).append(entrega)

            for parcial_num in range(1, 5):
                fin = getattr(fechas_row, f'p{parcial_num}_fin')
                if not fin or fin >= hoy:
                    continue  # solo parciales ya cerrados: ahi se conoce el resultado real

                tareas_parcial_ids = {e.tarea_id for e in entregas if e.tarea.parcial == parcial_num}
                n_tareas_parcial = len(tareas_parcial_ids)
                if n_tareas_parcial == 0:
                    continue

                for estudiante_id, entregas_est in por_estudiante.items():
                    entregas_parcial = [e for e in entregas_est if e.tarea.parcial == parcial_num]
                    if not entregas_parcial:
                        continue  # el estudiante no tiene ni un registro de Entrega en este parcial

                    n_sin_entrega = sum(
                        1 for e in entregas_parcial
                        if e.estado and 'sin entrega' in e.estado.lower()
                    )
                    n_calificadas = sum(1 for e in entregas_parcial if e.nota is not None)
                    n_sin_registro = n_tareas_parcial - len(entregas_parcial)

                    dias_atraso = []
                    for e in entregas_parcial:
                        if not e.ultima_mod_entrega or not e.tarea.cierre:
                            continue
                        f_entrega = parse_date_string(e.ultima_mod_entrega)
                        f_cierre = parse_date_string(e.tarea.cierre)
                        if f_entrega and f_cierre:
                            delta = (f_entrega - f_cierre).days
                            if delta > 0:
                                dias_atraso.append(delta)

                    nota_parcial = calcular_total_parcial(entregas_parcial, parcial_num, pesos)

                    filas.append({
                        'estudiante_id': estudiante_id,
                        'materia_id': materia.id,
                        'carrera': materia.carrera.nombre,
                        'parcial': parcial_num,
                        'n_tareas_parcial': n_tareas_parcial,
                        'pct_sin_entrega': round((n_sin_entrega + n_sin_registro) / n_tareas_parcial, 3),
                        'pct_calificadas': round(n_calificadas / n_tareas_parcial, 3),
                        'dias_atraso_promedio': round(sum(dias_atraso) / len(dias_atraso), 2) if dias_atraso else 0,
                        'n_entregas_atrasadas': len(dias_atraso),
                        'nota_parcial': round(nota_parcial, 2),
                        'en_riesgo': int(nota_parcial < nota_aprobacion),
                    })

        with open(config.CSV_DATASET_ML, 'w', newline='', encoding='utf-8') as archivo:
            if filas:
                writer = csv.DictWriter(archivo, fieldnames=filas[0].keys())
                writer.writeheader()
                writer.writerows(filas)

        total_materias = materias.count()
        self.stdout.write(
            f"Materias revisadas: {total_materias} - sin profesor enlazado: "
            f"{materias_sin_profesor}, sin PesosCategorias/FechasParciales en "
            f"/configuracion/: {materias_sin_config}, sin entregas de tipo 'assign': "
            f"{materias_sin_entregas}."
        )
        self.stdout.write(self.style.SUCCESS(
            f"Dataset exportado: {len(filas)} fila(s) en {config.CSV_DATASET_ML}."
        ))
        if len(filas) < 50:
            self.stdout.write(self.style.WARNING(
                "Menos de 50 filas: no alcanza todavia para entrenar un modelo "
                "confiable. Conviene seguir extrayendo materias/estudiantes antes de "
                "entrenar en Colab, o usar este CSV solo para probar que el pipeline "
                "corre de punta a punta."
            ))
