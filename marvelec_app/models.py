from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum


# --- ENTIDADES PRINCIPALES ---

class Obra(models.Model):
    """Un proyecto/obra en ejecución (ej. 'Hospital Regional de Rancagua')."""
    nombre = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=255, blank=True, verbose_name="Dirección / Ubicación")
    fecha_inicio = models.DateField(default=timezone.now)
    activa = models.BooleanField(default=True, verbose_name="¿Obra activa?")

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Subetapa(models.Model):
    """Segmento de avance dentro de una obra (ej. 'Piso 3 - Ala Norte')."""
    obra = models.ForeignKey(Obra, on_delete=models.CASCADE, related_name='subetapas')
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Subetapa"
        verbose_name_plural = "Subetapas"
        unique_together = ('obra', 'nombre')
        ordering = ['obra__nombre', 'nombre']

    def __str__(self):
        return f"{self.obra.nombre} - {self.nombre}"


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
        return f"{self.usuario.get_full_name() or self.usuario.username} ({self.get_rol_display()})"

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


# --- REGISTRO DE AVANCE DIARIO ---

class ReporteAvance(models.Model):
    """
    Reemplaza el mensaje de WhatsApp: un trabajador reporta su llegada a la obra,
    junto con los puntos ejecutados en el día en una subetapa determinada.
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
    subetapa = models.ForeignKey(Subetapa, on_delete=models.PROTECT, related_name='reportes')
    # Hora en que el trabajador hizo el reporte (puede venir del celular si se envió sin señal).
    fecha_hora = models.DateTimeField(default=timezone.now, db_index=True)
    foto_llegada = models.ImageField(upload_to='reportes/llegada/', blank=True, null=True)
    comentario = models.TextField(blank=True, verbose_name="Comentarios / consultas")
    total_puntos = models.PositiveIntegerField(default=0, editable=False)

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
        """Valida que la subetapa pertenezca a la obra seleccionada."""
        from django.core.exceptions import ValidationError
        if self.subetapa_id and self.obra_id and self.subetapa.obra_id != self.obra_id:
            raise ValidationError(
                {'subetapa': 'La subetapa seleccionada no pertenece a esta obra.'}
            )

    def calcular_total_puntos(self):
        """Recalcula el total de puntos ejecutados sumando todos sus registros."""
        total = self.registros.aggregate(t=Sum('cantidad'))['t'] or 0
        if total != self.total_puntos:
            self.total_puntos = total
            self.save(update_fields=['total_puntos'])

    def puntos_por_tipo(self):
        """Devuelve {'red': n, 'fuerza': n, 'iluminacion': n} (usa registros precargados si existen)."""
        conteo = {tipo: 0 for tipo, _ in RegistroPunto.TIPO_CHOICES}
        for registro in self.registros.all():
            conteo[registro.tipo_punto] = conteo.get(registro.tipo_punto, 0) + registro.cantidad
        return conteo

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
        return self.trabajador.get_full_name() or self.trabajador.username

    def __str__(self):
        fecha_str = self.fecha_hora.strftime('%d/%m/%Y') if self.fecha_hora else 'N/A'
        return f"Reporte de {self.trabajador.username} - {self.obra.nombre} ({fecha_str})"


class RegistroPunto(models.Model):
    """Detalle de puntos ejecutados por tipo dentro de un ReporteAvance."""
    TIPO_RED = 'red'
    TIPO_FUERZA = 'fuerza'
    TIPO_ILUMINACION = 'iluminacion'
    TIPO_CHOICES = [
        (TIPO_RED, 'Punto de Red'),
        (TIPO_FUERZA, 'Punto de Fuerza'),
        (TIPO_ILUMINACION, 'Punto de Iluminación'),
    ]

    reporte = models.ForeignKey(ReporteAvance, on_delete=models.CASCADE, related_name='registros')
    tipo_punto = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Registro de Puntos"
        verbose_name_plural = "Registros de Puntos"

    def __str__(self):
        return f"{self.get_tipo_punto_display()}: {self.cantidad}"


# --- SUSCRIPCIONES PUSH (NOTIFICACIONES) ---

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


# --- CENTRO DE NOTIFICACIONES ---

class Notificacion(models.Model):
    """Aviso dentro de la app (campanita). Además se envía como push si el usuario lo activó."""
    TIPO_NUEVO_REPORTE = 'nuevo_reporte'
    TIPO_REPORTE_CORREGIDO = 'reporte_corregido'
    TIPO_REPORTE_APROBADO = 'reporte_aprobado'
    TIPO_REPORTE_OBSERVADO = 'reporte_observado'
    TIPO_RESUMEN_DIARIO = 'resumen_diario'
    TIPO_CHOICES = [
        (TIPO_NUEVO_REPORTE, 'Nuevo reporte'),
        (TIPO_REPORTE_CORREGIDO, 'Reporte corregido'),
        (TIPO_REPORTE_APROBADO, 'Reporte aprobado'),
        (TIPO_REPORTE_OBSERVADO, 'Reporte observado'),
        (TIPO_RESUMEN_DIARIO, 'Resumen diario'),
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
