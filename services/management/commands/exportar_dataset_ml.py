import csv
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand

from data.models import Entrega
from gatfh import config

# Mismo diccionario que web/views.py::MESES, duplicado aca para no depender de un import
# cruzado hacia web (este comando corre tambien desde consola/cron sin request).
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}

# Umbral de "inactividad prolongada" para el modelo 2: dias sin una entrega (usada como
# evento de acceso simulado) antes de considerar que hubo un bache de inactividad.
# Ajustable con mas datos (ver seccion 5.4 del documento de requerimientos, que usa 14
# dias como "inactividad considerable").
UMBRAL_INACTIVIDAD_DIAS = 14

VENTANA_RITMO_DIAS = 30  # para "cuantas entregas tuvo en los ultimos N dias" (modelo 2)


def parse_fecha_hora(texto):
    """Tarea.apertura/cierre y Entrega.ultima_mod_entrega llegan de Moodle como texto
    absoluto ("lunes, 7 de julio de 2025, 20:30"), a diferencia de AccesoCurso.ultimo_acceso
    (relativo, "119 dias 14 horas") - por eso esto no depende de cuando se extrajo el dato,
    siempre da la misma fecha sin importar que dia se corra el comando."""
    if not texto:
        return None
    try:
        partes = texto.split(',')
        fecha_texto = partes[1].strip()
        dia, _, resto = fecha_texto.partition(' de ')
        mes, _, anio = resto.partition(' de ')
        hora, minuto = 0, 0
        if len(partes) > 2 and ':' in partes[2]:
            hora, minuto = map(int, partes[2].strip().split(':'))
        return datetime(int(anio), MESES[mes.lower()], int(dia), hora, minuto)
    except Exception:
        return None


