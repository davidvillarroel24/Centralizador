"""Inferencia en vivo con los modelos ya entrenados (ver §11 del README): carga los
.joblib una sola vez por proceso de gunicorn (no por request) y arma las features con
services/ml/features.py - las mismas funciones que usa exportar_dataset_ml.py para el
entrenamiento, para que entrenamiento e inferencia nunca calculen "lo mismo" de dos
formas distintas."""
from datetime import datetime

import joblib
import pandas as pd

from data.models import Entrega
from gatfh import config
from services.ml import features

_modelo_acumulacion = None
_modelo_inactividad = None


def _cargar_modelos():
    global _modelo_acumulacion, _modelo_inactividad
    if _modelo_acumulacion is None:
        _modelo_acumulacion = joblib.load(config.MODELO_ACUMULACION)
    if _modelo_inactividad is None:
        _modelo_inactividad = joblib.load(config.MODELO_INACTIVIDAD)


def _tareas_abiertas():
    """Entregas de tareas tipo 'assign' TODAVÍA ABIERTAS (cierre en el futuro), de
    materias activas - el universo sobre el que se aplica el modelo de acumulación. Una
    tarea sin fecha de cierre se descarta (dia_semana_cierre/hora_cierre no se pueden
    calcular sin ella)."""
    ahora = datetime.now()
    entregas = list(
        Entrega.objects.filter(tarea__tipo='assign', tarea__unidad__materia__activo=True)
        .select_related('tarea', 'tarea__unidad', 'tarea__unidad__materia', 'estudiante')
    )
    abiertas = []
    for e in entregas:
        cierre_dt = features.parse_fecha_hora(e.tarea.cierre)
        if not cierre_dt or cierre_dt <= ahora:
            continue
        e.cierre_dt = cierre_dt
        e.apertura_dt = features.parse_fecha_hora(e.tarea.apertura)
        abiertas.append(e)
    return abiertas


def predicciones_acumulacion():
    """[(estudiante_id, tarea_id, probabilidad), ...] para cada tarea todavía abierta,
    usando el historial de tareas YA CERRADAS de cada estudiante hasta ahora (mismo
    acumulador que el entrenamiento, evaluado al final en vez de fila a fila)."""
    _cargar_modelos()
    historiales = features.cargar_entregas_cerradas()
    abiertas = _tareas_abiertas()
    if not abiertas:
        return []

    filas, claves = [], []
    for e in abiertas:
        n_previas, n_atrasos, n_sin_entrega = features.historial_acumulacion_hasta_ahora(
            historiales.get(e.estudiante_id, [])
        )
        filas.append(features.fila_acumulacion(e, n_previas, n_atrasos, n_sin_entrega))
        claves.append((e.estudiante_id, e.tarea_id))

    df = pd.DataFrame(filas, columns=features.COLUMNAS_ACUMULACION)
    probabilidades = _modelo_acumulacion.predict_proba(df)[:, 1]
    return [(est_id, tarea_id, float(p)) for (est_id, tarea_id), p in zip(claves, probabilidades)]


def predicciones_inactividad():
    """[(estudiante_id, probabilidad), ...] para cada estudiante con al menos una entrega
    real, evaluando su ÚLTIMA entrega conocida - la única donde todavía no se sabe si va a
    tardar 14+ días en la próxima. anticipacion_horas usa el PROMEDIO histórico del
    estudiante (decisión 2026-11-23): en vivo no hay una tarea "actual" equivalente a la
    que usa el entrenamiento para esa feature puntual."""
    _cargar_modelos()
    historiales = features.cargar_entregas_cerradas()

    filas, claves = [], []
    for estudiante_id, entregas in historiales.items():
        eventos = features.eventos_de_acceso_simulado(entregas)
        if not eventos:
            continue
        actual, previos = eventos[-1], eventos[:-1]
        fila = features.fila_inactividad_posicional(actual, previos, entregas)

        anticipaciones = [
            h for h in (features.anticipacion_horas_de(e) for e in eventos) if h is not None
        ]
        fila['anticipacion_horas'] = (
            round(sum(anticipaciones) / len(anticipaciones), 1) if anticipaciones else None
        )

        filas.append(fila)
        claves.append(estudiante_id)

    if not filas:
        return []

    df = pd.DataFrame(filas, columns=features.COLUMNAS_INACTIVIDAD)
    probabilidades = _modelo_inactividad.predict_proba(df)[:, 1]
    return [(est_id, float(p)) for est_id, p in zip(claves, probabilidades)]
