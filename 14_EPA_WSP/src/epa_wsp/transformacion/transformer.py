"""Transformacion: reglas de los 3 scripts de carga de 102_calidad/.

- encuestas_chile   <- Traslado_Calidad_Servidor_55_EPA_ISN.py
- wsp_medallia      <- Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py (clean_row)
- medallia          <- CL_Carga_de_encuestas_MEDALLIA.py

Los traslados leian filas TIPADAS de [Externos_Frac] (pyodbc) y las
insertaban tal cual; ahora el origen es un CSV (texto), asi que cada valor
se convierte al tipo de su columna destino (mappings.py): int -> int,
datetime -> datetime, texto -> str. Los valores se insertan como parametros
nativos, nunca como texto (la sesion de SQL Server usa DATEFORMAT dmy).
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

import numpy as np
import pandas as pd

import mappings
from exceptions import ValidacionError
from mappings import Traslado

logger = logging.getLogger("epa_wsp")

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}
_TIPOS_ENTEROS = {"int", "bigint", "smallint", "tinyint"}
FLOAT_SUFFIX_RE = re.compile(r"^-?\d+\.0$")  # mismo patron que el script WSP original


# --------------------------------------------------------------------------- #
# Conversores texto -> tipo SQL
# --------------------------------------------------------------------------- #
def a_int(texto: str) -> int:
    """'5', '-1' o '10.00' (decimal de origen) -> int. Un decimal con parte
    fraccionaria se trunca hacia cero, como la conversion implicita
    numeric -> int de SQL Server al insertar el Decimal que entregaba pyodbc."""
    try:
        return int(Decimal(texto.strip()))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(texto) from exc


def a_datetime(texto: str) -> datetime:
    """'YYYY-MM-DD HH:MM:SS[.f...]' (lo que escribe csv.writer para un
    datetime). Fracciones de mas de 6 digitos se recortan a microsegundos."""
    texto = texto.strip()
    if "." in texto:
        base, fraccion = texto.split(".", 1)
        texto = f"{base}.{fraccion[:6]}"
    return datetime.fromisoformat(texto)


def _conversor(tipo_sql: str) -> Callable[[str], object] | None:
    if tipo_sql in _TIPOS_ENTEROS:
        return a_int
    if tipo_sql in ("datetime", "datetime2", "smalldatetime"):
        return a_datetime
    return None


def _convertir_columna(serie: pd.Series, tipo_sql: str, archivo: str, col: str) -> pd.Series:
    """Serie de texto (None = NULL) -> serie object con valores del tipo SQL."""
    conv = _conversor(tipo_sql)
    if conv is None:
        return serie.astype(object)
    valores = pd.Series([None] * len(serie), dtype=object, index=serie.index)
    errores = []
    for idx, texto in serie.items():
        if texto is None:
            continue
        try:
            valores.at[idx] = conv(texto)
        except (ValueError, TypeError):
            errores.append(texto)
    if errores:
        raise ValidacionError(
            f"{archivo}: {len(errores)} valores de '{col}' no convierten a {tipo_sql} (ej. {errores[:3]})"
        )
    return valores


def periodos_de(df: pd.DataFrame, columna: str) -> list[int]:
    """Periodos YYYYMM distintos presentes en el DataFrame ya transformado."""
    return sorted({int(v) for v in df[columna].dropna()})


# --------------------------------------------------------------------------- #
# EPA_ISN: ENCUESTA.csv -> TBL_ENCUESTAS_CHILE
# --------------------------------------------------------------------------- #
def encuestas_chile(crudo: pd.DataFrame, periodo_desde: int, traslado: Traslado = mappings.ENCUESTA) -> pd.DataFrame:
    """SELECT * FROM ENCUESTA WHERE periodo_evento >= 202601 + INSERT posicional.

    - Filtro de periodo del script (numerico; un NULL nunca cumple).
    - Celda vacia -> NULL. En el origen, los meses que publica el CSV no
      tienen '' en ninguna columna de texto (verificado: 0 de 15.279 filas).
    """
    periodo = pd.to_numeric(crudo[traslado.columna_periodo].str.strip(), errors="coerce")  # '' -> NaN
    df = crudo[(periodo >= periodo_desde).fillna(False)].reset_index(drop=True)

    resultado: dict[str, pd.Series] = {}
    for origen, destino in traslado.columnas.items():
        tipo, _ = traslado.esquema[destino]
        serie = df[origen].where(df[origen] != "", None)
        resultado[destino] = _convertir_columna(serie, tipo, traslado.archivo, destino)
    salida = pd.DataFrame(resultado, columns=traslado.columnas_destino)
    logger.info(
        "%s: %s filas en el CSV, %s con %s >= %s.",
        traslado.archivo, len(crudo), len(salida), traslado.columna_periodo, periodo_desde,
    )
    return salida


# --------------------------------------------------------------------------- #
# WSP: WS_MEDALLIA_2.csv -> TBL_ENCUESTAS_WSP_MEDALLIA
# --------------------------------------------------------------------------- #
def clean_value(valor, max_length: int | None, quitar_sufijo_float: bool):
    """clean_row() del script original, valor a valor y en el mismo orden:
    None -> None; NaN -> None; 'nan' (cualquier caso) -> None; en rutcli
    '77960408.0' -> '77960408'; texto mas largo que la columna -> truncado."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if isinstance(valor, str) and valor.lower() == "nan":
        return None
    if isinstance(valor, str) and quitar_sufijo_float and FLOAT_SUFFIX_RE.match(valor):
        return valor[:-2]
    if isinstance(valor, str) and max_length is not None and len(valor) > max_length:
        return valor[:max_length]
    return valor