class Command(BaseCommand):
    help = (
        "Boton 'Generar dataset' de Predicciones. Genera, directo del historial que ya "
        "existe en la base (sin esperar nada ni guardar fotos periodicas), dos CSV: "
        "dataset_riesgo_acumulacion.csv (una fila por tarea ya cerrada que un estudiante "
        "tenia asignada, prediciendo si la entrego tarde o no la entrego) y "
        "dataset_riesgo_inactividad.csv (una fila por cada entrega de un estudiante, "
        "usando sus propias fechas de entrega como eventos de acceso para medir si "
        "paso mucho tiempo hasta la siguiente)."
    )

    def handle(self, *args, **kwargs):
        entregas_por_estudiante = self._cargar_entregas()
        filas_acum = self._dataset_acumulacion(entregas_por_estudiante)
        filas_inact = self._dataset_inactividad(entregas_por_estudiante)
        self._reportar(filas_acum, filas_inact)

    def _cargar_entregas(self):
        """Todas las entregas de tareas tipo 'assign' con fecha de cierre ya pasada (el
        resultado, a tiempo/tarde/sin entregar, ya se conoce por completo - no hay nada
        que esperar), agrupadas por estudiante y ordenadas cronologicamente por el cierre
        de la tarea. Cada entrega lleva ya resuelto: cierre_dt, apertura_dt,
        entrega_dt (o None si nunca entrego) y atraso_horas (None si no aplica)."""
        ahora = datetime.now()
        entregas = list(
            Entrega.objects
            .filter(tarea__tipo='assign', tarea__unidad__materia__activo=True)
            .select_related('tarea', 'tarea__unidad', 'tarea__unidad__materia', 'estudiante')
        )

        por_estudiante = defaultdict(list)
        for e in entregas:
            tarea = e.tarea
            cierre_dt = parse_fecha_hora(tarea.cierre)
            if not cierre_dt or cierre_dt >= ahora:
                continue  # solo tareas ya cerradas: ahi se conoce el resultado real
            apertura_dt = parse_fecha_hora(tarea.apertura)

            sin_entregar = not e.estado or 'sin entrega' in e.estado.lower()
            entrega_dt = None if sin_entregar else parse_fecha_hora(e.ultima_mod_entrega)

            atraso_horas = None
            if entrega_dt:
                atraso_horas = (entrega_dt - cierre_dt).total_seconds() / 3600

            e.cierre_dt = cierre_dt
            e.apertura_dt = apertura_dt
            e.entrega_dt = entrega_dt
            e.atraso_horas = atraso_horas
            por_estudiante[e.estudiante_id].append(e)

        for lista in por_estudiante.values():
            lista.sort(key=lambda e: e.cierre_dt)
        return por_estudiante

    # ---------------------------------------------------------- modelo 1: acumulacion --
    def _dataset_acumulacion(self, entregas_por_estudiante):
        filas = []
        for estudiante_id, entregas in entregas_por_estudiante.items():
            n_previas = n_atrasos_previos = n_sin_entrega_previos = 0

            for e in entregas:
                entrego_tarde = e.entrega_dt is None or (e.atraso_horas is not None and e.atraso_horas > 0)

                anticipacion_horas = None
                if e.apertura_dt:
                    anticipacion_horas = (e.cierre_dt - e.apertura_dt).total_seconds() / 3600

                filas.append({
                    'estudiante_id': estudiante_id,
                    'materia_id': e.tarea.unidad.materia_id,
                    'tarea_id': e.tarea_id,
                    'cierre': e.cierre_dt.isoformat(),
                    'dia_semana_cierre': e.cierre_dt.weekday(),  # 0=lunes .. 6=domingo
                    'hora_cierre': e.cierre_dt.hour,
                    'anticipacion_horas': round(anticipacion_horas, 1) if anticipacion_horas is not None else '',
                    'categoria': e.tarea.categoria or '',
                    # Historial SOLO con tareas anteriores a esta (ordenadas por cierre):
                    # nunca se usa informacion de tareas que cerraron despues, para no
                    # filtrar al modelo el futuro dentro de su propio entrenamiento.
                    'n_tareas_previas': n_previas,
                    'pct_atrasos_previos': round(n_atrasos_previos / n_previas, 3) if n_previas else '',
                    'pct_sin_entrega_previos': round(n_sin_entrega_previos / n_previas, 3) if n_previas else '',
                    'entrega_tardia_o_no_entregada': int(entrego_tarde),
                })

                if e.entrega_dt is None:
                    n_sin_entrega_previos += 1
                elif entrego_tarde:
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
            eventos = [e for e in entregas if e.entrega_dt]
            eventos.sort(key=lambda e: e.entrega_dt)
            if len(eventos) < 2:
                continue  # no hay "siguiente evento" con que medir una brecha

            for i in range(len(eventos) - 1):
                actual, siguiente = eventos[i], eventos[i + 1]
                brecha_dias = (siguiente.entrega_dt - actual.entrega_dt).total_seconds() / 86400

                previos = eventos[:i]
                gaps_previos = [
                    (previos[j + 1].entrega_dt - previos[j].entrega_dt).total_seconds() / 86400
                    for j in range(len(previos) - 1)
                ]
                entregas_ultimos_30d = sum(
                    1 for e in previos
                    if (actual.entrega_dt - e.entrega_dt).days <= VENTANA_RITMO_DIAS
                )
                tareas_publicadas_30d = sum(
                    1 for e in entregas
                    if e.apertura_dt and 0 <= (actual.entrega_dt - e.apertura_dt).days <= VENTANA_RITMO_DIAS
                )
                anticipacion_horas = None
                if actual.apertura_dt:
                    anticipacion_horas = (actual.cierre_dt - actual.apertura_dt).total_seconds() / 3600

                filas.append({
                    'estudiante_id': estudiante_id,
                    'materia_id': actual.tarea.unidad.materia_id,
                    'tarea_id': actual.tarea_id,
                    'entrega': actual.entrega_dt.isoformat(),
                    'brecha_anterior_dias': round(gaps_previos[-1], 1) if gaps_previos else '',
                    'brecha_promedio_previa_dias': round(sum(gaps_previos) / len(gaps_previos), 1) if gaps_previos else '',
                    'entregas_ultimos_30d': entregas_ultimos_30d,
                    'tareas_publicadas_por_profesor_30d': tareas_publicadas_30d,
                    'anticipacion_horas': round(anticipacion_horas, 1) if anticipacion_horas is not None else '',
                    'inactividad_posterior': int(brecha_dias >= UMBRAL_INACTIVIDAD_DIAS),
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
