"""Validacion: lo que el .dtsx declara y no debe incumplirse.

  - validar_encabezados: el Excel Source mapea columnas POR NOMBRE; si falta
    una de las 8 el componente falla (error de validacion del Data Flow).
  - validar_esquema_destino: las columnas del OLE DB Destination existen en
    la tabla real y caben los anchos del Data Conversion.
  - validar_anchos_destino: ningun valor excede el ancho REAL de la columna
    (el destino falla con truncation = FailComponent).
"""

from __future__ import annotations

from mappings import COLUMNAS, TEXTO
from exceptions import ValidacionError

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}
_TIPOS_NUMERICOS = {"int", "decimal", "numeric"}


def validar_encabezados(encabezados: list[str]) -> dict[str, int]:
    """{columna del Excel: posicion}. Falla si falta alguna columna mapeada."""
    posiciones = {}
    for i, nombre in enumerate(encabezados):
        posiciones.setdefault(nombre, i)  # una columna repetida: manda la primera
    faltan = [c.origen for c in COLUMNAS if c.origen not in posiciones]
    if faltan:
        raise ValidacionError(
            f"Al Excel le faltan columnas que usa el Data Flow: {faltan}. Encabezados encontrados: {encabezados}"
        )
    return {c.origen: posiciones[c.origen] for c in COLUMNAS}


def validar_esquema_destino(esquema: dict[str, tuple[str, int | None]]) -> None:
    """'esquema' = {columna: (tipo, largo)} de la tabla destino."""
    problemas = []
    for col in COLUMNAS:
        if col.destino not in esquema:
            problemas.append(f"no existe la columna [{col.destino}]")
            continue
        tipo, _ = esquema[col.destino]
        if col.tipo == TEXTO:
            # Si el destino es mas angosto que el Data Conversion, el .dtsx solo falla cuando
            # un valor no cabe: lo revisa validar_anchos_destino, por valor.
            if tipo not in _TIPOS_TEXTO:
                problemas.append(f"[{col.destino}] deberia ser texto y es {tipo}")
        elif tipo not in _TIPOS_NUMERICOS:
            # El .dtsx la tenia int; el loader la pasa a decimal(10,2) (scripts_sql/ajustes) dentro de la transaccion.
            problemas.append(f"[{col.destino}] deberia ser numerica y es {tipo}")
    if problemas:
        raise ValidacionError("La tabla destino no coincide con el .dtsx: " + "; ".join(problemas))


def validar_anchos_destino(filas: list[tuple], esquema: dict[str, tuple[str, int | None]]) -> None:
    """Ningun texto excede el ancho real de la columna destino."""
    excedidos = []
    for j, col in enumerate(COLUMNAS):
        if col.tipo != TEXTO:
            continue
        _, largo = esquema[col.destino]
        if largo in (None, -1):
            continue
        maximo = max((len(f[j]) for f in filas if f[j] is not None), default=0)
        if maximo > largo:
            excedidos.append(f"[{col.destino}]: valor de {maximo} caracteres en una columna de {largo}")
    if excedidos:
        raise ValidacionError("Valores que no caben en la tabla destino: " + "; ".join(excedidos))
