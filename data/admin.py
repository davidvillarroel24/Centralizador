from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Carrera, Facultad, PerfilUsuario, Profesor


class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil (rol en el sistema)'
    filter_horizontal = ('facultades', 'carreras', 'materias')


class PerfilUsuarioUserAdmin(UserAdmin):
    inlines = (PerfilUsuarioInline,)
    list_display = UserAdmin.list_display + ('rol',)

    def rol(self, obj):
        return obj.perfil.get_rol_display() if hasattr(obj, 'perfil') else '-'
    rol.short_description = 'Rol'


admin.site.unregister(User)
admin.site.register(User, PerfilUsuarioUserAdmin)


@admin.register(Profesor)
class ProfesorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'moodle_id', 'user')
    search_fields = ('nombre', 'moodle_id')


@admin.register(Facultad)
class FacultadAdmin(admin.ModelAdmin):
    search_fields = ('nombre',)


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'facultad')
    search_fields = ('nombre',)
    list_filter = ('facultad',)
