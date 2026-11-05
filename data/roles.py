"""Helpers de rol, separados de models.py para no mezclar definicion de datos con logica
de permisos. Se usan desde las vistas (web/views.py), el sidebar (context processor,
registrado en gatfh/settings.py) y el decorador @requiere_rol."""

from functools import wraps

from django.db.models import Q
from django.shortcuts import redirect

from .models import Materia, PerfilUsuario, Profesor


def get_rol(user):
    """Rol del usuario logueado. Si todavia no tiene PerfilUsuario (cuentas creadas antes
    de este cambio), se asume Docente - es el rol mas restrictivo de los que ya tenian
    acceso, asi nadie gana permisos de mas por default."""
    if not user or not user.is_authenticated:
        return None
    perfil = getattr(user, 'perfil', None)
    return perfil.rol if perfil else PerfilUsuario.DOCENTE


def es_administrador(user):
    return get_rol(user) == PerfilUsuario.ADMINISTRADOR


VISITANTE_USERNAME = 'visitante'
# Fuera del rango real de Moodle (siempre positivo) a proposito, para que nunca choque con
# un Profesor.moodle_id de verdad.
VISITANTE_MOODLE_ID = -1


def get_or_crear_visitante_compartido():
    """Cuenta unica y compartida para el boton "Visitante" del login (ver
    ConfiguracionInstitucional.visitante_habilitado y PerfilUsuario.VISITANTE) - se crea
    perezosamente la primera vez que alguien la pide, mismo patron que
    ConfiguracionInstitucional.actual()/TrabajoExtraccion (fila unica via get_or_create).
    Contraseña inutilizable: nadie entra a esta cuenta por el formulario normal de usuario/
    contraseña, solo por el boton dedicado (login_view), que loguea directo sin pedir nada."""
    from django.contrib.auth.models import User

    user, creado = User.objects.get_or_create(
        username=VISITANTE_USERNAME,
        defaults={'first_name': 'Visitante'},
    )
    if creado:
        user.set_unusable_password()
        user.save()

    profesor, _ = Profesor.objects.get_or_create(
        moodle_id=VISITANTE_MOODLE_ID,
        defaults={
            'nombre': VISITANTE_USERNAME,
            'url': 'https://visitante.invalido/perfil-ficticio',
            'user': user,
        },
    )
    if profesor.user_id != user.id:
        profesor.user = user
        profesor.save(update_fields=['user'])

    PerfilUsuario.objects.get_or_create(user=user, defaults={'rol': PerfilUsuario.VISITANTE})
    return user


def materias_visibles_decano(user):
    """Union de las 3 formas de asignarle alcance a un Decano: facultades enteras, carreras
    enteras, o materias sueltas. Devuelve un queryset de Materia; vacio si el usuario no es
    Decano o no tiene nada asignado todavia."""
    perfil = getattr(user, 'perfil', None)
    if not perfil or perfil.rol != PerfilUsuario.DECANO:
        return Materia.objects.none()

    return Materia.objects.filter(
        Q(carrera__facultad__in=perfil.facultades.all())
        | Q(carrera__in=perfil.carreras.all())
        | Q(pk__in=perfil.materias.values_list('pk', flat=True))
    ).distinct()


def materias_visibles(user, facultad_id=None, carrera_id=None):
    """Punto unico de alcance por rol - lo que ve cada uno en materias/docentes/
    estudiantes/alertas/resumen es siempre "lo que caiga bajo este queryset de Materia":

    - Administrador: todas.
    - Decano: la union de sus facultades/carreras/materias asignadas (materias_visibles_decano).
    - Docente: solo las propias (Materia.profesores, via su Profesor vinculado).
    - Visitante: todas, de solo lectura (ve lo mismo que Administrador en materias/
      estudiantes/reportes) - opcionalmente acotable por facultad_id/carrera_id, igual que
      el resto, pero sin filtrar ve la lista completa.
    - Sin loguear / sin perfil: nada.
    """
    rol = get_rol(user)

    if rol == PerfilUsuario.ADMINISTRADOR:
        qs = Materia.objects.all()
    elif rol == PerfilUsuario.DECANO:
        qs = materias_visibles_decano(user)
    elif rol == PerfilUsuario.DOCENTE:
        profesor = Profesor.objects.filter(user=user).first()
        qs = profesor.materias.all() if profesor else Materia.objects.none()
    elif rol == PerfilUsuario.VISITANTE:
        qs = Materia.objects.all()
        if facultad_id:
            qs = qs.filter(carrera__facultad_id=facultad_id)
        elif carrera_id:
            qs = qs.filter(carrera_id=carrera_id)
    else:
        qs = Materia.objects.none()

    # Una materia inhabilitada (Materia.activo=False) no la ve nadie por esta via, ni
    # siquiera Administrador - es la "eliminacion logica" para casos como una materia
    # duplicada que no se quiere borrar de una (ver web/materias.html, toggle solo para
    # Administrador). Tambien saca a esa materia de los cursos seleccionables para
    # extraccion (cursos_base_por_rol usa esta misma funcion). Para ver/reactivar una
    # inhabilitada hay que ir a Materias como Administrador, que consulta aparte sin pasar
    # por esta funcion.
    return qs.filter(activo=True)


def requiere_rol(*roles_permitidos):
    """Decorador para vistas: si el rol del usuario logueado no esta en roles_permitidos,
    redirige a Resumen (la unica pagina que todos los roles pueden ver) en vez de dejarlo
    pasar. Complementa al sidebar (que ya oculta el link) - esto protege la URL directa,
    que ocultar un link no alcanza a tapar."""
    def decorador(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if get_rol(request.user) not in roles_permitidos:
                return redirect('resumen')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorador


def rol_usuario(request):
    """Context processor (ver gatfh/settings.py, TEMPLATES.OPTIONS.context_processors):
    agrega 'rol_usuario' a TODOS los templates automaticamente, para el sidebar (nombre +
    rol, que items mostrar) sin tener que tocar el context de cada vista por separado."""
    user = request.user
    rol = get_rol(user)
    nombre_mostrado = ''
    if user.is_authenticated:
        nombre_mostrado = user.get_full_name() or user.username
    return {
        'rol_usuario': rol,
        'rol_usuario_display': dict(PerfilUsuario.ROLES).get(rol, ''),
        'nombre_usuario_actual': nombre_mostrado,
        'ROL_ADMINISTRADOR': PerfilUsuario.ADMINISTRADOR,
        'ROL_DECANO': PerfilUsuario.DECANO,
        'ROL_DOCENTE': PerfilUsuario.DOCENTE,
        'ROL_VISITANTE': PerfilUsuario.VISITANTE,
    }
