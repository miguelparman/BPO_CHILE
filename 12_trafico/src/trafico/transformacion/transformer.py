"""Transformacion.

A) Tareas Execute SQL de enriquecimiento, ejecutadas en SQL Server con el
   T-SQL literal del .dtsx (ver sql.py):
     - TEMPORALES\\UPDATE                (normaliza LOGINID/PLACE, SERVICIO, tramos, FECHA/HORA)
     - LIMPIA TEMPORALES (6 tareas)      (ANI, RUT, COD_DNI, SEGMENTO, SEGMENTO COLA, LLAMA CCAA?)
     - CL_TRAFICO\\UPDATE_WSP            (INTERACTION_TYPE / SEGMENTO COLA de TBL_CHAT)

B) Data Flow 'CARGA' (CL_TEMPORALES -> CL_TRAFICO), migrado a pandas con la
   misma semantica de SSIS:
     - Conditional Split sobre ATENDIDA (Inbound / Chat; el resto se descarta).
     - Derived Column sobre CALLBACK (FECHA_DATE, FECHA_HORA).
     - Data Conversion de cada columna al tipo declarado en el .dtsx.
     - Conversion implicita del OLE DB Destination al tipo real de la columna.
   Error de conversion o truncamiento => ConversionError (FailComponent),
   salvo las columnas 'IgnoreFailure', que quedan NULL.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

import mappings
import sql
from exceptions import ConversionError
from extraccion.extractor import parsear_datetime
from mappings import ColumnaCarga, DestinoCarga

logger = logging.getLogger("trafico")


# =========================================================================== #
# A) Tareas SQL
# =========================================================================== #
def actualizar_temporales(db_temporales) -> None:
    """Package\\TEMPORALES\\UPDATE."""
    db_temporales.execute_script(sql.TEMPORALES_UPDATE)


def limpiar_temporales(db_temporales) -> None:
    """Secuencia Package\\LIMPIA TEMPORALES: 6 tareas en serie."""
    for nombre, script in sql.LIMPIA_TEMPORALES:
        logger.info("[Trafico]   LIMPIA TEMPORALES / %s", nombre)
        db_temporales.execute_script(script)


def actualizar_wsp(db_temporales) -> None:
    """Package\\CL_TRAFICO\\UPDATE_WSP (en el .dtsx corre sobre el Connection
    Manager de CL_TEMPORALES y actualiza [CL_TRAFICO].[dbo].[TBL_CHAT])."""
    db_temporales.execute_script(sql.CL_TRAFICO_UPDATE_WSP)


# =========================================================================== #
# B) Data Flow 'CARGA'
# =========================================================================== #
class _FalloConversion(Exception):
    pass


def _igual(valor: Any, literal: str) -> bool | None:
    """'==' de expresiones SSIS: NULL == x devuelve NULL."""
    return None if valor is None else valor == literal


def _y(a: bool | None, b: bool | None) -> bool | None:
    """'&&' de expresiones SSIS (logica de 3 valores): FALSE domina a NULL."""
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def dividir_atendida(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Conditional Split: cada fila va a la PRIMERA salida cuya condicion es
    verdadera. Si una condicion evalua a NULL, SSIS la envia al error output
    y, con disposicion 'FailComponent', aborta el Data Flow."""
    asignacion: list[str | None] = []
    for i, fila in enumerate(df[["MEDIA", "INTERACTION_TYPE"]].itertuples(index=False, name=None)):
        valores = dict(zip(("MEDIA", "INTERACTION_TYPE"), fila))
        destino = None
        for salida, condicion in mappings.SPLIT_ATENDIDA:
            resultado: bool | None = True
            for columna, literal in condicion.items():
                resultado = _y(resultado, _igual(valores[columna], literal))
            if resultado is None:
                raise ConversionError(
                    f"Division condicional: la condicion de la salida '{salida}' evalua a NULL "
                    f"en la fila {i} (MEDIA={valores['MEDIA']!r}, "
                    f"INTERACTION_TYPE={valores['INTERACTION_TYPE']!r}) -> FailComponent"
                )
            if resultado:
                destino = salida
                break
        asignacion.append(destino)
    serie = pd.Series(asignacion, index=df.index, dtype=object)
    return {salida: df[serie == salida].reset_index(drop=True) for salida, _ in mappings.SPLIT_ATENDIDA}


def derivar_callback(df: pd.DataFrame) -> pd.DataFrame:
    """Derived Column sobre TBL_55_CALLBACK:
         FECHA_DATE = (DT_DATE)FECHA
         FECHA_HORA = SUBSTRING((DT_STR,30,1252)FECHA,12,8)   -> 'HH:MM:SS'
    FECHA NULL -> ambas NULL (las expresiones SSIS propagan NULL)."""
    df = df.copy()
    fechas, horas = [], []
    for i, f in enumerate(df["FECHA"].tolist()):
        try:
            fechas.append(None if f is None else _a_fecha(f))
            horas.append(None if f is None else _a_fecha_hora(f).strftime("%H:%M:%S"))
        except (_FalloConversion, ValueError) as exc:
            raise ConversionError(
                f"Columna derivada (CALLBACK), fila {i}: FECHA={f!r} no es fecha/hora -> FailComponent"
            ) from exc
    df["FECHA_DATE"] = pd.Series(fechas, dtype=object, index=df.index)
    df["FECHA_HORA"] = pd.Series(horas, dtype=object, index=df.index)
    return df


