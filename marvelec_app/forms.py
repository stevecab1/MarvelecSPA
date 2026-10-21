# marvelec_app/forms.py
from django import forms

from . import etapas
from .models import Obra, Punto, Rack, ReporteAvance, TipoIncidencia
from .servicios import leer_coordenada, resolver_codigos

AYUDA_CODIGOS = 'DT 1-2-3-17, VD 9'


def obras_permitidas(obra_asignada):
    if obra_asignada:
        return Obra.objects.filter(pk=obra_asignada.pk)
    return Obra.objects.filter(activa=True)


class SeleccionPuntosMixin:
    """
    Puntos elegidos en el selector (ids) + los escritos como texto rápido ("DT 1-2-3").
    Tras validar deja `self.puntos` (lista de Punto) y `self.avisos` (códigos que no existen).
    """

    def _configurar_puntos(self, obras):
        self.fields['rack'].queryset = Rack.objects.filter(obra__in=obras).select_related('obra')
        self.fields['rack'].empty_label = 'Selecciona el rack'
        self.fields['puntos'].queryset = Punto.objects.filter(rack__obra__in=obras)
        self.puntos, self.avisos = [], []

    def _resolver_puntos(self, cleaned):
        rack = cleaned.get('rack')
        if not rack:
            return
        elegidos = [p for p in cleaned.get('puntos') or [] if p.rack_id == rack.pk]
        escritos, errores = resolver_codigos(rack, cleaned.get('codigos', ''))
        unicos = {p.pk: p for p in [*elegidos, *escritos]}
        self.puntos = list(Punto.objects.filter(pk__in=unicos).select_related('tipo', 'rack'))
        self.avisos = [{'codigo': '', 'etapa': '', 'motivo': e} for e in errores]
        if not self.puntos:
            mensaje = 'Selecciona al menos un punto o escribe sus códigos.'
            self.add_error(None, ' '.join([mensaje, *errores]) if errores else mensaje)


class ReporteAvanceForm(SeleccionPuntosMixin, forms.ModelForm):
    """Reporte de avance: rack, etapas completadas, puntos, foto opcional y comentario."""
    etapas = forms.MultipleChoiceField(
        choices=etapas.CHOICES, widget=forms.CheckboxSelectMultiple,
        error_messages={'required': 'Elige al menos una etapa.'},
    )
    puntos = forms.ModelMultipleChoiceField(queryset=Punto.objects.none(), required=False,
                                            widget=forms.MultipleHiddenInput)
    codigos = forms.CharField(
        required=False, max_length=4000, label='Escribir códigos',
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': AYUDA_CODIGOS, 'autocapitalize': 'characters'}),
    )

    class Meta:
        model = ReporteAvance
        fields = ['rack', 'foto', 'comentario']
        widgets = {
            'comentario': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Comentarios, consultas o novedades del día (opcional)'
            }),
            # 'capture' abre directamente la cámara del celular en vez del explorador de archivos.
            'foto': forms.FileInput(attrs={'capture': 'environment', 'accept': 'image/*'}),
        }

    def __init__(self, *args, obra_asignada=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._configurar_puntos(obras_permitidas(obra_asignada))
        if self.instance.pk and not self.is_bound:
            self.initial['etapas'] = etapas.ordenar(self.instance.avances.values_list('etapa', flat=True))
            self.initial['puntos'] = list(self.instance.avances.values_list('punto_id', flat=True).distinct())

    def clean(self):
        cleaned = super().clean()
        self._resolver_puntos(cleaned)
        rack = cleaned.get('rack')
        if rack:
            self.instance.obra = rack.obra
        return cleaned


class IncidenciaForm(SeleccionPuntosMixin, forms.Form):
    rack = forms.ModelChoiceField(queryset=Rack.objects.none())
    puntos = forms.ModelMultipleChoiceField(queryset=Punto.objects.none(), required=False,
                                            widget=forms.MultipleHiddenInput)
    codigos = forms.CharField(
        required=False, max_length=2000, label='Escribir códigos',
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': AYUDA_CODIGOS, 'autocapitalize': 'characters'}),
    )
    tipo = forms.ModelChoiceField(queryset=TipoIncidencia.objects.filter(activo=True), empty_label='¿Qué pasó?',
                                  error_messages={'required': 'Elige el tipo de incidencia.'})
    foto = forms.ImageField(required=False, widget=forms.FileInput(attrs={'capture': 'environment', 'accept': 'image/*'}))
    comentario = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={
        'rows': 2, 'placeholder': 'Detalle o ubicación (opcional)'}))
    latitud = forms.CharField(required=False, widget=forms.HiddenInput)
    longitud = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, obra_asignada=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._configurar_puntos(obras_permitidas(obra_asignada))

    def clean(self):
        cleaned = super().clean()
        self._resolver_puntos(cleaned)
        cleaned['latitud'] = leer_coordenada(cleaned.get('latitud'), 90)
        cleaned['longitud'] = leer_coordenada(cleaned.get('longitud'), 180)
        return cleaned


class AsistenciaForm(forms.Form):
    obra = forms.ModelChoiceField(queryset=Obra.objects.none(), empty_label='Selecciona la obra')
    foto = forms.ImageField(
        widget=forms.FileInput(attrs={'capture': 'environment', 'accept': 'image/*'}),
        error_messages={'required': 'La foto del lugar es obligatoria para marcar tu llegada.'},
    )
    latitud = forms.CharField(required=False, widget=forms.HiddenInput)
    longitud = forms.CharField(required=False, widget=forms.HiddenInput)
    precision = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, obra_asignada=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['obra'].queryset = obras_permitidas(obra_asignada)
        if obra_asignada:
            self.fields['obra'].initial = obra_asignada

    def clean(self):
        cleaned = super().clean()
        cleaned['latitud'] = leer_coordenada(cleaned.get('latitud'), 90)
        cleaned['longitud'] = leer_coordenada(cleaned.get('longitud'), 180)
        return cleaned


class RevisionForm(forms.Form):
    ACCIONES = [('aprobar', 'Aprobar'), ('observar', 'Observar')]
    accion = forms.ChoiceField(choices=ACCIONES)
    comentario = forms.CharField(
        required=False, max_length=1000,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Explica qué debe corregir el trabajador'}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get('accion') == 'observar' and not (datos.get('comentario') or '').strip():
            raise forms.ValidationError('Para observar un reporte debes indicar qué hay que corregir.')
        return datos


class RevisionAsistenciaForm(forms.Form):
    accion = forms.ChoiceField(choices=[('confirmar', 'Confirmar'), ('rechazar', 'Rechazar')])
    motivo = forms.CharField(required=False, max_length=500)

    def clean(self):
        datos = super().clean()
        if datos.get('accion') == 'rechazar' and not (datos.get('motivo') or '').strip():
            raise forms.ValidationError('Indica el motivo del rechazo.')
        return datos


class LiberarIncidenciaForm(forms.Form):
    comentario = forms.CharField(
        required=False, max_length=1000,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': '¿Cómo se resolvió? (opcional)'}),
    )


class CargarPuntosForm(forms.Form):
    obra = forms.ModelChoiceField(queryset=Obra.objects.none(), empty_label='Selecciona la obra')
    archivo = forms.FileField(
        label='Planilla Excel (.xlsx)',
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),
    )

    def __init__(self, *args, obras=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['obra'].queryset = obras if obras is not None else Obra.objects.none()
        if obras is not None and obras.count() == 1:
            self.fields['obra'].initial = obras.first()

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not archivo.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Sube el archivo en formato .xlsx (Excel).')
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError('El archivo supera los 10 MB.')
        return archivo
