# marvelec_app/templatetags/marvelec_tags.py
from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icono(nombre, clase=''):
    """Ícono del sprite SVG (templates/partials/iconos.html)."""
    return format_html(
        '<svg class="icon {}" aria-hidden="true"><use href="#i-{}"></use></svg>', clase, nombre
    )


@register.filter
def iniciales(usuario):
    nombre = usuario.get_full_name() or usuario.username
    partes = nombre.split()
    return ''.join(p[0] for p in partes[:2]) if partes else '?'


@register.filter
def nombre_usuario(usuario):
    return usuario.get_full_name() or usuario.username


@register.simple_tag(takes_context=True)
def qs(context, **cambios):
    """Querystring actual con algunos parámetros reemplazados (p. ej. la página)."""
    params = context['request'].GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ''):
            params.pop(clave, None)
        else:
            params[clave] = valor
    codificado = params.urlencode()
    return f'?{codificado}' if codificado else '?'


@register.filter
def porcentaje(valor, maximo):
    try:
        return max(0, min(100, round(100 * float(valor) / float(maximo)))) if maximo else 0
    except (TypeError, ValueError):
        return 0
