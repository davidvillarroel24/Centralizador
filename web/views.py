import asyncio
import traceback
import os
import re
import json
from datetime import datetime, timezone, date

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from urllib.parse import urlencode

from gatfh import config
from scraping.scrapers.tareas import obtener_tareas_async
from scraping.scrapers.detallesprofesores import obtener_tareas_docente_async
from scraping.scrapers.normalizacion import extraer_tareas_planas
from scraping.scrapers.asignartareas import auto_asignar_tareas, mostrar_resumen_tareas, generar_config_final
from scraping.scrapers.carreras import obtener_categorias, extraer_categorias, cargar_todo, procesar_datos
from scraping.scrapers.session import MoodleSession
from services.data_utils import cargarjson, exportarjson
from services.data_utils.import_to_db import import_tareas_from_json
from services.data_utils.import_estudiantes_to_db import import_estudiantes_from_json
from services.extraccion.trasformar import extraer_transformar
from services.utils import extraction_lock
from data.models import Materia, Profesor, Estudiante, Tarea, Entrega

from collections import Counter
from django.db.models import Count
from collections import defaultdict
from datetime import datetime

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

def handle_session_error(request, error_msg, next_url='/web/'):
    """Redirige a cookie_recovery_view con mensajes de error y la URL a retornar."""
    params = urlencode({'error': error_msg, 'next': next_url})
    return redirect(f'/web/session-cookie/?{params}')


