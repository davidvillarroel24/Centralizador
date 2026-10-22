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
    - Visitante: nada por default: solo ve algo si filtra explicitamente por facultad o
      carrera (facultad_id/carrera_id) - nunca la lista completa sin filtrar.
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
        qs = Materia.objects.none()
        if facultad_id:
            qs = Materia.objects.filter(carrera__facultad_id=facultad_id)
        elif carrera_id:
            qs = Materia.objects.filter(carrera_id=carrera_id)
    else:
        qs = Materia.objects.none()

    return qs


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
