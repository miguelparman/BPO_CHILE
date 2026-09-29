"""Validacion (no existia en el .dtsx: es la salvaguarda que reemplaza el
"si falla, sigue" de los scripts originales).

Todo corre ANTES de borrar/insertar, asi un problema de esquema o de datos
detiene el traslado sin haber tocado la tabla:

1) validar_esquemas: el esquema real (INFORMATION_SCHEMA) de las 3 tablas
   temporales sigue siendo el que asume mappings.py (mismos tipos y anchos).
2) validar_anchos: cada texto cabe en su columna. En el traslado EPA_ISN
   original un valor mas largo hacia fallar la transaccion completa ("todo o
   nada"); aqui se detecta antes y la tabla queda intacta. (El traslado WSP
   trunca al ancho -- clean_row -- y Medallia omite la fila: no aplica.)
3) validar_periodos: la ventana a reemplazar (DELETE por periodo) se deduce
   de los datos; debe haber al menos un periodo y todas las filas deben
   tener uno, o el reemplazo no seria idempotente.
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
from exceptions import ValidacionError
from mappings import Traslado

logger = logging.getLogger("epa_wsp")

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}


def _comparar(tabla: str, esperado: dict[str, tuple[str, int | None]], real: dict) -> list[str]:
    if not real:
        return [f"{tabla}: la tabla no existe"]
    problemas = []
    for col, (tipo, largo) in esperado.items():
        if col not in real:
            problemas.append(f"{tabla}.[{col}]: no existe")
        elif real[col] != (tipo, largo):
            problemas.append(f"{tabla}.[{col}]: se esperaba {tipo}({largo}) y es {real[col][0]}({real[col][1]})")
    sobrantes = set(real) - set(esperado)
    if sobrantes:
        logger.warning("%s tiene columnas no declaradas en mappings.py (quedaran NULL): %s", tabla, sorted(sobrantes))
    return problemas


def validar_esquemas(db_indicadores, traslados=mappings.TRASLADOS) -> None:
    problemas: list[str] = []
    for t in traslados:
        real = db_indicadores.columnas_de_tabla(t.tabla, mappings.SCHEMA)
        problemas += _comparar(f"CL_TEMPORALES_INDICADORES.{t.tabla}", t.esquema, real)
    if problemas:
        raise ValidacionError("El esquema real difiere del esperado:\n  " + "\n  ".join(problemas))
    logger.info("Esquema de %s tablas de CL_TEMPORALES_INDICADORES verificado.", len(traslados))


def validar_anchos(df: pd.DataFrame, traslado: Traslado) -> None:
    problemas = []
    for col in df.columns:
        tipo, largo = traslado.esquema[col]
        if tipo not in _TIPOS_TEXTO or largo in (None, -1):
            continue
        largos = df[col].dropna().astype(str).str.len()
        if len(largos) and int(largos.max()) > largo:
            n = int((largos > largo).sum())
            problemas.append(f"[{col}] {tipo}({largo}): {n} valores exceden el ancho (max {int(largos.max())})")
    if problemas:
        raise ValidacionError(f"{traslado.archivo} -> {traslado.tabla}:\n  " + "\n  ".join(problemas))


def validar_periodos(df: pd.DataFrame, traslado: Traslado) -> list[int]:
    """Devuelve los periodos YYYYMM de la ventana a reemplazar."""
    col = df[traslado.columna_periodo]
    sin_periodo = int(col.isna().sum())
    if sin_periodo:
        raise ValidacionError(f"{traslado.archivo}: {sin_periodo} filas sin '{traslado.columna_periodo}'")
    try:
        periodos = sorted({int(v) for v in col})
    except (TypeError, ValueError) as exc:
        raise ValidacionError(f"{traslado.archivo}: '{traslado.columna_periodo}' no es YYYYMM: {exc}") from exc
    malos = [p for p in periodos if not (190001 <= p <= 999912 and 1 <= p % 100 <= 12)]
    if malos:
        raise ValidacionError(f"{traslado.archivo}: periodos invalidos {malos}")
    if not periodos:
        raise ValidacionError(
            f"{traslado.archivo}: 0 filas para cargar; no se borra nada de {traslado.tabla} "
            "(con el TRUNCATE original la tabla habria quedado vacia)."
        )
    return periodos
