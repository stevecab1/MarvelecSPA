# marvelec_app/urls.py
from django.urls import path
from . import views
from .push import vapid_public_key, suscribir_push

app_name = 'marvelec_app'

urlpatterns = [
    # Raíz del sitio -> pantalla de inicio de sesión
    path('', views.login_usuario, name='inicio'),

    # --- Autenticación ---
    path('ingresar/', views.login_usuario, name='login'),
    path('salir/', views.logout_usuario, name='logout'),

    # --- Redirección según rol ---
    path('panel/', views.dashboard_redirect, name='panel'),

    # --- Vistas por rol ---
    path('panel/trabajador/', views.dashboard_trabajador, name='panel_trabajador'),
    path('panel/supervision/', views.dashboard_supervisor, name='panel_supervision'),

    # --- Exportación ---
    path('reportes/exportar-excel/', views.exportar_reportes_excel, name='exportar_excel'),

    # --- Notificaciones push ---
    path('notificaciones/vapid-key/', vapid_public_key, name='vapid_key'),
    path('notificaciones/suscribir/', suscribir_push, name='suscribir_push'),
]
