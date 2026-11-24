"""
(Agregado al ETL, no existe en el .dtsx original.)
Hoja 'VALIDADOR_SM' de ACTUAL_.xlsx -> TBL_CAMPAÑA_TERMOMETRO_VALIDADOR_SM.

Se carga completa (todas las columnas de la hoja). Luego 70_update_validador_sm.sql
la cruza con la tabla final por PERIODO y PLACE = ID_GENESYS_SM_TITULAR y
reemplaza NOM_SM y cod_dni (DNI).

Reglas:
  - Todo se trata como texto (el DNI no debe perder ceros iniciales).
  - Se descartan filas sin PERIODO o sin PLACE.
  - Duplicados de PERIODO + PLACE: se emite un aviso y se conserva solo una (la última).
  - Aviso (no se corrige) si algún DNI tiene menos de 8 dígitos: señal de un cero inicial perdido en el Excel.
"""
import logging

import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["PERIODO", "PLACE", "RUT_SM", "DNI", "NOM_SM", "MAIL_SM", "MAIL_FRACTALIA"]
LLAVE = ["PERIODO", "PLACE"]
LARGO_DNI = 8


def transform_validador_sm(df: pd.DataFrame) -> pd.DataFrame:
    faltantes = set(OUTPUT_COLUMNS) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas en la hoja VALIDADOR_SM: {sorted(faltantes)}")

    df = df[OUTPUT_COLUMNS].copy()
    for col in OUTPUT_COLUMNS:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)

    sin_llave = df[LLAVE].isna().any(axis=1)
    if sin_llave.any():
        logger.warning("VALIDADOR_SM: %d fila(s) sin PERIODO o PLACE se descartan", int(sin_llave.sum()))
        df = df[~sin_llave]

    dup = df.duplicated(LLAVE, keep="last")
    if dup.any():
        claves = df.loc[df.duplicated(LLAVE, keep=False), LLAVE].drop_duplicates()
        logger.warning(
            "VALIDADOR_SM: %d fila(s) duplicadas por PERIODO+PLACE; se conserva solo la última. Claves: %s",
            int(dup.sum()),
            [tuple(r) for r in claves.itertuples(index=False)],
        )
        df = df[~dup]

    cortos = df["DNI"].notna() & (df["DNI"].str.len() < LARGO_DNI)
    if cortos.any():
        logger.warning(
            "VALIDADOR_SM: %d DNI con menos de %d dígitos (posible cero inicial perdido en el Excel; "
            "guardar la columna como Texto). PLACE: %s",
            int(cortos.sum()), LARGO_DNI, df.loc[cortos, "PLACE"].tolist(),
        )

    return df.reset_index(drop=True)
