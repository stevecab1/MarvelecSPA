# marvelec_app/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Obra, Subetapa, ReporteAvance, RegistroPunto


class ReporteAvanceForm(forms.ModelForm):
    """Formulario que llena el trabajador al llegar a la obra."""

    class Meta:
        model = ReporteAvance
        fields = ['obra', 'subetapa', 'foto_llegada', 'comentario']
        widgets = {
            'comentario': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Comentarios, consultas o novedades del día (opcional)'
            }),
            # 'capture' abre directamente la cámara del celular en vez del explorador de archivos.
            'foto_llegada': forms.ClearableFileInput(attrs={'capture': 'environment', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        # Se le pasa la obra asignada del perfil del trabajador para acotar las opciones.
        obra_asignada = kwargs.pop('obra_asignada', None)
        super().__init__(*args, **kwargs)

        if obra_asignada:
            # El trabajador normal solo puede reportar en SU obra.
            self.fields['obra'].queryset = Obra.objects.filter(pk=obra_asignada.pk)
            self.fields['obra'].initial = obra_asignada
            self.fields['subetapa'].queryset = Subetapa.objects.filter(obra=obra_asignada)
        else:
            # Supervisor/gerencia sin obra fija: puede elegir entre todas las obras activas.
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


class RegistroPuntoForm(forms.ModelForm):
    class Meta:
        model = RegistroPunto
        fields = ['tipo_punto', 'cantidad']
        widgets = {
            'cantidad': forms.NumberInput(attrs={'min': '0', 'placeholder': '0'}),
        }


# Formset: permite ingresar varias filas de puntos (red / fuerza / iluminación)
# asociadas a UN ReporteAvance, en la misma pantalla.
RegistroPuntoFormSet = inlineformset_factory(
    ReporteAvance,
    RegistroPunto,
    form=RegistroPuntoForm,
    fields=['tipo_punto', 'cantidad'],
    extra=3,
    can_delete=True,
)
