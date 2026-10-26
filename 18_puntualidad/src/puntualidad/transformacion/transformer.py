"""Transformacion: el componente 'Data Conversion' del Data Flow TBL_SLA_CHILE.

  wstr(255)  -> str(largo, cp1252)   Tipologia, Dia/Hora, Condicion, Estado,
                                     Linea de Negocio, Motivo de contacto, Subtipologia
  r8         -> numeric(10,2)        SLA Real
Decision del usuario (2026-10-26): [SLA] se conserva decimal(10,2). El .dtsx insertaba ese
numeric(10,2) en una columna int y OLE DB lo redondeaba (los 6 valores 13,5 del Excel
quedaron en 14 en TBL_SLA); ahora TBL_SLA.SLA es decimal(10,2) y el valor real se conserva.

Todos los componentes tienen errorRowDisposition = truncationRowDisposition =
FailComponent: un valor mas ancho que la columna convertida, o un numero que no
convierte, detiene el Data Flow (ValidacionError).

Sin recorte: ACE no recorta espacios, y TBL_SLA tiene 'Solicitud Comercial '
con el espacio final.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from exceptions import ValidacionError
from logging_setup import NOMBRE_LOGGER
from mappings import (
    CODIFICACION_DESTINO,
    COLUMNAS,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    TEXTO,
    ColumnaSpec,
)

logger = logging.getLogger(NOMBRE_LOGGER)

_CENTESIMA = Decimal(1).scaleb(-NUMERIC_SCALE)
_MAXIMO = Decimal(10) ** (NUMERIC_PRECISION - NUMERIC_SCALE)


def convertir_texto(valor, col: ColumnaSpec, fila: int) -> str | None:
    """wstr -> str(largo, cp1252). NULL se mantiene NULL."""
    if valor is None:
        return None
    texto = valor if isinstance(valor, str) else str(valor)
    if len(texto) > col.largo:
        raise ValidacionError(
            f"Fila {fila}, columna '{col.origen}': el valor de {len(texto)} caracteres no cabe en str({col.largo}) "
            f"(Data Conversion, truncationRowDisposition = FailComponent): {texto[:60]!r}"
        )
    # DT_WSTR -> DT_STR cp1252: lo que no existe en la code page pasa a '?'
    convertido = texto.encode(CODIFICACION_DESTINO, errors="replace").decode(CODIFICACION_DESTINO)
    if convertido != texto:
        logger.warning("Fila %s, columna '%s': caracteres fuera de %s pasan a '?': %r", fila, col.origen, CODIFICACION_DESTINO, texto)
    return convertido


def convertir_numero(valor, col: ColumnaSpec, fila: int) -> Decimal | None:
    """r8 -> numeric(10,2) (redondeo half-up a 2 decimales, como el Data Conversion)."""
    if valor is None:
        return None
    try:
        decimal = Decimal(repr(float(valor)))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValidacionError(
            f"Fila {fila}, columna '{col.origen}': {valor!r} no se puede convertir a numeric({NUMERIC_PRECISION},{NUMERIC_SCALE}) "
            "(Data Conversion, errorRowDisposition = FailComponent)."
        ) from exc
    numerico = decimal.quantize(_CENTESIMA, rounding=ROUND_HALF_UP)
    if abs(numerico) >= _MAXIMO:
        raise ValidacionError(f"Fila {fila}, columna '{col.origen}': {valor!r} excede numeric({NUMERIC_PRECISION},{NUMERIC_SCALE}).")
    return numerico


def transformar(filas: list[tuple], posiciones: dict[str, int]) -> list[tuple]:
    """Filas del Excel -> tuplas en el orden de mappings.COLUMNAS (las 8
    columnas que carga el OLE DB Destination)."""
    salida = []
    con_decimales = 0
    for n, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        valores = []
        for col in COLUMNAS:
            celda = fila[posiciones[col.origen]] if posiciones[col.origen] < len(fila) else None
            if col.tipo == TEXTO:
                valores.append(convertir_texto(celda, col, n))
            else:
                valor = convertir_numero(celda, col, n)
                if valor is not None and valor != valor.to_integral_value():
                    con_decimales += 1
                valores.append(valor)
        salida.append(tuple(valores))
    if con_decimales:
        logger.info("%s valor(es) de 'SLA Real' con decimales se conservan tal cual (TBL_SLA.SLA es decimal(10,2)).", con_decimales)
    return salida
