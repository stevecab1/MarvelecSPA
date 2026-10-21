# marvelec_app/servicios.py
"""
Reglas de negocio compartidas por los formularios web y las APIs que usa la app del celular
(también para lo que se guardó sin señal y se envía después).
"""
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import etapas
from .models import Asistencia, AvancePunto, Incidencia, Punto, ReporteAvance
from .notificaciones import (
    notificar_asistencia_rechazada, notificar_incidencias, notificar_liberacion, notificar_nuevo_reporte,
    notificar_revision,
)

# Un registro guardado sin señal puede llegar hasta 7 días después.
MAX_ATRASO_OFFLINE = timedelta(days=7)


# =========================================================
# Lectura de datos que vienen del celular
# =========================================================

def leer_uuid(valor):
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def leer_fecha_cliente(valor):
    """
    Hora en que el trabajador hizo el registro en su celular. Se acepta sólo si es razonable
    (no futura, no más antigua que MAX_ATRASO_OFFLINE); si no, se usa la hora actual.
    """
    ahora = timezone.now()
    if not valor:
        return ahora
    try:
        fecha = datetime.fromisoformat(str(valor))
    except ValueError:
        return ahora
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    if fecha > ahora + timedelta(minutes=5) or fecha < ahora - MAX_ATRASO_OFFLINE:
        return ahora
    return min(fecha, ahora)


def leer_coordenada(valor, limite):
    try:
        numero = Decimal(str(valor)).quantize(Decimal('0.000001'))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return numero if -limite <= numero <= limite else None


# =========================================================
# Códigos rápidos: "DT 1-2-3, 7 a 12; VD-015"
# =========================================================

# Entre dos números, estas palabras indican un rango. El guion NO es rango: en WhatsApp
# los trabajadores escriben "Dt 1-2-3-4" para listar puntos sueltos.
MARCADORES_RANGO = {'A', 'AL', 'HASTA', '..'}
CONECTORES = {'Y', 'E'}
MAX_RANGO = 500


def parsear_codigos(texto):
    """Devuelve ({(sigla, numero), ...}, [errores])."""
    tokens = re.findall(r'[A-Za-zÑñ]+|\d+|\.\.', texto or '')
    pares, errores = set(), []
    sigla = None
    i = 0
    while i < len(tokens):
        token = tokens[i].upper()
        if token.isdigit():
            if sigla is None:
                errores.append(f'Falta el tipo antes de "{token}" (por ejemplo: DT {token}).')
                i += 1
                continue
            numero = int(token)
            es_rango = (
                i + 2 < len(tokens) and tokens[i + 1].upper() in MARCADORES_RANGO and tokens[i + 2].isdigit()
            )
            if es_rango:
                desde, hasta = sorted((numero, int(tokens[i + 2])))
                if hasta - desde > MAX_RANGO:
                    errores.append(f'El rango {sigla} {desde} a {hasta} es demasiado grande.')
                else:
                    pares.update((sigla, n) for n in range(desde, hasta + 1))
                i += 3
                continue
            pares.add((sigla, numero))
        elif token not in MARCADORES_RANGO and token not in CONECTORES:
            sigla = token
        i += 1
    return pares, errores


def resolver_codigos(rack, texto):
    """Convierte el texto en puntos del rack. Devuelve ([Punto], [errores])."""
    pares, errores = parsear_codigos(texto)
    if not pares:
        return [], errores
    existentes = {
        (p.tipo.sigla, p.numero): p
        for p in Punto.objects.filter(rack=rack, tipo__sigla__in={s for s, _ in pares}).select_related('tipo')
    }
    faltan = sorted(pares - existentes.keys())
    if faltan:
        lista = ', '.join(f'{s}-{n:03d}' for s, n in faltan[:12])
        extra = f' y {len(faltan) - 12} más' if len(faltan) > 12 else ''
        errores.append(f'No existen en el rack {rack.nombre}: {lista}{extra}.')
    return [existentes[k] for k in sorted(pares) if k in existentes], errores


