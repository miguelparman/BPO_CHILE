"""
Reemplaza el Data Flow 'TBL_CAMPAÑA_TERMOMETRO_SF_TEMP_2':
  Reporte_termometro_v2 (CSV) -> Conversión de datos -> Columna derivada -> OLE DB Destination

Columna derivada:
  PERIODO = @[User::Periodo]

CONFIRMADO contra el esquema real de TBL_CAMPAÑA_TERMOMETRO_SF_TEMP
(INFORMATION_SCHEMA.COLUMNS):

  CSV real                                          -> Columna destino confirmada
  ---------------------------------------------------------------------------
  "No. identificación fiscal"                       -> "No  identificación fiscal" (doble espacio)
  "Plan de acción: Caso"                             -> "Plan de acción  Caso" (doble espacio)
  "Plan de acción: Creado por"                       -> igual (con dos puntos, SIN cambio)
  "11. Satisfacción general", etc.                   -> igual (con punto, sin cambio)
  "ISC (...): Ref.", "ISC (...): Fecha de creación"  -> igual (sin cambio)

  Columnas del CSV que NO EXISTEN en la tabla destino (se descartan, insertarlas
  causaría un error de "columna inválida"):
    - "Nombre del cliente"
    - "Subsegmento local"
    - "Supervisor Nivel 2"
    - "Plan de acción: Plan de acción"
    - "Plan de acción: Estado"

  "Estado" y "Peso" SÍ existen en la tabla, pero a propósito NO se cargan aquí:
  en el paquete original quedan NULL después del Data Flow y se calculan
  después con los Execute SQL Task "UPDATE ESTADO" / "UPDATE PESO". Si los
  cargáramos aquí, esas actualizaciones (que filtran por "WHERE Estado IS
  NULL") dejarían de aplicar.

TAMBIÉN CORREGIDO: 'Promedio del termómetro' usa coma como separador decimal
("10,00", "6,77") -- si se convierte directo con pd.to_numeric sin reemplazar
la coma, todo el campo queda NaN.
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

RENAME_MAP = {
    "No. identificación fiscal": "No  identificación fiscal",
    "Plan de acción: Caso": "Plan de acción  Caso",
}

TEXT_COLUMNS = [
    "No  identificación fiscal",
    "1. Oferta Comercial",
    "2. Instalación",
    "3. Facturación",
    "4. Cobranza",
    "5. Soporte Técnico Fijo",
    "6. Soporte Técnico Móvil",
    "7. Recambio de equipo",
    "8. Atención postventa",
    "9. Cobertura móvil",
    "10. Canal de autoatención web",
    "12. Expectativas",
    "13. Empresa Perfecta",
    "Comentarios",
    "ISC (Índice de Satisfacción del Cliente): Ref.",
    "Plan de acción: Creado por",
    "Plan de acción  Caso",
]
DATE_COLUMNS = ["Fecha de la encuesta", "ISC (Índice de Satisfacción del Cliente): Fecha de creación"]
INT_COLUMNS = ["11. Satisfacción general", "14. Probabilidad de recomendación"]
NUMERIC_COMMA_COLUMNS = ["Promedio del termómetro"]  # usa coma decimal en el archivo real

# Columnas que realmente existen en TBL_CAMPAÑA_TERMOMETRO_SF_TEMP y se cargan
# en este paso (Estado y Peso se excluyen a propósito, ver docstring)
OUTPUT_COLUMNS = [
    "No  identificación fiscal",
    "Fecha de la encuesta",
    "Promedio del termómetro",
    "1. Oferta Comercial",
    "2. Instalación",
    "3. Facturación",
    "4. Cobranza",
    "5. Soporte Técnico Fijo",
    "6. Soporte Técnico Móvil",
    "7. Recambio de equipo",
    "8. Atención postventa",
    "9. Cobertura móvil",
    "10. Canal de autoatención web",
    "11. Satisfacción general",
    "12. Expectativas",
    "13. Empresa Perfecta",
    "14. Probabilidad de recomendación",
    "Comentarios",
    "PERIODO",
    "ISC (Índice de Satisfacción del Cliente): Ref.",
    "Plan de acción: Creado por",
    "ISC (Índice de Satisfacción del Cliente): Fecha de creación",
    "Plan de acción  Caso",
]


def transform_encuestas(df: pd.DataFrame, periodo: int) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=RENAME_MAP)

    for col in TEXT_COLUMNS:
        if col in df.columns:
            # dtype "string" (nullable), no astype(str) -- ver nota en transformacion/clientes.py
            df[col] = df[col].astype("string").str.strip()

    for col in DATE_COLUMNS:
        if col in df.columns:
            # formato real observado: DD-MM-YYYY (ej. "23-07-2026")
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    for col in INT_COLUMNS:
        if col in df.columns:
            # valores como "No evaluado" se vuelven NaN (coerce), igual que
            # pasaría si el Data Convert de SSIS fallara ese cast a entero
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in NUMERIC_COMMA_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].str.replace(",", ".", regex=False), errors="coerce"
            )

    df["PERIODO"] = periodo

    faltantes = set(OUTPUT_COLUMNS) - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas en el CSV de Salesforce: {faltantes}")

    return df[OUTPUT_COLUMNS]
