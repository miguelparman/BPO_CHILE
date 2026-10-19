"""TRANSFORMACION: equivalente a la 'Conversion de datos' de cada Data Flow.

  - 'Caso SF'  DT_R8  -> DT_STR(n): el numero como texto (12239535.0 ->
    '12239535'; hasta 15 digitos significativos, como la conversion de SSIS).
  - 'Fecha'    DT_DATE -> DT_DBDATE: solo la fecha (se descarta la hora).
  - texto      DT_WSTR(255) -> DT_STR(n) code page 1252.

Columnas IgnoreFailure: un valor mas largo que n se TRUNCA a n (decision del
usuario: no dejar NULL el valor completo); un caracter que no existe en 1252
se reemplaza por '?'. Las columnas FailComponent ya fueron revisadas por
validacion/validator.py (si un valor no cabe, el flujo falla como en SSIS).

Devuelve las filas en el orden de mappings.FlujoSpec.columnas (= orden de
columnas del INSERT).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from extraccion.extractor import Fila
from mappings import CASO, CODE_PAGE, FECHA, IGNORE, ColumnaSpec, FlujoSpec


def r8_a_texto(valor: float) -> str:
    """DT_R8 -> DT_STR como SSIS: entero sin decimales si lo es, si no hasta
    15 digitos significativos (notacion E para magnitudes grandes)."""
    if valor.is_integer() and abs(valor) < 1e15:
        return str(int(valor))
    return format(valor, ".15G")


def convertir(columna: ColumnaSpec, valor: Any) -> Any:
    """Valor ya convertido al tipo destino, SIN aplicar ancho ni code page."""
    if valor is None:
        return None
    if columna.tipo == CASO:
        return r8_a_texto(valor)
    if columna.tipo == FECHA:
        return valor.date() if isinstance(valor, datetime) else valor
    return valor


def _a_cp1252(texto: str) -> str:
    return texto.encode(CODE_PAGE, errors="replace").decode(CODE_PAGE)


def aplicar_ancho(columna: ColumnaSpec, valor: Any) -> Any:
    """Ancho y code page de DT_STR para columnas IgnoreFailure."""
    if valor is None or columna.ancho is None or not isinstance(valor, str):
        return valor
    if columna.disposicion == IGNORE:
        return _a_cp1252(valor)[: columna.ancho]
    return valor


class Transformer:
    def transformar(self, flujo: FlujoSpec, filas: Sequence[Fila]) -> list[tuple]:
        return [
            tuple(aplicar_ancho(c, convertir(c, fila[c.origen])) for c in flujo.columnas)
            for fila in filas
        ]