# =========================================================
# Avance por punto y etapa
# =========================================================

def _omitido(punto, etapa, motivo):
    return {'codigo': punto.codigo if punto else '', 'etapa': etapa, 'motivo': motivo}


def validar_avances(puntos, claves, excluir_reporte=None):
    """
    Revisa cada (punto, etapa) contra lo ya registrado.
    Devuelve (validos: [(Punto, clave)], omitidos: [dict]).
    Un requisito previo cuenta si ya estaba registrado o si viene en este mismo reporte.
    """
    claves = etapas.ordenar(claves)
    ids = [p.pk for p in puntos]

    hechas = defaultdict(dict)
    registrados = AvancePunto.objects.filter(punto_id__in=ids).select_related('reporte__trabajador')
    if excluir_reporte is not None:
        registrados = registrados.exclude(reporte=excluir_reporte)
    for avance in registrados:
        hechas[avance.punto_id][avance.etapa] = avance

    bloqueos = {}
    for inc in Incidencia.objects.filter(punto_id__in=ids, estado=Incidencia.ESTADO_ABIERTA).select_related('tipo'):
        bloqueos.setdefault(inc.punto_id, inc.tipo.nombre)

    validos, omitidos = [], []
    for punto in sorted(puntos, key=lambda p: (p.tipo.sigla, p.numero)):
        if punto.pk in bloqueos:
            omitidos.append(_omitido(punto, '', f'bloqueado por incidencia "{bloqueos[punto.pk]}"'))
            continue
        completadas = set(hechas[punto.pk])
        for clave in claves:
            previo = hechas[punto.pk].get(clave)
            if previo:
                fecha = timezone.localtime(previo.reporte.fecha_hora)
                omitidos.append(_omitido(
                    punto, clave,
                    f'{etapas.nombre(clave).lower()} ya registrada por {previo.reporte.nombre_trabajador} '
                    f'el {fecha:%d-%m}',
                ))
                continue
            faltan = etapas.faltantes(clave, completadas)
            if faltan:
                omitidos.append(_omitido(
                    punto, clave, 'falta ' + ' y '.join(etapas.nombre(f).lower() for f in faltan),
                ))
                continue
            validos.append((punto, clave))
            completadas.add(clave)
    return validos, omitidos


def _sin_validos(omitidos):
    detalle = [f"{o['codigo']}: {o['motivo']}" if o['codigo'] else o['motivo'] for o in omitidos[:8]]
    return ValidationError(['No se registró ningún avance.'] + detalle)


def _guardar_avances(reporte, validos):
    AvancePunto.objects.bulk_create([AvancePunto(reporte=reporte, punto=p, etapa=e) for p, e in validos])
    # bulk_create no dispara señales: recalcular el total explícitamente.
    reporte.calcular_total_puntos()


def crear_reporte(usuario, form, uuid_cliente=None, fecha_cliente=None, offline=False):
    """
    Guarda un reporte de avance de forma atómica y notifica a los supervisores.
    Registra los pares punto-etapa válidos y guarda los demás como omitidos (con su motivo).
    Idempotente: si ya existe un reporte con el mismo uuid_cliente, lo devuelve sin duplicarlo.
    Devuelve (reporte, creado).
    """
    if uuid_cliente:
        existente = ReporteAvance.objects.filter(uuid_cliente=uuid_cliente, trabajador=usuario).first()
        if existente:
            return existente, False

    validos, omitidos = validar_avances(form.puntos, form.cleaned_data['etapas'])
    omitidos = form.avisos + omitidos
    if not validos:
        raise _sin_validos(omitidos)

    try:
        with transaction.atomic():
            reporte = form.save(commit=False)
            reporte.trabajador = usuario
            reporte.fecha_hora = leer_fecha_cliente(fecha_cliente)
            reporte.uuid_cliente = uuid_cliente
            reporte.enviado_offline = offline
            reporte.omitidos = omitidos
            reporte.full_clean(exclude=['total_puntos', 'omitidos'])
            reporte.save()
            _guardar_avances(reporte, validos)
    except IntegrityError:
        # Dos reintentos simultáneos del mismo envío: gana el primero.
        existente = uuid_cliente and ReporteAvance.objects.filter(uuid_cliente=uuid_cliente, trabajador=usuario).first()
        if existente:
            return existente, False
        raise ValidationError('Otra persona registró estos puntos al mismo tiempo. Vuelve a intentarlo.')

    notificar_nuevo_reporte(reporte)
    return reporte, True


