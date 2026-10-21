from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from . import etapas


def _nombre(usuario):
    return usuario.get_full_name() or usuario.username


# =========================================================
# OBRA, ZONAS Y PERSONAL
# =========================================================

class Obra(models.Model):
    """Un proyecto/obra en ejecución (ej. 'Hospital Sótero del Río')."""
    nombre = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=255, blank=True, verbose_name="Dirección / Ubicación")
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_termino_planificada = models.DateField(
        null=True, blank=True, verbose_name="Fecha de término planificada",
        help_text="Se usa para estimar si la obra va atrasada.",
    )
    activa = models.BooleanField(default=True, verbose_name="¿Obra activa?")

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Zona(models.Model):
    """Sector de la obra al que llegan los puntos (ej. 'Sótano 1 - Ala Norte')."""
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='zonas')
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"
        unique_together = ('obra', 'nombre')
        ordering = ['obra__nombre', 'nombre']

    def __str__(self):
        return self.nombre


class PerfilTrabajador(models.Model):
    """Perfil asociado a cada usuario: define su rol y, si corresponde, su obra."""
    ROL_TRABAJADOR = 'trabajador'
    ROL_SUPERVISOR = 'supervisor'
    ROL_GERENCIA = 'gerencia'
    ROL_CHOICES = [
        (ROL_TRABAJADOR, 'Trabajador'),
        (ROL_SUPERVISOR, 'Supervisor'),
        (ROL_GERENCIA, 'Gerencia'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default=ROL_TRABAJADOR)
    # Un trabajador o supervisor normalmente está asignado a UNA obra.
    # Gerencia no requiere obra_asignada: ve todas las obras.
    obra_asignada = models.ForeignKey(
        Obra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trabajadores', verbose_name="Obra asignada"
    )

    class Meta:
        verbose_name = "Perfil de Trabajador"
        verbose_name_plural = "Perfiles de Trabajadores"

    def __str__(self):
        return f"{_nombre(self.usuario)} ({self.get_rol_display()})"

    @property
    def es_supervisor_o_gerencia(self):
        return self.rol in (self.ROL_SUPERVISOR, self.ROL_GERENCIA)

    def puede_revisar_obra(self, obra_id):
        """Gerencia revisa todo; un supervisor sólo su obra (o todas si no tiene obra fija)."""
        if self.rol == self.ROL_GERENCIA:
            return True
        if self.rol == self.ROL_SUPERVISOR:
            return not self.obra_asignada_id or self.obra_asignada_id == obra_id
        return False


# =========================================================
# INVENTARIO DE PUNTOS (planilla de paquetes)
# =========================================================

class Rack(models.Model):
    """Rack de comunicaciones al que llegan los cables (ej. '1H', 'RN1J')."""
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='racks')
    nombre = models.CharField(max_length=50)
    ubicacion = models.CharField(max_length=150, blank=True, verbose_name="Ubicación",
                                 help_text="Ej. sala de comunicaciones del sótano 1.")

    class Meta:
        verbose_name = "Rack"
        verbose_name_plural = "Racks"
        unique_together = ('obra', 'nombre')
        ordering = ['obra__nombre', 'nombre']

    def __str__(self):
        return f"Rack {self.nombre}"

    def get_absolute_url(self):
        return reverse('marvelec_app:rack_detalle', args=[self.pk])


class Paquete(models.Model):
    """Grupo de cables que van del rack a la misma zona y comparten metraje."""
    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name='paquetes')
    numero = models.PositiveIntegerField()
    zona = models.ForeignKey(Zona, on_delete=models.SET_NULL, null=True, blank=True, related_name='paquetes')
    metros = models.PositiveIntegerField(null=True, blank=True, verbose_name="Metros por punto")

    class Meta:
        verbose_name = "Paquete"
        verbose_name_plural = "Paquetes"
        unique_together = ('rack', 'numero')
        ordering = ['rack__nombre', 'numero']

    def __str__(self):
        return f"Paquete {self.numero:02d}"

    def clean(self):
        if self.zona_id and self.rack_id and self.zona.obra_id != self.rack.obra_id:
            raise ValidationError({'zona': 'La zona no pertenece a la obra del rack.'})


class TipoPunto(models.Model):
    """Prefijo del código del punto (DT, VD, RI...). El nombre se completa en el admin."""
    sigla = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=60, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Tipo de punto"
        verbose_name_plural = "Tipos de punto"
        ordering = ['orden', 'sigla']

    def __str__(self):
        return f"{self.sigla} · {self.nombre}" if self.nombre else self.sigla

    def save(self, *args, **kwargs):
        self.sigla = self.sigla.strip().upper()
        super().save(*args, **kwargs)


