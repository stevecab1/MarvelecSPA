# marvelec_app/etapas.py
"""
Etapas por las que pasa cada punto de cableado estructurado, en orden.
Fuente: "PROCESO EXPLICADO.txt" y "TIEMPOS DE LOS PROCESOS.txt" (carpeta Contexto Proyecto).

Bajada y peinado se hacen en paralelo (una cuadrilla en terreno, otra en el rack), igual que
los dos ponchados; la identificación exige ambos extremos listos y la certificación ambos ponchados.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Etapa:
    clave: str
    nombre: str
    corto: str
    requiere: tuple
    # Rendimiento estándar: puntos por persona en una jornada.
    estandar: float


ETAPAS = (
    Etapa('tendido', 'Tendido', 'Tendido', (), round(80 / 3, 1)),
    Etapa('bajada', 'Bajada de puntos', 'Bajada', ('tendido',), round(50 / 3, 1)),
    Etapa('peinado', 'Peinado de rack', 'Peinado', ('tendido',), round(350 / 2 / 3, 1)),
    Etapa('identificacion', 'Identificación (tonos)', 'Identif.', ('bajada', 'peinado'), 50.0),
    Etapa('ponchado_rack', 'Ponchado en rack', 'P. rack', ('identificacion',), 70.0),
    Etapa('ponchado_usuario', 'Ponchado en usuario', 'P. usuario', ('identificacion',), 60.0),
    Etapa('certificacion', 'Certificación', 'Certif.', ('ponchado_rack', 'ponchado_usuario'), 65.0),
)

POR_CLAVE = {e.clave: e for e in ETAPAS}
CLAVES = tuple(e.clave for e in ETAPAS)
CHOICES = [(e.clave, e.nombre) for e in ETAPAS]
ORDEN = {e.clave: i for i, e in enumerate(ETAPAS)}
FINAL = 'certificacion'


def ordenar(claves):
    """Claves válidas, sin repetir, en el orden del proceso."""
    return sorted({c for c in claves if c in POR_CLAVE}, key=ORDEN.__getitem__)


def nombre(clave):
    etapa = POR_CLAVE.get(clave)
    return etapa.nombre if etapa else clave


def faltantes(clave, hechas):
    """Requisitos de `clave` que aún no están en `hechas`."""
    return [r for r in POR_CLAVE[clave].requiere if r not in hechas]


def para_js():
    """Datos de las etapas para el navegador (selector de puntos, también sin señal)."""
    return [{'clave': e.clave, 'nombre': e.nombre, 'corto': e.corto, 'requiere': list(e.requiere)} for e in ETAPAS]