def _dependientes(clave):
    return [e.clave for e in etapas.ETAPAS if clave in e.requiere]


def corregir_reporte(reporte, form):
    """El trabajador corrige un reporte observado: se rehacen sus avances y vuelve a revisión."""
    nuevos, omitidos = validar_avances(form.puntos, form.cleaned_data['etapas'], excluir_reporte=reporte)
    omitidos = form.avisos + omitidos
    if not nuevos:
        raise _sin_validos(omitidos)

    # No se puede quitar una etapa de la que ya dependen avances de otros reportes.
    nuevos_pares = {(p.pk, e) for p, e in nuevos}
    for avance in reporte.avances.select_related('punto__tipo'):
        if (avance.punto_id, avance.etapa) in nuevos_pares:
            continue
        dependiente = AvancePunto.objects.filter(
            punto_id=avance.punto_id, etapa__in=_dependientes(avance.etapa)
        ).exclude(reporte=reporte).first()
        if dependiente:
            raise ValidationError(
                f'No se puede quitar {avance.get_etapa_display().lower()} de {avance.punto.codigo}: '
                f'ya tiene {dependiente.get_etapa_display().lower()} registrada.'
            )

    with transaction.atomic():
        reporte = form.save(commit=False)
        reporte.full_clean(exclude=['total_puntos', 'omitidos'])
        reporte.estado = ReporteAvance.ESTADO_PENDIENTE
        reporte.omitidos = omitidos
        reporte.save()
        reporte.avances.all().delete()
        _guardar_avances(reporte, nuevos)
    notificar_nuevo_reporte(reporte, corregido=True)
    return reporte


def revisar_reporte(reporte, revisor, accion, comentario=''):
    """Aprueba u observa un reporte y avisa al trabajador."""
    if accion == 'aprobar':
        reporte.aprobar(revisor)
    else:
        reporte.observar(revisor, comentario.strip())
    notificar_revision(reporte)
    return reporte


# =========================================================
# Incidencias
# =========================================================

def registrar_incidencia(usuario, puntos, tipo, foto=None, comentario='', latitud=None, longitud=None,
                         uuid_cliente=None, fecha_cliente=None, offline=False):
    """
    Crea una incidencia por punto (el punto queda bloqueado) y avisa a los supervisores.
    Devuelve (incidencias, omitidos, creadas). Idempotente por uuid_cliente.
    """
    if uuid_cliente:
        existentes = list(Incidencia.objects.filter(uuid_cliente=uuid_cliente, reportada_por=usuario))
        if existentes:
            return existentes, [], False

    ya_abiertas = set(Incidencia.objects.filter(
        punto__in=puntos, tipo=tipo, estado=Incidencia.ESTADO_ABIERTA
    ).values_list('punto_id', flat=True))
    creada = leer_fecha_cliente(fecha_cliente)
    nuevas, omitidos = [], []

    with transaction.atomic():
        for punto in puntos:
            if punto.pk in ya_abiertas:
                omitidos.append(f'{punto.codigo}: ya tiene una incidencia abierta de este tipo')
                continue
            incidencia = Incidencia(
                punto=punto, tipo=tipo, reportada_por=usuario, creada=creada, comentario=comentario.strip(),
                latitud=latitud, longitud=longitud, uuid_cliente=uuid_cliente, enviado_offline=offline,
            )
            if foto and not nuevas:
                incidencia.foto = foto
            elif nuevas and nuevas[0].foto:
                incidencia.foto = nuevas[0].foto.name  # la misma foto respalda a todos los puntos
            incidencia.save()
            nuevas.append(incidencia)

    if not nuevas:
        raise ValidationError(omitidos or 'No se registró ninguna incidencia.')
    notificar_incidencias(nuevas)
    return nuevas, omitidos, True