def wsp_medallia(crudo: pd.DataFrame, traslado: Traslado = mappings.WSP) -> pd.DataFrame:
    """SELECT <21 columnas> FROM WS_MEDALLIA_2 + clean_row + INSERT."""
    resultado: dict[str, pd.Series] = {}
    for origen, destino in traslado.columnas.items():
        tipo, largo = traslado.esquema[destino]
        serie = crudo[origen]
        vacio = serie == ""

        # Celda vacia: NULL, salvo las columnas cuyo '' real se reconoce
        # porque otra columna de la fila esta informada (ver mappings).
        referencia = mappings.WSP_TEXTO_VACIO_SI_INFORMADA.get(origen)
        if referencia is not None:
            nulo = vacio & (crudo[referencia] == "")
        else:
            nulo = vacio
        serie = serie.where(~nulo, None)

        max_length = largo if (tipo in _TIPOS_TEXTO and largo not in (None, -1)) else None
        quitar = origen == mappings.WSP_COLUMNA_SUFIJO_FLOAT
        serie = serie.map(lambda v: clean_value(v, max_length, quitar), na_action=None)
        resultado[destino] = _convertir_columna(serie, tipo, traslado.archivo, destino)

    salida = pd.DataFrame(resultado, columns=traslado.columnas_destino)
    truncados = {
        d: int((crudo[o].str.len() > traslado.esquema[d][1]).sum())
        for o, d in traslado.columnas.items()
        if traslado.esquema[d][0] in _TIPOS_TEXTO and traslado.esquema[d][1] not in (None, -1)
    }
    truncados = {k: v for k, v in truncados.items() if v}
    if truncados:
        logger.warning("%s: valores truncados al ancho de la columna destino: %s", traslado.archivo, truncados)
    logger.info("%s: %s filas transformadas.", traslado.archivo, len(salida))
    return salida


# --------------------------------------------------------------------------- #
# MEDALLIA: Encuestas_Medallia.csv -> TBL_ENCUESTAS_MEDALLIA
# --------------------------------------------------------------------------- #
_NULOS_MEDALLIA = {np.nan: None, "": None, "nan": None, "None": None, "NULL": None, "Null": None}


def medallia(crudo: pd.DataFrame, traslado: Traslado = mappings.MEDALLIA) -> tuple[pd.DataFrame, list[int]]:
    """Reglas de CL_Carga_de_encuestas_MEDALLIA.py, en su mismo orden:
    1. NaN, '', 'nan', 'None', 'NULL', 'Null' -> None.
    2. Columna duplicada '<razones>.1' fusionada (combine_first) y eliminada.
    3. Responsedate: '%d-%m-%Y' -> datetime.
    4. Resto de columnas -> str (None se mantiene).
    5. Proyeccion y orden de las 16 columnas.

    Devuelve (filas a insertar, numeros de fila rechazados). En el original,
    una Responsedate vacia o invalida quedaba como NaT (el .where(..., None)
    no la cambia en una columna datetime) y pyodbc la enviaba fuera de rango:
    el INSERT de ESA fila fallaba y se contaba como 'Registro con error'
    (verificado contra SQL Server, error 242). Aqui esas filas se rechazan
    antes de insertar, con el mismo numero de fila (base 1)."""
    df = crudo.replace(_NULOS_MEDALLIA)

    original = mappings.MEDALLIA_COLUMNA_DUPLICADA
    duplicada = original + ".1"
    if duplicada in df.columns:
        df[original] = df[original].combine_first(df[duplicada])
        df = df.drop(columns=[duplicada])

    faltantes = [c for c in traslado.columnas if c not in df.columns]
    if faltantes:
        raise ValidacionError(f"{traslado.archivo}: faltan columnas obligatorias {faltantes}")

    fechas = pd.to_datetime(df["Responsedate"], format="%d-%m-%Y", errors="coerce")
    salida: dict[str, pd.Series] = {}
    for col in traslado.columnas:
        if col == "Responsedate":
            salida[col] = pd.Series(
                [None if pd.isna(v) else v.to_pydatetime() for v in fechas], dtype=object, index=df.index
            )
        else:
            salida[col] = df[col].astype(str).where(df[col].notnull(), None).astype(object)
    resultado = pd.DataFrame(salida, columns=traslado.columnas_destino).reset_index(drop=True)
    sin_fecha = fechas.isna().to_numpy()
    rechazadas = [i + 1 for i in np.flatnonzero(sin_fecha)]
    if rechazadas:
        logger.warning(
            "%s: %s filas sin Responsedate valida (dd-mm-aaaa) se omiten, como en el original: filas %s",
            traslado.archivo, len(rechazadas), rechazadas[:20],
        )
    validas = resultado[~sin_fecha].reset_index(drop=True)
    logger.info("%s: %s filas transformadas (%s rechazadas).", traslado.archivo, len(validas), len(rechazadas))
    return validas, rechazadas
