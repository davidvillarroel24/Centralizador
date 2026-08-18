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
    created = {'materias': 0, 'unidades': 0, 'tareas': 0, 'skipped': 0}

    # Asegurar una carrera por defecto
    facultad, _ = Facultad.objects.get_or_create(nombre='Importadas')
    carrera, _ = Carrera.objects.get_or_create(facultad=facultad, nombre='Importadas')

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

        # url base: tomar la primera tarea disponible
        first_url = None
        try:
            first_unidad = curso.get('tareas', [])[0]
            first_contenido = first_unidad.get('contenido', [])[0]
            first_url = first_contenido.get('url')
        except Exception:
            first_url = ''

        materia, created_m = Materia.objects.get_or_create(
            moodle_nombre=moodle_nombre,
            defaults={'nombre': asignatura, 'gestion': gestion or 0, 'moodle_url': first_url or '', 'carrera': carrera}
        )
        if created_m:
            created['materias'] += 1

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
