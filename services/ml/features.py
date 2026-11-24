"""Features compartidas entre el entrenamiento (exportar_dataset_ml, que arma los CSV
para Colab) y la inferencia en vivo (services/ml/predictor.py). UNA sola implementación
de cada cuenta (dia_semana_cierre, pct_atrasos_previos, brecha_anterior_dias...) para que
nunca diverjan entre lo que el modelo aprendió y lo que se le pide que prediga - el mismo
tipo de bug que ya encontramos y arreglamos con el "texto en línea" (dos caminos de código
calculando "lo mismo" terminan divergiendo sin que nadie lo note).

Los nombres/columnas acá coinciden exactamente con feature_names_in_ de los .joblib
entrenados (ver data/ml/modelo_acumulacion.joblib / modelo_inactividad.joblib)."""
from collections import defaultdict
from datetime import datetime

from data.models import Entrega

# Mismo diccionario que web/views.py::MESES, duplicado a propósito (ver
# exportar_dataset_ml.py original): este módulo no depende de web para poder usarse
# también desde comandos de consola/cron.
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}

# Umbral de "inactividad prolongada" usado al entrenar el modelo 2 (ver sección 5.4 del
# documento de requerimientos): días sin una entrega (evento de acceso simulado) antes de
# considerar que hubo un bache de inactividad.
UMBRAL_INACTIVIDAD_DIAS = 14
VENTANA_RITMO_DIAS = 30  # "cuántas entregas/tareas tuvo en los últimos N días" (modelo 2)

# Una categoría queda afuera como base de la codificación one-hot (drop_first): al
# entrenar en Colab, pandas.get_dummies ordenó las categorías alfabéticamente y dejó
# "examen" como esa base - por eso no tiene columna propia acá.
CATEGORIAS_ONEHOT = ['designlab', 'etek', 'mitek', 'training']

COLUMNAS_ACUMULACION = [
    'dia_semana_cierre', 'hora_cierre', 'anticipacion_horas', 'n_tareas_previas',
    'pct_atrasos_previos', 'pct_sin_entrega_previos',
    'categoria_designlab', 'categoria_etek', 'categoria_mitek', 'categoria_training',
]
COLUMNAS_INACTIVIDAD = [
    'brecha_anterior_dias', 'brecha_promedio_previa_dias', 'entregas_ultimos_30d',
    'tareas_publicadas_por_profesor_30d', 'anticipacion_horas',
]


def parse_fecha_hora(texto):
    """Tarea.apertura/cierre y Entrega.ultima_mod_entrega llegan de Moodle como texto
    absoluto ("lunes, 7 de julio de 2025, 20:30"), a diferencia de AccesoCurso.ultimo_acceso
    (relativo, "119 dias 14 horas") - por eso esto no depende de cuando se extrajo el dato,
    siempre da la misma fecha sin importar qué día se corra."""
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


def cargar_entregas_cerradas(estudiante_id=None):
    """Entregas de tareas tipo 'assign' YA CERRADAS (el resultado - a tiempo/tarde/sin
    entregar - ya se conoce por completo), agrupadas por estudiante y ordenadas
    cronológicamente por el cierre de la tarea. Cada entrega queda con cierre_dt/
    apertura_dt/entrega_dt/atraso_horas ya resueltos. Mismo filtro para entrenamiento e
    inferencia - es lo que hace que ambos usen exactamente el mismo universo de datos."""
    ahora = datetime.now()
    qs = Entrega.objects.filter(tarea__tipo='assign', tarea__unidad__materia__activo=True)
    if estudiante_id is not None:
        qs = qs.filter(estudiante_id=estudiante_id)
    entregas = list(
        qs.select_related('tarea', 'tarea__unidad', 'tarea__unidad__materia', 'estudiante')
    )

    por_estudiante = defaultdict(list)
    for e in entregas:
        tarea = e.tarea
        cierre_dt = parse_fecha_hora(tarea.cierre)
        if not cierre_dt or cierre_dt >= ahora:
            continue
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


def entrego_tarde(entrega):
    return entrega.entrega_dt is None or (entrega.atraso_horas is not None and entrega.atraso_horas > 0)


def _categoria_onehot(categoria):
    return {f'categoria_{c}': int(categoria == c) for c in CATEGORIAS_ONEHOT}