class Punto(models.Model):
    """Un punto de red (ej. DT-015 del rack 1H). Avanza etapa por etapa hasta su certificación."""
    rack = models.ForeignKey(Rack, on_delete=models.PROTECT, related_name='puntos')
    paquete = models.ForeignKey(Paquete, on_delete=models.SET_NULL, null=True, blank=True, related_name='puntos')
    tipo = models.ForeignKey(TipoPunto, on_delete=models.PROTECT, related_name='puntos')
    numero = models.PositiveIntegerField()
    metros = models.PositiveIntegerField(null=True, blank=True,
                                         help_text="Sólo si difiere del metraje del paquete.")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Punto"
        verbose_name_plural = "Puntos"
        unique_together = ('rack', 'tipo', 'numero')
        ordering = ['rack__nombre', 'tipo__orden', 'tipo__sigla', 'numero']

    def __str__(self):
        return f"{self.codigo} (Rack {self.rack.nombre})"

    @property
    def codigo(self):
        return f"{self.tipo.sigla}-{self.numero:03d}"

    @property
    def metros_efectivos(self):
        if self.metros is not None:
            return self.metros
        return self.paquete.metros if self.paquete_id else None

    def clean(self):
        if self.paquete_id and self.rack_id and self.paquete.rack_id != self.rack_id:
            raise ValidationError({'paquete': 'El paquete no pertenece a este rack.'})

    def get_absolute_url(self):
        return reverse('marvelec_app:punto_detalle', args=[self.pk])


# =========================================================
# REGISTRO DE AVANCE
# =========================================================

class ReporteAvance(models.Model):
    """
    Reemplaza el mensaje de WhatsApp: un trabajador informa qué etapas completó en qué puntos
    de un rack. Cada par punto-etapa queda como un AvancePunto. La llegada a la obra es aparte.
    """
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_APROBADO = 'aprobado'
    ESTADO_OBSERVADO = 'observado'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente de revisión'),
        (ESTADO_APROBADO, 'Aprobado'),
        (ESTADO_OBSERVADO, 'Observado'),
    ]

    trabajador = models.ForeignKey(User, on_delete=models.PROTECT, related_name='reportes_avance')
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name='reportes')
    rack = models.ForeignKey(Rack, on_delete=models.PROTECT, related_name='reportes')
    # Hora en que el trabajador hizo el reporte (puede venir del celular si se envió sin señal).
    fecha_hora = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Fecha y hora")
    foto = models.ImageField(
        upload_to='reportes/avance/%Y/%m/', blank=True, null=True, verbose_name="Foto del avance"
    )
    comentario = models.TextField(blank=True, verbose_name="Comentarios / consultas")
    total_puntos = models.PositiveIntegerField(
        default=0, editable=False, help_text="Cantidad de etapas registradas (punto × etapa)."
    )
    omitidos = models.JSONField(
        default=list, blank=True,
        help_text="Puntos que el sistema no registró y por qué (ej. etapa ya registrada).",
    )

    # --- Revisión del supervisor ---
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE, db_index=True)
    revisado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reportes_revisados'
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    comentario_revision = models.TextField(blank=True, verbose_name="Observación del supervisor")

    # --- Envío desde el celular ---
    # Identificador generado en el celular: evita duplicados si un envío sin señal se reintenta.
    uuid_cliente = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    enviado_offline = models.BooleanField(default=False, verbose_name="¿Enviado sin conexión?")

    class Meta:
        verbose_name = "Reporte de Avance"
        verbose_name_plural = "Reportes de Avance"
        ordering = ['-fecha_hora']

    def clean(self):
        if self.rack_id and self.obra_id and self.rack.obra_id != self.obra_id:
            raise ValidationError({'rack': 'El rack seleccionado no pertenece a esta obra.'})

    def calcular_total_puntos(self):
        total = self.avances.count()
        if total != self.total_puntos:
            self.total_puntos = total
            self.save(update_fields=['total_puntos'])

    def resumen_etapas(self):
        """[(clave, nombre de etapa, cantidad de puntos)] en el orden del proceso (usa avances precargados)."""
        conteo = {}
        for avance in self.avances.all():
            conteo[avance.etapa] = conteo.get(avance.etapa, 0) + 1
        return [(c, etapas.nombre(c), conteo[c]) for c in etapas.ordenar(conteo)]

    def codigos_por_etapa(self):
        """[(clave, nombre de etapa, ['DT-001', ...])] (requiere avances__punto__tipo precargados)."""
        grupos = {}
        for avance in self.avances.all():
            grupos.setdefault(avance.etapa, []).append(avance.punto)
        return [
            (c, etapas.nombre(c), [p.codigo for p in sorted(grupos[c], key=lambda p: (p.tipo.sigla, p.numero))])
            for c in etapas.ordenar(grupos)
        ]

    # --- Revisión ---
    def aprobar(self, usuario):
        self.estado = self.ESTADO_APROBADO
        self.revisado_por = usuario
        self.revisado_en = timezone.now()
        self.comentario_revision = ''
        self.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'comentario_revision'])

    def observar(self, usuario, comentario):
        self.estado = self.ESTADO_OBSERVADO
        self.revisado_por = usuario
        self.revisado_en = timezone.now()
        self.comentario_revision = comentario
        self.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'comentario_revision'])

    # --- Permisos ---
    def puede_ver(self, perfil):
        """El autor, gerencia, y supervisores de la obra (o sin obra fija) pueden ver el reporte."""
        if self.trabajador_id == perfil.usuario_id:
            return True
        return perfil.puede_revisar_obra(self.obra_id)

    def puede_editar(self, usuario):
        """Sólo el autor puede corregir su reporte, y sólo si fue observado."""
        return self.trabajador_id == usuario.id and self.estado == self.ESTADO_OBSERVADO

    @property
    def nombre_trabajador(self):
        return _nombre(self.trabajador)

    def get_absolute_url(self):
        return reverse('marvelec_app:reporte_detalle', args=[self.pk])

    def __str__(self):
        fecha_str = timezone.localtime(self.fecha_hora).strftime('%d/%m/%Y') if self.fecha_hora else 'N/A'
        return f"Reporte #{self.pk} de {self.nombre_trabajador} ({fecha_str})"


