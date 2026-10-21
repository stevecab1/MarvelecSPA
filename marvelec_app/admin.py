import re

from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RelatedDropdownFilter
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from . import etapas
from .models import (
    Asistencia, AvancePunto, Incidencia, Notificacion, Obra, Paquete, PerfilTrabajador, Punto, Rack,
    ReporteAvance, ResumenDiarioEnviado, SuscripcionPush, TipoIncidencia, TipoPunto, Zona,
)
from .servicios import liberar_incidencia, revisar_asistencia, revisar_reporte


def _contar(queryset, campo):
    """Cuenta filas relacionadas en una subconsulta (sin multiplicar filas del listado)."""
    return Coalesce(
        Subquery(
            queryset.filter(**{campo: OuterRef('pk')}).order_by().values(campo)
            .annotate(c=Count('pk')).values('c')
        ),
        Value(0),
        output_field=IntegerField(),
    )


def _miniatura(archivo):
    if not archivo:
        return '-'
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" width="48" height="48" '
        'style="object-fit:cover;border-radius:6px;" /></a>', archivo.url
    )


def _foto_grande(archivo, vacio):
    if not archivo:
        return vacio
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" width="300" style="border-radius:8px;" /></a>', archivo.url
    )


# ---------- OBRA, ZONAS, RACKS, PAQUETES ----------

class ZonaInline(TabularInline):
    model = Zona
    extra = 1
    fields = ('nombre', 'descripcion')


@admin.register(Obra)
class ObraAdmin(ModelAdmin):
    list_display = ('nombre', 'direccion', 'fecha_inicio', 'fecha_termino_planificada', 'activa', 'n_racks', 'n_puntos')
    list_editable = ('activa',)
    list_filter = ('activa',)
    search_fields = ('nombre', 'direccion')
    inlines = [ZonaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _n_racks=Count('racks', distinct=True),
            _n_puntos=_contar(Punto.objects.all(), 'rack__obra'),
        )

    @display(description='Racks', ordering='_n_racks')
    def n_racks(self, obj):
        return obj._n_racks

    @display(description='Puntos', ordering='_n_puntos')
    def n_puntos(self, obj):
        return obj._n_puntos


