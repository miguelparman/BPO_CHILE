"""Transformacion: Derived Columns 'Dia_mes' y 'FechaAnsi' + Data Conversion.

Expresiones del .dtsx (FriendlyExpression), aplicadas en este orden:

  Dia_mes   (reemplazan la columna, DT_STR(100))
    MES       = (DT_I2)MES < 10 ? "0" + MES : MES
    DIA       = (DT_I2)DIA < 10 ? "0" + DIA : DIA
    INTERVALO = LEN(TRIM(INTERVALO)) == 4 ? "0" + TRIM(INTERVALO) : TRIM(INTERVALO)
  FechaAnsi (columna nueva DT_WSTR, sobre MES/DIA ya rellenados)
    FechaAnsi = [AÑO] + MES + DIA
  Conversion de datos
    'Copy of <col>' = (DT_STR, 50, 1252) <col>   para las 45 columnas + FechaAnsi

Se reproducen literalmente, incluso donde el resultado no es intuitivo:
  - el cast (DT_I2) solo decide si se antepone "0"; se concatena al texto
    ORIGINAL: MES = "9" -> "09", pero MES = "09" -> "009" (9 < 10);
  - TRIM de SSIS quita solo espacios (no tabs) al inicio y al final, y solo
    se aplica a INTERVALO; MES/DIA no se recortan;
  - NULL se propaga: MES NULL -> NULL; cualquier parte NULL -> FechaAnsi NULL.
Los valores que no pueden convertirse (MES/DIA no numericos, mas de 50
caracteres) los rechaza validacion/validator.py antes de llegar aqui.
"""

from __future__ import annotations

import pandas as pd

import mappings
from validacion.validator import cast_dt_i2

EXPRESIONES_SSIS = {
    "MES": '(DT_I2)MES < 10 ? "0" + MES : MES',
    "DIA": '(DT_I2)DIA < 10 ? "0" + DIA : DIA',
    "INTERVALO": 'LEN(TRIM(INTERVALO)) == 4 ? "0" + TRIM(INTERVALO) : TRIM(INTERVALO)',
    mappings.COLUMNA_FECHA_ANSI: "[AÑO] + MES + DIA",
}


def rellenar_dia_mes(valor: str | None) -> str | None:
    """(DT_I2)x < 10 ? "0" + x : x"""
    if valor is None:
        return None
    return "0" + valor if cast_dt_i2(valor) < 10 else valor


def _trim_ssis(valor: str) -> str:
    return valor.strip(" ")


def rellenar_intervalo(valor: str | None) -> str | None:
    """LEN(TRIM(x)) == 4 ? "0" + TRIM(x) : TRIM(x)"""
    if valor is None:
        return None
    recortado = _trim_ssis(valor)
    return "0" + recortado if len(recortado) == 4 else recortado


def fecha_ansi(anio: str | None, mes: str | None, dia: str | None) -> str | None:
    """[AÑO] + MES + DIA (concatenacion SSIS: NULL si alguna parte es NULL)."""
    if anio is None or mes is None or dia is None:
        return None
    return anio + mes + dia


def transformar(df_origen: pd.DataFrame) -> pd.DataFrame:
    """Aplica Dia_mes -> FechaAnsi -> Data Conversion y devuelve las filas con
    los nombres y el orden de TBL_CONEXIONES (sin [DNI])."""
    df = df_origen.copy()
    df["MES"] = df["MES"].map(rellenar_dia_mes).astype(object)
    df["DIA"] = df["DIA"].map(rellenar_dia_mes).astype(object)
    df["INTERVALO"] = df["INTERVALO"].map(rellenar_intervalo).astype(object)
    df[mappings.COLUMNA_FECHA_ANSI] = pd.Series(
        [fecha_ansi(a, m, d) for a, m, d in zip(df["AÑO"], df["MES"], df["DIA"])], index=df.index, dtype=object
    )
    destino = df.rename(columns=mappings.MAPEO_DESTINO)
    return destino[list(mappings.COLUMNAS_INSERT)].astype(object)
