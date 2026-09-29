from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RelatedDropdownFilter
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import (
    Obra, Subetapa, PerfilTrabajador, ReporteAvance, RegistroPunto, SuscripcionPush, Notificacion,
    ResumenDiarioEnviado,
)
from .servicios import revisar_reporte


def _suma_puntos(campo):
    """Total de puntos de los reportes de cada fila, en la misma consulta del listado."""
    return Coalesce(
        Subquery(
            ReporteAvance.objects.filter(**{campo: OuterRef('pk')}).order_by()
            .values(campo).annotate(t=Sum('total_puntos')).values('t')
        ),
        Value(0),
        output_field=IntegerField(),
    )


# ---------- OBRA + SUBETAPAS ----------

class SubetapaInline(TabularInline):
    model = Subetapa
    extra = 1
    fields = ('nombre', 'descripcion')


@admin.register(Obra)
class ObraAdmin(ModelAdmin):
    list_display = ('nombre', 'direccion', 'fecha_inicio', 'activa', 'n_subetapas', 'total_puntos_obra')
    list_editable = ('activa',)
    list_filter = ('activa',)
    search_fields = ('nombre', 'direccion')
    inlines = [SubetapaInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _n_subetapas=Count('subetapas', distinct=True),
            _total_puntos=_suma_puntos('obra'),
        )

    @display(description='Subetapas', ordering='_n_subetapas')
    def n_subetapas(self, obj):
        return obj._n_subetapas

    @display(description='Total puntos', ordering='_total_puntos')
    def total_puntos_obra(self, obj):
        return obj._total_puntos


@admin.register(Subetapa)
class SubetapaAdmin(ModelAdmin):
    list_display = ('nombre', 'obra', 'descripcion', 'total_puntos_subetapa')
    list_select_related = ('obra',)
    list_filter = (('obra', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('nombre', 'obra__nombre')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_total_puntos=_suma_puntos('subetapa'))

    @display(description='Total puntos', ordering='_total_puntos')
    def total_puntos_subetapa(self, obj):
        return obj._total_puntos


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


# ---------- REPORTE + PUNTOS ----------

class RegistroPuntoInline(TabularInline):
    model = RegistroPunto
    extra = 1
    fields = ('tipo_punto', 'cantidad')


@admin.register(ReporteAvance)
class ReporteAvanceAdmin(ModelAdmin):
    list_display = ('reporte', 'trabajador_nombre', 'obra', 'subetapa_nombre', 'total_puntos', 'estado_label',
                    'fecha_hora', 'ver_miniatura')
    list_select_related = ('trabajador', 'obra', 'subetapa')
    readonly_fields = ('total_puntos', 'ver_foto_grande', 'revisado_por', 'revisado_en', 'enviado_offline')
    list_filter = (
        ('estado', ChoicesDropdownFilter),
        ('obra', RelatedDropdownFilter),
        ('subetapa', RelatedDropdownFilter),
        ('trabajador', RelatedDropdownFilter),
        'fecha_hora',
    )
    list_filter_submit = True
    search_fields = ('trabajador__username', 'trabajador__first_name', 'trabajador__last_name',
                     'obra__nombre', 'subetapa__nombre')
    date_hierarchy = 'fecha_hora'
    inlines = [RegistroPuntoInline]
    fields = ('trabajador', 'obra', 'subetapa', 'comentario',
              'foto', 'ver_foto_grande', 'total_puntos', 'fecha_hora',
              'estado', 'revisado_por', 'revisado_en', 'comentario_revision', 'enviado_offline')
    actions = ['aprobar_seleccionados']

    @display(description='Reporte', ordering='pk')
    def reporte(self, obj):
        return f'#{obj.pk}'

    @display(description='Trabajador', ordering='trabajador__first_name')
    def trabajador_nombre(self, obj):
        return obj.nombre_trabajador

    @display(description='Subetapa', ordering='subetapa__nombre')
    def subetapa_nombre(self, obj):
        return obj.subetapa.nombre

    @display(description='Estado', ordering='estado', label={
        ReporteAvance.ESTADO_PENDIENTE: 'warning',
        ReporteAvance.ESTADO_APROBADO: 'success',
        ReporteAvance.ESTADO_OBSERVADO: 'danger',
    })
    def estado_label(self, obj):
        return obj.estado, obj.get_estado_display()

    @display(description='Foto')
    def ver_miniatura(self, obj):
        if obj.foto:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" width="48" height="48" '
                'style="object-fit:cover;border-radius:6px;" /></a>',
                obj.foto.url
            )
        return '-'

    @display(description='Vista previa de la foto')
    def ver_foto_grande(self, obj):
        if obj.foto:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" width="300" '
                'style="border-radius:8px;" /></a>',
                obj.foto.url
            )
        return 'Este reporte no tiene foto del avance.'

    @admin.action(description='Aprobar reportes seleccionados (solo pendientes)')
    def aprobar_seleccionados(self, request, queryset):
        # Mismo servicio que la app: el trabajador recibe el aviso de aprobación.
        pendientes = queryset.filter(estado=ReporteAvance.ESTADO_PENDIENTE).exclude(
            trabajador=request.user
        ).select_related('trabajador', 'obra', 'subetapa')
        n = 0
        for reporte in pendientes:
            revisar_reporte(reporte, request.user, 'aprobar')
            n += 1
        self.message_user(request, f'{n} reporte(s) aprobados; se avisó a cada trabajador.', messages.SUCCESS)


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
