"""Lookup 'Busqueda' del Data Flow.

Configuracion en el .dtsx:
  - CacheType = 0 (Full Cache): la referencia se lee UNA vez, antes de
    procesar el archivo, con el SqlCommand literal (sql.LOOKUP_REFERENCIA):
        SELECT [FECHA ANSI],HORA,[ID CONEXION] FROM TBL_CONEXIONES
        WHERE [FECHA ANSI] >= CONVERT(VARCHAR(8),DATEADD(month,-1,getdate()),112)
    (ventana de 1 mes segun el reloj del SQL Server);
  - claves: Copy of FechaAnsi -> [FECHA ANSI], Copy of INTERVALO -> HORA,
    Copy of AGENT_LOGIN -> [ID CONEXION];
  - NoMatchBehavior = 1: las filas SIN coincidencia van a la salida
    'no coincidentes', que es la UNICA conectada al destino. Las que
    coinciden (ya cargadas) se descartan.

Semantica que se conserva:
  - comparacion exacta de DT_STR (sensible a mayusculas y espacios);
  - en Full Cache, NULL coincide con NULL;
  - la cache NO se actualiza con las filas que se van insertando: si el
    archivo trae dos filas con la misma clave (y no esta en la tabla), se
    insertan ambas.
"""

from __future__ import annotations

import pandas as pd

import mappings

Clave = tuple[str | None, str | None, str | None]


def _a_texto(valor) -> str | None:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    return valor if isinstance(valor, str) else str(valor)


def construir_cache(df_referencia: pd.DataFrame) -> set[Clave]:
    columnas = [ref for _, ref in mappings.CLAVE_LOOKUP]
    return {tuple(_a_texto(v) for v in fila) for fila in df_referencia[columnas].itertuples(index=False, name=None)}


def filas_no_coincidentes(df: pd.DataFrame, cache: set[Clave]) -> pd.DataFrame:
    """Devuelve las filas cuya clave no esta en la cache (salida al destino)."""
    columnas = [flujo for flujo, _ in mappings.CLAVE_LOOKUP]
    coincide = [tuple(fila) in cache for fila in df[columnas].itertuples(index=False, name=None)]
    return df.loc[[not c for c in coincide]]
