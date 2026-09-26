# marvelec_app/views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Sum
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Obra, Subetapa, PerfilTrabajador, ReporteAvance, RegistroPunto
from .forms import ReporteAvanceForm, RegistroPuntoFormSet


# --- AUTENTICACIÓN ---

def login_usuario(request):
    if request.user.is_authenticated:
        return redirect('marvelec_app:panel')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('marvelec_app:panel')
        messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'registration/login.html')


def logout_usuario(request):
    logout(request)
    return redirect('marvelec_app:login')


def _get_perfil(user):
    """Devuelve el PerfilTrabajador del usuario, creándolo si por algún motivo no existe."""
    perfil, _ = PerfilTrabajador.objects.get_or_create(usuario=user)
    return perfil


@login_required
def dashboard_redirect(request):
    perfil = _get_perfil(request.user)
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return redirect('marvelec_app:panel_trabajador')
    return redirect('marvelec_app:panel_supervision')


# --- VISTA TRABAJADOR ---

@login_required
def dashboard_trabajador(request):
    perfil = _get_perfil(request.user)

    if request.method == 'POST':
        form = ReporteAvanceForm(request.POST, request.FILES, obra_asignada=perfil.obra_asignada)
        formset = RegistroPuntoFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                # Guardado atómico: si algo falla, no queda un reporte a medias.
                with transaction.atomic():
                    reporte = form.save(commit=False)
                    reporte.trabajador = request.user
                    reporte.full_clean(exclude=['total_puntos'])  # valida coherencia obra-subetapa
                    reporte.save()

                    formset.instance = reporte
                    formset.save()
                    reporte.calcular_total_puntos()

                # Notificar a supervisores/gerentes (fuera del atomic para no bloquear)
                try:
                    from .push import notificar_supervisores_de_obra
                    notificar_supervisores_de_obra(reporte)
                except Exception:
                    pass  # Si falla la notificación, el reporte ya se guardó bien.

                messages.success(request, 'Reporte de avance enviado correctamente.')
                return redirect('marvelec_app:panel_trabajador')
            except ValidationError as e:
                # Muestra el error de validación (ej. subetapa que no corresponde a la obra).
                for msg in e.messages:
                    messages.error(request, msg)
        else:
            messages.error(request, 'Revisa los datos del reporte: hay errores en el formulario.')
    else:
        form = ReporteAvanceForm(obra_asignada=perfil.obra_asignada)
        formset = RegistroPuntoFormSet()

    mis_reportes = ReporteAvance.objects.filter(trabajador=request.user).select_related(
        'obra', 'subetapa'
    ).prefetch_related('registros')[:15]

    context = {
        'perfil': perfil,
        'form': form,
        'formset': formset,
        'mis_reportes': mis_reportes,
    }
    return render(request, 'marvelec_app/dashboard_trabajador.html', context)


# --- VISTA SUPERVISOR / GERENCIA ---

@login_required
def dashboard_supervisor(request):
    perfil = _get_perfil(request.user)
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return redirect('marvelec_app:panel_trabajador')

    reportes = ReporteAvance.objects.select_related('trabajador', 'obra', 'subetapa').prefetch_related('registros')

    # Un supervisor solo ve su propia obra; gerencia ve todas.
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada:
        reportes = reportes.filter(obra=perfil.obra_asignada)

    # --- Filtros opcionales desde el panel ---
    obra_id = request.GET.get('obra')
    subetapa_id = request.GET.get('subetapa')
    trabajador_id = request.GET.get('trabajador')

    if obra_id:
        reportes = reportes.filter(obra_id=obra_id)
    if subetapa_id:
        reportes = reportes.filter(subetapa_id=subetapa_id)
    if trabajador_id:
        reportes = reportes.filter(trabajador_id=trabajador_id)

    total_puntos = reportes.aggregate(t=Sum('total_puntos'))['t'] or 0

    if perfil.rol == PerfilTrabajador.ROL_GERENCIA or not perfil.obra_asignada:
        obras_disponibles = Obra.objects.all()
    else:
        obras_disponibles = Obra.objects.filter(pk=perfil.obra_asignada_id)

    context = {
        'perfil': perfil,
        'reportes': reportes.order_by('-fecha_hora')[:200],
        'total_puntos': total_puntos,
        'obras_disponibles': obras_disponibles,
        'subetapas_disponibles': Subetapa.objects.filter(obra_id=obra_id) if obra_id else Subetapa.objects.none(),
    }
    return render(request, 'marvelec_app/dashboard_supervisor.html', context)


@login_required
def exportar_reportes_excel(request):
    """Exporta a Excel los reportes de avance visibles para el usuario (con los mismos filtros)."""
    import openpyxl
    from openpyxl.utils import get_column_letter

    perfil = _get_perfil(request.user)
    if perfil.rol == PerfilTrabajador.ROL_TRABAJADOR:
        return redirect('marvelec_app:panel_trabajador')

    reportes = ReporteAvance.objects.select_related('trabajador', 'obra', 'subetapa').prefetch_related('registros')
    if perfil.rol == PerfilTrabajador.ROL_SUPERVISOR and perfil.obra_asignada:
        reportes = reportes.filter(obra=perfil.obra_asignada)

    obra_id = request.GET.get('obra')
    subetapa_id = request.GET.get('subetapa')
    if obra_id:
        reportes = reportes.filter(obra_id=obra_id)
    if subetapa_id:
        reportes = reportes.filter(subetapa_id=subetapa_id)

    reportes = reportes.order_by('-fecha_hora')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reportes de Avance"

    headers = ['Fecha', 'Trabajador', 'Obra', 'Subetapa', 'Puntos Red', 'Puntos Fuerza',
               'Puntos Iluminación', 'Total Puntos', 'Comentario']
    ws.append(headers)

    for reporte in reportes:
        conteo = {tipo: 0 for tipo, _ in RegistroPunto.TIPO_CHOICES}
        for registro in reporte.registros.all():
            conteo[registro.tipo_punto] = conteo.get(registro.tipo_punto, 0) + registro.cantidad

        ws.append([
            reporte.fecha_hora.strftime('%d-%m-%Y %H:%M'),
            reporte.trabajador.get_full_name() or reporte.trabajador.username,
            reporte.obra.nombre,
            reporte.subetapa.nombre,
            conteo.get(RegistroPunto.TIPO_RED, 0),
            conteo.get(RegistroPunto.TIPO_FUERZA, 0),
            conteo.get(RegistroPunto.TIPO_ILUMINACION, 0),
            reporte.total_puntos,
            reporte.comentario,
        ])

    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 22

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="reportes_avance_marvelec.xlsx"'
    wb.save(response)
    return response
