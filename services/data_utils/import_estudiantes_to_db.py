from decimal import Decimal, InvalidOperation
from gatfh import config
from services.data_utils import cargarjson
from data.models import Tarea, Estudiante, Entrega
import re


CALIFICACION_FINAL_RE = re.compile(r'(\d+[.,]\d+)\s*/\s*(\d+[.,]\d+)')


def parsear_calificacion_final(calificacion_final):
    """Extrae (nota, nota_maxima) de calificacion_final ('16,70 / 100,00' -> (16.70, 100.00)).

    calificacion_final es el campo seguro para parsear: solo tiene numeros y el separador
    "/" entre nota asignada y nota maxima (a diferencia de `calificacion`, que trae pegado
    el texto del boton de Moodle, ej. 'Calificar16,70 / 100,00'). Cuando la tarea todavia
    no fue calificada, Moodle lo deja en '-'; eso (o cualquier otro formato inesperado) debe
    devolver (None, None) en vez de guardar basura que despues rompa el calculo de notas en
    'Generar Excel' - es la seguridad que faltaba."""
    if not calificacion_final:
        return None, None
    match = CALIFICACION_FINAL_RE.search(calificacion_final)
    if not match:
        return None, None
    try:
        nota = Decimal(match.group(1).replace(',', '.'))
        nota_maxima = Decimal(match.group(2).replace(',', '.'))
    except InvalidOperation:
        return None, None
    return nota, nota_maxima


def import_estudiantes_from_json():
    """Importa estudiantes y entregas desde el JSON generado por el scraper hacia los modelos.
    Estructura esperada: [{"id": tarea_moodle_id, "estudiantes": [...], ...}]
    """
    try:
        estudiantes_raw = cargarjson.cargar_estudiantes()
    except Exception as e:
        return {'error': str(e)}

    created = {'estudiantes': 0, 'entregas': 0, 'skipped': 0, 'updated': 0}

    for task_group in estudiantes_raw:
        tarea_id = task_group.get('id')
        if not tarea_id:
            created['skipped'] += 1
            continue

        try:
            tarea = Tarea.objects.get(moodle_id=tarea_id)
        except Tarea.DoesNotExist:
            created['skipped'] += 1
            continue

        for est_data in task_group.get('estudiantes', []):
            userid = est_data.get('userid')
            nombre = est_data.get('nombre')
            email = est_data.get('email')

            if not userid or not nombre or not email:
                created['skipped'] += 1
                continue

            # Crear o actualizar estudiante
            try:
                estudiante, created_e = Estudiante.objects.get_or_create(
                    moodle_userid=int(userid),
                    defaults={'nombre': nombre, 'email': email}
                )
                if created_e:
                    created['estudiantes'] += 1
                else:
                    # actualizar si cambió nombre o email
                    if estudiante.nombre != nombre or estudiante.email != email:
                        estudiante.nombre = nombre
                        estudiante.email = email
                        estudiante.save()
                        created['updated'] += 1
            except Exception:
                created['skipped'] += 1
                continue

            calificacion_final_raw = est_data.get('calificacion_final')
            nota, nota_maxima = parsear_calificacion_final(calificacion_final_raw)

            # Crear o actualizar entrega
            try:
                entrega, created_ent = Entrega.objects.get_or_create(
                    tarea=tarea,
                    estudiante=estudiante,
                    defaults={
                        'estado': est_data.get('estado'),
                        'calificacion': est_data.get('calificacion'),
                        'nota': nota,
                        'nota_maxima': nota_maxima,
                        'ultima_mod_entrega': est_data.get('ultima_mod_entrega'),
                        'ultima_mod_calificacion': est_data.get('ultima_mod_calificacion'),
                        'comentarios_entrega': est_data.get('comentarios_entrega'),
                        'comentarios_feedback': est_data.get('comentarios_feedback'),
                        'calificacion_final': calificacion_final_raw,
                        'link_calificar': est_data.get('link_calificar'),
                    }
                )
                if created_ent:
                    created['entregas'] += 1
                else:
                    # actualizar entrega
                    entrega.estado = est_data.get('estado', entrega.estado)
                    entrega.calificacion = est_data.get('calificacion', entrega.calificacion)
                    entrega.nota = nota
                    entrega.nota_maxima = nota_maxima
                    entrega.ultima_mod_entrega = est_data.get('ultima_mod_entrega', entrega.ultima_mod_entrega)
                    entrega.ultima_mod_calificacion = est_data.get('ultima_mod_calificacion', entrega.ultima_mod_calificacion)
                    entrega.comentarios_feedback = est_data.get('comentarios_feedback', entrega.comentarios_feedback)
                    entrega.calificacion_final = calificacion_final_raw
                    entrega.save()
                    created['updated'] += 1
            except Exception as e:
                created['skipped'] += 1
                continue

    return created
