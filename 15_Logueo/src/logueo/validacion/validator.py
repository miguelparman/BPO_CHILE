"""Validacion: reproduce los puntos donde el Data Flow FALLA (FailComponent)
y agrega 2 controles previos que el .dtsx no tenia (marcados [extra]).

  1. validar_archivo          Flat File Source: 45 columnas, cada valor <= 100
                              caracteres (DT_STR(100), truncamiento = FailComponent).
                              [extra] la cabecera debe ser la declarada en el .dtsx:
                              SSIS mapea por posicion y cargaria datos corridos si
                              203_bot_portal_comercial cambiara el orden.
  2. validar_casts            Derived Column 'Dia_mes': (DT_I2)MES y (DT_I2)DIA
                              deben poder convertirse (si no, FailComponent).
  3. validar_conversion       Data Conversion a DT_STR(50): ningun valor puede
                              superar 50 caracteres (FailComponent ante truncamiento).
  4. validar_esquema_destino  [extra] TBL_CONEXIONES tiene las columnas varchar
                              que el destino mapea, con ancho >= 50 y [DNI].

Todas se ejecutan ANTES de insertar: si algo falla no se inserta ninguna fila
(el fast load de SSIS hace un solo commit, asi que tampoco dejaba filas).
"""

from __future__ import annotations

import re

import pandas as pd

import mappings
from exceptions import ValidacionError

_MAX_EJEMPLOS = 5
_ENTERO = re.compile(r"^[+-]?\d+$")
_I2_MIN, _I2_MAX = -32768, 32767


def _ejemplos(items: list) -> str:
    extra = f" (y {len(items) - _MAX_EJEMPLOS} mas)" if len(items) > _MAX_EJEMPLOS else ""
    return ", ".join(str(i) for i in items[:_MAX_EJEMPLOS]) + extra


def cast_dt_i2(valor: str) -> int:
    """(DT_I2) de un DT_STR: entero de 16 bits (se toleran espacios alrededor).
    Lanza ValueError si no es convertible, como la expresion SSIS."""
    texto = valor.strip()
    if not _ENTERO.match(texto):
        raise ValueError(f"{valor!r} no es un entero")
    numero = int(texto)
    if not _I2_MIN <= numero <= _I2_MAX:
        raise ValueError(f"{valor!r} fuera de rango DT_I2")
    return numero


def validar_archivo(cabecera: list[str], filas: list[list[str]]) -> None:
    esperada = list(mappings.COLUMNAS_ORIGEN)
    if cabecera != esperada:
        diferencias = [f"#{i + 1}: {c!r} (esperada {e!r})" for i, (c, e) in enumerate(zip(cabecera, esperada)) if c != e]
        if len(cabecera) != len(esperada):
            diferencias.insert(0, f"{len(cabecera)} columnas (esperadas {len(esperada)})")
        raise ValidacionError(f"La cabecera del archivo no coincide con la del .dtsx: {_ejemplos(diferencias)}")
    if not filas:
        raise ValidacionError("El archivo no tiene filas de datos.")

    cortas = [n for n, fila in enumerate(filas, start=2) if len(fila) != len(esperada)]
    if cortas:
        raise ValidacionError(f"Filas con menos de {len(esperada)} columnas (linea del archivo): {_ejemplos(cortas)}")

    largas = [
        f"linea {n} [{col}] ({len(v)} car.)"
        for n, fila in enumerate(filas, start=2)
        for col, v in zip(esperada, fila)
        if len(v) > mappings.ANCHO_ORIGEN
    ]
    if largas:
        raise ValidacionError(f"Valores que superan DT_STR({mappings.ANCHO_ORIGEN}) del Flat File Source: {_ejemplos(largas)}")


def validar_casts(df: pd.DataFrame) -> None:
    errores = []
    for col in ("MES", "DIA"):
        for n, valor in zip(df.index, df[col]):
            if valor is None:
                continue
            try:
                cast_dt_i2(valor)
            except ValueError:
                errores.append(f"linea {n + 2} [{col}]={valor!r}")
    if errores:
        raise ValidacionError(f"Derived Column 'Dia_mes': (DT_I2) no convertible: {_ejemplos(errores)}")


def validar_conversion(df_destino: pd.DataFrame) -> None:
    errores = []
    for col in df_destino.columns:
        largos = df_destino[col].map(lambda v: 0 if v is None else len(v))
        for n in largos.index[largos > mappings.ANCHO_CONVERSION]:
            errores.append(f"linea {n + 2} [{col}] ({largos[n]} car.)")
    if errores:
        raise ValidacionError(
            f"Data Conversion a DT_STR({mappings.ANCHO_CONVERSION}): valores que se truncarian: {_ejemplos(errores)}"
        )


def validar_esquema_destino(columnas_reales: dict[str, tuple[str, int | None]]) -> None:
    if not columnas_reales:
        raise ValidacionError(f"No existe la tabla [{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}].")
    errores = []
    for col, (tipo, ancho) in mappings.ESQUEMA_DESTINO.items():
        if col not in columnas_reales:
            errores.append(f"falta [{col}]")
            continue
        tipo_real, ancho_real = columnas_reales[col]
        if tipo_real != tipo:
            errores.append(f"[{col}] es {tipo_real} (esperado {tipo})")
        elif ancho_real != -1 and (ancho_real or 0) < ancho:
            errores.append(f"[{col}] {tipo_real}({ancho_real}) < {ancho}")
    if errores:
        raise ValidacionError(f"[{mappings.TABLA_DESTINO}] no coincide con el destino del .dtsx: {_ejemplos(errores)}")