def _a_fecha_hora(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    if isinstance(valor, str):
        return parsear_datetime(valor)
    raise _FalloConversion(f"no es fecha/hora: {valor!r}")


def _a_fecha(valor: Any) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip()[:10])
        except ValueError as exc:
            raise _FalloConversion(str(exc)) from exc
    raise _FalloConversion(f"no es fecha: {valor!r}")


def _a_texto(valor: Any) -> str:
    if isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, int):
        return str(valor)
    raise _FalloConversion(f"no convierte a texto: {valor!r}")


def convertir_ssis(valor: Any, conversion: str | None, largo: int | None) -> Any:
    """Data Conversion al tipo SSIS de la columna. NULL se mantiene NULL."""
    if valor is None or conversion is None:
        return valor
    if conversion in ("DT_STR", "DT_WSTR"):
        texto = _a_texto(valor)
        if conversion == "DT_STR":
            try:
                texto.encode("cp1252")
            except UnicodeEncodeError as exc:
                raise _FalloConversion(f"caracter no representable en la code page 1252: {texto!r}") from exc
        if largo is not None and len(texto) > largo:
            raise _FalloConversion(f"truncamiento: {len(texto)} caracteres > {conversion}({largo}): {texto!r}")
        return texto
    if conversion == "DT_I4":
        try:
            entero = int(valor)
        except (TypeError, ValueError) as exc:
            raise _FalloConversion(f"no convierte a DT_I4: {valor!r}") from exc
        if not -(2**31) <= entero < 2**31:
            raise _FalloConversion(f"desborde DT_I4: {entero}")
        return entero
    if conversion == "DT_DBTIMESTAMP":
        try:
            return _a_fecha_hora(valor)
        except ValueError as exc:
            raise _FalloConversion(f"no convierte a DT_DBTIMESTAMP: {valor!r}") from exc
    if conversion == "DT_DBDATE":
        return _a_fecha(valor)
    raise ValueError(f"Conversion SSIS no soportada: {conversion}")


def convertir_destino(valor: Any, tipo: str, largo: int | None) -> Any:
    """Conversion implicita del OLE DB Destination al tipo real de la columna
    (p.ej. DT_I4 -> varchar(5), DT_WSTR -> datetime)."""
    if valor is None:
        return None
    if tipo in ("varchar", "nvarchar", "char", "nchar"):
        texto = _a_texto(valor)
        if largo not in (None, -1) and len(texto) > largo:
            raise _FalloConversion(f"no cabe en {tipo}({largo}): {texto!r}")
        return texto
    if tipo == "date":
        return _a_fecha(valor)
    if tipo in ("datetime", "datetime2", "smalldatetime"):
        try:
            return _a_fecha_hora(valor)
        except ValueError as exc:
            raise _FalloConversion(f"no convierte a {tipo}: {valor!r}") from exc
    return valor


def _convertir_columna(serie: pd.Series, col: ColumnaCarga, destino: DestinoCarga) -> pd.Series:
    valores = []
    for i, valor in enumerate(serie.tolist()):
        try:
            v = convertir_ssis(valor, col.conversion, col.largo)
            v = convertir_destino(v, col.tipo_destino, col.largo_destino)
        except _FalloConversion as exc:
            if col.ignorar_fallo:
                v = None
            else:
                raise ConversionError(
                    f"CARGA/{destino.componente} -> {destino.tabla}.[{col.destino}] "
                    f"(origen [{col.origen}], fila {i}): {exc} -> FailComponent"
                ) from exc
        valores.append(v)
    return pd.Series(valores, dtype=object, index=serie.index)


def mapear_destino(df_origen: pd.DataFrame, destino: DestinoCarga) -> pd.DataFrame:
    """Data Conversion + mapeo de columnas del OLE DB Destination."""
    columnas = {
        col.destino: _convertir_columna(df_origen[col.origen], col, destino) for col in destino.columnas
    }
    return pd.DataFrame(columnas, columns=[c.destino for c in destino.columnas])


def transformar_carga(temporales: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Data Flow completo: {tabla temporal: df} -> {tabla CL_TRAFICO: df}.
    Se transforma TODO antes de escribir: un fallo aborta sin haber insertado."""
    divisiones = dividir_atendida(temporales["TBL_TRAFICO_ATENDIDA"])
    descartadas = len(temporales["TBL_TRAFICO_ATENDIDA"]) - sum(len(d) for d in divisiones.values())
    logger.info(
        "Division condicional ATENDIDA: %s",
        ", ".join(f"{k}={len(v)}" for k, v in divisiones.items()) + f", salida predeterminada (descartada)={descartadas}",
    )
    callback = derivar_callback(temporales["TBL_TRAFICO_CALLBACK"])

    resultado = {}
    for destino in mappings.DESTINOS:
        if destino.salida_split:
            origen = divisiones[destino.salida_split]
        elif destino.tabla_origen == "TBL_TRAFICO_CALLBACK":
            origen = callback
        else:
            origen = temporales[destino.tabla_origen]
        resultado[destino.tabla] = mapear_destino(origen, destino)
    return resultado
