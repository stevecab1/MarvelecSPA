# MARVELEC SPA — Sistema de Reporte y Seguimiento de Avance

Proyecto Django simplificado, inspirado en la arquitectura de un sistema anterior de
gestión de bombas de combustible, adaptado al contexto de **MARVELEC SPA**
(contratista de obra gruesa eléctrica).

Reemplaza el flujo informal de WhatsApp: cada trabajador reporta su llegada a la obra,
sube una foto y registra los **puntos ejecutados** (red / fuerza / iluminación) por
**subetapa**. Supervisores y gerencia ven un panel consolidado, filtrable y exportable
a Excel.

## 1. Requisitos

- Python 3.11+ instalado
- Visual Studio Code (recomendado, con la extensión oficial de Python)

## 2. Instalación (Windows / macOS / Linux)

Abre una terminal en la carpeta del proyecto y ejecuta:

```bash
# 1. Crear entorno virtual
python -m venv venv

# 2. Activarlo
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear la base de datos (SQLite, no requiere instalar nada extra)
python manage.py migrate

# 5. Crear un usuario administrador (será tu primer usuario "gerencia")
python manage.py createsuperuser

# 6. Levantar el servidor
python manage.py runserver
```

Luego abre http://127.0.0.1:8000/ en el navegador.

## 3. Primeros pasos dentro del sistema

1. Entra a **/admin/** con el superusuario creado.
2. Crea una **Obra** (ej. "Hospital Regional") y agrégale **Subetapas** (ej. "Piso 1",
   "Piso 2 - Ala Norte") directamente desde la misma pantalla de la Obra.
3. Edita el usuario superusuario (o crea nuevos usuarios) y en la sección
   **"Perfil de Trabajador"** define su **rol** (Trabajador / Supervisor / Gerencia) y,
   si corresponde, su **obra asignada**.
4. Cierra sesión del admin y entra por **/login/** con un usuario de rol "Trabajador"
   para ver el formulario de reporte diario.
5. Entra con un usuario "Supervisor" o "Gerencia" para ver el panel consolidado y el
   botón **"Exportar a Excel"**.

## 4. Estructura del proyecto

```
marvelec_project/
├── manage.py
├── requirements.txt
├── marvelec_project/       # Configuración global (settings, urls, wsgi/asgi)
├── marvelec_app/           # App principal
│   ├── models.py           # Obra, Subetapa, PerfilTrabajador, ReporteAvance, RegistroPunto
│   ├── forms.py            # Formulario de reporte + formset de puntos
│   ├── views.py            # Login, dashboards por rol, exportación a Excel
│   ├── admin.py            # Panel de administración
│   ├── signals.py          # Recalcula totales y crea perfiles automáticamente
│   ├── urls.py
│   ├── templates/
│   └── static/
└── templates/base.html     # Plantilla base compartida
```

## 5. Modelo de datos (resumen)

- **Obra**: un proyecto en ejecución (ej. un hospital).
- **Subetapa**: segmento dentro de una obra (piso, ala, sector).
- **PerfilTrabajador**: rol del usuario (trabajador / supervisor / gerencia) y su obra.
- **ReporteAvance**: un reporte diario (foto de llegada + comentario), con total de
  puntos calculado automáticamente.
- **RegistroPunto**: detalle de puntos ejecutados por tipo (red / fuerza / iluminación)
  dentro de un reporte.

## 6. Próximos pasos sugeridos (para el pilotaje / Hito 3)

- Restringir el formulario de reporte a **una vez por día por trabajador** si se
  requiere evitar duplicados.
- Agregar un indicador de **puntos por jornada por trabajador** en el panel de
  gerencia (base para el sistema de bonificación).
- Migrar la base de datos a PostgreSQL y desplegar en un servicio como Render o
  Railway cuando el piloto pase a producción (basta con instalar `dj-database-url` y
  leer `DATABASE_URL` desde variables de entorno, tal como en el proyecto anterior).
