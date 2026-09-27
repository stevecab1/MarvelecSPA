# marvelec_app/urls.py
from django.urls import path
from . import views
from .push import vapid_public_key, suscribir_push, desuscribir_push

app_name = 'marvelec_app'

urlpatterns = [
    # Raíz del sitio -> pantalla de inicio de sesión
    path('', views.login_usuario, name='inicio'),

    # --- Autenticación ---
    path('ingresar/', views.login_usuario, name='login'),
    path('salir/', views.logout_usuario, name='logout'),

    # --- Redirección según rol ---
    path('panel/', views.dashboard_redirect, name='panel'),

    # --- App del trabajador (celular) ---
    path('panel/trabajador/', views.dashboard_trabajador, name='panel_trabajador'),
    path('panel/trabajador/nuevo/', views.nuevo_reporte, name='nuevo_reporte'),
    path('panel/trabajador/historial/', views.historial_trabajador, name='historial_trabajador'),
    path('api/reportes/', views.api_crear_reporte, name='api_crear_reporte'),

    # --- Programa de supervisión / gerencia (PC) ---
    path('panel/supervision/', views.dashboard_supervisor, name='panel_supervision'),
    path('panel/supervision/revisar/', views.cola_revision, name='cola_revision'),
    path('panel/supervision/revisar/masivo/', views.revisar_masivo, name='revisar_masivo'),
    path('panel/supervision/reportes/', views.lista_reportes, name='lista_reportes'),
    path('panel/supervision/trabajadores/', views.trabajadores, name='trabajadores'),

    # --- Reportes ---
    path('reportes/<int:pk>/', views.reporte_detalle, name='reporte_detalle'),
    path('reportes/<int:pk>/editar/', views.editar_reporte, name='editar_reporte'),
    path('reportes/<int:pk>/revisar/', views.revisar, name='revisar_reporte'),
    path('reportes/exportar-excel/', views.exportar_reportes_excel, name='exportar_excel'),

    # --- Centro de notificaciones ---
    path('notificaciones/', views.notificaciones, name='notificaciones'),
    path('notificaciones/estado/', views.notificaciones_estado, name='notificaciones_estado'),
    path('notificaciones/leer-todas/', views.notificaciones_leer_todas, name='notificaciones_leer_todas'),
    path('notificaciones/<int:pk>/leer/', views.notificacion_leer, name='notificacion_leer'),

    # --- Notificaciones push ---
    path('notificaciones/vapid-key/', vapid_public_key, name='vapid_key'),
    path('notificaciones/suscribir/', suscribir_push, name='suscribir_push'),
    path('notificaciones/desuscribir/', desuscribir_push, name='desuscribir_push'),

    # --- Tareas programadas ---
    path('tareas/resumen-diario/', views.tarea_resumen_diario, name='tarea_resumen_diario'),

    # --- PWA ---
    path('sw.js', views.service_worker, name='service_worker'),
    path('manifest.webmanifest', views.manifest, name='manifest'),
]
