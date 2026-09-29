from django.urls import path

from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('extraccion/', views.dashboard, name='dashboard'),
    path('extraccion/detener/', views.detener_extraccion, name='detener_extraccion'),
    path('resumen/', views.resumen, name='resumen'),
    path('materias/', views.materias_view, name='materias'),    
    path('docentes/', views.docentes_view, name='docentes'),
    path('estudiantes/', views.estudiantes_view, name='estudiantes'),
    path('alertas/', views.alertas_view, name='alertas'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('session-cookie/', views.cookie_recovery_view, name='session_cookie'),
    path('predicciones/', views.predicciones_view, name='predicciones'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('configuracion/', views.configuracion_view, name='configuracion'),
]
