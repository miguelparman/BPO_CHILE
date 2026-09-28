"""Extraccion.

1) TEMPORALES: reemplaza la parte "SELECT ... FROM [Externos_Frac].[dbo].[X]
   WHERE <periodo>" de los 7 scripts Traslado_Trafico_Servidor_55_*.py. Lee
   el CSV equivalente de SharePoint, aplica el mismo filtro de periodo, se
   queda con las columnas del INSERT original y convierte cada valor al tipo
   Python que antes entregaba pyodbc desde SQL Server (int, date, datetime,
   str o None). Los valores se insertan luego como parametros nativos: nunca
   como texto, porque la sesion de SQL Server usa DATEFORMAT dmy y un
   '2026-09-01' en texto podria leerse como 9 de enero.

2) CL_TRAFICO: lectura de las tablas temporales (OLE DB Sources 'TBL_55_*'
   del Data Flow CARGA, AccessMode=0 = tabla completa).

Si un valor no se puede convertir al tipo de su columna temporal se lanza
ValidacionError: en el script original el INSERT habria fallado.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Callable

import pandas as pd

import mappings
from exceptions import ExtraccionError, ValidacionError
from mappings import OrigenCsv

logger = logging.getLogger("trafico")

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}


def parsear_datetime(texto: str) -> datetime:
    """'YYYY-MM-DD HH:MM:SS[.f...]' (formato ISO que escribe csv.writer para
    un datetime, o el texto de un datetime2). Fracciones de mas de 6 digitos
    se recortan a microsegundos."""
    texto = texto.strip()
    if "." in texto:
        base, fraccion = texto.split(".", 1)
        texto = f"{base}.{fraccion[:6]}"
    return datetime.fromisoformat(texto)


def _a_int(texto: str) -> int:
    return int(texto)


def _a_date(texto: str) -> date:
    return date.fromisoformat(texto.strip()[:10])


def _formatear_datetime2(texto: str) -> str:
    """Texto de un datetime2(7) tal como lo guardaba SQL Server al convertirlo
    a nvarchar: 'YYYY-MM-DD HH:MM:SS.fffffff'."""
    dt = parsear_datetime(texto)
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond:06d}0"


def _conversor(tipo_sql: str) -> Callable[[str], object] | None:
    if tipo_sql in ("int", "bigint", "smallint", "tinyint"):
        return _a_int
    if tipo_sql == "date":
        return _a_date
    if tipo_sql in ("datetime", "datetime2", "smalldatetime"):
        return parsear_datetime
    return None


def filtrar_periodo(df: pd.DataFrame, origen: OrigenCsv, periodo: int) -> pd.DataFrame:
    """Filtro de periodo de cada script original:
       - 'WHERE DATE_YYYYMM >= ?'                         (int YYYYMM)
       - 'WHERE CONVERT(VARCHAR(6),[FECHA],112) >= ?'     (Callback, datetime)
    Una celda vacia (NULL en el origen) nunca cumple la condicion."""
    col = df[origen.columna_periodo]
    no_vacio = col.str.strip() != ""
    if origen.periodo_desde_fecha:
        yyyymm = col.where(no_vacio, "").str[:7].str.replace("-", "", regex=False)
    else:
        yyyymm = col
    mascara = no_vacio & (pd.to_numeric(yyyymm.where(no_vacio, "0"), errors="coerce") >= periodo)
    return df[mascara.fillna(False)].reset_index(drop=True)


def tipificar(df: pd.DataFrame, origen: OrigenCsv) -> pd.DataFrame:
    """Proyecta las columnas del INSERT original y convierte cada valor al
    tipo de su columna en la tabla temporal."""
    faltantes = [c for c in origen.columnas if c not in df.columns]
    if faltantes:
        raise ValidacionError(f"{origen.archivo}: faltan columnas obligatorias {faltantes}")

    esquema = mappings.TIPOS_TEMPORALES[origen.tabla_temporal]
    resultado: dict[str, pd.Series] = {}
    for col in origen.columnas:
        tipo_sql, _ = esquema[col]
        serie = df[col]
        vacio = serie.str.strip() == "" if tipo_sql not in _TIPOS_TEXTO else serie == ""

        if col in origen.columnas_texto_datetime2:
            conv: Callable[[str], object] | None = _formatear_datetime2
        else:
            conv = _conversor(tipo_sql)

        if conv is None:  # texto: se inserta tal cual
            valores = serie.astype(object)
            if origen.texto_vacio_como_null:
                valores = valores.where(~vacio, None)
        else:
            valores = pd.Series([None] * len(serie), dtype=object, index=serie.index)
            errores = []
            for idx in serie.index[~vacio]:
                try:
                    valores.at[idx] = conv(serie.at[idx])
                except (ValueError, TypeError):
                    errores.append(serie.at[idx])
            if errores:
                raise ValidacionError(
                    f"{origen.archivo}: {len(errores)} valores de '{col}' no convierten a "
                    f"{tipo_sql} (ej. {errores[:3]})"
                )
        resultado[col] = valores
    return pd.DataFrame(resultado, columns=list(origen.columnas))


def extraer_origen(reader, origen: OrigenCsv, periodo: int) -> pd.DataFrame:
    """CSV de SharePoint -> DataFrame listo para insertar en la temporal."""
    try:
        crudo = reader.read_csv(origen.archivo)
    except Exception as exc:  # noqa: BLE001 - se re-lanza tipado
        raise ExtraccionError(f"No se pudo leer '{origen.archivo}' de SharePoint: {exc}") from exc

    if origen.columna_periodo not in crudo.columns:
        raise ValidacionError(f"{origen.archivo}: falta la columna de periodo '{origen.columna_periodo}'")
    filtrado = filtrar_periodo(crudo, origen, periodo)
    df = tipificar(filtrado, origen)
    logger.info(
        "%s: %s filas en el CSV, %s del periodo >= %s.", origen.archivo, len(crudo), len(df), periodo
    )
    return df


def leer_temporal(db_temporales, tabla: str) -> pd.DataFrame:
    """OLE DB Source 'TBL_55_*' (tabla completa)."""
    return db_temporales.read_table(tabla, mappings.SCHEMA)