def load_courses():
    """Carga los cursos (Materia) desde Postgres en vez del JSON legado.

    El resto del dashboard (selección de cursos, filtrado de tareas por
    asignatura) sigue trabajando con dicts {id, asignatura, url} para no
    tener que tocar el pipeline de scraping basado en cursos.json.
    """
    materias = Materia.objects.select_related('carrera').order_by('nombre')
    return [
        {
            'id': materia.id,
            'asignatura': materia.moodle_nombre,
            'url': materia.moodle_url,
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
        cookie_value = request.POST.get('moodle_cookie', '').strip()
        if not username or not password or not cookie_value:
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
                profesor.moodle_session_hash = make_password(cookie_value)
                profesor.user = user
                profesor.save(update_fields=['moodle_session_hash', 'user'])
            request.session['MoodleSession'] = cookie_value
            login(request, user)
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
    logout(request)
    return redirect('login')


def normalize_asignatura(value):
    return str(value or '').strip().lower()


def filter_courses_by_role(request, courses, role='all'):
    # Materias con al menos un profesor asignado (Materia.profesores): heurística
    # actual para distinguir "el usuario las ve como docente" de "las ve como
    # estudiante", ya que el modelo no registra el rol por curso del usuario logueado.
    con_profesor_normalizadas = {
        normalize_asignatura(m)
        for m in Materia.objects.filter(profesores__isnull=False).values_list('moodle_nombre', flat=True)
    }

    current_profesor = get_current_profesor(request)
    docente_materias = {
        normalize_asignatura(m)
        for m in current_profesor.materias.values_list('moodle_nombre', flat=True)
    } if current_profesor else set()

    estudiante_materias = {
        normalize_asignatura(course.get('asignatura'))
        for course in courses
        if normalize_asignatura(course.get('asignatura')) not in con_profesor_normalizadas
    }

    if role == 'docente':
        return [course for course in courses if normalize_asignatura(course.get('asignatura')) in docente_materias]
    if role == 'estudiante':
        return [course for course in courses if normalize_asignatura(course.get('asignatura')) in estudiante_materias]

    # 'all': únicamente los cursos donde el usuario actual participa como
    # docente y/o como estudiante — no todas las materias de la base de datos.
    relevantes = docente_materias | estudiante_materias
    return [course for course in courses if normalize_asignatura(course.get('asignatura')) in relevantes]


def parse_selected_course_ids(request):
    selected = request.POST.getlist('courses') if request.method == 'POST' else request.GET.getlist('courses')
    ids = []
    for value in selected:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def get_asignaturas_by_course_ids(courses, selected_ids):
    """Obtiene las asignaturas de los cursos seleccionados por ID."""
    if not selected_ids:
        return []
    asignaturas = []
    for course in courses:
        if course.get('id') in selected_ids:
            asignaturas.append(course.get('asignatura'))
    return asignaturas


def filter_tareas_by_asignatura(tareas, asignaturas):
    """Filtra tareas por asignaturas seleccionadas."""
    if not asignaturas:
        return tareas
    return [curso for curso in tareas if curso.get('asignatura') in asignaturas]


def run_normalizado_web(selected_ids, courses):
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para normalizar.')

    asignaturas = get_asignaturas_by_course_ids(courses, selected_ids)
    tareas = cargarjson.cargar_tareas()
    tareas_seleccionadas = filter_tareas_by_asignatura(tareas, asignaturas)

    if not tareas_seleccionadas:
        raise ValueError('No se encontraron tareas para los cursos seleccionados.')

    normalizado = extraer_tareas_planas(tareas_seleccionadas)
    exportarjson.save_normalizacion(normalizado)

    import_result = import_tareas_from_json()
    return {
        'title': 'Normalizado',
        'detail': (
            f'Normalización completada: {len(normalizado)} tareas planas guardadas en {config.JSON_NORMALIZACION}. '
            f'Importación a DB: {import_result}.'
        ),
        'count': len(normalizado),
    }


def run_asignacion_web(selected_ids):
    config_base = cargarjson.cargar_fechas()
    tareas = cargarjson.cargar_normalizacion()
    warning = None

    if selected_ids:
        tareas_filtradas = [t for t in tareas if t.get('curso_id') in selected_ids]
        if tareas_filtradas:
            tareas = tareas_filtradas
        else:
            warning = 'No se encontró curso_id en normalización; usando todos los datos disponibles.'

    asignaciones = auto_asignar_tareas(tareas, config_base.get('rangos_parciales', []))
    asignaciones_ordenados = mostrar_resumen_tareas(asignaciones)
    config_final, errores = generar_config_final(asignaciones_ordenados, config_base)
    exportarjson.save_asignacion(config_final)

    result = {
        'title': 'Asignación',
        'detail': f'Asignación generada: {len(asignaciones)} tareas procesadas. Errores: {len(errores)}.',
        'count': len(asignaciones),
        'errors': len(errores),
    }

    if warning:
        result['warning'] = warning

    return result


def run_extraer_carreras_web(cookie, stop_event=None):
    """Paso 0, previo a la seleccion de cursos: recorre todas las facultades/categorias de
    Moodle y arma la jerarquia Facultad > Carrera > Nivel > Materia (+ profesor por materia)
    en linkcarreras.json. Sin esto el selector de cursos del dashboard esta vacio, porque
    `load_courses()` lee `Materia` desde Postgres, no desde JSON.

    Replica la cadena de 3 pasos del prototipo (categorias -> carreras -> linkcarreras,
    ver Versioines Demo/moodle_app_async/scripts/run_scraping.py) en una sola accion web,
    pasando el cookie explicitamente igual que `run_extraer_tareas_web` (no por
    `services.utils.run_scraping`, que todavia instancia `MoodleSession()` sin cookie).

    No soporta cancelacion a mitad de camino (stop_event no se revisa dentro de
    `cargar_todo`): son ~7 facultades, bastante mas rapido que extraer tareas/estudiantes.
    """
    moodle = MoodleSession(cookie=cookie)

    pagina = obtener_categorias(moodle)
    categorias = extraer_categorias(pagina)
    exportarjson.save_categorias(categorias)

    carreras_html = cargar_todo(moodle, categorias)
    exportarjson.save_carreras(carreras_html)

    linkcarreras = procesar_datos(carreras_html)
    exportarjson.save_Linkcarreras(linkcarreras)

    total_materias = sum(len(item.get('materias') or []) for item in linkcarreras)
    detalle = (
        f'Extracción de carreras completada: {len(categorias)} categoría(s) recorridas, '
        f'{len(linkcarreras)} carrera(s)/nivel(es) con {total_materias} materia(s) en total, '
        f'guardado en {config.JSON_LINKCARRERAS}. Todavía no se importó a la base de datos '
        f'(correr "python manage.py importar_facultades/carreras/niveles/materias/profesores").'
    )
    return {
        'title': 'Carreras extraídas',
        'detail': detalle,
        'count': len(linkcarreras),
    }


def run_extraer_tareas_web(selected_ids, courses, cookie, stop_event=None):
    """Primer paso real del pipeline (antes de Normalizar): entra a cada curso seleccionado
    y trae todas las tareas de todas sus secciones, sin discriminar tipo. Llama a Moodle de
    verdad, por eso pasa por el candado de extraction_lock en la vista `dashboard`, igual que
    `run_estudiantes_web`."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer sus tareas.')

    cursos_seleccionados = [c for c in courses if c.get('id') in selected_ids]
    if not cursos_seleccionados:
        raise ValueError('No se encontraron los cursos seleccionados.')

    moodle = MoodleSession(cookie=cookie)

    # Se conserva lo ya extraido de otros cursos y se reemplaza solo lo de los seleccionados,
    # para poder correr esta accion curso por curso sin perder el resto del avance.
    asignaturas_seleccionadas = {c.get('asignatura') for c in cursos_seleccionados}
    tareas_previas = [
        t for t in cargarjson.cargar_tareas()
        if t.get('asignatura') not in asignaturas_seleccionadas
    ]

    tareas_nuevas = asyncio.run(
        obtener_tareas_async(moodle, cursos_seleccionados, stop_event)
    )
    detenido = stop_event is not None and stop_event.is_set()

    exportarjson.save_tareas(tareas_previas + tareas_nuevas)

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


def run_estudiantes_web(selected_ids, courses, cookie, stop_event=None):
    """Segundo paso que llama a Moodle de verdad: entra a cada tarea ya extraida por
    `run_extraer_tareas_web` y trae los datos de entrega/calificacion de los estudiantes.
    Tambien pasa por el candado de extraction_lock en la vista `dashboard`."""
    if not selected_ids:
        raise ValueError('Debes seleccionar al menos un curso para extraer estudiantes.')

    asignaturas = get_asignaturas_by_course_ids(courses, selected_ids)
    tareas = cargarjson.cargar_tareas()
    tareas_seleccionadas = filter_tareas_by_asignatura(tareas, asignaturas)

    if not tareas_seleccionadas:
        raise ValueError('No se encontraron tareas para los cursos seleccionados.')

    moodle = MoodleSession(cookie=cookie)
    estudiantes = []
    detenido = False

    for curso in tareas_seleccionadas:
        if stop_event is not None and stop_event.is_set():
            detenido = True
            break
        curso_estudiantes = asyncio.run(
            obtener_tareas_docente_async(moodle, [curso], stop_event)
        )
        estudiantes.extend(curso_estudiantes)

    exportarjson.save_estudiantes(estudiantes)

    import_result = import_estudiantes_from_json()
    detalle = (
        f'Extracción de estudiantes completada: {len(estudiantes)} registros guardados en {config.JSON_ESTUDIANTES}. '
        f'Importación a DB: {import_result}.'
    )
    if detenido:
        detalle = f'Extracción detenida manualmente. Resultados parciales: {detalle}'
    return {
        'title': 'Estudiantes',
        'detail': detalle,
        'count': len(estudiantes),
        'detenido': detenido,
    }


def run_transformar_web(selected_ids):
    extraer_transformar()
    return {
        'title': 'Transformar',
        'detail': f'Transformación completada y Excel generado. Revisa el archivo notas.xlsx en el directorio del proyecto.',
        'count': None,
    }


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    role = request.GET.get('role', request.POST.get('role', 'all'))
    courses = load_courses()
    courses = filter_courses_by_role(request, courses, role)
    selected_ids = parse_selected_course_ids(request)
    selected_ids_str = [str(cid) for cid in selected_ids]
    selected_count = len(selected_ids)
    action_result = None
    error = None

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'normalizado':
                action_result = run_normalizado_web(selected_ids, courses)
            elif action == 'asignacion':
                action_result = run_asignacion_web(selected_ids)
            elif action in ('extraer_carreras', 'extraer_tareas', 'estudiantes'):
                # Unicas acciones que llaman a Moodle de verdad: pasan por el candado global
                # para que no arranquen dos extracciones de usuarios distintos en paralelo.
                cookie = request.session.get('MoodleSession')
                job_id = extraction_lock.try_acquire_lock(request.user.username)
                if job_id is None:
                    candado = extraction_lock.current_lock()
                    error = (
                        f'Ya hay una extracción en curso (iniciada por {candado.usuario}). '
                        'Esperá a que termine o cancelala vos mismo si es tuya, e intentá de nuevo.'
                    )
                else:
                    stop_event = extraction_lock.get_stop_event(job_id)
                    try:
                        if action == 'extraer_carreras':
                            action_result = run_extraer_carreras_web(cookie, stop_event)
                        elif action == 'extraer_tareas':
                            action_result = run_extraer_tareas_web(selected_ids, courses, cookie, stop_event)
                        else:
                            action_result = run_estudiantes_web(selected_ids, courses, cookie, stop_event)
                    finally:
                        extraction_lock.release_lock(job_id)
            elif action == 'transformar':
                action_result = run_transformar_web(selected_ids)
            elif action == 'guardar_cookie':
                # Solo vive en la sesion del navegador (nunca en la base de datos).
                cookie_value = request.POST.get('moodle_cookie', '').strip()
                if not cookie_value:
                    error = 'Pega el valor de la cookie antes de guardar.'
                else:
                    request.session['MoodleSession'] = cookie_value
                    action_result = {
                        'title': 'Cookie',
                        'detail': 'Cookie guardada en tu sesión de navegador. No se guarda en la base de datos.',
                        'count': None,
                    }
            else:
                error = 'Acción desconocida.'
        except Exception as exc:
            error_str = str(exc)
            # Si el error menciona "cookie", "sesión", "autenticación" o "MoodleSession", redirigir al formulario
            if any(word in error_str.lower() for word in ['cookie', 'sesión', 'session', 'autenticación', 'moodlesession']):
                return handle_session_error(request, f"Sesión expirada: {error_str}", next_url=request.path)
            error = error_str
            traceback.print_exc()

    candado_actual = extraction_lock.current_lock()
    context = {
        'courses': courses,
        'course_count': len(courses),
        'selected_ids': selected_ids_str,
        'selected_count': selected_count,
        'role': role,
        'action_result': action_result,
        'error': error,
        'extraccion_en_curso': candado_actual,
        'cookie_guardada': bool(request.session.get('MoodleSession')),
    }
    return render(request, 'web/dashboard.html', context)


@login_required
@require_http_methods(['POST'])
def detener_extraccion(request):
    """Boton de emergencia: marca la extraccion en curso para que se corte apenas termine
    la seccion que este en vuelo, en vez de esperar a que acabe sola o vencer el timeout."""
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

    try:
        from django.db.models import Count, Q, Max

        kpis['materias'] = Materia.objects.count()
        kpis['docentes'] = Profesor.objects.count()
        kpis['estudiantes'] = Estudiante.objects.count()

        # contar tareas totalesfiltranndo por mitek etek y examen
        
        FILTROS_ACTIVIDADES = [
            "Examen",
            "tek",
        ]

        filtro_tareas = Q()

        for filtro in FILTROS_ACTIVIDADES:
            filtro_tareas |= Q(titulo__icontains=filtro)

        tareas_filtradas = Tarea.objects.filter(filtro_tareas)

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

        materias_sin_actividades = Materia.objects.filter(unidades__tareas__isnull=True).distinct()
        if materias_sin_actividades.exists():
            alertas.append(f"Materias sin actividades: {materias_sin_actividades.count()}")

        tareas_sin_cierre = Tarea.objects.filter(Q(cierre__isnull=True) | Q(cierre__exact=''))
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
            Tarea.objects.values('unidad__materia__nombre')
            .annotate(count=Count('id'))
            .order_by('-count')[:8]
        )
        labels = [m.get('unidad__materia__nombre') or 'Desconocida' for m in materias_counts]
        data = [m.get('count') for m in materias_counts]
        chart_materias = {'labels': labels, 'data': data}

        datos_tareas_por_ano = Tarea.objects.values('unidad__materia__gestion').annotate(count=Count('id')).order_by('unidad__materia__gestion')
        datos_entregas_por_ano = Entrega.objects.values('tarea__unidad__materia__gestion').annotate(count=Count('id')).order_by('tarea__unidad__materia__gestion')

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

    return render(request, 'web/resumen.html', context)


@login_required
def materias_view(request):
    materias = Materia.objects.all()[:200]
    materias = Materia.objects.select_related(
        'carrera',
        'nivel'
    ).prefetch_related(
        'profesores'
    )
    context = {'materias': materias}
    return render(request, 'web/materias.html', context)


@login_required
def docentes_view(request):

    docentes = Profesor.objects.annotate(
    total_materias=Count(
        'materias',
        distinct=True
        )
    ).prefetch_related(
        'materias'
    ).order_by(
        'nombre'
    )

    for docente in docentes:

        contador = Counter()

        for materia in docente.materias.all():
            contador[materia.gestion] += 1

        docente.gestiones = dict(
            sorted(contador.items())
        )

    context = {
        'docentes': docentes
    }

    return render(
        request,
        'web/docentes.html',
        context
    )


@login_required
def estudiantes_view(request):

    estudiantes = Estudiante.objects.annotate(
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

        for e in estudiante.entregas.all():
            print(e.tarea.unidad.materia_id)
            
        contador = Counter()

            
        materias = {
            entrega.tarea.unidad.materia
            for entrega in estudiante.entregas.all()
                if entrega.tarea and entrega.tarea.unidad
        }

        #print("Controlando estudiante:",
        #    estudiante.nombre,
        #    materias
        #)

        for materia in materias:
            contador[materia.gestion] += 1

        estudiante.gestiones = dict(
            sorted(contador.items())
        )

    context = {
        'estudiantes': estudiantes
    }

    return render(
        request,
        'web/estudiantes.html',
        context
    )

@login_required
def alertas_view(request):
    # Alertas detalladas: listar materias sin actividades, tareas sin cierre y estudiantes sobrecargados
    detalles = {}
    try:
        from django.db.models import Q, Count

        materias_sin = Materia.objects.filter(unidades__tareas__isnull=True).distinct()
        detalles['materias_sin_actividades'] = list(materias_sin.values('id', 'nombre')[:200])

        tareas_sin_cierre_qs = Tarea.objects.filter(Q(cierre__isnull=True) | Q(cierre__exact=''))
        detalles['tareas_sin_cierre'] = list(tareas_sin_cierre_qs.values('moodle_id', 'titulo')[:200])

        # estudiantes con muchas entregas pendientes
        threshold = 8
        estudiantes_sobrecarga = (
            Entrega.objects.filter(Q(calificacion__isnull=True) | Q(calificacion__exact=''))
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
def cookie_recovery_view(request):
    """Formulario para pegar el cookie `MoodleSession` en la sesión del navegador (solo server-side, en session).
    Parámetros GET opcionales:
    - error: mensaje de error (e.g., "La sesión expiró, por favor pega tu cookie")
    - next: URL a redirigir después de guardar la cookie (default: /web/)
    """
    message = None
    error_msg = request.GET.get('error')
    next_url = request.GET.get('next', '/web/')

    if request.method == 'POST':
        cookie_value = request.POST.get('moodle_cookie')
        if cookie_value:
            request.session['MoodleSession'] = cookie_value.strip()
            message = 'Cookie guardada en la sesión. Puedes reintentar la operación.'
            if request.user.is_authenticated:
                profesor = Profesor.objects.filter(nombre__iexact=request.user.username).first()
                if profesor:
                    profesor.moodle_session_hash = make_password(cookie_value)
                    profesor.save(update_fields=['moodle_session_hash'])
                    message = 'Cookie guardada y asociada a tu usuario.'
        else:
            message = 'No se recibió ningún valor de cookie.'

    context = {
        'message': message,
        'error_msg': error_msg,
        'next_url': next_url,
    }
    return render(request, 'web/session_recovery.html', context)


@login_required
def predicciones_view(request):
    # estructura inicial para ML
    context = {'mensaje': 'Predicciones: espacio reservado para ML.'}
    return render(request, 'web/predicciones.html', context)


@login_required
def reportes_view(request):
    # filtros básicos se implementarán en esta página
    context = {'mensaje': 'Reportes: filtros por Docente/Carrera/Materia/Gestión/Fecha.'}
    return render(request, 'web/reportes.html', context)


@login_required
def configuracion_view(request):
    # panel de administración de parámetros (temporal)
    context = {'mensaje': 'Configuración de categorías, parciales y reglas.'}
    return render(request, 'web/configuracion.html', context)

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