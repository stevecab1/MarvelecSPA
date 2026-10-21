# marvelec_app/urls.py
from django.urls import path

from . import views
from .push import desuscribir_push, suscribir_push, vapid_public_key

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
    path('panel/trabajador/llegada/', views.marcar_asistencia, name='marcar_asistencia'),
    path('panel/trabajador/nuevo/', views.nuevo_reporte, name='nuevo_reporte'),
    path('panel/trabajador/incidencia/', views.nueva_incidencia, name='nueva_incidencia'),
    path('panel/trabajador/historial/', views.historial_trabajador, name='historial_trabajador'),
    path('api/reportes/', views.api_crear_reporte, name='api_crear_reporte'),
    path('api/incidencias/', views.api_incidencia, name='api_incidencia'),
    path('api/asistencia/', views.api_asistencia, name='api_asistencia'),

    # --- Programa de supervisión / gerencia (PC) ---
    path('panel/supervision/', views.dashboard_supervisor, name='panel_supervision'),
    path('panel/supervision/avance/', views.avance_obra, name='avance_obra'),
    path('panel/supervision/racks/<int:pk>/', views.rack_detalle, name='rack_detalle'),
    path('panel/supervision/puntos/<int:pk>/', views.punto_detalle, name='punto_detalle'),
    path('panel/supervision/puntos/cargar/', views.cargar_puntos, name='cargar_puntos'),
    path('panel/supervision/puntos/plantilla.xlsx', views.plantilla_puntos, name='plantilla_puntos'),
    path('panel/supervision/incidencias/', views.incidencias, name='incidencias'),
    path('panel/supervision/incidencias/<int:pk>/liberar/', views.liberar_incidencia, name='liberar_incidencia'),
    path('panel/supervision/asistencia/', views.asistencia_dia, name='asistencia_dia'),
    path('panel/supervision/asistencia/mes/', views.asistencia_mes, name='asistencia_mes'),
    path('panel/supervision/asistencia/<int:pk>/revisar/', views.revisar_asistencia, name='revisar_asistencia'),
    path('panel/supervision/asistencia/confirmar/', views.confirmar_asistencias, name='confirmar_asistencias'),
    path('panel/supervision/revisar/', views.cola_revision, name='cola_revision'),
    path('panel/supervision/revisar/masivo/', views.revisar_masivo, name='revisar_masivo'),
    path('panel/supervision/reportes/', views.lista_reportes, name='lista_reportes'),
    path('panel/supervision/trabajadores/', views.trabajadores, name='trabajadores'),

    # --- Reportes ---
    path('reportes/<int:pk>/', views.reporte_detalle, name='reporte_detalle'),
    path('reportes/<int:pk>/editar/', views.editar_reporte, name='editar_reporte'),
    path('reportes/<int:pk>/revisar/', views.revisar, name='revisar_reporte'),
    path('reportes/exportar-excel/', views.exportar_reportes_excel, name='exportar_excel'),
    path('reportes/exportar-puntos/', views.exportar_estado_puntos, name='exportar_estado_puntos'),
    path('reportes/exportar-asistencia/', views.exportar_asistencia, name='exportar_asistencia'),

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
