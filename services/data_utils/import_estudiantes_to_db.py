from gatfh import config
from services.data_utils import cargarjson
from data.models import Tarea, Estudiante, Entrega
import re


def extract_grade(grade_str):
    """Extrae la calificación del formato 'Calificar100,00 / 100,00' → '100,00'"""
    if not grade_str:
        return None
    # Remover 'Calificar' y extrae el primer número con coma/punto decimal
    match = re.search(r'(\d+[.,]\d+)', grade_str)
    return match.group(1) if match else None


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

            # Extraer calificación
            calif_raw = est_data.get('calificacion')
            calif_parsed = extract_grade(calif_raw) if calif_raw else None

            # Crear o actualizar entrega
            try:
                entrega, created_ent = Entrega.objects.get_or_create(
                    tarea=tarea,
                    estudiante=estudiante,
                    defaults={
                        'estado': est_data.get('estado'),
                        'calificacion': calif_parsed,
                        'ultima_mod_entrega': est_data.get('ultima_mod_entrega'),
                        'ultima_mod_calificacion': est_data.get('ultima_mod_calificacion'),
                        'comentarios_entrega': est_data.get('comentarios_entrega'),
                        'comentarios_feedback': est_data.get('comentarios_feedback'),
                        'calificacion_final': est_data.get('calificacion_final'),
                        'link_calificar': est_data.get('link_calificar'),
                    }
                )
                if created_ent:
                    created['entregas'] += 1
                else:
                    # actualizar entrega
                    entrega.estado = est_data.get('estado', entrega.estado)
                    entrega.calificacion = calif_parsed or entrega.calificacion
                    entrega.ultima_mod_entrega = est_data.get('ultima_mod_entrega', entrega.ultima_mod_entrega)
                    entrega.ultima_mod_calificacion = est_data.get('ultima_mod_calificacion', entrega.ultima_mod_calificacion)
                    entrega.comentarios_feedback = est_data.get('comentarios_feedback', entrega.comentarios_feedback)
                    entrega.calificacion_final = est_data.get('calificacion_final', entrega.calificacion_final)
                    entrega.save()
                    created['updated'] += 1
            except Exception as e:
                created['skipped'] += 1
                continue

    return created
