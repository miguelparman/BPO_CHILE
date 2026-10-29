import pandas as pd
import pyodbc
import numpy as np


import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str = "ODBC Driver 17 for SQL Server") -> str:
    """Devuelve el driver ODBC a usar: el indicado si esta instalado en esta
    maquina; si no, el mas nuevo de los instalados (varia entre equipos)."""
    import pyodbc

    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            return candidato
    return nombre

# Ruta al archivo CSV
csv_file = r"D:\IRISCENE ENGINEERING CORPORATION SLU\Data Analytics Reporting Fractalia - Medallia\Encuestas_Medallia.csv"

# Leer todo como texto
df = pd.read_csv(csv_file, encoding='latin1', dtype=str)

# Reemplazar NaN por None (muy importante)
df = df.replace({np.nan: None, '': None, 'nan': None, 'None': None, 'NULL': None, 'Null': None})

# Manejo de columna duplicada
columna_original = '¿Podrías contarnos las razones de tu respuesta?'
columna_duplicada = columna_original + '.1'

if columna_duplicada in df.columns:
    df[columna_original] = df[columna_original].combine_first(df[columna_duplicada])
    df.drop(columns=[columna_duplicada], inplace=True)

# Lista de columnas esperadas
columnas = [
    'ID de encuesta',
    'Tipo de Encuesta',
    'ANI_CONTACTO',
    'Responsedate',
    'FECHA_EVENTO',
    'NPS',
    '¿Lograste resolver tu requerimiento?',
    'SAT - Asesor',
    'Facilidad de gestión',
    'SAT - Satisfacción General',
    'Estado de encuesta',
    '¿Podrías contarnos las razones de tu respuesta?',
    'ID_CLIENTE_BIEN',
    'PLATAFORMA',
    'CATEGORIA_EMPRESA',
    'NOMBRE_EMPRESA'
]

# Convertir Responsedate a datetime
df['Responsedate'] = pd.to_datetime(df['Responsedate'], format='%d-%m-%Y', errors='coerce')
df['Responsedate'] = df['Responsedate'].where(df['Responsedate'].notnull(), None)

# Forzar todo (menos la fecha) a str explícitamente
for col in columnas:
    if col != 'Responsedate':
        df[col] = df[col].astype(str).where(df[col].notnull(), None)

# Reordenar columnas
df = df[columnas]

# Mostrar información previa
print("Total de registros leídos:", len(df))
#print("Primeras 5 filas a insertar:")
#print(df.head())

# Conectar a SQL Server
conn_str = (
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=172.17.0.162;"
    "DATABASE=CL_TEMPORALES_INDICADORES;"
    f"UID={os.environ['DB_USER']};"
    f"PWD={os.environ['DB_PASSWORD']}"
)
conn = pyodbc.connect(conn_str)
conn.autocommit = True
cursor = conn.cursor()

# Truncar tabla
cursor.execute("TRUNCATE TABLE [TBL_ENCUESTAS_MEDALLIA]")

# Insertar fila por fila con control de errores
insert_query = """
    INSERT INTO [TBL_ENCUESTAS_MEDALLIA] (
        [ID de encuesta],
        [Tipo de Encuesta],
        [ANI_CONTACTO],
        [Responsedate],
        [FECHA_EVENTO],
        [NPS],
        [¿Lograste resolver tu requerimiento?],
        [SAT - Asesor],
        [Facilidad de gestión],
        [SAT - Satisfacción General],
        [Estado de encuesta],
        [¿Podrías contarnos las razones de tu respuesta?],
        [ID_CLIENTE_BIEN],
        [PLATAFORMA],
        CATEGORIA_EMPRESA,
        NOMBRE_EMPRESA
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

datos = [tuple(x) for x in df.values]
errores = 0

for i, fila in enumerate(datos):
    try:
        cursor.execute(insert_query, fila)
    except pyodbc.Error as e:
        errores += 1
        print(f"\n❌ Error en fila {i + 1}:")
        print(f"Datos: {fila}")
        print(f"Error: {e}")

print(f"\n✅ Inserción finalizada. Registros con error: {errores} / {len(df)}")

cursor.close()
conn.close()
