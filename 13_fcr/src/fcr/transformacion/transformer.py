"""Transformacion: la logica de 'Alimenta Tabla' en pandas.

Por cada base (mappings.BASES), igual que cada bloque SELECT ... INTO #TBL_TMP_*:

  XA  FECHA = CAST(AGENT_START AS DATE)
      HORA  = CAST(CAST(AGENT_START AS TIME) AS VARCHAR(8))   -> 'HH:MM:SS' (trunca fracciones)
      ANI, SERVICIO, LOGINID, BASE = '<literal>'
      [FECHA/HORA] = CAST(AGENT_START AS DATETIME)             -> identidad (origen ya es datetime)
  XB  [FECHA/HORA-PROXIMO] = LEAD([FECHA/HORA]) OVER (PARTITION BY ANI, SERVICIO ORDER BY [FECHA/HORA])
      FCR_x = CASE WHEN DATEDIFF(SECOND, [FECHA/HORA], [FECHA/HORA-PROXIMO]) <= s THEN 0 ELSE 1 END

y luego UNION ALL de las 5 bases + TRAMO_QUIEBRE (primer FCR_x = 0).

Detalles de SQL Server que se reproducen:
- La ventana LEAD es POR BASE (cada base es una #temp distinta): la misma ANI
  en LLAMADAS y en WHATSAPP no se encadena.
- La ventana solo ve las filas >= periodo (el filtro esta en XA, antes del
  LEAD): la ultima atencion de cada ANI queda con PROXIMO NULL -> todos los FCR = 1.
- PARTITION BY agrupa los NULL juntos y compara con la collation de la
  columna (Modern_Spanish_CI_AS): sin distinguir mayusculas ni espacios finales.
- DATEDIFF(SECOND, a, b) cuenta limites de segundo cruzados, no segundos
  transcurridos: floor(b) - floor(a) al segundo.
- DATEDIFF con NULL da NULL, 'NULL <= s' es UNKNOWN -> rama ELSE -> 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import mappings

def es_nulo(serie: pd.Series) -> pd.Series:
    return serie.map(lambda v: v is None or (not isinstance(v, str) and pd.isna(v))).astype(bool)


def clave_collation(serie: pd.Series) -> pd.Series:
    """Clave de igualdad equivalente a la collation *_CI_AS de SQL Server:
    insensible a mayusculas y a espacios finales (el padding ANSI de '='),
    sensible a acentos. Los NULL se distinguen con es_nulo() y no con un valor
    centinela: NULL y '' son particiones DISTINTAS en SQL Server (y pandas
    agrupa como iguales cadenas que solo difieren desde un caracter nulo)."""
    return serie.map(lambda v: "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v).rstrip(" ").upper())


def diferencia_segundos(desde: pd.Series, hasta: pd.Series) -> pd.Series:
    """DATEDIFF(SECOND, desde, hasta): limites de segundo cruzados. NULL si
    cualquiera de los dos es NULL (NaN)."""
    return (hasta.dt.floor("s") - desde.dt.floor("s")).dt.total_seconds()


def preparar_base(origen: pd.DataFrame, base: mappings.BaseFCR) -> pd.DataFrame:
    """Bloque 'XA': columnas derivadas de AGENT_START y la etiqueta BASE."""
    inicio = pd.to_datetime(origen[mappings.COLUMNA_INICIO].astype("object"))
    return pd.DataFrame(
        {
            "FECHA": pd.Series([t.date() for t in inicio], index=origen.index, dtype=object),
            "HORA": inicio.dt.strftime("%H:%M:%S").astype(object),
            "ANI": origen["ANI"].astype(object),
            "SERVICIO": origen["SERVICIO"].astype(object),
            "LOGINID": origen["LOGINID"].astype(object),
            "BASE": base.base,
            "FECHA/HORA": inicio,
        },
        index=origen.index,
    )


def calcular_fcr(df: pd.DataFrame) -> pd.DataFrame:
    """Bloque 'XB': LEAD por ANI+SERVICIO y los 14 indicadores FCR_x."""
    df = df.copy()
    claves = pd.DataFrame(
        {
            "_ani_nulo": es_nulo(df["ANI"]),
            "_ani": clave_collation(df["ANI"]),
            "_srv_nulo": es_nulo(df["SERVICIO"]),
            "_srv": clave_collation(df["SERVICIO"]),
            "_t": df["FECHA/HORA"],
        },
        index=df.index,
    )
    particion = ["_ani_nulo", "_ani", "_srv_nulo", "_srv"]
    # Orden estable: en empates de [FECHA/HORA] SQL Server no garantiza el
    # orden (ver docs/EQUIVALENCIA.md); aqui se conserva el de lectura.
    ordenado = claves.sort_values([*particion, "_t"], kind="mergesort")
    proximo = ordenado.groupby(particion, sort=False)["_t"].shift(-1)
    df["FECHA/HORA-PROXIMO"] = proximo.reindex(df.index)
    segundos = diferencia_segundos(df["FECHA/HORA"], df["FECHA/HORA-PROXIMO"])
    for umbral in mappings.UMBRALES:
        # NaN <= s es False -> 1, igual que la rama ELSE con DATEDIFF NULL.
        df[umbral.columna] = np.where(segundos <= umbral.segundos, 0, 1).astype("int64")
    return df


def tramo_quiebre(df: pd.DataFrame) -> pd.Series:
    """CASE WHEN FCR_30min = 0 THEN 'Quiebre en 30 Min' WHEN ... ELSE 'Sin Quiebre' END."""
    condiciones = [df[u.columna].to_numpy() == 0 for u in mappings.UMBRALES]
    etiquetas = [u.tramo for u in mappings.UMBRALES]
    return pd.Series(np.select(condiciones, etiquetas, default=mappings.SIN_QUIEBRE), index=df.index, dtype=object)


def transformar(extraidos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Las 5 bases -> filas de TBL_FCR, columnas en orden de posicion."""
    partes = [calcular_fcr(preparar_base(extraidos[b.tabla_temporal], b)) for b in mappings.BASES]
    union = pd.concat(partes, ignore_index=True)
    union["TRAMO_QUIEBRE"] = tramo_quiebre(union)
    return union[list(mappings.NOMBRES_DESTINO)]
