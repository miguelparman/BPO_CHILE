"""Validacion. Todo se verifica ANTES de 'Limpia Tabla' (el DELETE), para
no dejar TBL_FCR con el periodo borrado:

1. Esquema real (INFORMATION_SCHEMA) de TBL_FCR = mappings.COLUMNAS_DESTINO,
   en el MISMO ORDEN: el INSERT original es posicional (sin lista de columnas),
   asi que un cambio de orden en la tabla cambiaria el significado de la carga.
2. Esquema de las tablas de origen: columnas presentes y AGENT_START 'datetime'.
3. Datos extraidos: sin AGENT_START NULL y SERVICIO = el de la base.
4. Resultado: columnas NOT NULL con valor, FCR en {0,1}, anchos de texto que
   caben en el destino (en SSIS un valor mas largo haria fallar el INSERT
   con 'String or binary data would be truncated').
"""

from __future__ import annotations

import pandas as pd

import mappings
from exceptions import ValidacionError


def validar_esquemas(db) -> None:
    reales = db.columnas_de_tabla(mappings.TABLA_DESTINO, mappings.SCHEMA)
    esperados = [(c, t, l) for c, t, l in mappings.COLUMNAS_DESTINO]
    obtenidos = [(c, t, l) for c, (t, l) in reales.items()]
    if obtenidos != esperados:
        raise ValidacionError(
            f"El esquema de [{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}] no coincide con el esperado "
            f"(orden, tipo, largo).\n  esperado: {esperados}\n  real:     {obtenidos}"
        )
    for tabla in sorted({b.tabla_origen for b in mappings.BASES}):
        reales = db.columnas_de_tabla(tabla, mappings.SCHEMA)
        for col, esperado in mappings.COLUMNAS_ORIGEN.items():
            if col not in reales:
                raise ValidacionError(f"Falta la columna '{col}' en [{mappings.SCHEMA}].[{tabla}].")
            if reales[col] != esperado:
                raise ValidacionError(f"[{tabla}].[{col}] es {reales[col]}, se esperaba {esperado}.")


def validar_extraccion(df: pd.DataFrame, base: mappings.BaseFCR) -> None:
    faltan = [c for c in mappings.COLUMNAS_ORIGEN if c not in df.columns]
    if faltan:
        raise ValidacionError(f"{base.tabla_temporal}: faltan columnas {faltan}.")
    if df[mappings.COLUMNA_INICIO].isna().any():
        raise ValidacionError(f"{base.tabla_temporal}: hay filas con {mappings.COLUMNA_INICIO} NULL.")
    servicios = {str(s).rstrip(" ").upper() for s in df["SERVICIO"].dropna()}
    if servicios - {base.servicio.upper()}:
        raise ValidacionError(f"{base.tabla_temporal}: SERVICIO inesperado {sorted(servicios)}.")


def validar_resultado(df: pd.DataFrame) -> None:
    if list(df.columns) != list(mappings.NOMBRES_DESTINO):
        raise ValidacionError(f"Columnas del resultado fuera de orden: {list(df.columns)}")
    for col in mappings.COLUMNAS_NO_NULAS:
        if df[col].isna().any():
            raise ValidacionError(f"La columna NOT NULL '{col}' tiene valores NULL.")
    for u in mappings.UMBRALES:
        if not df[u.columna].isin([0, 1]).all():
            raise ValidacionError(f"'{u.columna}' tiene valores distintos de 0/1.")
    for col, tipo, largo in mappings.COLUMNAS_DESTINO:
        if tipo in ("varchar", "nvarchar") and largo is not None and not df.empty:
            largos = df[col].dropna().map(len)
            if not largos.empty and largos.max() > largo:
                raise ValidacionError(f"'{col}' tiene valores de {largos.max()} caracteres; el destino es {tipo}({largo}).")
