from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models import Sum
from .models import Obra, Subetapa, PerfilTrabajador, ReporteAvance, RegistroPunto, SuscripcionPush


# ---------- OBRA + SUBETAPAS ----------

class SubetapaInline(admin.TabularInline):
    model = Subetapa
    extra = 1
    fields = ('nombre', 'descripcion')


class ObraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'fecha_inicio', 'activa', 'n_subetapas', 'total_puntos_obra')
    list_editable = ('activa',)
    list_filter = ('activa',)
    search_fields = ('nombre', 'direccion')
    inlines = [SubetapaInline]

    def n_subetapas(self, obj):
        return obj.subetapas.count()
    n_subetapas.short_description = 'Subetapas'

    def total_puntos_obra(self, obj):
        total = obj.reportes.aggregate(t=Sum('total_puntos'))['t'] or 0
        return total
    total_puntos_obra.short_description = 'Total puntos'


# ---------- SUBETAPA (vista directa) ----------

class SubetapaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'obra', 'descripcion', 'total_puntos_subetapa')
    list_filter = ('obra',)
    search_fields = ('nombre', 'obra__nombre')

    def total_puntos_subetapa(self, obj):
        total = obj.reportes.aggregate(t=Sum('total_puntos'))['t'] or 0
        return total
    total_puntos_subetapa.short_description = 'Total puntos'


# ---------- USUARIO + PERFIL ----------

class PerfilTrabajadorInline(admin.StackedInline):
    model = PerfilTrabajador
    can_delete = False
    verbose_name_plural = 'Perfil de Trabajador (Rol y Obra)'
    fields = ('rol', 'obra_asignada')
    max_num = 1
    min_num = 1
    extra = 1


class UserAdmin(BaseUserAdmin):
    inlines = (PerfilTrabajadorInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_rol', 'get_obra')

    def get_rol(self, obj):
        try:
            return obj.perfil.get_rol_display()
        except PerfilTrabajador.DoesNotExist:
            return "-"
    get_rol.short_description = 'Rol'

    def get_obra(self, obj):
        try:
            return obj.perfil.obra_asignada or "-"
        except PerfilTrabajador.DoesNotExist:
            return "-"
    get_obra.short_description = 'Obra Asignada'


class PerfilTrabajadorAdmin(admin.ModelAdmin):
    """Vista directa de perfiles, útil para asignar roles y obras en masa."""
    list_display = ('usuario', 'rol', 'obra_asignada')
    list_filter = ('rol', 'obra_asignada')
    list_editable = ('rol', 'obra_asignada')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name')


# ---------- REPORTE + PUNTOS ----------

class RegistroPuntoInline(admin.TabularInline):
    model = RegistroPunto
    extra = 1
    fields = ('tipo_punto', 'cantidad')


class ReporteAvanceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'trabajador', 'obra', 'subetapa', 'total_puntos', 'fecha_hora', 'ver_miniatura')
    readonly_fields = ('total_puntos', 'fecha_hora', 'ver_foto_grande')
    list_filter = ('obra', 'subetapa', 'fecha_hora', 'trabajador')
    search_fields = ('trabajador__username', 'obra__nombre', 'subetapa__nombre')
    date_hierarchy = 'fecha_hora'
    inlines = [RegistroPuntoInline]
    fields = ('trabajador', 'obra', 'subetapa', 'comentario',
              'foto_llegada', 'ver_foto_grande', 'total_puntos', 'fecha_hora')

    def ver_miniatura(self, obj):
        if obj.foto_llegada:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" width="48" height="48" '
                'style="object-fit:cover;border-radius:4px;" /></a>',
                obj.foto_llegada.url
            )
        return "Sin foto"
    ver_miniatura.short_description = 'Foto'

    def ver_foto_grande(self, obj):
        if obj.foto_llegada:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" width="300" '
                'style="border-radius:8px;" /></a>',
                obj.foto_llegada.url
            )
        return "Este reporte no tiene foto de llegada."
    ver_foto_grande.short_description = 'Vista previa de la foto'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(Obra, ObraAdmin)
admin.site.register(Subetapa, SubetapaAdmin)
admin.site.register(PerfilTrabajador, PerfilTrabajadorAdmin)
admin.site.register(ReporteAvance, ReporteAvanceAdmin)
admin.site.register(SuscripcionPush)

admin.site.site_header = "MARVELEC SPA - Administración"
admin.site.site_title = "MARVELEC SPA"
admin.site.index_title = "Panel de Reporte y Seguimiento de Avance"
