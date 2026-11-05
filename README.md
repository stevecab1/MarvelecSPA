# MARVELEC SPA — Sistema de Reporte y Seguimiento de Avance

Reemplaza el flujo informal de WhatsApp de **MARVELEC SPA** en obras de **cableado
estructurado**. Cada punto de la obra (ej. `DT-015` del rack `1H`) se sigue de extremo a
extremo por sus 7 etapas:

**tendido → bajada / peinado de rack → identificación (tonos) → ponchado en rack / en usuario → certificación**

Es una sola aplicación web instalable (PWA) con dos experiencias:

- **App del trabajador (celular):** marca su **llegada** con foto y GPS; reporta qué **etapa**
  terminó en qué **puntos** (selector por paquete o escribiendo `DT 1-2-3, VD 9` como en
  WhatsApp); reporta **incidencias** tipificadas (sin canalización, materiales obstruyendo…)
  que dejan el punto bloqueado. Todo funciona **sin señal** y se envía al volver la conexión.
- **Programa de supervisión (PC):** carga de la **planilla de paquetes** (Excel), **avance de
  obra** por rack y etapa con **proyección de término**, detalle de rack y de punto, cola de
  revisión (**aprobar u observar**), **incidencias** con liberación y tiempo detenido,
  **asistencia** del día y del mes, ranking por **rendimiento vs. estándar** y exportaciones a Excel.
- **Chat de consultas:** conversaciones **privadas** entre un trabajador y su jefatura (supervisores
  y gerencia de su obra), con texto y foto. No hay grupos ni mensajes entre trabajadores: el canal
  compartido es justamente lo que el sistema vino a reemplazar.
- **Notificaciones:** campanita + **push** en celular y PC (nuevo reporte, incidencia,
  punto liberado, llegada rechazada, revisión, mensaje nuevo) y **resumen diario**.

Las reglas del sistema vienen de los documentos del levantamiento (carpeta *Contexto Proyecto*):
el orden de las etapas, los rendimientos estándar por etapa y los tipos de incidencia.

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

1. Entra a **/admin/** (tema [Unfold](https://unfoldadmin.com)) y crea la **Obra** (con su
   fecha de término planificada, para estimar atrasos).
2. Crea usuarios y, en **"Perfil de Trabajador"**, define su **rol** (Trabajador /
   Supervisor / Gerencia) y su **obra asignada**.
3. En el programa de supervisión: **Cargar puntos** → sube la planilla de paquetes (la misma
   que se arma tras medir: una hoja por rack, `PAQUETE 01`, los códigos y `36 METROS`) →
   revisa la vista previa → **Cargar**. También acepta una tabla simple (hay plantilla).
4. Con un trabajador, en el celular: **Marcar llegada** (foto) → **Reportar avance**: rack →
   etapa → puntos → Enviar. Si algo impide avanzar: **Incidencia**.
5. Con un supervisor, en el PC: confirma la **Asistencia**, revisa **Por revisar** (`A` aprobar,
   `O` observar), libera **Incidencias** y mira **Avance de obra**.
6. En cada dispositivo toca **"Activar notificaciones"**. En iPhone primero hay que
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
| `CLOUDINARY_URL` | Almacenamiento de las fotos (ver abajo). Sin ella, se guardan en el disco |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | SMTP para correos de respaldo (opcional) |

**Fotos (obligatorio en producción).** Las fotos de llegada, avance e incidencias se guardan en
[Cloudinary](https://cloudinary.com) (plan gratuito). En *Dashboard → API Keys* se copia el
**API environment variable** con el formato `cloudinary://<api_key>:<api_secret>@<cloud_name>`
y se pega en Render como `CLOUDINARY_URL`.

Si la variable no está, Django guarda las fotos en el disco local: sirve para desarrollo, pero en
Render ese disco **se borra en cada despliegue** y se perderían las fotos que respaldan la asistencia.
En los tests siempre se usa el disco, nunca Cloudinary.

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
├── models.py            # Obra, Zona, Rack, Paquete, TipoPunto, Punto, ReporteAvance, AvancePunto,
│                        # TipoIncidencia, Incidencia, Asistencia, PerfilTrabajador, Notificacion...
├── etapas.py            # Las 7 etapas: orden, requisitos previos y rendimiento estándar
├── importador.py        # Lectura de la planilla de paquetes (Excel) y carga de puntos
├── servicios.py         # Reglas: validar etapas, omitidos, incidencias, asistencia (atómico, idempotente)
├── consultas.py         # Permisos por rol, filtros, estado de obra, proyección, ranking, selector
├── notificaciones.py    # Centro de avisos + envío push/correo en segundo plano
├── resumen.py           # Resumen diario
├── push.py              # Web Push (VAPID) y suscripciones
├── views/               # comunes, trabajador, api (celular/offline), supervision, exportar (Excel)
├── management/commands/ # resumen_diario, generar_vapid
├── templates/marvelec_app/
│   ├── trabajador/      # inicio, asistencia, nuevo_reporte, incidencia, historial, detalle
│   ├── supervision/     # resumen, avance_obra, rack, punto, incidencias, asistencia, revisar,
│   │                    # reportes, trabajadores, cargar_puntos
│   ├── partials/        # selector de puntos, filtros, tarjetas
│   └── pwa/             # sw.js y manifest (servidos desde la raíz del sitio)
└── static/marvelec_app/
    ├── css/style.css    # Sistema de diseño (claro/oscuro, móvil y escritorio, colores por etapa)
    ├── js/              # app.js, trabajador.js (selector, GPS), outbox.js (cola sin señal),
    │                    # supervision.js, chat.js (sondeo del hilo abierto)
    └── vendor/          # Chart.js
templates/
├── base.html
└── layouts/             # movil.html (barra inferior), escritorio.html (menú lateral)
```

### Reglas de negocio principales

- Una etapa se registra **una sola vez por punto** (si otro ya la registró, queda "omitida"
  con el motivo y quién la hizo).
- Una etapa exige sus **requisitos previos** (ej. identificación = bajada + peinado). Vale si
  vienen en el mismo reporte.
- Un punto con **incidencia abierta** no avanza hasta que el supervisor la libera.
- El reporte guarda lo válido y muestra lo **omitido** al trabajador y al supervisor.
- **Asistencia**: una por día, con foto obligatoria. Si se rechaza, se puede volver a marcar.
  Sólo los días **confirmados** cuentan como jornada.
- **Rendimiento** = Σ (puntos de cada etapa ÷ estándar de la etapa) ÷ jornadas. 100% = estándar.
- **Chat:** un trabajador sólo conversa con la jefatura de su obra, nunca con otro trabajador. El hilo
  abierto se actualiza por sondeo cada 5 s (Render en plan gratuito no mantiene WebSockets). Sin señal
  el mensaje **no** se guarda para después: se avisa, para que una consulta urgente no llegue tarde.
  Los mensajes no llenan la campanita; el chat tiene su propio contador.

## 6. Tests

```bash
python manage.py test marvelec_app
```

## 7. Pendientes conocidos

- **Fase 2:** cuadrillas y asignación de paquetes, PDF de certificación Fluke por punto, falla de
  certificación que devuelve el punto atrás.
- La **administración puede leer las conversaciones** desde `/admin/` (sólo lectura, para soporte).
  Conviene avisarlo al equipo.
- **Fase 3:** merma de cable (metros cortados vs. medidos por punto).
