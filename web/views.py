import traceback
import os
import re
import json
from datetime import datetime, timezone, date
from io import BytesIO, StringIO

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import FileResponse, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from urllib.parse import urlencode

from gatfh import config
from services.utils import run_scraping
from services.data_utils.import_to_db import (
    import_tareas_from_json, import_asignacion_from_json,
    import_participantes_a_accesos,
)
from services.data_utils.import_estudiantes_to_db import import_estudiantes_from_json
from services.extraccion.trasformar import extraer_transformar
from services.imports.facultades import importar_facultades
from services.imports.carreras import importar_carreras
from services.imports.niveles import importar_niveles
from services.imports.profesores import importar_profesores
from services.imports.materias import importar_materias
from services.imports.detalles_tareas import importar_detalles_tareas
from services.utils import extraction_lock
from services.utils.reportes import datos_reporte_acceso, datos_reporte_contenido, generar_excel_reporte, generar_pdf_reporte

REPORTES_DISPONIBLES = ('acceso', 'tareas', 'material')
from data.models import Materia, Profesor, Estudiante, Tarea, Entrega, FechasParciales, PesosCategorias, AccesoCurso
from data.cookie_crypto import cifrar_cookie, descifrar_cookie
from data.roles import es_administrador, requiere_rol, materias_visibles, get_rol
from data.models import PerfilUsuario, Facultad, Carrera
from django.utils import timezone as dj_timezone

from collections import Counter
from django.db.models import Count, Q
from collections import defaultdict
from datetime import datetime

ROLES_STAFF = (PerfilUsuario.ADMINISTRADOR, PerfilUsuario.DECANO, PerfilUsuario.DOCENTE)
ROLES_GESTION = (PerfilUsuario.ADMINISTRADOR, PerfilUsuario.DECANO)


def extension_version():
    """Lee la version actual de chrome_extension/manifest.json, para mostrarla en
    Configuración y - mas importante - para usarla como cache-buster (?v=X.Y.Z) en el link
    de descarga del .zip. Sin esto, el navegador puede seguir sirviendo una copia vieja del
    .zip cacheada de una descarga anterior, aunque el archivo en el servidor ya haya
    cambiado (fue justo lo que paso el 2026-10-22: el .zip del servidor ya estaba
    actualizado, pero Chrome seguia devolviendo la version cacheada de la misma URL)."""
    from django.conf import settings
    ruta = settings.BASE_DIR / 'chrome_extension' / 'manifest.json'
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f).get('version', '0.0.0')
    except Exception:
        return '0.0.0'

MESES = {
    'enero': 1,
    'febrero': 2,
    'marzo': 3,
    'abril': 4,
    'mayo': 5,
    'junio': 6,
    'julio': 7,
    'agosto': 8,
    'septiembre': 9,
    'octubre': 10,
    'noviembre': 11,
    'diciembre': 12,
}

def load_courses():
    """Carga los cursos (Materia) desde Postgres en vez del JSON legado.

    El resto del dashboard (selección de cursos, filtrado de tareas por
    asignatura) sigue trabajando con dicts {id, asignatura, url} para no
    tener que tocar el pipeline de scraping basado en cursos.json.
    """
    materias = Materia.objects.select_related('carrera').prefetch_related('profesores').order_by('nombre')

    # Estudiantes por materia (via AccesoCurso, el padron real de /user/index.php - ver
    # "3b. Extraer último acceso"), para el buscador. Son pocas filas (decenas, no miles)
    # asi que se resuelve siempre, sin volverlo condicional a si hay busqueda o no.
    estudiante_nombre_por_userid = dict(Estudiante.objects.values_list('moodle_userid', 'nombre'))
    estudiantes_por_materia = defaultdict(list)
    for materia_id, userid in AccesoCurso.objects.filter(
        rol__icontains='estudiante'
    ).values_list('materia_id', 'moodle_userid'):
        nombre = estudiante_nombre_por_userid.get(userid)
        if nombre:
            estudiantes_por_materia[materia_id].append(nombre)

    return [
        {
            'id': materia.id,
            'asignatura': materia.moodle_nombre,
            'nombre': materia.nombre,
            'url': materia.moodle_url,
            'carrera_id': materia.carrera_id,
            'carrera_nombre': materia.carrera.nombre if materia.carrera_id else '',
            'gestion': materia.gestion,
            'docentes': [p.nombre for p in materia.profesores.all()],
            'estudiantes': estudiantes_por_materia.get(materia.id, []),
        }
        for materia in materias
    ]


def get_current_profesor(request):
    if not request.user.is_authenticated:
        return None
    try:
        profesor = Profesor.objects.filter(user=request.user).first()
        if profesor:
            return profesor
    except Exception:
        return None

    # Compatibilidad con cuentas creadas antes de vincular Profesor.user:
    # se resuelve por nombre una unica vez y se deja el vinculo guardado.
    nombre_usuario = request.user.get_full_name() or request.user.username
    nombre_usuario = nombre_usuario.strip()
    if not nombre_usuario:
        return None
    try:
        profesor = Profesor.objects.filter(nombre__iexact=nombre_usuario, user__isnull=True).first()
        if not profesor:
            profesor = Profesor.objects.filter(nombre__icontains=nombre_usuario, user__isnull=True).first()
        if profesor:
            profesor.user = request.user
            profesor.save(update_fields=['user'])
        return profesor
    except Exception:
        return None


def register_view(request):
    message = None
    error = None
    nombres_profesores = list(
        Profesor.objects.exclude(nombre='').order_by('nombre').values_list('nombre', flat=True)
    )
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        if not username or not password:
            error = 'Todos los campos son obligatorios.'
        elif not Profesor.objects.filter(nombre__iexact=username).exists():
            error = 'El usuario debe coincidir con un docente registrado.'
        elif User.objects.filter(username__iexact=username).exists():
            error = 'Ya existe un usuario con ese nombre. Usa inicio de sesión.'
        else:
            user = User.objects.create_user(username=username)
            user.set_password(password)
            user.save()
            profesor = Profesor.objects.filter(nombre__iexact=username).first()
            if profesor:
                profesor.user = user
                profesor.save(update_fields=['user'])
            login(request, user)
            # La cookie de Moodle ya no se pide acá: se captura con la extensión
            # desde la pantalla de extracción, la primera vez que haga falta.
            return redirect('dashboard')
    context = {'message': message, 'error': error, 'nombres_profesores': nombres_profesores}
    return render(request, 'web/register.html', context)


