"""Conversion texto -> DT_DATE de SSIS (Data Conversion / Flat File Source con
LocaleID es-ES 3082 / es-PE 10250: dia primero).

Formatos aceptados (los que publica 201_bot_salesforce y sus variantes):
    dd-mm-yyyy H:MM[:SS]      '23-10-2026 9:08'      (el unico visto en los CSV)
    dd/mm/yyyy H:MM[:SS]
    dd-mm-yyyy                (solo fecha)
    ... con sufijo AM/PM: 'a. m.', 'p.\\xa0m.', o 'aM'/'pM' (lo que deja el
        REPLACE(".\\xa0m.","M") de la Derived Column de Correos)
    yyyy-mm-dd[ T]HH:MM[:SS[.fff]]
Cualquier otro texto (incluido '') no es una fecha: en SSIS es un error de
conversion y el componente (FailComponent) detiene el paquete.
"""

from __future__ import annotations

import re
from datetime import datetime

_DMY = re.compile(
    r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})"
    r"(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?"
    r"(?:\s*([aApP])\.?[\s\xa0]*[mM]\.?)?)?$"
)
_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?)?$")


def _armar(anio, mes, dia, hora, minuto, segundo, fraccion, meridiano=None) -> datetime:
    h = int(hora or 0)
    if meridiano:
        if not 1 <= h <= 12:
            raise ValueError("hora fuera de rango para AM/PM")
        h = h % 12 + (12 if meridiano.lower() == "p" else 0)
    micro = int((fraccion or "0").ljust(3, "0")) * 1000
    return datetime(int(anio), int(mes), int(dia), h, int(minuto or 0), int(segundo or 0), micro)


def parsear_fecha(texto: str) -> datetime:
    """datetime del texto o ValueError si no es una fecha valida."""
    valor = texto.strip()
    m = _DMY.match(valor)
    if m:
        dia, mes, anio, hora, minuto, segundo, fraccion, meridiano = m.groups()
        return _armar(anio, mes, dia, hora, minuto, segundo, fraccion, meridiano)
    m = _YMD.match(valor)
    if m:
        anio, mes, dia, hora, minuto, segundo, fraccion = m.groups()
        return _armar(anio, mes, dia, hora, minuto, segundo, fraccion)
    raise ValueError(f"'{texto}' no es una fecha reconocible")


def fecha_a_texto(valor: datetime) -> str:
    """DT_DATE -> DT_WSTR para la staging (solo 'Fecha de recepcion' de Casos,
    cuya columna de salida del Flat File Source es DT_DATE). Formato ISO: la
    'CARGA CASOS CHILE' lo convierte con CAST(... AS datetime2), que lo
    interpreta igual con cualquier DATEFORMAT."""
    return valor.strftime("%Y-%m-%d %H:%M:%S")