class AvancePunto(models.Model):
    """Una etapa completada en un punto. Cada etapa se registra una sola vez por punto."""
    reporte = models.ForeignKey(ReporteAvance, on_delete=models.CASCADE, related_name='avances')
    punto = models.ForeignKey(Punto, on_delete=models.PROTECT, related_name='avances')
    etapa = models.CharField(max_length=30, choices=etapas.CHOICES, db_index=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Avance de punto"
        verbose_name_plural = "Avances de puntos"
        constraints = [
            models.UniqueConstraint(fields=['punto', 'etapa'], name='etapa_unica_por_punto'),
        ]

    def __str__(self):
        return f"{self.punto.codigo}: {self.get_etapa_display()}"


# =========================================================
# INCIDENCIAS (puntos bloqueados)
# =========================================================

class TipoIncidencia(models.Model):
    """Causas tipificadas por las que un punto no puede avanzar (ej. 'Sin canalización')."""
    nombre = models.CharField(max_length=80, unique=True)
    es_falla_certificacion = models.BooleanField(
        default=False, verbose_name="¿Falla de certificación?",
        help_text="Ej. tierra cruzada o fallo por distancia, detectadas con el Fluke.",
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Tipo de incidencia"
        verbose_name_plural = "Tipos de incidencia"
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class Incidencia(models.Model):
    """Problema en un punto. Mientras esté abierta, el punto queda bloqueado."""
    ESTADO_ABIERTA = 'abierta'
    ESTADO_LIBERADA = 'liberada'
    ESTADO_CHOICES = [(ESTADO_ABIERTA, 'Abierta'), (ESTADO_LIBERADA, 'Liberada')]

    punto = models.ForeignKey(Punto, on_delete=models.CASCADE, related_name='incidencias')
    tipo = models.ForeignKey(TipoIncidencia, on_delete=models.PROTECT, related_name='incidencias')
    reportada_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='incidencias_reportadas')
    creada = models.DateTimeField(default=timezone.now, db_index=True)
    foto = models.ImageField(upload_to='incidencias/%Y/%m/', blank=True, null=True)
    comentario = models.TextField(blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_ABIERTA, db_index=True)
    liberada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='incidencias_liberadas'
    )
    liberada_en = models.DateTimeField(null=True, blank=True)
    comentario_liberacion = models.TextField(blank=True, verbose_name="¿Cómo se resolvió?")

    # Un envío desde el celular puede crear varias incidencias (una por punto) con el mismo uuid.
    uuid_cliente = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    enviado_offline = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Incidencia"
        verbose_name_plural = "Incidencias"
        ordering = ['-creada']
        constraints = [
            models.UniqueConstraint(
                fields=['punto', 'tipo'], condition=Q(estado='abierta'), name='una_incidencia_abierta_por_tipo',
            ),
        ]

    def __str__(self):
        return f"{self.punto.codigo}: {self.tipo.nombre}"

    @property
    def abierta(self):
        return self.estado == self.ESTADO_ABIERTA

    @property
    def tiempo_detenido(self):
        return (self.liberada_en or timezone.now()) - self.creada

    @property
    def horas_detenido(self):
        return round(self.tiempo_detenido.total_seconds() / 3600, 1)

    @property
    def url_mapa(self):
        if self.latitud is None or self.longitud is None:
            return ''
        return f'https://www.openstreetmap.org/?mlat={self.latitud}&mlon={self.longitud}#map=19/{self.latitud}/{self.longitud}'

    def get_absolute_url(self):
        return reverse('marvelec_app:punto_detalle', args=[self.punto_id])