def liberar_incidencia(incidencia, usuario, comentario=''):
    """El supervisor marca resuelta la incidencia: el punto puede seguir avanzando."""
    if not incidencia.abierta:
        return incidencia
    incidencia.estado = Incidencia.ESTADO_LIBERADA
    incidencia.liberada_por = usuario
    incidencia.liberada_en = timezone.now()
    incidencia.comentario_liberacion = comentario.strip()
    incidencia.save(update_fields=['estado', 'liberada_por', 'liberada_en', 'comentario_liberacion'])
    notificar_liberacion(incidencia)
    return incidencia


# =========================================================
# Asistencia
# =========================================================

def marcar_asistencia(usuario, obra, foto, latitud=None, longitud=None, precision=None,
                      uuid_cliente=None, fecha_cliente=None, offline=False):
    """
    Registra la llegada del día. Una por día; si la del día fue rechazada, se puede volver a marcar.
    Devuelve (asistencia, creada).
    """
    if uuid_cliente:
        existente = Asistencia.objects.filter(uuid_cliente=uuid_cliente, trabajador=usuario).first()
        if existente:
            return existente, False

    hora = leer_fecha_cliente(fecha_cliente)
    fecha = timezone.localdate(hora)
    previa = Asistencia.objects.filter(trabajador=usuario, fecha=fecha).first()
    if previa and previa.estado != Asistencia.ESTADO_RECHAZADA:
        raise ValidationError(
            f'Ya marcaste tu llegada el {fecha:%d-%m} a las {timezone.localtime(previa.hora):%H:%M}.'
        )

    asistencia = previa or Asistencia(trabajador=usuario, fecha=fecha)
    asistencia.obra = obra
    asistencia.hora = hora
    asistencia.foto = foto
    asistencia.latitud, asistencia.longitud, asistencia.precision = latitud, longitud, precision
    asistencia.estado = Asistencia.ESTADO_PENDIENTE
    asistencia.revisado_por = None
    asistencia.revisado_en = None
    asistencia.motivo_rechazo = ''
    asistencia.uuid_cliente = uuid_cliente
    asistencia.enviado_offline = offline
    try:
        with transaction.atomic():
            asistencia.save()
    except IntegrityError:
        existente = uuid_cliente and Asistencia.objects.filter(uuid_cliente=uuid_cliente).first()
        if existente:
            return existente, False
        raise ValidationError('Ya marcaste tu llegada hoy.')
    return asistencia, True


def revisar_asistencia(asistencia, revisor, accion, motivo=''):
    """Confirma o rechaza una marca de llegada. Al rechazar se avisa al trabajador."""
    if accion == 'rechazar' and not motivo.strip():
        raise ValidationError('Indica el motivo del rechazo.')
    asistencia.estado = Asistencia.ESTADO_CONFIRMADA if accion == 'confirmar' else Asistencia.ESTADO_RECHAZADA
    asistencia.revisado_por = revisor
    asistencia.revisado_en = timezone.now()
    asistencia.motivo_rechazo = motivo.strip() if accion == 'rechazar' else ''
    asistencia.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'motivo_rechazo'])
    if asistencia.estado == Asistencia.ESTADO_RECHAZADA:
        notificar_asistencia_rechazada(asistencia)
    return asistencia
