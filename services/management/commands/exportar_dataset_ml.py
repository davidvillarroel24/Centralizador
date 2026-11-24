import csv

from django.core.management.base import BaseCommand

from gatfh import config
from services.ml import features


class Command(BaseCommand):
    help = (
        "Boton 'Generar dataset' de Predicciones. Genera, directo del historial que ya "
        "existe en la base (sin esperar nada ni guardar fotos periodicas), dos CSV: "
        "dataset_riesgo_acumulacion.csv (una fila por tarea ya cerrada que un estudiante "
        "tenia asignada, prediciendo si la entrego tarde o no la entrego) y "
        "dataset_riesgo_inactividad.csv (una fila por cada entrega de un estudiante, "
        "usando sus propias fechas de entrega como eventos de acceso para medir si "
        "paso mucho tiempo hasta la siguiente). Las features se calculan con "
        "services/ml/features.py - compartido con el predictor que usa los modelos ya "
        "entrenados, para que entrenamiento e inferencia nunca calculen 'lo mismo' de dos "
        "formas distintas."
    )

    def handle(self, *args, **kwargs):
        entregas_por_estudiante = features.cargar_entregas_cerradas()
        filas_acum = self._dataset_acumulacion(entregas_por_estudiante)
        filas_inact = self._dataset_inactividad(entregas_por_estudiante)
        self._reportar(filas_acum, filas_inact)

    # ---------------------------------------------------------- modelo 1: acumulacion --
    def _dataset_acumulacion(self, entregas_por_estudiante):
        filas = []
        for estudiante_id, entregas in entregas_por_estudiante.items():
            n_previas = n_atrasos_previos = n_sin_entrega_previos = 0

            for e in entregas:
                fila = features.fila_acumulacion(e, n_previas, n_atrasos_previos, n_sin_entrega_previos)
                filas.append({
                    'estudiante_id': estudiante_id,
                    'materia_id': e.tarea.unidad.materia_id,
                    'tarea_id': e.tarea_id,
                    'cierre': e.cierre_dt.isoformat(),
                    'dia_semana_cierre': fila['dia_semana_cierre'],
                    'hora_cierre': fila['hora_cierre'],
                    'anticipacion_horas': fila['anticipacion_horas'] if fila['anticipacion_horas'] is not None else '',
                    'categoria': e.tarea.categoria or '',
                    'n_tareas_previas': fila['n_tareas_previas'],
                    'pct_atrasos_previos': fila['pct_atrasos_previos'] if fila['pct_atrasos_previos'] is not None else '',
                    'pct_sin_entrega_previos': fila['pct_sin_entrega_previos'] if fila['pct_sin_entrega_previos'] is not None else '',
                    'entrega_tardia_o_no_entregada': int(features.entrego_tarde(e)),
                })

                if e.entrega_dt is None:
                    n_sin_entrega_previos += 1
                elif features.entrego_tarde(e):
                    n_atrasos_previos += 1
                n_previas += 1

        with open(config.CSV_DATASET_ACUMULACION, 'w', newline='', encoding='utf-8') as archivo:
            if filas:
                writer = csv.DictWriter(archivo, fieldnames=filas[0].keys())
                writer.writeheader()
                writer.writerows(filas)
        return filas

    # ---------------------------------------------------------- modelo 2: inactividad -
    def _dataset_inactividad(self, entregas_por_estudiante):
        """Usa las fechas en que cada estudiante efectivamente entrego algo como eventos
        de 'acceso simulado' (entregar una tarea exige haber entrado a Moodle) para medir
        brechas de inactividad a lo largo de su propio historial, sin depender de
        AccesoCurso (que solo tiene una lectura actual, no historica). Limitacion a
        documentar: esto solo ve accesos que terminaron en una entrega, no cada visita a
        la plataforma - subestima la actividad real, nunca la sobreestima."""
        filas = []
        for estudiante_id, entregas in entregas_por_estudiante.items():
            eventos = features.eventos_de_acceso_simulado(entregas)
            if len(eventos) < 2:
                continue  # no hay "siguiente evento" con que medir una brecha

            for i in range(len(eventos) - 1):
                actual, siguiente = eventos[i], eventos[i + 1]
                brecha_dias = (siguiente.entrega_dt - actual.entrega_dt).total_seconds() / 86400

                fila = features.fila_inactividad_posicional(actual, eventos[:i], entregas)
                anticipacion_horas = features.anticipacion_horas_de(actual)

                filas.append({
                    'estudiante_id': estudiante_id,
                    'materia_id': actual.tarea.unidad.materia_id,
                    'tarea_id': actual.tarea_id,
                    'entrega': actual.entrega_dt.isoformat(),
                    'brecha_anterior_dias': fila['brecha_anterior_dias'] if fila['brecha_anterior_dias'] is not None else '',
                    'brecha_promedio_previa_dias': fila['brecha_promedio_previa_dias'] if fila['brecha_promedio_previa_dias'] is not None else '',
                    'entregas_ultimos_30d': fila['entregas_ultimos_30d'],
                    'tareas_publicadas_por_profesor_30d': fila['tareas_publicadas_por_profesor_30d'],
                    'anticipacion_horas': round(anticipacion_horas, 1) if anticipacion_horas is not None else '',
                    'inactividad_posterior': int(brecha_dias >= features.UMBRAL_INACTIVIDAD_DIAS),
                })

        with open(config.CSV_DATASET_INACTIVIDAD, 'w', newline='', encoding='utf-8') as archivo:
            if filas:
                writer = csv.DictWriter(archivo, fieldnames=filas[0].keys())
                writer.writeheader()
                writer.writerows(filas)
        return filas

    # ------------------------------------------------------------------ reporte -------
    def _reportar(self, filas_acum, filas_inact):
        self.stdout.write(self.style.SUCCESS(
            f"dataset_riesgo_acumulacion.csv: {len(filas_acum)} fila(s) en "
            f"{config.CSV_DATASET_ACUMULACION}."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"dataset_riesgo_inactividad.csv: {len(filas_inact)} fila(s) en "
            f"{config.CSV_DATASET_INACTIVIDAD}."
        ))
        if len(filas_acum) < 50 or len(filas_inact) < 50:
            self.stdout.write(self.style.WARNING(
                "Menos de 50 filas en alguno de los dos datasets: todavia no alcanza "
                "para entrenar un modelo confiable. Conviene seguir extrayendo "
                "materias/estudiantes antes de entrenar en Colab, o usar estos CSV solo "
                "para probar que el pipeline corre de punta a punta."
            ))
