from django.urls import path

from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('extraccion/', views.dashboard, name='dashboard'),
    path('extraccion/detener/', views.detener_extraccion, name='detener_extraccion'),
    path('extraccion/descargar-excel/', views.descargar_excel, name='descargar_excel'),
    path('extraccion/guardar-cookie/', views.guardar_cookie_extension, name='guardar_cookie_extension'),
    path('extraccion/progreso/', views.progreso_extraccion, name='progreso_extraccion'),
    path('resumen/', views.resumen, name='resumen'),
    path('materias/', views.materias_view, name='materias'),    
    path('docentes/', views.docentes_view, name='docentes'),
    path('docentes/gestionar-rol/', views.gestionar_rol_docente, name='gestionar_rol_docente'),
    path('estudiantes/', views.estudiantes_view, name='estudiantes'),
    path('alertas/', views.alertas_view, name='alertas'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('predicciones/', views.predicciones_view, name='predicciones'),
    path('predicciones/descargar/', views.predicciones_descargar_csv, name='predicciones_descargar_csv'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('reportes/descargar/<str:tipo>/<str:formato>/', views.reportes_descargar, name='reportes_descargar'),
    path('configuracion/', views.configuracion_view, name='configuracion'),
    path('extension/privacidad/', views.extension_privacidad_view, name='extension_privacidad'),
]