def login_view(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = 'Usuario o contraseña incorrectos.'
        elif not Profesor.objects.filter(nombre__iexact=username).exists():
            error = 'El usuario debe coincidir con un docente registrado.'
        else:
            login(request, user)
            return redirect('resumen')
    return render(request, 'web/login.html', {'error': error})


def logout_view(request):
    # Borra la cookie de Moodle guardada en la base al cerrar sesión (la otra forma en la
    # que "vence", además de las 2 horas vía cookie_vigente()).
    profesor = get_current_profesor(request)
    if profesor and profesor.moodle_cookie_cifrada:
        profesor.borrar_cookie()
    logout(request)
    return redirect('login')


def normalize_asignatura(value):
    return str(value or '').strip().lower()


def filter_courses_by_role(request, courses, role='all'):
    current_profesor = get_current_profesor(request)

    # 'docente': Materia.profesores (M2M) ya liga de verdad al profesor logueado con sus
    # materias (via "Importar profesores"/"Importar materias"), independiente de Moodle.
    docente_materias = {
        normalize_asignatura(m)
        for m in current_profesor.materias.values_list('moodle_nombre', flat=True)
    } if current_profesor else set()

    # 'estudiante': antes era "cualquier materia sin profesor asignado en toda la BD",
    # sin ninguna relacion con el usuario logueado. Ahora usa AccesoCurso (padron real de
    # /user/index.php, ver "3b. Extraer último acceso" + "Importar último acceso"):
    # materias donde el moodle_userid de este profesor aparece con rol de estudiante.
    # Si todavia no se extrajo el "último acceso" de un curso, no va a aparecer aca hasta
    # que se corra esa extraccion - no es un bug, es que falta ese dato.
    estudiante_ids = set()
    if current_profesor and current_profesor.moodle_id:
        estudiante_ids = set(
            AccesoCurso.objects.filter(
                moodle_userid=current_profesor.moodle_id,
                rol__icontains='estudiante',
            ).values_list('materia_id', flat=True)
        )

    if role == 'docente':
        return [course for course in courses if normalize_asignatura(course.get('asignatura')) in docente_materias]
    if role == 'estudiante':
        return [course for course in courses if course.get('id') in estudiante_ids]

    # 'all': únicamente los cursos donde el usuario actual participa como
    # docente y/o como estudiante — no todas las materias de la base de datos.
    return [
        course for course in courses
        if normalize_asignatura(course.get('asignatura')) in docente_materias
        or course.get('id') in estudiante_ids
    ]


def tiene_cursos_como(request, rol_moodle):
    """Para mostrar/ocultar los pills Docente/Estudiante solo cuando aplican de verdad:
    ej. si todavía no se corrió "3. Extraer último acceso" para ningún curso propio,
    AccesoCurso no tiene filas para este profesor y el pill 'Estudiante' no debería
    aparecer (no es que el filtro esté roto, es que falta ese dato)."""
    current_profesor = get_current_profesor(request)
    if not current_profesor:
        return False
    if rol_moodle == 'docente':
        return current_profesor.materias.exists()
    if rol_moodle == 'estudiante':
        if not current_profesor.moodle_id:
            return False
        return AccesoCurso.objects.filter(
            moodle_userid=current_profesor.moodle_id,
            rol__icontains='estudiante',
        ).exists()
    return False


def parse_selected_course_ids(request):
    selected = request.POST.getlist('courses') if request.method == 'POST' else request.GET.getlist('courses')
    ids = []
    for value in selected:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def run_importar_tareas_web():
    """Importa tareas.json (ya extraido por 'Extraer tareas del curso') hacia Materia/
    Unidad/Tarea en la base de datos. Antes esto pasaba escondido dentro del boton
    'Normalizar' (ya eliminado, ver asignacion_tareas en run_scraping.py); ahora es su
    propio paso explicito, para poder correrlo de nuevo sin depender de normalizacion.json
    (que ademas nunca era la fuente real de esta importacion)."""
    import_result = import_tareas_from_json()
    return {
        'title': 'Tareas importadas a BD',
        'detail': f'Importación a la base de datos completada: {import_result}.',
        'count': None,
    }


def run_asignacion_web(selected_ids, profesor):
    """La asignacion en si vive en services/utils/run_scraping.py::asignacion_tareas() -
    mismo codigo que usa el comando CLI `extraer_asignacion`. La config de parciales/pesos
    es la del `profesor` logueado (Profesor.config_tareas, ver /configuracion/), no un
    archivo global compartido."""
    if profesor is None:
        raise ValueError(
            'Tu cuenta no está vinculada a ningún Profesor, así que no hay una config de '
            'parciales/pesos de dónde partir. Configurala primero en /configuracion/.'
        )
    config_base = config_tareas_de(profesor)
    asignaciones, errores, warning = run_scraping.asignacion_tareas(selected_ids, config_base=config_base)

    result = {
        'title': 'Asignación',
        'detail': f'Asignación generada: {len(asignaciones)} tareas procesadas. Errores: {len(errores)}.',
        'count': len(asignaciones),
        'errors': len(errores),
    }

    if warning:
        result['warning'] = warning

    return result


def construir_asignacion_detalle(ids):
    """Arma, por parcial, la lista de tareas (tipo=assign) de los cursos seleccionados con
    su categoria actual - llena el modal de revision manual. Lee directo de Tarea (BD), no
    de asignacion.json: asi siempre refleja lo que ya quedo en la base (el ultimo "G.
    Importar asignación" corrido) y queda scopeado al curso tildado, no a lo ultimo que
    haya en el archivo compartido. None si no hay cursos seleccionados o no tienen tareas
    importadas todavia."""
    if not ids:
        return None
    multiples_cursos = len(ids) > 1
    tareas_qs = (
        Tarea.objects.filter(tipo='assign', unidad__materia_id__in=ids)
        .select_related('unidad__materia')
        .order_by('unidad__materia__nombre', 'titulo')
    )

    por_parcial = defaultdict(list)
    for t in tareas_qs:
        titulo = f'{t.titulo} ({t.unidad.materia.nombre})' if multiples_cursos else t.titulo
        por_parcial[t.parcial or 0].append({
            'id': t.moodle_id, 'titulo': titulo, 'categoria': t.categoria, 'parcial': t.parcial,
        })

    if not por_parcial:
        return None

    parciales = []
    for numero in sorted(por_parcial.keys()):
        etiqueta = f'Parcial {numero}' if numero else 'Sin parcial asignado todavía'
        parciales.append({'numero': numero, 'etiqueta': etiqueta, 'tareas': por_parcial[numero]})
    return parciales


def run_guardar_asignacion_manual_web(post_data, ids):
    """Guarda las correcciones manuales de categoria y parcial directo en Tarea (BD) -
    reemplazo del viejo editar_tareas_interactivamente() por consola. El parcial lo pone
    por defecto la asignacion automatica (segun la fecha de cierre), pero ahora se puede
    corregir a mano acá para el caso puntual en que la fecha no alcance o esté mal. Al
    escribir directo en la base, ya no hace falta un paso de "Importar asignación"
    después - el cambio queda al toque."""
    if not ids:
        raise ValueError('Debes seleccionar al menos un curso para guardar su asignación.')

    PARCIALES_VALIDOS = {'1', '2', '3', '4'}

    tareas = Tarea.objects.filter(tipo='assign', unidad__materia_id__in=ids)
    cambios = 0
    for t in tareas:
        campos = []
        nueva_categoria = post_data.get(f'categoria_{t.moodle_id}')
        if nueva_categoria in CATEGORIAS_PESO and nueva_categoria != t.categoria:
            t.categoria = nueva_categoria
            campos.append('categoria')

        nuevo_parcial = post_data.get(f'parcial_{t.moodle_id}')
        if nuevo_parcial in PARCIALES_VALIDOS and int(nuevo_parcial) != t.parcial:
            t.parcial = int(nuevo_parcial)
            campos.append('parcial')

        if campos:
            t.save(update_fields=campos)
            cambios += 1

    return {
        'title': 'Asignación actualizada',
        'detail': f'{cambios} tarea(s) con categoría y/o parcial corregidos directamente en la base de datos.',
        'count': cambios,
    }


def run_importar_asignacion_web():
    """Importa asignacion.json (ya generado por 'Asignar tareas') hacia las columnas
    Tarea.categoria/Tarea.parcial. Paso separado a proposito: permite revisar el resultado
    de 'Asignar tareas' antes de confirmarlo en la base, igual que 'Importar tareas a BD'
    es un paso aparte de 'Extraer tareas del curso'."""
    import_result = import_asignacion_from_json()
    return {
        'title': 'Asignación importada a BD',
        'detail': f'Importación a la base de datos completada: {import_result}.',
        'count': None,
    }


def run_extraer_carreras_web(cookie, stop_event=None):
    """Paso 0, previo a la seleccion de cursos: recorre todas las facultades/categorias de
    Moodle y arma la jerarquia Facultad > Carrera > Nivel > Materia (+ profesor por materia)
    en linkcarreras.json. Sin esto el selector de cursos del dashboard esta vacio, porque
    `load_courses()` lee `Materia` desde Postgres, no desde JSON.

    La extraccion en si vive en services/utils/run_scraping.py::extraer_carreras_completo()
    - mismo codigo que usan los comandos CLI (extraer_carreras_completo, o los 3 pasos
    sueltos extraer_categorias/extraer_carreras/extraer_linkcarreras).

    No soporta cancelacion a mitad de camino (stop_event no se revisa dentro de
    `cargar_todo`): son ~7 facultades, bastante mas rapido que extraer tareas/estudiantes.
    """
    categorias, carreras_html, linkcarreras = run_scraping.extraer_carreras_completo(
        cookie=cookie, stop_event=stop_event
    )

    total_materias = sum(len(item.get('materias') or []) for item in linkcarreras)
    detalle = (
        f'Extracción de carreras completada: {len(categorias)} categoría(s) recorridas, '
        f'{len(linkcarreras)} carrera(s)/nivel(es) con {total_materias} materia(s) en total, '
        f'guardado en {config.JSON_LINKCARRERAS}. Todavía no se importó a la base de datos '
        f'(usar los botones de "Importar a la base de datos", en orden A → E).'
    )
    return {
        'title': 'Carreras extraídas',
        'detail': detalle,
        'count': len(linkcarreras),
    }


# Importadores de linkcarreras.json -> DB, en el orden del README (§3.1 paso 3):
# profesores va antes que materias porque materias enlaza cada Materia a su Profesor ya creado.
IMPORTADORES_CARRERAS = {
    'importar_facultades': ('facultades', importar_facultades),
    'importar_carreras': ('carreras', importar_carreras),
    'importar_niveles': ('niveles', importar_niveles),
    'importar_profesores': ('profesores', importar_profesores),
    'importar_materias': ('materias', importar_materias),
}


def run_importar_web(action):
    entidad, importador = IMPORTADORES_CARRERAS[action]
    count = importador()
    return {
        'title': f'Importación de {entidad}',
        'detail': (
            f'Importación de {entidad} desde {config.JSON_LINKCARRERAS} completada: '
            f'{count} procesadas.'
        ),
        'count': count,
    }


def run_extraer_tareas_web(selected_ids, cookie, stop_event=None, profesor=None):
    """Primer paso real del pipeline (antes de Normalizar): entra a cada curso seleccionado
    y trae todas las tareas de todas sus secciones, sin discriminar tipo. Llama a Moodle de
    verdad, por eso pasa por el candado de extraction_lock en la vista `dashboard`, igual que
    `run_estudiantes_web`.

    La extraccion en si vive en services/utils/run_scraping.py::tareas() - es el mismo
    codigo que usa el comando CLI `extraer_tareas`, para que un print() puesto ahi se vea
    sin importar si se dispara desde el boton o desde la consola.

    `profesor`: Profesor del usuario logueado (get_current_profesor), para que tareas.json
    sepa a quien pertenecen los datos guardados - ver el docstring de run_scraping.tareas."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer sus tareas.')

    profesor_id = profesor.id if profesor is not None else None
    tareas_nuevas, detenido = run_scraping.tareas(
        selected_ids, cookie=cookie, stop_event=stop_event, profesor_id=profesor_id
    )

    detalle = (
        f'Extracción de tareas completada: {len(tareas_nuevas)} curso(s) procesados, '
        f'guardados en {config.JSON_TAREAS}.'
    )
    if detenido:
        detalle = f'Extracción detenida manualmente. Resultados parciales: {detalle}'
    return {
        'title': 'Tareas extraídas',
        'detail': detalle,
        'count': len(tareas_nuevas),
        'detenido': detenido,
    }


def run_estudiantes_web(selected_ids, cookie, stop_event=None, profesor=None):
    """Segundo paso que llama a Moodle de verdad: entra a cada tarea ya extraida por
    `run_extraer_tareas_web` y trae los datos de entrega/calificacion de los estudiantes.
    Tambien pasa por el candado de extraction_lock en la vista `dashboard`.

    La extraccion en si vive en services/utils/run_scraping.py::estudiantes() - mismo
    codigo que usa el comando CLI `extraer_estudiantes`.

    `profesor`: Profesor del usuario logueado. estudiantes() exige que tenga
    PesosCategorias guardado (candado de validacion previa, ver su docstring); si no hay
    profesor o no tiene pesos, falla ahi con un mensaje claro antes de llamar a Moodle."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer estudiantes.')

    profesor_id = profesor.id if profesor is not None else None
    estudiantes, detenido = run_scraping.estudiantes(
        selected_ids, cookie=cookie, stop_event=stop_event, profesor_id=profesor_id
    )

    detalle = (
        f'Extracción de estudiantes completada: {len(estudiantes)} registros guardados en '
        f'{config.JSON_ESTUDIANTES}. Todavía no se importó a la base de datos, para eso usá '
        f'"Importar estudiantes".'
    )
    if detenido:
        detalle = f'Extracción detenida manualmente. Resultados parciales: {detalle}'
    return {
        'title': 'Estudiantes',
        'detail': detalle,
        'count': len(estudiantes),
        'detenido': detenido,
    }


def run_importar_estudiantes_web():
    """Importa estudiantes.json (ya extraido por 'Extraer estudiantes') hacia Estudiante/
    Entrega en la base de datos, parseando nota/nota_maxima desde calificacion_final (ver
    import_estudiantes_to_db.parsear_calificacion_final). Paso separado a proposito, mismo
    criterio que 'Importar tareas'/'Importar asignación'."""
    import_result = import_estudiantes_from_json()
    return {
        'title': 'Estudiantes importados a BD',
        'detail': f'Importación a la base de datos completada: {import_result}.',
        'count': None,
    }


def run_participantes_web(selected_ids, cookie, stop_event=None):
    """Tercer llamado real a Moodle: trae el padron de inscritos (estudiantes Y profesores)
    de /user/index.php?id=<curso>, con su ultimo acceso - a diferencia de `estudiantes`, que
    solo ve a quien entrego algo, esto trae a todos los inscritos. Pasa por el mismo candado
    de extraction_lock que extraer_tareas/estudiantes en la vista `dashboard`.

    La extraccion en si vive en services/utils/run_scraping.py::participantes()."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer sus participantes.')

    resultado, detenido = run_scraping.participantes(selected_ids, cookie=cookie, stop_event=stop_event)

    detalle = (
        f'Extracción de participantes completada: {len(resultado)} registro(s) guardados en '
        f'{config.JSON_PARTICIPANTES}. Todavía no se importó a la base de datos, para eso usá '
        f'los botones de importación de participantes.'
    )
    if detenido:
        detalle = f'Extracción detenida manualmente. Resultados parciales: {detalle}'
    return {
        'title': 'Último acceso extraído',
        'detail': detalle,
        'count': len(resultado),
        'detenido': detenido,
    }


def run_importar_participantes_web():
    """Importa participantes.json (ya extraido por 'Extraer último acceso') hacia
    AccesoCurso, una fila por (materia, moodle_userid) que sirve tanto para estudiantes
    como para profesores (ver comentario en el modelo AccesoCurso)."""
    import_result = import_participantes_a_accesos()
    return {
        'title': 'Último acceso importado',
        'detail': f'Importación a la base de datos completada: {import_result}.',
        'count': None,
    }


@login_required
@requiere_rol(*ROLES_STAFF)
@require_http_methods(['POST'])
def descargar_excel(request):
    """Genera el Excel filtrado por los cursos seleccionados y los pesos del profesor
    logueado, y lo devuelve directo como descarga (sin pasar por el disco del servidor:
    `generar_excel` escribe a un BytesIO en memoria). Antes el boton "Generar Excel" solo
    guardaba notas.xlsx en el servidor y había que ir a buscarlo a mano.

    Es un botón aparte del dispatcher de dashboard() (vía formaction en el template) porque
    una respuesta de archivo no encaja con el patrón Post-Redirect-Get del resto de
    acciones: acá, si todo sale bien, la respuesta ES el archivo, no un redirect."""
    role = request.POST.get('role', 'all')
    selected_ids = parse_selected_course_ids(request)
    try:
        if not selected_ids:
            raise ValueError('Debes seleccionar al menos un curso para generar el Excel.')
        profesor = get_current_profesor(request)
        buffer = BytesIO()
        total, _ = extraer_transformar(selected_ids, profesor, archivo=buffer)
        if total == 0:
            raise ValueError(
                'No se encontraron estudiantes con entregas para los cursos seleccionados. '
                'Corré primero "Importar estudiantes" y "Importar asignación" para esos cursos.'
            )
    except Exception as exc:
        request.session['dashboard_flash'] = {'action_result': None, 'error': str(exc)}
        redirect_params = [('role', role)] + [('courses', cid) for cid in [str(c) for c in selected_ids]]
        return redirect(f"{reverse('dashboard')}?{urlencode(redirect_params)}")

    return FileResponse(
        buffer,
        as_attachment=True,
        filename='notas.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@login_required
@requiere_rol(*ROLES_STAFF)
@csrf_protect
@require_http_methods(['POST'])
def guardar_cookie_extension(request):
    """Recibe la cookie MoodleSession directo de la extensión (fetch JSON), ya
    confirmada por el usuario en el SweetAlert2 de la página - nunca pasa por un campo
    de texto visible. Se cifra (ver data/cookie_crypto.py) y se guarda asociada al
    profesor logueado, con la marca de tiempo que habilita la expiración perezosa de
    2 horas. También se deja en la sesión del navegador tal cual antes, para no tener
    que tocar ninguna de las funciones de extracción que ya leían de ahí."""
    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

    cookie_value = (data.get('cookie') or '').strip()
    if not cookie_value:
        return JsonResponse({'ok': False, 'error': 'La cookie recibida está vacía.'}, status=400)

    profesor = get_current_profesor(request)
    if not profesor:
        return JsonResponse(
            {'ok': False, 'error': 'No se encontró tu perfil de profesor para guardar la cookie.'},
            status=400,
        )

    profesor.moodle_cookie_cifrada = cifrar_cookie(request.user, cookie_value)
    profesor.moodle_cookie_guardada_en = dj_timezone.now()
    profesor.save(update_fields=['moodle_cookie_cifrada', 'moodle_cookie_guardada_en'])
    request.session['MoodleSession'] = cookie_value

    return JsonResponse({'ok': True})


@login_required
@requiere_rol(*ROLES_STAFF)
@require_http_methods(['GET'])
def progreso_extraccion(request):
    """Sondeado por JS cada 1-2s mientras un botón de extracción está corriendo, para
    mostrar un spinner con texto real ("Extrayendo tareas de la materia: X") sin tocar la
    arquitectura síncrona existente: la extracción sigue bloqueando al worker que la
    disparó, pero este endpoint lo atiende el OTRO worker de gunicorn libre (se corre con
    --workers 2, ver deploy/web/entrypoint.sh) - no hace falta nada async ni un job en
    segundo plano para esto."""
    candado = extraction_lock.current_lock()
    return JsonResponse({
        'en_curso': bool(candado),
        'paso_actual': candado.paso_actual if candado else '',
        'usuario': candado.usuario if candado else '',
    })


# Botones encadenados: antes había que apretar, en orden, "0. Extraer" y después A, B, C,
# D, E a mano (o "1. Extraer" -> F -> "2. Asignar" -> G, etc). Ahora cada botón hace toda
# su cadena de una sola vez - si un paso intermedio falla, se corta ahí (no sigue con datos
# a medio importar) y el mensaje dice hasta dónde llegó.

def importar_carreras_az(pasos):
    """Corre los importadores A-E en el orden del README, acumulando el detalle de cada
    paso en `pasos` (lista, mutada in-place) para que el mensaje de error diga hasta dónde
    llegó si alguno falla a mitad de camino."""
    for action in ('importar_facultades', 'importar_carreras', 'importar_niveles',
                   'importar_profesores', 'importar_materias'):
        try:
            resultado = run_importar_web(action)
            pasos.append(resultado['detail'])
        except Exception as exc:
            raise ValueError(
                f"Se detuvo en \"{action}\" después de completar: {' | '.join(pasos)}. Error: {exc}"
            ) from exc


def run_cargar_carreras_web(cookie, stop_event):
    """'0. Extraer carreras' + importadores A-E, en el orden del README. Solo lo dispara
    quien tiene rol Administrador (chequeado en la vista, antes de llamar a esto)."""
    pasos = []
    resultado = run_extraer_carreras_web(cookie, stop_event)
    pasos.append(resultado['detail'])
    importar_carreras_az(pasos)
    return {'title': 'Carreras extraídas e importadas', 'detail': ' | '.join(pasos), 'count': None}


def run_importar_carreras_completo_web():
    """Solo los importadores A-E, sin volver a tocar Moodle - para cuando ya se extrajo
    (linkcarreras.json ya está actualizado, ej. tras arreglar un bug de parseo) y alcanza
    con re-importar sin pagar de nuevo el costo de una extracción completa."""
    pasos = []
    importar_carreras_az(pasos)
    return {'title': 'Carreras importadas (sin re-extraer)', 'detail': ' | '.join(pasos), 'count': None}


def run_cargar_tareas_web(selected_ids, cookie, stop_event, profesor):
    """'1. Extraer tareas' -> 'F. Importar tareas' -> '2. Asignar tareas' ->
    'G. Importar asignación'. Si la extracción se detuvo a mano (botón "Detener
    extracción") o cualquier paso de la cadena falla, no sigue con los siguientes -
    importar/asignar sobre datos a medio traer ensuciaría la base."""
    pasos = []
    resultado = run_extraer_tareas_web(selected_ids, cookie, stop_event, profesor=profesor)
    pasos.append(resultado['detail'])
    if resultado.get('detenido'):
        return {'title': 'Tareas extraídas (detenido)', 'detail': ' | '.join(pasos), 'count': resultado['count']}

    try:
        resultado = run_importar_tareas_web()
        pasos.append(resultado['detail'])
        resultado = run_asignacion_web(selected_ids, profesor)
        pasos.append(resultado['detail'])
        resultado = run_importar_asignacion_web()
        pasos.append(resultado['detail'])
    except Exception as exc:
        raise ValueError(f"Se detuvo después de: {' | '.join(pasos)}. Error: {exc}") from exc

    return {
        'title': 'Tareas extraídas, asignadas e importadas',
        'detail': ' | '.join(pasos),
        'count': None,
    }


def run_cargar_estudiantes_web(selected_ids, cookie, stop_event, profesor):
    """'3. Extraer estudiantes' -> 'H. Importar estudiantes'."""
    pasos = []
    resultado = run_estudiantes_web(selected_ids, cookie, stop_event, profesor=profesor)
    pasos.append(resultado['detail'])
    if resultado.get('detenido'):
        return {'title': 'Estudiantes extraídos (detenido)', 'detail': ' | '.join(pasos), 'count': resultado['count']}

    try:
        resultado = run_importar_estudiantes_web()
        pasos.append(resultado['detail'])
    except Exception as exc:
        raise ValueError(f"Se detuvo después de: {' | '.join(pasos)}. Error: {exc}") from exc

    return {'title': 'Estudiantes extraídos e importados', 'detail': ' | '.join(pasos), 'count': None}


def run_cargar_ultimo_acceso_web(selected_ids, cookie, stop_event):
    """'3b. Extraer último acceso' -> 'I. Importar último acceso'."""
    pasos = []
    resultado = run_participantes_web(selected_ids, cookie, stop_event)
    pasos.append(resultado['detail'])
    if resultado.get('detenido'):
        return {'title': 'Último acceso extraído (detenido)', 'detail': ' | '.join(pasos), 'count': resultado['count']}

    try:
        resultado = run_importar_participantes_web()
        pasos.append(resultado['detail'])
    except Exception as exc:
        raise ValueError(f"Se detuvo después de: {' | '.join(pasos)}. Error: {exc}") from exc

    return {'title': 'Último acceso extraído e importado', 'detail': ' | '.join(pasos), 'count': None}


def run_extraer_detalle_web(selected_ids, cookie, stop_event=None):
    """Descripción + archivos adjuntos por el DOCENTE en cada tarea tipo 'assign' de los
    cursos seleccionados (ArchivoTarea) - separado de "1" a propósito: es otra vuelta
    completa por Moodle, una visita por tarea, mismo costo que "2. Extraer estudiantes".
    Solo tiene sentido después de que "1" ya haya importado esas tareas a la base - ver
    run_scraping.detalle_tarea(), que revienta con un mensaje claro si no encuentra
    ninguna."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer el detalle de sus tareas.')

    resultado, detenido = run_scraping.detalle_tarea(selected_ids, cookie=cookie, stop_event=stop_event)

    detalle = (
        f'Extracción de detalle de tareas completada: {len(resultado)} tarea(s) procesada(s), '
        f'guardadas en {config.JSON_DETALLES}.'
    )
    if detenido:
        detalle = f'Extracción detenida manualmente. Resultados parciales: {detalle}'
    return {
        'title': 'Detalle de tareas extraído',
        'detail': detalle,
        'count': len(resultado),
        'detenido': detenido,
    }


def run_importar_detalle_web():
    """Importa detalle.json (ya extraido por 'Extraer detalle de tareas') hacia
    Tarea.descripcion/url_entrega y ArchivoTarea (los archivos que subió el docente en la
    descripción)."""
    importar_detalles_tareas()
    return {
        'title': 'Detalle de tareas importado',
        'detail': 'Importación a la base de datos completada.',
        'count': None,
    }


def run_cargar_detalle_web(selected_ids, cookie, stop_event):
    """'2. Extraer detalle de tareas' -> 'Importar detalle de tareas'."""
    pasos = []
    resultado = run_extraer_detalle_web(selected_ids, cookie, stop_event)
    pasos.append(resultado['detail'])
    if resultado.get('detenido'):
        return {'title': 'Detalle de tareas extraído (detenido)', 'detail': ' | '.join(pasos), 'count': resultado['count']}

    try:
        resultado = run_importar_detalle_web()
        pasos.append(resultado['detail'])
    except Exception as exc:
        raise ValueError(f"Se detuvo después de: {' | '.join(pasos)}. Error: {exc}") from exc

    return {'title': 'Detalle de tareas extraído e importado', 'detail': ' | '.join(pasos), 'count': None}


def cursos_base_por_rol(request, role):
    """Set de cursos de partida para el selector de extracción, según el rol de
    PerfilUsuario - antes de aplicar los filtros de Carrera/Materia/búsqueda. Administrador
    ve todo; Decano ve su alcance asignado (+ lo que enseña como Docente, si también lo es
    - no es excluyente); Docente (y cualquier caso sin perfil) sigue el comportamiento de
    siempre, con los pills Todos/Estudiante/Docente (que solo tienen sentido para "qué
    cursos son MÍOS", no para un rol de supervisión como Decano/Administrador)."""
    rol_actual = get_rol(request.user)
    todos = load_courses()

    if rol_actual == PerfilUsuario.ADMINISTRADOR:
        return todos, False

    if rol_actual == PerfilUsuario.DECANO:
        materias_qs = materias_visibles_decano(request.user)
        profesor_actual = get_current_profesor(request)
        if profesor_actual:
            materias_qs = materias_qs | profesor_actual.materias.all()
        ids_decano = set(materias_qs.values_list('id', flat=True))
        return [c for c in todos if c['id'] in ids_decano], False

    return filter_courses_by_role(request, todos, role), True


@login_required
@requiere_rol(*ROLES_STAFF)
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    role = request.GET.get('role', request.POST.get('role', 'all'))
    carrera_dash = request.GET.get('carrera_dash', request.POST.get('carrera_dash', ''))
    materia_dash = request.GET.get('materia_dash', request.POST.get('materia_dash', ''))
    busqueda = (request.GET.get('q', request.POST.get('q', '')) or '').strip()

    courses, mostrar_pills = cursos_base_por_rol(request, role)
    mostrar_pill_docente = mostrar_pills and tiene_cursos_como(request, 'docente')
    mostrar_pill_estudiante = mostrar_pills and tiene_cursos_como(request, 'estudiante')
    # El pill "Estudiante" solo sirve si de verdad hay cursos propios como estudiante para
    # separar de los de docente - si no hay ninguno, todo el grupo de pills sobra (ya se ve
    # todo bajo "Todos" sin elegir nada).
    mostrar_pills = mostrar_pills and mostrar_pill_estudiante

    # Para los 2 dropdowns ("Carreras"/"Materias") se arman ANTES de aplicar sus propios
    # filtros, para que siempre muestren todas las opciones del alcance del usuario, no
    # solo la ya elegida.
    carreras_disponibles = sorted(
        {(c['carrera_id'], c['carrera_nombre']) for c in courses if c['carrera_id']},
        key=lambda par: par[1]
    )
    materias_disponibles = sorted(courses, key=lambda c: c['nombre'])

    if carrera_dash:
        courses = [c for c in courses if str(c['carrera_id']) == carrera_dash]
    if materia_dash:
        courses = [c for c in courses if str(c['id']) == materia_dash]
    if busqueda:
        q = busqueda.lower()
        courses = [
            c for c in courses
            if q in c['nombre'].lower()
            or q in c['carrera_nombre'].lower()
            or any(q in d.lower() for d in c['docentes'])
            or any(q in e.lower() for e in c['estudiantes'])
        ]

    # Ordenado por carrera para que el template pueda agruparlas con {% regroup %} (una
    # cuenta Administrador, o un Decano con una facultad entera asignada, puede tener
    # cientos de materias - como una sola grilla plana, antes había que scrollear sin fin
    # para encontrar una). {% regroup %} necesita la lista ya ordenada por esa clave.
    courses.sort(key=lambda c: (c['carrera_nombre'] or '', c['nombre']))

    selected_ids = parse_selected_course_ids(request)
    selected_ids_str = [str(cid) for cid in selected_ids]
    selected_count = len(selected_ids)
    action_result = None
    error = None
    abrir_modal_asignacion = False

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'importar_tareas':
                action_result = run_importar_tareas_web()
            elif action == 'asignacion':
                action_result = run_asignacion_web(selected_ids, get_current_profesor(request))
            elif action == 'importar_asignacion':
                action_result = run_importar_asignacion_web()
            elif action == 'ver_asignacion':
                # No corre nada: solo valida la seleccion y marca para reabrir el modal
                # despues del redirect - el contenido en si se arma mas abajo, en cada GET,
                # a partir de selected_ids (que el redirect conserva en la URL).
                if not selected_ids:
                    error = 'Debes seleccionar al menos un curso para revisar su asignación.'
                else:
                    abrir_modal_asignacion = True
            elif action == 'guardar_asignacion_manual':
                action_result = run_guardar_asignacion_manual_web(request.POST, selected_ids)
                abrir_modal_asignacion = True
            elif action == 'importar_estudiantes':
                action_result = run_importar_estudiantes_web()
            elif action == 'importar_participantes':
                action_result = run_importar_participantes_web()
            elif action in ('cargar_carreras', 'cargar_tareas', 'cargar_detalle', 'cargar_estudiantes',
                             'cargar_ultimo_acceso', 'extraer_carreras', 'extraer_tareas', 'estudiantes',
                             'extraer_participantes'):
                # Unicas acciones que llaman a Moodle de verdad: pasan por el candado global
                # para que no arranquen dos extracciones de usuarios distintos en paralelo.
                # "cargar_carreras" ademas es la unica que solo puede disparar un Administrador
                # (toca Facultad/Carrera/Nivel/Profesor para TODO el sistema, no solo lo propio).
                if action == 'cargar_carreras' and not es_administrador(request.user):
                    raise ValueError('Solo una cuenta Administrador puede extraer e importar carreras.')
                cookie = request.session.get('MoodleSession')
                if not cookie:
                    # "Expiracion perezosa", paso previo a extraer: si la sesion del
                    # navegador no la tiene (pestaña nueva, otro dispositivo), se intenta
                    # descifrar la que esta guardada en la base para este profesor - solo
                    # si no paso ya el tiempo limite. Si funciona, se la deja en la sesion
                    # igual que antes, asi el resto de la extraccion no se entera del
                    # cambio (sigue leyendo cookie de esta misma variable).
                    profesor_actual = get_current_profesor(request)
                    if profesor_actual and profesor_actual.cookie_vigente():
                        cookie = descifrar_cookie(request.user, profesor_actual.moodle_cookie_cifrada)
                        if cookie:
                            request.session['MoodleSession'] = cookie
                if not cookie:
                    # Sin esto, se tomaba el candado global y recien se descubria que no
                    # habia cookie al fallar la primera request a Moodle (login redirect ->
                    # SesionExpiradaError) - ocupando el candado para nada y tardando mas en
                    # avisar. Frenar antes de tocar Moodle o el candado.
                    raise ValueError(
                        'No hay ninguna cookie de Moodle guardada, o venció (dura 2 horas). '
                        'Extraela de nuevo con el botón de cookie arriba antes de iniciar una extracción.'
                    )
                job_id, aviso_candado_vencido = extraction_lock.try_acquire_lock(request.user.username)
                if job_id is None:
                    candado = extraction_lock.current_lock()
                    error = (
                        f'Ya hay una extracción en curso (iniciada por {candado.usuario}). '
                        'Esperá a que termine o cancelala vos mismo si es tuya, e intentá de nuevo.'
                    )
                else:
                    stop_event = extraction_lock.get_stop_event(job_id)
                    try:
                        profesor_actual = get_current_profesor(request)
                        if action in ('extraer_carreras', 'cargar_carreras'):
                            action_result = (
                                run_cargar_carreras_web(cookie, stop_event) if action == 'cargar_carreras'
                                else run_extraer_carreras_web(cookie, stop_event)
                            )
                        elif action in ('extraer_tareas', 'cargar_tareas'):
                            action_result = (
                                run_cargar_tareas_web(selected_ids, cookie, stop_event, profesor_actual)
                                if action == 'cargar_tareas'
                                else run_extraer_tareas_web(selected_ids, cookie, stop_event, profesor=profesor_actual)
                            )
                        elif action in ('extraer_participantes', 'cargar_ultimo_acceso'):
                            action_result = (
                                run_cargar_ultimo_acceso_web(selected_ids, cookie, stop_event)
                                if action == 'cargar_ultimo_acceso'
                                else run_participantes_web(selected_ids, cookie, stop_event)
                            )
                        elif action == 'cargar_detalle':
                            action_result = run_cargar_detalle_web(selected_ids, cookie, stop_event)
                        else:
                            action_result = (
                                run_cargar_estudiantes_web(selected_ids, cookie, stop_event, profesor_actual)
                                if action == 'cargar_estudiantes'
                                else run_estudiantes_web(selected_ids, cookie, stop_event, profesor=profesor_actual)
                            )
                        if aviso_candado_vencido:
                            action_result['warning'] = aviso_candado_vencido
                    finally:
                        extraction_lock.release_lock(job_id)
            elif action == 'importar_carreras_completo':
                # "Solo importar" del cuadro de confirmación de "0.": no toca Moodle, no
                # necesita cookie ni el candado - mismo gate de Administrador que
                # "cargar_carreras" porque también escribe Facultad/Carrera/Nivel/Profesor/
                # Materia para todo el sistema.
                if not es_administrador(request.user):
                    raise ValueError('Solo una cuenta Administrador puede importar carreras.')
                action_result = run_importar_carreras_completo_web()
            elif action in IMPORTADORES_CARRERAS:
                action_result = run_importar_web(action)
            else:
                error = 'Acción desconocida.'
        except Exception as exc:
            error_str = str(exc)
            # Antes, un error de cookie/sesión redirigía a una pantalla aparte para
            # "recuperar" pegando una cookie nueva y reintentar. Ya no: cualquier error
            # durante una extracción la detiene del todo (el candado ya se libera en el
            # finally de arriba) y se muestra acá mismo, como cualquier otro error - nada
            # de intentar seguir a mitad de camino.
            if any(word in error_str.lower() for word in ['cookie', 'sesión', 'session', 'autenticación', 'moodlesession']):
                error_str = f"Sesión expirada: {error_str}"
            error = error_str
            traceback.print_exc()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Pedido por fetch() desde JS (los botones "cargar_*" de extracción, ver
            # dashboard.html): nada de Post-Redirect-Get ni de mover al usuario de donde
            # está - se devuelve el resultado tal cual y la página lo muestra en el lugar
            # (SweetAlert2), sin recargar ni perder la selección de cursos ni el scroll.
            return JsonResponse({
                'action_result': action_result,
                'error': error,
                'abrir_modal_asignacion': bool(abrir_modal_asignacion and not error),
            })

        # Post-Redirect-Get: sin esto, la ultima peticion del navegador queda como el POST
        # de la accion. Si el usuario recarga (F5) y confirma "reenviar formulario", el
        # navegador repite ese POST tal cual - re-disparando la misma accion, scraping real
        # incluido (extraction_lock no protege esto: ya se libero para cuando se llega a
        # refrescar). El resultado/error se guarda un instante en sesion ("flash") y se
        # consume en el GET de abajo, para poder mostrarlo despues del redirect.
        request.session['dashboard_flash'] = {'action_result': action_result, 'error': error}
        redirect_params = [('role', role)] + [('courses', cid) for cid in selected_ids_str]
        if carrera_dash:
            redirect_params.append(('carrera_dash', carrera_dash))
        if materia_dash:
            redirect_params.append(('materia_dash', materia_dash))
        if busqueda:
            redirect_params.append(('q', busqueda))
        if abrir_modal_asignacion and not error:
            redirect_params.append(('modal', 'asignacion'))
        return redirect(f"{reverse('dashboard')}?{urlencode(redirect_params)}")

    flash = request.session.pop('dashboard_flash', None) or {}
    action_result = flash.get('action_result')
    error = flash.get('error')

    candado_actual = extraction_lock.current_lock()
    profesor_actual = get_current_profesor(request)
    cookie_guardada = bool(request.session.get('MoodleSession')) or bool(
        profesor_actual and profesor_actual.cookie_vigente()
    )
    context = {
        'courses': courses,
        'course_count': len(courses),
        'selected_ids': selected_ids_str,
        'selected_count': selected_count,
        'role': role,
        'action_result': action_result,
        'error': error,
        'extraccion_en_curso': candado_actual,
        'cookie_guardada': cookie_guardada,
        'asignacion_detalle': construir_asignacion_detalle(selected_ids),
        'abrir_modal_asignacion': request.GET.get('modal') == 'asignacion',
        'categorias_peso': [{'key': cat, 'label': CATEGORIA_LABELS[cat]} for cat in CATEGORIAS_PESO],
        'es_administrador': es_administrador(request.user),
        'mostrar_pills_rol': mostrar_pills,
        'mostrar_pill_docente': mostrar_pill_docente,
        'mostrar_pill_estudiante': mostrar_pill_estudiante,
        'carreras_disponibles': carreras_disponibles,
        'materias_disponibles': materias_disponibles,
        'carrera_dash': carrera_dash,
        'materia_dash': materia_dash,
        'busqueda': busqueda,
        # Con algun filtro ya puesto el resultado es chico y conviene ver los grupos de
        # carrera abiertos de entrada, en vez de obligar a desplegarlos para ver lo que ya
        # se filtro a proposito.
        'grupos_carrera_abiertos': bool(carrera_dash or materia_dash or busqueda),
    }
    return render(request, 'web/dashboard.html', context)


@login_required
@requiere_rol(*ROLES_STAFF)
@require_http_methods(['POST'])
def detener_extraccion(request):
    """Boton de emergencia: marca la extraccion en curso para que se corte apenas termine
    la seccion que este en vuelo, en vez de esperar a que acabe sola o vencer el timeout.

    Solo puede detenerla quien la inicio, o un admin (request.user.is_staff) - antes
    cualquier usuario logueado podia cortar la extraccion de cualquier otro sin ninguna
    verificacion. El template ya deshabilita el boton para quien no cumple esto, pero el
    chequeo real tiene que estar aca: un POST directo a esta URL se saltaria el HTML."""
    candado = extraction_lock.current_lock()
    if candado and not (request.user.is_staff or candado.usuario == request.user.username):
        return redirect(f"{reverse('dashboard')}?detenido=sin_permiso")
    detenida = extraction_lock.request_stop()
    return redirect(f"{reverse('dashboard')}?detenido={'1' if detenida else '0'}")

@login_required
def resumen(request):
    def parse_date_string(fecha_str):
        try:
            partes = fecha_str.split(',')

            # "7 de julio de 2025"
            fecha_texto = partes[1].strip()

            # "20:30"
            hora_texto = partes[2].strip()

            dia, _, resto = fecha_texto.partition(' de ')
            mes, _, anio = resto.partition(' de ')

            hora, minuto = map(int, hora_texto.split(':'))

            return datetime(
                int(anio),
                MESES[mes.lower()],
                int(dia),
                hora,
                minuto
            )

        except Exception as e:
            print("Error fecha:", fecha_str, e)
            return None
        
    def overload_student_count(entregas):

        cargas = defaultdict(int)

        for entrega in entregas:
            fecha = parse_date_string(entrega.tarea.cierre)
            if not fecha:
                continue
            fecha = fecha.date() if hasattr(fecha, 'date') else fecha
            clave = (
                entrega.estudiante_id,
                fecha
            )
            cargas[clave] += 1
                
        print("TOTAL CLAVES:", len(cargas))
            
        for clave, cantidad in list(cargas.items())[:20]:
            print(clave, cantidad)
            
        estudiantes_sobrecargados = set()
        for (estudiante_id, fecha), cantidad in cargas.items():
            if cantidad >= 3:                    
                print("SOBRECARGA:", estudiante_id, fecha, cantidad)
                estudiantes_sobrecargados.add(estudiante_id)
        return len(estudiantes_sobrecargados)

    kpis = {
        'materias': 0,
        'docentes': 0,
        'estudiantes': 0,
        'actividades': 0,
        'actividades_pendientes': 0,
        'materias_con_retraso': 0,
        'posibles_sobrecargas': 0,
        'ultima_sincronizacion': None,
    }

    # Alcance por rol: Administrador ve todo; Decano/Docente, solo lo suyo
    # (materias_visibles); Visitante no ve nada salvo que filtre por facultad o carrera.
    rol = get_rol(request.user)
    facultad_id = request.GET.get('facultad') or None
    carrera_id = request.GET.get('carrera') or None
    if rol == PerfilUsuario.ADMINISTRADOR:
        materias_qs = Materia.objects.all()
    else:
        materias_qs = materias_visibles(request.user, facultad_id=facultad_id, carrera_id=carrera_id)

    try:
        from django.db.models import Count, Q, Max

        kpis['materias'] = materias_qs.count()
        kpis['docentes'] = Profesor.objects.filter(materias__in=materias_qs).distinct().count()
        kpis['estudiantes'] = Estudiante.objects.filter(
            entregas__tarea__unidad__materia__in=materias_qs
        ).distinct().count()

        # contar tareas totalesfiltranndo por mitek etek y examen

        FILTROS_ACTIVIDADES = [
            "Examen",
            "tek",
        ]

        filtro_tareas = Q()

        for filtro in FILTROS_ACTIVIDADES:
            filtro_tareas |= Q(titulo__icontains=filtro)

        tareas_filtradas = Tarea.objects.filter(filtro_tareas, unidad__materia__in=materias_qs)

        tarea_ids = list(
            tareas_filtradas.values_list('id', flat=True)
        )

        kpis['actividades'] = len(tarea_ids)

        #kpis['actividades'] = Tarea.objects.count()
        #tareas pendientes en rango de entrga
        
        pendientes = Entrega.objects.filter(
            tarea_id__in=tarea_ids
        ).filter(
            Q(estado__icontains='sin entrega')
        )

        kpis['actividades_pendientes'] = (
            pendientes
            .values('tarea_id')
            .distinct()
            .count()
        )

        #kpis['actividades_pendientes'] = pendientes.count()

        #pendientes = Entrega.objects.filter(
        #    Q(estado__icontains='sin entregar') |
        #    Q(estado__icontains='enviado para calificar') |
        #    Q(calificacion__isnull=True) |
        #    Q(calificacion__exact='')
        #)
        #kpis['actividades_pendientes'] = pendientes.count()

        #Sobrecargas
        entregas = Entrega.objects.select_related(
            'tarea',
            'estudiante'
        ).filter(
            tarea_id__in=tarea_ids
        )

        for entrega in entregas[:5]:
            print("dato:", entrega.tarea.cierre, entrega.estudiante_id)
            print("Entrega:",len(entregas))

        kpis['posibles_sobrecargas'] = overload_student_count(entregas)

        #Tareas con retraso 
        hoy = datetime.now().date()
        materia_retraso_ids = set()
        entregas = Entrega.objects.filter(
            tarea_id__in=tarea_ids
        )

        #for entrega in entregas[:5]:
        #    print("FECHA:", entrega.tarea.cierre)
        #    print("PARSE:", parse_date_string(entrega.tarea.cierre))
        #    print("HOY:", hoy)
        #    print("Entregas:",len(entregas))

        for entrega in entregas:
            cierre_date = parse_date_string(entrega.tarea.cierre)
        #    print("cierre_date:", cierre_date)

            if not cierre_date:
                continue
            cierre_date = cierre_date.date()
            if (
                cierre_date < hoy and
                entrega.estado and
                'sin entrega' in entrega.estado.lower()

            ):
                #print(
                #    "TAREA:", entrega.tarea.titulo,
                #    "| ESTADO:", repr(entrega.estado),
                #    "| materia_id:", entrega.tarea.unidad.materia_id
                #)
                materia_retraso_ids.add(
                    entrega.tarea.unidad.materia_id
                )

        kpis['materias_con_retraso'] = len(materia_retraso_ids)
        ##hoy = datetime.now().date()
        ##materia_retraso_ids = set()
        ##for tarea in Tarea.objects.exclude(cierre__isnull=True).exclude(cierre__exact=''):
        ##    cierre_date = parse_date_string(tarea.cierre)
        ##    if cierre_date and cierre_date < hoy and tarea.unidad_id:
        ##        materia_retraso_ids.add(tarea.unidad.materia_id)
        ##kpis['materias_con_retraso'] = len(materia_retraso_ids)

        ultima_actualizacion = Materia.objects.aggregate(last=Max('actualizado')).get('last')
        ultima_actualizacion = max(filter(None, [ultima_actualizacion, Profesor.objects.aggregate(last=Max('actualizado')).get('last')]))
        if ultima_actualizacion:
            kpis['ultima_sincronizacion'] = ultima_actualizacion.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass

    alertas = []
    try:
        if kpis['materias'] == 0:
            alertas.append('No hay materias monitoreadas.')

        materias_sin_actividades = Materia.objects.filter(
            unidades__tareas__isnull=True, pk__in=materias_qs
        ).distinct()
        if materias_sin_actividades.exists():
            alertas.append(f"Materias sin actividades: {materias_sin_actividades.count()}")

        tareas_sin_cierre = Tarea.objects.filter(
            Q(cierre__isnull=True) | Q(cierre__exact=''), unidad__materia__in=materias_qs
        )
        if tareas_sin_cierre.exists():
            alertas.append(f"Tareas sin fecha de cierre: {tareas_sin_cierre.count()}")

        if kpis['posibles_sobrecargas'] > 0:
            alertas.append(f"Estudiantes con posible sobrecarga: {kpis['posibles_sobrecargas']}")

        if kpis['materias_con_retraso'] > 0:
            alertas.append(f"Materias con retraso: {kpis['materias_con_retraso']}")
    except Exception:
        pass

    context = {
        'kpis': kpis,
        'alertas': alertas,
    }
    #alertas detalladas: listar materias sin actividades, tareas sin cierre y estudiantes sobrecargados

    try:
        from django.db.models import Count
        chart_kpis = {
            'labels': ['Pendientes', 'Calificadas'],
            'data': [kpis['actividades_pendientes'], max(0, kpis['actividades'] - kpis['actividades_pendientes'])]
        }

        materias_counts = (
            Tarea.objects.filter(unidad__materia__in=materias_qs)
            .values('unidad__materia__nombre')
            .annotate(count=Count('id'))
            .order_by('-count')[:8]
        )
        labels = [m.get('unidad__materia__nombre') or 'Desconocida' for m in materias_counts]
        data = [m.get('count') for m in materias_counts]
        chart_materias = {'labels': labels, 'data': data}

        datos_tareas_por_ano = (
            Tarea.objects.filter(unidad__materia__in=materias_qs)
            .values('unidad__materia__gestion').annotate(count=Count('id')).order_by('unidad__materia__gestion')
        )
        datos_entregas_por_ano = (
            Entrega.objects.filter(tarea__unidad__materia__in=materias_qs)
            .values('tarea__unidad__materia__gestion').annotate(count=Count('id')).order_by('tarea__unidad__materia__gestion')
        )

        yearly_data = {}
        for item in datos_tareas_por_ano:
            year = item.get('unidad__materia__gestion') or 'Sin año'
            yearly_data[year] = {'tareas': item.get('count', 0), 'entregas': 0}
        for item in datos_entregas_por_ano:
            year = item.get('tarea__unidad__materia__gestion') or 'Sin año'
            yearly_data.setdefault(year, {'tareas': 0, 'entregas': 0})
            yearly_data[year]['entregas'] = item.get('count', 0)

        def sort_year_key(value):
            try:
                return (int(value), '')
            except Exception:
                return (9999, str(value))

        sorted_years = sorted(yearly_data.keys(), key=sort_year_key)
        year_labels = [str(year) for year in sorted_years]
        year_tareas = [yearly_data[year]['tareas'] for year in sorted_years]
        year_entregas = [yearly_data[year]['entregas'] for year in sorted_years]

        chart_yearly = {
            'labels': year_labels,
            'tareas': year_tareas,
            'entregas': year_entregas,
        }

        context['chart_kpis_json'] = json.dumps(chart_kpis)
        context['chart_materias_json'] = json.dumps(chart_materias)
        context['chart_yearly_json'] = json.dumps(chart_yearly)
    except Exception:
        context['chart_kpis_json'] = json.dumps({'labels': [], 'data': []})
        context['chart_materias_json'] = json.dumps({'labels': [], 'data': []})
        context['chart_yearly_json'] = json.dumps({'labels': [], 'tareas': [], 'entregas': []})

    if rol == PerfilUsuario.VISITANTE:
        context['es_visitante'] = True
        context['facultades_filtro'] = Facultad.objects.order_by('nombre')
        context['carreras_filtro'] = Carrera.objects.select_related('facultad').order_by('facultad__nombre', 'nombre')
        context['facultad_seleccionada'] = facultad_id
        context['carrera_seleccionada'] = carrera_id

    return render(request, 'web/resumen.html', context)


@login_required
@requiere_rol(*ROLES_STAFF)
def materias_view(request):
    materias = materias_visibles(request.user).select_related(
        'carrera',
        'nivel'
    ).prefetch_related(
        'profesores'
    )
    context = {'materias': materias}
    return render(request, 'web/materias.html', context)


@login_required
@requiere_rol(*ROLES_GESTION)
def docentes_view(request):

    docentes = Profesor.objects.all()
    if es_administrador(request.user):
        # Administrador ve TODOS los docentes, incluso sin ninguna materia todavia
        # (recien importado, por ejemplo) - el scope de materias_visibles() solo tiene
        # sentido para acotar a un Decano a lo suyo.
        pass
    else:
        docentes = docentes.filter(materias__in=materias_visibles(request.user)).distinct()

    docentes = docentes.select_related('user', 'user__perfil').annotate(
    total_materias=Count(
        'materias',
        distinct=True
        ),
    total_assigns=Count(
        'materias__unidades__tareas',
        filter=Q(materias__unidades__tareas__tipo='assign'),
        distinct=True
        )
    ).prefetch_related(
        'materias', 'user__perfil__facultades', 'user__perfil__carreras', 'user__perfil__materias'
    ).order_by(
        'nombre'
    )

    es_admin = es_administrador(request.user)

    for docente in docentes:

        contador = Counter()

        for materia in docente.materias.all():
            contador[materia.gestion] += 1

        docente.gestiones = dict(
            sorted(contador.items())
        )

        # Datos para el modal de "Gestionar rol" (solo Administrador la usa, pero se
        # calculan solo si hace falta para no pagar el costo en el resto de los roles).
        if es_admin:
            perfil = getattr(docente.user, 'perfil', None) if docente.user else None
            docente.rol_actual = perfil.rol if perfil else None
            docente.perfil_facultades_ids = [f.id for f in perfil.facultades.all()] if perfil else []
            docente.perfil_carreras_ids = [c.id for c in perfil.carreras.all()] if perfil else []
            docente.perfil_materias_ids = [m.id for m in perfil.materias.all()] if perfil else []

    context = {
        'docentes': docentes,
    }
    if es_admin:
        context['roles_choices'] = PerfilUsuario.ROLES
        context['facultades_todas'] = Facultad.objects.order_by('nombre')
        context['carreras_todas'] = Carrera.objects.select_related('facultad').order_by('facultad__nombre', 'nombre')
        context['materias_todas'] = Materia.objects.select_related('carrera').order_by('carrera__nombre', 'nombre')

    return render(
        request,
        'web/docentes.html',
        context
    )


@login_required
@requiere_rol(PerfilUsuario.ADMINISTRADOR)
@require_http_methods(['POST'])
def gestionar_rol_docente(request):
    """Cambia el rol (y, si es Decano, el alcance de facultades/carreras/materias) del
    usuario vinculado a un Profesor. Visible solo en la tabla de Docentes para una cuenta
    Administrador (ver docentes.html) - un Decano puede VER esta tabla pero no gestionar
    roles desde ella."""
    profesor_id = request.POST.get('profesor_id')
    nuevo_rol = request.POST.get('rol')

    profesor = Profesor.objects.filter(pk=profesor_id).first()
    if not profesor:
        return JsonResponse({'ok': False, 'error': 'No se encontró ese docente.'}, status=404)
    if not profesor.user:
        return JsonResponse(
            {'ok': False, 'error': f'{profesor.nombre} todavía no tiene una cuenta registrada en Centralizador; no se le puede asignar un rol hasta que se registre.'},
            status=400,
        )
    if nuevo_rol not in dict(PerfilUsuario.ROLES):
        return JsonResponse({'ok': False, 'error': 'Rol inválido.'}, status=400)

    perfil, _ = PerfilUsuario.objects.get_or_create(user=profesor.user)
    perfil.rol = nuevo_rol

    if nuevo_rol == PerfilUsuario.DECANO:
        facultades_ids = request.POST.getlist('facultades')
        carreras_ids = request.POST.getlist('carreras')
        materias_ids = request.POST.getlist('materias')
        perfil.save()
        perfil.facultades.set(Facultad.objects.filter(pk__in=facultades_ids))
        perfil.carreras.set(Carrera.objects.filter(pk__in=carreras_ids))
        perfil.materias.set(Materia.objects.filter(pk__in=materias_ids))
    else:
        # Al salir de Decano, se limpia el alcance que tuviera guardado - no tiene sentido
        # dejarlo colgado si despues vuelve a ser Decano se vuelve a elegir de cero.
        perfil.save()
        perfil.facultades.clear()
        perfil.carreras.clear()
        perfil.materias.clear()

    return JsonResponse({'ok': True, 'rol': nuevo_rol, 'rol_display': dict(PerfilUsuario.ROLES)[nuevo_rol]})


@login_required
@requiere_rol(*ROLES_STAFF)
def estudiantes_view(request):

    estudiantes = Estudiante.objects.all()
    if not es_administrador(request.user):
        estudiantes = estudiantes.filter(
            entregas__tarea__unidad__materia__in=materias_visibles(request.user)
        ).distinct()

    estudiantes = estudiantes.annotate(
        total_materias=Count(
            'entregas__tarea__unidad__materia',
            distinct=True
        ),
        total_entregas=Count(
            'entregas',
            distinct=True
        )
    ).prefetch_related(
        'entregas__tarea__unidad__materia'
    )


    for estudiante in estudiantes:

        contador = Counter()

        materias = {
            entrega.tarea.unidad.materia
            for entrega in estudiante.entregas.all()
                if entrega.tarea and entrega.tarea.unidad
        }

        for materia in materias:
            contador[materia.gestion] += 1

        estudiante.gestiones = dict(
            sorted(contador.items())
        )

        # Moodle no tiene un "perfil general" sin curso - /user/view.php?id=X alcanza para
        # llegar al perfil igual, aunque algunos campos del tab "Detalles del curso" no se
        # vean sin el parametro course=.
        estudiante.perfil_url = f"{config.BASE_URL}/user/view.php?id={estudiante.moodle_userid}"

    context = {
        'estudiantes': estudiantes
    }

    return render(
        request,
        'web/estudiantes.html',
        context
    )


def _archivos_lista(qs):
    return [{'nombre': a.nombre, 'url': a.url} for a in qs]


@login_required
@requiere_rol(*ROLES_STAFF)
def estudiante_avances(request, estudiante_id):
    """JSON para el modal "Ver avances" de estudiantes.html: todas las entregas de este
    estudiante (opcionalmente filtradas por materia), con el archivo que el estudiante
    adjuntó (ArchivoEntrega) y el detalle/archivos de la tarea en sí (ArchivoTarea) uno al
    lado del otro, para comparar "qué entregó" contra "qué pedía la tarea"."""
    estudiante = Estudiante.objects.filter(pk=estudiante_id).first()
    if not estudiante:
        return JsonResponse({'error': 'No se encontró ese estudiante.'}, status=404)

    materias_qs = materias_visibles(request.user) if not es_administrador(request.user) else Materia.objects.all()
    entregas = (
        Entrega.objects.filter(estudiante=estudiante, tarea__unidad__materia__in=materias_qs)
        .select_related('tarea__unidad__materia')
        .prefetch_related('archivos_entrega', 'tarea__archivos_tarea')
        .order_by('tarea__unidad__materia__nombre', 'tarea__titulo')
    )

    # Para el dropdown del modal: todas las materias donde este estudiante tiene al menos
    # una entrega, sin aplicar el filtro de materia_id (si no, la opcion elegida seria la
    # unica que queda en la lista una vez filtrado).
    materias_filtro = sorted(
        Materia.objects.filter(unidades__tareas__entregas__estudiante=estudiante, pk__in=materias_qs)
        .distinct().values_list('id', 'nombre'),
        key=lambda par: par[1],
    )

    materia_id = request.GET.get('materia_id')
    if materia_id:
        entregas = entregas.filter(tarea__unidad__materia_id=materia_id)

    filas = [{
        'materia': e.tarea.unidad.materia.nombre,
        'tarea': e.tarea.titulo,
        'tarea_url': e.tarea.url,
        'estado': e.estado or '—',
        'nota': f'{e.nota}/{e.nota_maxima}' if e.nota is not None else '—',
        'archivos_entrega': _archivos_lista(e.archivos_entrega.all()),
        'tarea_descripcion': e.tarea.descripcion,
        'archivos_tarea': _archivos_lista(e.tarea.archivos_tarea.all()),
    } for e in entregas]

    return JsonResponse({
        'estudiante': estudiante.nombre,
        'materias_filtro': [{'id': mid, 'nombre': nombre} for mid, nombre in materias_filtro],
        'entregas': filas,
    })


@login_required
@requiere_rol(*ROLES_GESTION)
def docente_avances(request, profesor_id):
    """JSON para el modal "Ver avances" de docentes.html: las tareas tipo 'assign' que este
    docente asignó (opcionalmente filtradas por materia), con la descripción y los archivos
    que subió en cada una (ArchivoTarea)."""
    docente = Profesor.objects.filter(pk=profesor_id).first()
    if not docente:
        return JsonResponse({'error': 'No se encontró ese docente.'}, status=404)

    materias_qs = materias_visibles(request.user) if not es_administrador(request.user) else Materia.objects.all()
    materias_docente = docente.materias.filter(pk__in=materias_qs).order_by('nombre')

    materia_id = request.GET.get('materia_id')
    if materia_id:
        materias_docente = materias_docente.filter(pk=materia_id)

    tareas = (
        Tarea.objects.filter(tipo='assign', unidad__materia__in=materias_docente)
        .select_related('unidad__materia')
        .prefetch_related('archivos_tarea')
        .order_by('unidad__materia__nombre', 'unidad__nombre', 'titulo')
    )

    filas = [{
        'materia': t.unidad.materia.nombre,
        'unidad': t.unidad.nombre,
        'tarea': t.titulo,
        'tarea_url': t.url,
        'cierre': t.cierre or '—',
        'descripcion': t.descripcion,
        'archivos_tarea': _archivos_lista(t.archivos_tarea.all()),
    } for t in tareas]

    materias_filtro = [
        {'id': m.id, 'nombre': m.nombre}
        for m in docente.materias.filter(pk__in=materias_qs).order_by('nombre')
    ]

    return JsonResponse({
        'docente': docente.nombre,
        'materias_filtro': materias_filtro,
        'tareas': filas,
    })


@login_required
@requiere_rol(*ROLES_STAFF)
def alertas_view(request):
    # Alertas detalladas: listar materias sin actividades, tareas sin cierre y estudiantes sobrecargados
    detalles = {}
    try:
        from django.db.models import Q, Count

        materias_qs = materias_visibles(request.user) if not es_administrador(request.user) else Materia.objects.all()

        materias_sin = Materia.objects.filter(
            unidades__tareas__isnull=True, pk__in=materias_qs
        ).distinct()
        detalles['materias_sin_actividades'] = list(materias_sin.values('id', 'nombre')[:200])

        tareas_sin_cierre_qs = Tarea.objects.filter(
            Q(cierre__isnull=True) | Q(cierre__exact=''),
            unidad__materia__in=materias_qs,
        )
        detalles['tareas_sin_cierre'] = list(tareas_sin_cierre_qs.values('moodle_id', 'titulo')[:200])

        # estudiantes con muchas entregas pendientes
        threshold = 8
        estudiantes_sobrecarga = (
            Entrega.objects.filter(
                Q(calificacion__isnull=True) | Q(calificacion__exact=''),
                tarea__unidad__materia__in=materias_qs,
            )
            .values('estudiante__id', 'estudiante__nombre')
            .annotate(pendientes=Count('id'))
            .filter(pendientes__gt=threshold)
        )
        detalles['estudiantes_sobrecarga'] = list(estudiantes_sobrecarga)

    except Exception:
        detalles = {}

    context = {'alertas_detalle': detalles}
    return render(request, 'web/alertas.html', context)




@login_required
@requiere_rol(*ROLES_STAFF)
@require_http_methods(['GET', 'POST'])
def predicciones_view(request):
    error = None

    if request.method == 'POST':
        if not es_administrador(request.user):
            error = 'Solo una cuenta Administrador puede generar el dataset.'
        else:
            try:
                from django.core.management import call_command
                salida = StringIO()
                call_command('exportar_dataset_ml', stdout=salida)
                request.session['predicciones_flash'] = {'detalle': salida.getvalue()}
            except Exception as exc:
                error = str(exc)
                traceback.print_exc()
        if error:
            request.session['predicciones_flash'] = {'error': error}
        return redirect('predicciones')

    flash = request.session.pop('predicciones_flash', None) or {}

    dataset_existe = os.path.exists(config.CSV_DATASET_ML)
    dataset_filas = None
    dataset_generado_en = None
    if dataset_existe:
        with open(config.CSV_DATASET_ML, encoding='utf-8') as archivo:
            dataset_filas = max(sum(1 for _ in archivo) - 1, 0)  # -1 por el encabezado
        dataset_generado_en = dj_timezone.make_aware(
            datetime.fromtimestamp(os.path.getmtime(config.CSV_DATASET_ML))
        )

    context = {
        'es_administrador': es_administrador(request.user),
        'dataset_existe': dataset_existe,
        'dataset_filas': dataset_filas,
        'dataset_generado_en': dataset_generado_en,
        'flash_detalle': flash.get('detalle'),
        'flash_error': flash.get('error'),
    }
    return render(request, 'web/predicciones.html', context)


@login_required
@requiere_rol(PerfilUsuario.ADMINISTRADOR)
@require_http_methods(['GET'])
def predicciones_descargar_csv(request):
    if not os.path.exists(config.CSV_DATASET_ML):
        request.session['predicciones_flash'] = {
            'error': 'Todavía no se generó el dataset. Usá "Generar dataset" primero.'
        }
        return redirect('predicciones')
    return FileResponse(
        open(config.CSV_DATASET_ML, 'rb'),
        as_attachment=True,
        filename='dataset_ml.csv',
        content_type='text/csv',
    )


def _materias_qs_reportes(request):
    return Materia.objects.all() if es_administrador(request.user) else materias_visibles(request.user)


@login_required
@requiere_rol(*ROLES_STAFF)
def reportes_view(request):
    materias_qs = _materias_qs_reportes(request)

    rol_acceso = request.GET.get('rol_acceso', 'todos')
    materia_acceso = request.GET.get('materia_acceso', '')
    docente_tareas = request.GET.get('docente_tareas', '')
    docente_material = request.GET.get('docente_material', '')

    context = {
        'materias_disponibles': materias_qs.order_by('nombre'),
        'docentes_disponibles': Profesor.objects.filter(materias__in=materias_qs).distinct().order_by('nombre'),
        'rol_acceso': rol_acceso,
        'materia_acceso': materia_acceso,
        'docente_tareas': docente_tareas,
        'docente_material': docente_material,
        'filas_acceso': datos_reporte_acceso(materias_qs, rol_acceso, materia_acceso),
        'filas_tareas': datos_reporte_contenido(materias_qs, 'assign', docente_tareas),
        'filas_material': datos_reporte_contenido(materias_qs, 'url', docente_material),
    }
    return render(request, 'web/reportes.html', context)


@login_required
@requiere_rol(*ROLES_STAFF)
def reportes_descargar(request, tipo, formato):
    if tipo not in REPORTES_DISPONIBLES:
        return JsonResponse({'error': 'Reporte desconocido.'}, status=404)
    if formato not in ('excel', 'pdf'):
        return JsonResponse({'error': 'Formato desconocido.'}, status=404)

    materias_qs = _materias_qs_reportes(request)
    if tipo == 'acceso':
        filas = datos_reporte_acceso(materias_qs, request.GET.get('rol_acceso', 'todos'), request.GET.get('materia_acceso', ''))
    else:
        filas = datos_reporte_contenido(
            materias_qs,
            'assign' if tipo == 'tareas' else 'url',
            request.GET.get('docente_tareas' if tipo == 'tareas' else 'docente_material', ''),
        )

    if formato == 'excel':
        buffer = generar_excel_reporte(tipo, filas)
        return FileResponse(
            buffer, as_attachment=True, filename=f'reporte_{tipo}.xlsx',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    buffer = generar_pdf_reporte(tipo, filas)
    return FileResponse(buffer, as_attachment=True, filename=f'reporte_{tipo}.pdf', content_type='application/pdf')


CATEGORIAS_PESO = ['mitek', 'etek', 'training', 'designlab', 'examen']
CATEGORIA_LABELS = {
    'mitek': 'Mi-Tek',
    'etek': 'E-Tek',
    'training': 'Training',
    'designlab': 'Design Lab',
    'examen': 'Examen',
}


def config_tareas_de(profesor):
    """Config de parciales/pesos del `profesor` dado, leida de las tablas normalizadas
    FechasParciales y PesosCategorias (data/models.py) - una fila por profesor en cada
    una, columnas fijas en vez de un blob JSON. Devuelve el mismo shape de dict que
    `run_scraping.asignacion_tareas()` ya esperaba ({'rangos_parciales': [...],
    'pesos_default': {...}}), asi esa funcion no tuvo que cambiar."""
    fechas = FechasParciales.objects.filter(profesor=profesor).first()
    rangos = [
        {
            'parcial': i,
            'inicio': getattr(fechas, f'p{i}_inicio', None).isoformat() if fechas and getattr(fechas, f'p{i}_inicio', None) else None,
            'fin': getattr(fechas, f'p{i}_fin', None).isoformat() if fechas and getattr(fechas, f'p{i}_fin', None) else None,
        }
        for i in range(1, 5)
    ]

    pesos_row = PesosCategorias.objects.filter(profesor=profesor).first()
    pesos = {cat: getattr(pesos_row, cat, 0) if pesos_row else 0 for cat in CATEGORIAS_PESO}

    return {'rangos_parciales': rangos, 'pesos_default': pesos}


@login_required
@requiere_rol(*ROLES_STAFF)
def configuracion_view(request):
    """Reemplaza al config_tareas.json que antes solo se editaba a mano y era compartido
    por todos (ver Versioines Demo/moodle_app_async/core/config_tareas.json) - ahora cada
    profesor tiene su propia config en Profesor.config_tareas. Los rangos de fecha de cada
    parcial y los pesos por categoria de tarea (Mi-Tek/E-Tek/Training/Design Lab/Examen)
    son lo que "3. Asignar tareas" (run_asignacion_web -> run_scraping.asignacion_tareas())
    usa para construir asignacion.json."""
    error = None
    saved = False

    profesor = get_current_profesor(request)
    if profesor is None:
        context = {
            'error': (
                'Tu cuenta no está vinculada a ningún Profesor todavía, así que no hay '
                'dónde guardar esta configuración. Iniciá sesión con un usuario que '
                'coincida con un docente registrado.'
            ),
            'rangos_parciales': [],
            'pesos_rows': [],
            'total_pesos': 0,
            'saved': False,
            'extension_version': extension_version(),
        }
        return render(request, 'web/configuracion.html', context)

    config_actual = config_tareas_de(profesor)

    if request.method == 'POST':
        try:
            rangos = []
            for i in range(1, 5):
                inicio = request.POST.get(f'parcial_{i}_inicio', '').strip() or None
                fin = request.POST.get(f'parcial_{i}_fin', '').strip() or None
                if inicio and fin and inicio > fin:
                    raise ValueError(f'El Parcial {i} tiene la fecha de inicio después de la de fin.')
                rangos.append({'parcial': i, 'inicio': inicio, 'fin': fin})

            pesos = {}
            for cat in CATEGORIAS_PESO:
                valor = request.POST.get(f'peso_{cat}', '0').strip()
                peso = int(valor) if valor else 0
                if peso < 0:
                    raise ValueError('Los pesos no pueden ser negativos.')
                pesos[cat] = peso

            fechas_kwargs = {}
            for r in rangos:
                i = r['parcial']
                fechas_kwargs[f'p{i}_inicio'] = r['inicio']
                fechas_kwargs[f'p{i}_fin'] = r['fin']
            FechasParciales.objects.update_or_create(profesor=profesor, defaults=fechas_kwargs)
            PesosCategorias.objects.update_or_create(profesor=profesor, defaults=pesos)

            config_actual = {'rangos_parciales': rangos, 'pesos_default': pesos}
            saved = True
        except ValueError as exc:
            error = str(exc) if str(exc) else 'Los pesos deben ser números enteros.'

    pesos_rows = [
        {'cat': cat, 'label': CATEGORIA_LABELS[cat], 'peso': config_actual['pesos_default'][cat]}
        for cat in CATEGORIAS_PESO
    ]

    context = {
        'rangos_parciales': config_actual['rangos_parciales'],
        'pesos_rows': pesos_rows,
        'total_pesos': sum(config_actual['pesos_default'].values()),
        'saved': saved,
        'error': error,
        'extension_version': extension_version(),
    }
    return render(request, 'web/configuracion.html', context)


def extension_privacidad_view(request):
    """Politica de privacidad de la extension de Chrome "Captura cookie Moodle" (ver
    chrome_extension/) - pagina publica a proposito (sin @login_required): la Chrome Web
    Store la exige como requisito de publicacion y el revisor de Google no esta logueado
    en Centralizador."""
    return render(request, 'web/extension_privacidad.html')


def parse_date_string(fecha_str):
    try:
        partes = fecha_str.split(',')

        # "7 de julio de 2025"
        fecha_texto = partes[1].strip()

        dia, _, resto = fecha_texto.partition(' de ')
        mes, _, anio = resto.partition(' de ')

        return datetime(
            int(anio),
            MESES[mes.lower()],
            int(dia)
        ).date()

    except Exception as e:
        print("Error fecha:", fecha_str, e)
        return None