# ------------------------------------------------------------- modelo 1: acumulación ----
def fila_acumulacion(entrega, n_previas, n_atrasos_previos, n_sin_entrega_previos):
    """Las 10 features del modelo de acumulación para UNA tarea/entrega, dado el estado
    del historial justo ANTES de ella. Usado fila por fila (avanzando el historial) al
    exportar el dataset, y una sola vez (con el historial completo hasta hoy) al predecir
    en vivo sobre una tarea todavía abierta."""
    anticipacion_horas = None
    if entrega.apertura_dt:
        anticipacion_horas = (entrega.cierre_dt - entrega.apertura_dt).total_seconds() / 3600
    fila = {
        'dia_semana_cierre': entrega.cierre_dt.weekday(),  # 0=lunes .. 6=domingo
        'hora_cierre': entrega.cierre_dt.hour,
        'anticipacion_horas': round(anticipacion_horas, 1) if anticipacion_horas is not None else None,
        'n_tareas_previas': n_previas,
        'pct_atrasos_previos': round(n_atrasos_previos / n_previas, 3) if n_previas else None,
        'pct_sin_entrega_previos': round(n_sin_entrega_previos / n_previas, 3) if n_previas else None,
    }
    fila.update(_categoria_onehot(entrega.tarea.categoria or ''))
    return fila


def historial_acumulacion_hasta_ahora(entregas_cerradas_estudiante):
    """n_previas/n_atrasos_previos/n_sin_entrega_previos TOTALES de un estudiante, tras
    procesar todo su historial de tareas ya cerradas - el mismo acumulador que se avanza
    fila a fila al exportar, pero evaluado al final: "cómo está su historial ahora", para
    aplicarlo a una tarea todavía abierta."""
    n_previas = n_atrasos = n_sin_entrega = 0
    for e in entregas_cerradas_estudiante:
        if e.entrega_dt is None:
            n_sin_entrega += 1
        elif entrego_tarde(e):
            n_atrasos += 1
        n_previas += 1
    return n_previas, n_atrasos, n_sin_entrega


# -------------------------------------------------------------- modelo 2: inactividad ---
def eventos_de_acceso_simulado(entregas_cerradas_estudiante):
    """Entregas con fecha real (las únicas que sirven de "evento de acceso simulado"),
    ordenadas cronológicamente - mismo recorte que usa el entrenamiento."""
    eventos = [e for e in entregas_cerradas_estudiante if e.entrega_dt]
    eventos.sort(key=lambda e: e.entrega_dt)
    return eventos


def fila_inactividad_posicional(evento_actual, previos, eventos_totales):
    """Las 4 features "posicionales" del modelo de inactividad (todo menos
    anticipacion_horas, que se calcula distinto en entrenamiento vs. inferencia - ver
    predictor.py), ancladas en `evento_actual`: brecha hasta el evento anterior, promedio
    de brechas previas, y ritmo de entregas/publicaciones en los últimos 30 días contados
    desde `evento_actual`. Mismo cálculo para entrenamiento (evento_actual = cada entrega,
    salvo la última) y para inferencia (evento_actual = la ÚLTIMA entrega real del
    estudiante, que es la única donde todavía no se sabe si va a tardar 14+ días en la
    próxima)."""
    gaps_previos = [
        (previos[j + 1].entrega_dt - previos[j].entrega_dt).total_seconds() / 86400
        for j in range(len(previos) - 1)
    ]
    entregas_ultimos_30d = sum(
        1 for e in previos
        if (evento_actual.entrega_dt - e.entrega_dt).days <= VENTANA_RITMO_DIAS
    )
    tareas_publicadas_30d = sum(
        1 for e in eventos_totales
        if e.apertura_dt and 0 <= (evento_actual.entrega_dt - e.apertura_dt).days <= VENTANA_RITMO_DIAS
    )
    return {
        'brecha_anterior_dias': round(gaps_previos[-1], 1) if gaps_previos else None,
        'brecha_promedio_previa_dias': round(sum(gaps_previos) / len(gaps_previos), 1) if gaps_previos else None,
        'entregas_ultimos_30d': entregas_ultimos_30d,
        'tareas_publicadas_por_profesor_30d': tareas_publicadas_30d,
    }


def anticipacion_horas_de(evento):
    """anticipacion_horas de UNA entrega puntual (apertura->cierre de su tarea). Se usa
    tal cual al entrenar (la tarea de esa entrega concreta) y se promedia sobre el
    historial para inferencia (ver predictor.py: no hay una "tarea actual" equivalente en
    vivo para el modelo de inactividad)."""
    if not evento.apertura_dt:
        return None
    return (evento.cierre_dt - evento.apertura_dt).total_seconds() / 3600
