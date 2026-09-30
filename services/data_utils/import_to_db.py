from gatfh import config
from services.data_utils import cargarjson
from data.models import Facultad, Carrera, Nivel, Materia, Unidad, Tarea, Estudiante, Entrega, Profesor
from django.db import transaction
import re


def import_tareas_from_json():
    """Importa tareas desde el JSON generado por el scraper hacia los modelos básicos.
    Crea entidades mínimas para Facultad/Carrera si no existen.
    """
    cursos = cargarjson.cargar_tareas()
    created = {'materias': 0, 'unidades': 0, 'tareas': 0, 'skipped': 0, 'materias_url_corregida': 0}

    # Asegurar una carrera por defecto
    facultad, _ = Facultad.objects.get_or_create(nombre='Importadas')
    carrera, _ = Carrera.objects.get_or_create(facultad=facultad, nombre='Importadas')

    # cursos.json es la fuente confiable de la URL real del curso (tareas.json solo trae
    # asignatura + tareas, no la url del curso en si). Se usa tanto para crear Materias
    # nuevas como para corregir moodle_url en Materias ya creadas con un valor incorrecto
    # (bug historico: se guardaba la url de la primera tarea de la seccion 1 -que puede ser
    # cualquier recurso, no el curso- en vez de la url del curso).
    try:
        cursos_con_url = cargarjson.cargar_cursos()
    except Exception:
        # cursos.json es un cache local del scraper (gitignored, no existe en Render);
        # si falta, simplemente no hay con que corregir moodle_url en esta corrida.
        cursos_con_url = []
    urls_por_asignatura = {
        c.get('asignatura'): c.get('url')
        for c in cursos_con_url
        if c.get('asignatura') and c.get('url')
    }

    for curso in cursos:
        asignatura = curso.get('asignatura') or curso.get('nombre')
        if not asignatura:
            created['skipped'] += 1
            continue

        # usar la asignatura completa como moodle_nombre
        moodle_nombre = asignatura
        # intentar inferir gestion (año) desde el texto
        gestion_match = re.search(r"(\d{4})", asignatura)
        gestion = int(gestion_match.group(1)) if gestion_match else 0

        url_curso = urls_por_asignatura.get(asignatura, '')

        materia, created_m = Materia.objects.get_or_create(
            moodle_nombre=moodle_nombre,
            defaults={'nombre': asignatura, 'gestion': gestion or 0, 'moodle_url': url_curso, 'carrera': carrera}
        )
        if created_m:
            created['materias'] += 1
        elif url_curso and '/course/view.php' not in materia.moodle_url:
            materia.moodle_url = url_curso
            materia.save(update_fields=['moodle_url'])
            created['materias_url_corregida'] += 1

        # procesar unidades y tareas
        for unidad_obj in curso.get('tareas', []):
            unidad_nombre = unidad_obj.get('unidad') or 'Sin unidad'
            unidad, created_u = Unidad.objects.get_or_create(materia=materia, nombre=unidad_nombre)
            if created_u:
                created['unidades'] += 1

            for contenido in unidad_obj.get('contenido', []):
                moodle_id = contenido.get('id')
                titulo = contenido.get('Titulo') or contenido.get('titulo') or ''
                apertura = contenido.get('apertura')
                cierre = contenido.get('cierre')
                url = contenido.get('url') or ''

                if not moodle_id:
                    created['skipped'] += 1
                    continue

                tarea, created_t = Tarea.objects.get_or_create(
                    moodle_id=moodle_id,
                    defaults={
                        'unidad': unidad,
                        'titulo': titulo,
                        'tipo': 'assign' if '/mod/assign/' in url else 'url',
                        'apertura': apertura,
                        'cierre': cierre,
                        'url': url,
                    }
                )
                if not created_t:
                    # actualizar campos básicos por si cambiaron
                    tarea.unidad = unidad
                    tarea.titulo = titulo
                    tarea.apertura = apertura
                    tarea.cierre = cierre
                    tarea.url = url
                    tarea.save()
                else:
                    created['tareas'] += 1

    return created
