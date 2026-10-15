from datetime import date

from django.core.management.base import BaseCommand

from data.models import AccesoCurso, ConfiguracionInstitucional, Entrega, FechasParciales, Materia, PesosCategorias
from gatfh import config
from services.data_utils.run_export import CATEGORIAS_PESO, calcular_total_parcial
from web.views import parse_date_string

import csv
import re


def parsear_dias_ultimo_acceso(texto):
    """AccesoCurso.ultimo_acceso es texto crudo de Moodle ("119 días 14 horas", "Nunca",
    "15 horas 38 minutos"), medido al momento de la extraccion - no al cierre del parcial
    (no hay historial, solo esta foto). Se usa igual como mejor señal disponible de
    abandono: None si nunca entro o no hay dato (CSV lo deja vacio, para imputar despues
    en Colab en vez de inventar un 0 que mentiria "accedio hoy")."""
    if not texto:
        return None
    texto_low = texto.lower()
    if 'nunca' in texto_low:
        return None
    m = re.search(r'(\d+)\s*d[ií]as?', texto_low)
    if m:
        return int(m.group(1))
    return 0  # "X horas Y minutos" sin "dias": accedio el mismo dia de la extraccion


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
        filas_sin_acceso = 0
        parciales_sin_cobertura = 0
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

            # Una lectura por materia (no por parcial/estudiante): AccesoCurso es una foto
            # unica al momento de la extraccion, sin historial por parcial. Si todavia no
            # se corrio "3b. Extraer último acceso" para esta materia, el dict queda vacio
            # y dias_desde_ultimo_acceso sale en blanco para todas sus filas.
            acceso_por_userid = {
                a.moodle_userid: a.ultimo_acceso
                for a in AccesoCurso.objects.filter(materia=materia)
            }

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

                # Muchos docentes no califican todas las categorias en Moodle (llevan
                # planillas propias aparte) - exigir que las 5 esten calificadas (como
                # antes) descartaba practicamente todo. Ahora solo se salta el parcial si
                # NINGUNA categoria con peso tiene ni una sola calificacion (ahi si no hay
                # nada de que partir); con cobertura parcial, se calcula igual y se informa
                # cuanto peso quedo realmente representado (`peso_cubierto`) para que en
                # Colab se pueda filtrar/ponderar por confiabilidad en vez de adivinar.
                categorias_con_peso = [cat for cat in CATEGORIAS_PESO if pesos.get(cat, 0) > 0]
                categorias_calificadas = [
                    cat for cat in categorias_con_peso
                    if any(
                        e.tarea.parcial == parcial_num and e.tarea.categoria == cat and e.nota is not None
                        for e in entregas
                    )
                ]
                if not categorias_calificadas:
                    parciales_sin_cobertura += 1
                    continue
                peso_cubierto = sum(pesos.get(cat, 0) for cat in categorias_calificadas)

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
                    # nota_parcial queda "sobre peso_cubierto", no sobre 100, cuando falta
                    # calificar alguna categoria (misma logica que calcular_total_parcial:
                    # una categoria sin calificar aporta 0 en vez de excluirse). Comparar
                    # eso directo contra nota_aprobacion (pensada sobre 100) etiquetaria
                    # "en_riesgo" a cualquiera con cobertura parcial, sin importar que le
                    # haya ido bien en lo que si se califico - por eso el label usa la nota
                    # reescalada a 100 sobre lo efectivamente cubierto, no nota_parcial cruda.
                    nota_normalizada = (nota_parcial / peso_cubierto * 100) if peso_cubierto else 0

                    moodle_userid = entregas_parcial[0].estudiante.moodle_userid
                    dias_ultimo_acceso = parsear_dias_ultimo_acceso(acceso_por_userid.get(moodle_userid))
                    if dias_ultimo_acceso is None:
                        filas_sin_acceso += 1

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
                        'dias_desde_ultimo_acceso': dias_ultimo_acceso,
                        'peso_cubierto': peso_cubierto,
                        'nota_parcial': round(nota_parcial, 2),
                        'nota_parcial_normalizada': round(nota_normalizada, 2),
                        'en_riesgo': int(nota_normalizada < nota_aprobacion),
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
            f"{materias_sin_entregas}, parciales saltados por no tener NINGUNA categoria "
            f"calificada en Moodle: {parciales_sin_cobertura}."
        )
        self.stdout.write(self.style.SUCCESS(
            f"Dataset exportado: {len(filas)} fila(s) en {config.CSV_DATASET_ML}."
        ))
        if filas:
            pesos_cubiertos = [f['peso_cubierto'] for f in filas]
            self.stdout.write(
                f"peso_cubierto: min {min(pesos_cubiertos)}, max {max(pesos_cubiertos)}, "
                f"promedio {round(sum(pesos_cubiertos) / len(pesos_cubiertos), 1)} (de 100 "
                "posible) - cuanto menor, menos confiable el 'en_riesgo' de esa fila "
                "porque se basa en menos categorias calificadas en Moodle."
            )
        if filas and filas_sin_acceso:
            self.stdout.write(self.style.WARNING(
                f"{filas_sin_acceso}/{len(filas)} fila(s) sin dias_desde_ultimo_acceso "
                "(columna vacia): falta correr \"3b. Extraer último acceso\" + su "
                "importador para esas materias, o el estudiante nunca entró a Moodle."
            ))
        if len(filas) < 50:
            self.stdout.write(self.style.WARNING(
                "Menos de 50 filas: no alcanza todavia para entrenar un modelo "
                "confiable. Conviene seguir extrayendo materias/estudiantes antes de "
                "entrenar en Colab, o usar este CSV solo para probar que el pipeline "
                "corre de punta a punta."
            ))
