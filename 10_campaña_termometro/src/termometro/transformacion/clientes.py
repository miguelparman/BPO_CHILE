"""
Reemplaza el Data Flow 'BASE TERMOMETRO':
  Origen de Excel 1 -> Columna derivada -> Conversión de datos -> OLE DB Destination

Columna derivada original (SSIS expression language):
  RUT_SIN_DV = REPLACE(RUT_DV, "-", "")
  RUT        = RIGHT("0000000000" + LEFT(RUT_SIN_DV, LEN(RUT_SIN_DV) - 1), 10)
  PERIODO    = @[User::Periodo]

Es decir: RUT_SIN_DV le quita el guion; RUT además le quita el dígito
verificador (último carácter) y rellena con ceros a la izquierda hasta 10 dígitos.

CONFIRMADO contra el esquema real de TBL_CAMPAÑA_TERMOMETRO_SOURCE:
  - La columna se llama "TENTA FO" (con espacio), no "TENTA_FO" (guion bajo)
    como viene en el Excel -- se renombra explícitamente más abajo.
  - La tabla también tiene una columna SUB_SEGME que el Excel de clientes no
    trae. Se deja fuera del INSERT a propósito (queda NULL): el SQL final de
    todas formas toma SUB_SEGME desde el cruce con CL_CARTERA, no desde aquí.
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Columnas de origen (Excel) que se castean a texto
_TEXT_SOURCE_COLUMNS = ["RUT_DV", "NOMCLI", "NOM_SM", "NOM_SUP", "SEGME", "RUT", "RUT_SIN_DV", "TENTA_FO"]

# Renombre confirmado contra INFORMATION_SCHEMA.COLUMNS de TBL_CAMPAÑA_TERMOMETRO_SOURCE
RENAME_MAP = {"TENTA_FO": "TENTA FO"}

# Columnas que realmente se insertan (nombres ya en formato destino)
OUTPUT_COLUMNS = [
    "RUT_DV",
    "NOMCLI",
    "NOM_SM",
    "NOM_SUP",
    "SEGME",
    "RUT",
    "RUT_SIN_DV",
    "TENTA FO",
    "PERIODO",
]


def transform_clientes(df: pd.DataFrame, periodo: int) -> pd.DataFrame:
    df = df.copy()

    df["RUT_SIN_DV"] = df["RUT_DV"].astype("string").str.replace("-", "", regex=False)
    df["RUT"] = df["RUT_SIN_DV"].str[:-1].str.zfill(10)
    df["PERIODO"] = periodo

    # Data Convert -> texto (wstr) para estas columnas.
    # OJO: usar dtype "string" (nullable), NO astype(str) -- astype(str) convierte
    # celdas vacías/NaN en el texto literal "nan", ensuciando la tabla destino.
    for col in _TEXT_SOURCE_COLUMNS:
        df[col] = df[col].astype("string").str.strip()

    df = df.rename(columns=RENAME_MAP)

    faltantes = set(OUTPUT_COLUMNS) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas en el Excel de clientes: {faltantes}")

    return df[OUTPUT_COLUMNS]
