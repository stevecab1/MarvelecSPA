# marvelec_app/forms.py
from django import forms
from .models import Obra, Subetapa, ReporteAvance, RegistroPunto


class ReporteAvanceForm(forms.ModelForm):
    """Formulario de reporte de avance: subetapa, foto opcional y comentario."""

    class Meta:
        model = ReporteAvance
        fields = ['obra', 'subetapa', 'foto', 'comentario']
        widgets = {
            'comentario': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Comentarios, consultas o novedades del día (opcional)'
            }),
            # 'capture' abre directamente la cámara del celular en vez del explorador de archivos.
            'foto': forms.FileInput(attrs={'capture': 'environment', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        # Se le pasa la obra asignada del perfil del trabajador para acotar las opciones.
        obra_asignada = kwargs.pop('obra_asignada', None)
        super().__init__(*args, **kwargs)
        self.fields['obra'].empty_label = 'Selecciona la obra'
        self.fields['subetapa'].empty_label = 'Selecciona la subetapa'

        if obra_asignada:
            # El trabajador normal solo puede reportar en SU obra.
            self.fields['obra'].queryset = Obra.objects.filter(pk=obra_asignada.pk)
            self.fields['obra'].initial = obra_asignada
            self.fields['subetapa'].queryset = Subetapa.objects.filter(obra=obra_asignada)
        else:
            # Sin obra fija: puede elegir entre todas las obras activas.
            self.fields['obra'].queryset = Obra.objects.filter(activa=True)
            self.fields['subetapa'].queryset = Subetapa.objects.none()

        # Si ya viene una obra seleccionada (POST o instancia), acotar subetapas a esa obra.
        obra_id = None
        if self.data.get('obra'):
            obra_id = self.data.get('obra')
        elif self.instance and self.instance.pk:
            obra_id = self.instance.obra_id

        if obra_id:
            self.fields['subetapa'].queryset = Subetapa.objects.filter(obra_id=obra_id)


class PuntosForm(forms.Form):
    """Cantidad de puntos ejecutados por tipo (una fila fija por tipo de punto)."""

    def __init__(self, *args, reporte=None, **kwargs):
        super().__init__(*args, **kwargs)
        actuales = reporte.puntos_por_tipo() if reporte else {}
        for tipo, etiqueta in RegistroPunto.TIPO_CHOICES:
            self.fields[tipo] = forms.IntegerField(
                label=etiqueta, min_value=0, max_value=9999, required=False,
                initial=actuales.get(tipo, 0),
                widget=forms.NumberInput(attrs={'inputmode': 'numeric', 'min': 0, 'class': 'stepper-input'}),
            )

    def cantidades(self):
        return {tipo: self.cleaned_data.get(tipo) or 0 for tipo, _ in RegistroPunto.TIPO_CHOICES}

    def filas(self):
        """Para la plantilla: [(tipo, campo_bound), ...]."""
        return [(tipo, self[tipo]) for tipo, _ in RegistroPunto.TIPO_CHOICES]

    def guardar(self, reporte):
        """Reemplaza los registros del reporte por las cantidades ingresadas (omite los 0)."""
        reporte.registros.all().delete()
        RegistroPunto.objects.bulk_create([
            RegistroPunto(reporte=reporte, tipo_punto=tipo, cantidad=cantidad)
            for tipo, cantidad in self.cantidades().items() if cantidad
        ])
        # bulk_create no dispara señales: recalcular el total explícitamente.
        reporte.calcular_total_puntos()


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