# =========================================================
# ASISTENCIA
# =========================================================

class Asistencia(models.Model):
    """Marca de llegada a la obra (foto del lugar). El supervisor la confirma o la rechaza."""
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_CONFIRMADA = 'confirmada'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_CONFIRMADA, 'Confirmada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
    ]

    trabajador = models.ForeignKey(User, on_delete=models.PROTECT, related_name='asistencias')
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name='asistencias')
    fecha = models.DateField(db_index=True)
    hora = models.DateTimeField(default=timezone.now, verbose_name="Hora de llegada")
    foto = models.ImageField(upload_to='asistencia/%Y/%m/', verbose_name="Foto de llegada")
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    precision = models.PositiveIntegerField(null=True, blank=True, help_text="Precisión del GPS en metros.")

    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE, db_index=True)
    revisado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='asistencias_revisadas'
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    motivo_rechazo = models.TextField(blank=True)

    uuid_cliente = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    enviado_offline = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        ordering = ['-fecha', 'trabajador__first_name']
        constraints = [
            models.UniqueConstraint(fields=['trabajador', 'fecha'], name='una_asistencia_por_dia'),
        ]

    def __str__(self):
        return f"{_nombre(self.trabajador)} · {self.fecha:%d-%m-%Y}"

    @property
    def url_mapa(self):
        if self.latitud is None or self.longitud is None:
            return ''
        return f'https://www.openstreetmap.org/?mlat={self.latitud}&mlon={self.longitud}#map=18/{self.latitud}/{self.longitud}'


# =========================================================
# NOTIFICACIONES
# =========================================================

class SuscripcionPush(models.Model):
    """Almacena la suscripción push de cada navegador/dispositivo de un usuario."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suscripciones_push')
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suscripción Push"
        verbose_name_plural = "Suscripciones Push"

    def __str__(self):
        return f"Push {self.usuario.username} ({self.endpoint[:40]}...)"


class Notificacion(models.Model):
    """Aviso dentro de la app (campanita). Además se envía como push si el usuario lo activó."""
    TIPO_NUEVO_REPORTE = 'nuevo_reporte'
    TIPO_REPORTE_CORREGIDO = 'reporte_corregido'
    TIPO_REPORTE_APROBADO = 'reporte_aprobado'
    TIPO_REPORTE_OBSERVADO = 'reporte_observado'
    TIPO_RESUMEN_DIARIO = 'resumen_diario'
    TIPO_NUEVA_INCIDENCIA = 'nueva_incidencia'
    TIPO_INCIDENCIA_LIBERADA = 'incidencia_liberada'
    TIPO_ASISTENCIA_RECHAZADA = 'asistencia_rechazada'
    TIPO_CHOICES = [
        (TIPO_NUEVO_REPORTE, 'Nuevo reporte'),
        (TIPO_REPORTE_CORREGIDO, 'Reporte corregido'),
        (TIPO_REPORTE_APROBADO, 'Reporte aprobado'),
        (TIPO_REPORTE_OBSERVADO, 'Reporte observado'),
        (TIPO_RESUMEN_DIARIO, 'Resumen diario'),
        (TIPO_NUEVA_INCIDENCIA, 'Nueva incidencia'),
        (TIPO_INCIDENCIA_LIBERADA, 'Incidencia liberada'),
        (TIPO_ASISTENCIA_RECHAZADA, 'Asistencia rechazada'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificaciones')
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    titulo = models.CharField(max_length=150)
    cuerpo = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)
    reporte = models.ForeignKey(
        ReporteAvance, on_delete=models.CASCADE, null=True, blank=True, related_name='notificaciones'
    )
    leida = models.BooleanField(default=False)
    creada = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ['-creada']
        indexes = [models.Index(fields=['usuario', 'leida'])]

    def __str__(self):
        return f"{self.usuario.username}: {self.titulo}"


class ResumenDiarioEnviado(models.Model):
    """Registro de resúmenes diarios enviados: evita mandar dos veces el mismo día."""
    fecha = models.DateField(unique=True)
    enviado_en = models.DateTimeField(auto_now_add=True)
    destinatarios = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Resumen diario enviado"
        verbose_name_plural = "Resúmenes diarios enviados"
        ordering = ['-fecha']

    def __str__(self):
        return f"Resumen {self.fecha:%d-%m-%Y} ({self.destinatarios} destinatarios)"