@admin.register(Zona)
class ZonaAdmin(ModelAdmin):
    list_display = ('nombre', 'obra', 'descripcion', 'n_paquetes')
    list_select_related = ('obra',)
    list_filter = (('obra', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('nombre', 'obra__nombre')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n_paquetes=Count('paquetes'))

    @display(description='Paquetes', ordering='_n_paquetes')
    def n_paquetes(self, obj):
        return obj._n_paquetes


class PaqueteInline(TabularInline):
    model = Paquete
    extra = 0
    fields = ('numero', 'zona', 'metros')


@admin.register(Rack)
class RackAdmin(ModelAdmin):
    list_display = ('nombre', 'obra', 'ubicacion', 'n_paquetes', 'n_puntos', 'n_certificados')
    list_select_related = ('obra',)
    list_filter = (('obra', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('nombre', 'obra__nombre')
    inlines = [PaqueteInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _n_paquetes=_contar(Paquete.objects.all(), 'rack'),
            _n_puntos=_contar(Punto.objects.all(), 'rack'),
            _n_cert=_contar(AvancePunto.objects.filter(etapa=etapas.FINAL), 'punto__rack'),
        )

    @display(description='Paquetes', ordering='_n_paquetes')
    def n_paquetes(self, obj):
        return obj._n_paquetes

    @display(description='Puntos', ordering='_n_puntos')
    def n_puntos(self, obj):
        return obj._n_puntos

    @display(description='Certificados', ordering='_n_cert')
    def n_certificados(self, obj):
        return obj._n_cert


@admin.register(Paquete)
class PaqueteAdmin(ModelAdmin):
    list_display = ('__str__', 'rack', 'obra', 'zona', 'metros', 'n_puntos')
    list_select_related = ('rack__obra', 'zona')
    list_editable = ('metros',)
    list_filter = (('rack__obra', RelatedDropdownFilter), ('rack', RelatedDropdownFilter))
    list_filter_submit = True
    search_fields = ('rack__nombre', '=numero')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n_puntos=Count('puntos'))

    @display(description='Obra', ordering='rack__obra__nombre')
    def obra(self, obj):
        return obj.rack.obra

    @display(description='Puntos', ordering='_n_puntos')
    def n_puntos(self, obj):
        return obj._n_puntos


# ---------- PUNTOS ----------

@admin.register(TipoPunto)
class TipoPuntoAdmin(ModelAdmin):
    list_display = ('sigla', 'nombre', 'orden', 'n_puntos')
    list_editable = ('nombre', 'orden')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n_puntos=Count('puntos'))

    @display(description='Puntos', ordering='_n_puntos')
    def n_puntos(self, obj):
        return obj._n_puntos


class AvancePuntoInline(TabularInline):
    model = AvancePunto
    extra = 0
    fields = ('etapa', 'reporte', 'trabajador', 'fecha')
    readonly_fields = ('etapa', 'reporte', 'trabajador', 'fecha')
    can_delete = True
    verbose_name_plural = 'Etapas registradas'

    def has_add_permission(self, request, obj=None):
        return False

    @display(description='Trabajador')
    def trabajador(self, obj):
        return obj.reporte.nombre_trabajador

    @display(description='Fecha')
    def fecha(self, obj):
        return timezone.localtime(obj.reporte.fecha_hora).strftime('%d-%m-%Y %H:%M')


class IncidenciaInline(TabularInline):
    model = Incidencia
    fk_name = 'punto'
    extra = 0
    fields = ('tipo', 'estado', 'reportada_por', 'creada', 'liberada_en')
    readonly_fields = ('tipo', 'estado', 'reportada_por', 'creada', 'liberada_en')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


CODIGO_BUSQUEDA = re.compile(r'^\s*([A-Za-z]{1,10})\s*-?\s*(\d+)\s*$')


@admin.register(Punto)
class PuntoAdmin(ModelAdmin):
    list_display = ('codigo_punto', 'rack', 'obra', 'paquete', 'metros_punto', 'avance', 'bloqueado')
    list_select_related = ('rack__obra', 'tipo', 'paquete')
    list_filter = (
        ('rack__obra', RelatedDropdownFilter), ('rack', RelatedDropdownFilter), ('tipo', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ('rack__nombre', 'tipo__sigla')
    search_help_text = 'Busca por código (ej. DT-015 o dt15) o por rack.'
    readonly_fields = ('creado',)
    inlines = [AvancePuntoInline, IncidenciaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _n_etapas=Count('avances', distinct=True),
            _bloqueado=Exists(Incidencia.objects.filter(punto=OuterRef('pk'), estado=Incidencia.ESTADO_ABIERTA)),
        )

    def get_search_results(self, request, queryset, search_term):
        codigo = CODIGO_BUSQUEDA.match(search_term or '')
        if codigo:
            return queryset.filter(tipo__sigla__iexact=codigo.group(1), numero=int(codigo.group(2))), False
        return super().get_search_results(request, queryset, search_term)

    @display(description='Código', ordering='numero')
    def codigo_punto(self, obj):
        return obj.codigo

    @display(description='Obra', ordering='rack__obra__nombre')
    def obra(self, obj):
        return obj.rack.obra

    @display(description='Metros')
    def metros_punto(self, obj):
        return obj.metros_efectivos if obj.metros_efectivos is not None else '-'

    @display(description='Etapas', ordering='_n_etapas')
    def avance(self, obj):
        return f'{obj._n_etapas}/{len(etapas.ETAPAS)}'

    @display(description='Bloqueado', boolean=True, ordering='_bloqueado')
    def bloqueado(self, obj):
        return obj._bloqueado


# ---------- USUARIO + PERFIL ----------

class PerfilTrabajadorInline(StackedInline):
    model = PerfilTrabajador
    can_delete = False
    verbose_name_plural = 'Perfil de Trabajador (Rol y Obra)'
    fields = ('rol', 'obra_asignada')
    max_num = 1
    min_num = 1
    extra = 1


COLOR_ROL = {
    PerfilTrabajador.ROL_TRABAJADOR: 'info',
    PerfilTrabajador.ROL_SUPERVISOR: 'warning',
    PerfilTrabajador.ROL_GERENCIA: 'primary',
}

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    inlines = (PerfilTrabajadorInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_rol', 'get_obra')
    list_select_related = ('perfil', 'perfil__obra_asignada')

    @display(description='Rol', label=COLOR_ROL)
    def get_rol(self, obj):
        try:
            return obj.perfil.rol, obj.perfil.get_rol_display()
        except PerfilTrabajador.DoesNotExist:
            return '-'

    @display(description='Obra asignada')
    def get_obra(self, obj):
        try:
            return obj.perfil.obra_asignada or '-'
        except PerfilTrabajador.DoesNotExist:
            return '-'


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(PerfilTrabajador)
class PerfilTrabajadorAdmin(ModelAdmin):
    """Vista directa de perfiles, útil para asignar roles y obras en masa."""
    list_display = ('usuario', 'rol', 'obra_asignada')
    list_select_related = ('usuario', 'obra_asignada')
    list_filter = (('rol', ChoicesDropdownFilter), ('obra_asignada', RelatedDropdownFilter))
    list_filter_submit = True
    list_editable = ('rol', 'obra_asignada')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name')


# ---------- REPORTES DE AVANCE ----------

class AvanceReporteInline(TabularInline):
    model = AvancePunto
    extra = 0
    fields = ('punto', 'etapa')
    readonly_fields = ('punto', 'etapa')
    verbose_name_plural = 'Etapas registradas en este reporte'

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('punto__tipo', 'punto__rack')


@admin.register(ReporteAvance)
class ReporteAvanceAdmin(ModelAdmin):
    list_display = ('reporte', 'trabajador_nombre', 'obra', 'rack', 'resumen', 'total_puntos', 'estado_label',
                    'fecha_hora', 'ver_miniatura')
    list_select_related = ('trabajador', 'obra', 'rack')
    readonly_fields = ('total_puntos', 'ver_foto_grande', 'lista_omitidos', 'revisado_por', 'revisado_en',
                       'enviado_offline')
    list_filter = (
        ('estado', ChoicesDropdownFilter),
        ('obra', RelatedDropdownFilter),
        ('rack', RelatedDropdownFilter),
        ('trabajador', RelatedDropdownFilter),
        'fecha_hora',
    )
    list_filter_submit = True
    search_fields = ('trabajador__username', 'trabajador__first_name', 'trabajador__last_name',
                     'obra__nombre', 'rack__nombre')
    date_hierarchy = 'fecha_hora'
    inlines = [AvanceReporteInline]
    fields = ('trabajador', 'obra', 'rack', 'fecha_hora', 'comentario', 'foto', 'ver_foto_grande',
              'total_puntos', 'lista_omitidos', 'estado', 'revisado_por', 'revisado_en', 'comentario_revision',
              'enviado_offline')
    actions = ['aprobar_seleccionados']

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('avances')

    @display(description='Reporte', ordering='pk')
    def reporte(self, obj):
        return f'#{obj.pk}'

    @display(description='Trabajador', ordering='trabajador__first_name')
    def trabajador_nombre(self, obj):
        return obj.nombre_trabajador

    @display(description='Etapas')
    def resumen(self, obj):
        return ', '.join(f'{nombre} ({n})' for _, nombre, n in obj.resumen_etapas()) or '-'

    @display(description='Estado', ordering='estado', label={
        ReporteAvance.ESTADO_PENDIENTE: 'warning',
        ReporteAvance.ESTADO_APROBADO: 'success',
        ReporteAvance.ESTADO_OBSERVADO: 'danger',
    })
    def estado_label(self, obj):
        return obj.estado, obj.get_estado_display()

    @display(description='Foto')
    def ver_miniatura(self, obj):
        return _miniatura(obj.foto)

    @display(description='Vista previa de la foto')
    def ver_foto_grande(self, obj):
        return _foto_grande(obj.foto, 'Este reporte no tiene foto del avance.')

    @display(description='No registrados')
    def lista_omitidos(self, obj):
        if not obj.omitidos:
            return '-'
        return format_html_join(
            mark_safe('<br>'), '{}: {}', ((o.get('codigo') or '—', o.get('motivo', '')) for o in obj.omitidos)
        )

    @admin.action(description='Aprobar reportes seleccionados (solo pendientes)')
    def aprobar_seleccionados(self, request, queryset):
        # Mismo servicio que la app: el trabajador recibe el aviso de aprobación.
        pendientes = queryset.filter(estado=ReporteAvance.ESTADO_PENDIENTE).exclude(
            trabajador=request.user
        ).select_related('trabajador', 'obra', 'rack')
        n = 0
        for reporte in pendientes:
            revisar_reporte(reporte, request.user, 'aprobar')
            n += 1
        self.message_user(request, f'{n} reporte(s) aprobados; se avisó a cada trabajador.', messages.SUCCESS)


# ---------- TERRENO: INCIDENCIAS Y ASISTENCIA ----------

@admin.register(TipoIncidencia)
class TipoIncidenciaAdmin(ModelAdmin):
    list_display = ('nombre', 'es_falla_certificacion', 'activo', 'orden')
    list_editable = ('es_falla_certificacion', 'activo', 'orden')


@admin.register(Incidencia)
class IncidenciaAdmin(ModelAdmin):
    list_display = ('codigo_punto', 'rack', 'tipo', 'estado_label', 'reportada_por', 'creada', 'detenido', 'foto_mini')
    list_select_related = ('punto__tipo', 'punto__rack', 'tipo', 'reportada_por')
    list_filter = (
        ('estado', ChoicesDropdownFilter), ('tipo', RelatedDropdownFilter),
        ('punto__rack__obra', RelatedDropdownFilter), ('punto__rack', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ('punto__rack__nombre', 'comentario', 'reportada_por__username')
    date_hierarchy = 'creada'
    raw_id_fields = ('punto',)
    readonly_fields = ('foto_grande', 'liberada_por', 'liberada_en')
    actions = ['liberar_seleccionadas']

    @display(description='Punto', ordering='punto__numero')
    def codigo_punto(self, obj):
        return obj.punto.codigo

    @display(description='Rack', ordering='punto__rack__nombre')
    def rack(self, obj):
        return obj.punto.rack

    @display(description='Estado', ordering='estado', label={
        Incidencia.ESTADO_ABIERTA: 'danger', Incidencia.ESTADO_LIBERADA: 'success',
    })
    def estado_label(self, obj):
        return obj.estado, obj.get_estado_display()

    @display(description='Horas detenido')
    def detenido(self, obj):
        return obj.horas_detenido

    @display(description='Foto')
    def foto_mini(self, obj):
        return _miniatura(obj.foto)

    @display(description='Vista previa')
    def foto_grande(self, obj):
        return _foto_grande(obj.foto, 'Sin foto.')

    @admin.action(description='Liberar incidencias seleccionadas')
    def liberar_seleccionadas(self, request, queryset):
        abiertas = queryset.filter(estado=Incidencia.ESTADO_ABIERTA).select_related(
            'punto__tipo', 'punto__rack', 'tipo', 'reportada_por'
        )
        n = 0
        for incidencia in abiertas:
            liberar_incidencia(incidencia, request.user, 'Liberada desde el panel de administración.')
            n += 1
        self.message_user(request, f'{n} incidencia(s) liberadas.', messages.SUCCESS)


@admin.register(Asistencia)
class AsistenciaAdmin(ModelAdmin):
    list_display = ('trabajador_nombre', 'obra', 'fecha', 'hora_llegada', 'estado_label', 'foto_mini', 'gps')
    list_select_related = ('trabajador', 'obra')
    list_filter = (
        ('estado', ChoicesDropdownFilter), ('obra', RelatedDropdownFilter), ('trabajador', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ('trabajador__username', 'trabajador__first_name', 'trabajador__last_name')
    date_hierarchy = 'fecha'
    readonly_fields = ('foto_grande', 'revisado_por', 'revisado_en', 'enviado_offline')
    actions = ['confirmar_seleccionadas']

    @display(description='Trabajador', ordering='trabajador__first_name')
    def trabajador_nombre(self, obj):
        return obj.trabajador.get_full_name() or obj.trabajador.username

    @display(description='Hora', ordering='hora')
    def hora_llegada(self, obj):
        return timezone.localtime(obj.hora).strftime('%H:%M')

    @display(description='Estado', ordering='estado', label={
        Asistencia.ESTADO_PENDIENTE: 'warning', Asistencia.ESTADO_CONFIRMADA: 'success',
        Asistencia.ESTADO_RECHAZADA: 'danger',
    })
    def estado_label(self, obj):
        return obj.estado, obj.get_estado_display()

    @display(description='Foto')
    def foto_mini(self, obj):
        return _miniatura(obj.foto)

    @display(description='Vista previa')
    def foto_grande(self, obj):
        return _foto_grande(obj.foto, 'Sin foto.')

    @display(description='GPS')
    def gps(self, obj):
        if not obj.url_mapa:
            return '-'
        return format_html('<a href="{}" target="_blank">Ver mapa</a>', obj.url_mapa)

    @admin.action(description='Confirmar asistencias seleccionadas (solo pendientes)')
    def confirmar_seleccionadas(self, request, queryset):
        n = 0
        for asistencia in queryset.filter(estado=Asistencia.ESTADO_PENDIENTE):
            revisar_asistencia(asistencia, request.user, 'confirmar')
            n += 1
        self.message_user(request, f'{n} asistencia(s) confirmadas.', messages.SUCCESS)


# ---------- SISTEMA ----------

@admin.register(Notificacion)
class NotificacionAdmin(ModelAdmin):
    list_display = ('titulo', 'usuario', 'tipo', 'leida', 'creada')
    list_select_related = ('usuario',)
    list_filter = (('tipo', ChoicesDropdownFilter), 'leida')
    list_filter_submit = True
    search_fields = ('titulo', 'cuerpo', 'usuario__username')
    raw_id_fields = ('reporte',)


@admin.register(SuscripcionPush)
class SuscripcionPushAdmin(ModelAdmin):
    list_display = ('usuario', 'creado')
    list_select_related = ('usuario',)
    search_fields = ('usuario__username',)


@admin.register(ResumenDiarioEnviado)
class ResumenDiarioEnviadoAdmin(ModelAdmin):
    list_display = ('fecha', 'destinatarios', 'enviado_en')
