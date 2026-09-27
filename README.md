# MARVELEC SPA — Sistema de Reporte y Seguimiento de Avance

Reemplaza el flujo informal de WhatsApp de **MARVELEC SPA** (contratista de obra gruesa
eléctrica). Es una sola aplicación web instalable (PWA) con dos experiencias:

- **App del trabajador (celular):** reporta su llegada con foto y los **puntos ejecutados**
  (red / fuerza / iluminación) por **subetapa**. Funciona **sin señal**: el reporte queda
  guardado en el teléfono y se envía solo al volver la conexión.
- **Programa de supervisión (PC):** resumen con gráficos, cola de revisión para
  **aprobar u observar** reportes, lista filtrable, ranking de **puntos por jornada** por
  trabajador y exportación a Excel.
- **Notificaciones:** centro de avisos (campanita) + **push** en celular y PC:
  nuevo reporte → supervisor; aprobado/observado → trabajador; **resumen diario** con quién
  no reportó.

## 1. Instalación local

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abre http://127.0.0.1:8000/ (las notificaciones push y la instalación como app requieren
`localhost` o HTTPS).

## 2. Primeros pasos

1. Entra a **/admin/** y crea una **Obra** con sus **Subetapas**.
2. Crea usuarios y, en **"Perfil de Trabajador"**, define su **rol** (Trabajador /
   Supervisor / Gerencia) y su **obra asignada**.
3. Con un trabajador, en el celular: *Reportar* → foto → puntos con los botones − / + → Enviar.
4. Con un supervisor, en el PC: *Por revisar* → **Aprobar** (tecla `A`) u **Observar** (tecla `O`).
5. En cada dispositivo toca **"Activar notificaciones"**. En iPhone primero hay que
   instalar la app (Safari → Compartir → *Agregar a inicio*, iOS 16.4+).

## 3. Instalar como aplicación

- **Android (Chrome):** menú ⋮ → *Instalar aplicación*.
- **iPhone (Safari):** Compartir → *Agregar a inicio*.
- **PC (Chrome / Edge):** ícono de instalar en la barra de direcciones. Queda como programa
  con su propia ventana y avisos de escritorio.

## 4. Despliegue en Render

**Build command:** `./build.sh` · **Start command:** `gunicorn marvelec_project.wsgi:application`

Variables de entorno:

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave larga aleatoria |
| `DJANGO_DEBUG` | `False` |
| `DATABASE_URL` | La setea Render al conectar PostgreSQL |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | Superusuario inicial |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Claves de notificaciones push (ver abajo) |
| `VAPID_CLAIM_EMAIL` | Correo de contacto para los servicios push (opcional) |
| `CRON_TOKEN` | Texto secreto largo para el resumen diario |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | SMTP para correos de respaldo (opcional) |

**Claves VAPID (obligatorio para push en producción).** Genéralas una sola vez en tu PC:

```bash
python manage.py generar_vapid
```

y pega ambas líneas en Render. Si no se configuran, el servidor genera claves nuevas en
cada deploy y todos los dispositivos pierden las notificaciones hasta reactivarlas.

**Resumen diario.** En GitHub → *Settings → Secrets and variables → Actions* crea
`MARVELEC_URL` (ej. `https://marvelec.onrender.com`) y `CRON_TOKEN` (el mismo de Render).
El workflow `.github/workflows/resumen-diario.yml` lo dispara cada noche (~21:00 Chile).
También se puede enviar a mano: `python manage.py resumen_diario [--fecha 2026-09-27] [--forzar]`.

## 5. Estructura

```
marvelec_app/
├── models.py            # Obra, Subetapa, PerfilTrabajador, ReporteAvance (+ revisión),
│                        # RegistroPunto, SuscripcionPush, Notificacion, ResumenDiarioEnviado
├── views.py             # App trabajador, API offline, supervisión, detalle, Excel, avisos, PWA
├── consultas.py         # Permisos por rol, filtros, KPIs, gráficos y ranking (reutilizables)
├── servicios.py         # Crear / corregir / revisar reportes (atómico, idempotente)
├── notificaciones.py    # Centro de avisos + envío push/correo en segundo plano
├── resumen.py           # Resumen diario
├── push.py              # Web Push (VAPID) y suscripciones
├── management/commands/ # resumen_diario, generar_vapid
├── templates/marvelec_app/
│   ├── trabajador/      # inicio, nuevo_reporte, historial, detalle, avisos
│   ├── supervision/     # resumen, revisar, reportes, trabajadores, avisos
│   └── pwa/             # sw.js y manifest (servidos desde la raíz del sitio)
└── static/marvelec_app/
    ├── css/style.css    # Sistema de diseño (claro/oscuro, móvil y escritorio)
    ├── js/              # app.js, trabajador.js, outbox.js (cola sin señal), supervision.js
    └── vendor/          # Chart.js
templates/
├── base.html
└── layouts/             # movil.html (barra inferior), escritorio.html (menú lateral)
```

## 6. Tests

```bash
python manage.py test marvelec_app
```

## 7. Pendientes conocidos

- Las **fotos** se guardan en el disco de Render, que en el plan gratuito se borra al
  redesplegar → integrar almacenamiento en la nube (Cloudinary, S3) para `MEDIA_ROOT`.
- La **base de datos** PostgreSQL gratuita de Render expira a los 90 días.
- Límite de un reporte por trabajador por día: se evaluará más adelante.
