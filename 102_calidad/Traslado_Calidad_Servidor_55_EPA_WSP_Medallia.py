import pyodbc
import math
import re
import time


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

BATCH_SIZE = 5000

FLOAT_SUFFIX_RE = re.compile(r'^-?\d+\.0$')

def clean_row(row, max_lengths=None, float_suffix_indices=None):
    cleaned = []
    for i, value in enumerate(row):
        if value is None:
            cleaned.append(None)
        elif isinstance(value, float) and math.isnan(value):
            cleaned.append(None)
        elif isinstance(value, str) and value.lower() == 'nan':
            cleaned.append(None)
        elif isinstance(value, str) and float_suffix_indices and i in float_suffix_indices and FLOAT_SUFFIX_RE.match(value):
            cleaned.append(value[:-2])
        elif isinstance(value, str) and max_lengths and max_lengths[i] is not None and len(value) > max_lengths[i]:
            cleaned.append(value[:max_lengths[i]])
        else:
            cleaned.append(value)
    return tuple(cleaned)


# Conexión al servidor de origen
#conn_origin = pyodbc.connect(
#    "DRIVER={ODBC Driver 17 for SQL Server};"
#    "SERVER=18.230.10.223;"
#    "DATABASE=Externos_Frac;"
#    "UID=BPOSERV;"
#    "PWD=<ver .env>",
#    autocommit=True
#)

conn_origin = pyodbc.connect(
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=sqlclu01lis01.tchile.local;"
    "DATABASE=Externos_Frac;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
    autocommit=True
)

# fast_executemany acelera drásticamente los inserts masivos
conn_destination = pyodbc.connect(
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=172.17.0.162;"
    "DATABASE=CL_TEMPORALES_INDICADORES;"
    f"UID={os.environ['DB_USER']};"
    f"PWD={os.environ['DB_PASSWORD']}",
    autocommit=False
)
conn_destination.autocommit = False

cursor_origin = conn_origin.cursor()
cursor_destination = conn_destination.cursor()
cursor_destination.fast_executemany = True

# Truncar la tabla de destino
cursor_destination.execute("TRUNCATE TABLE [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_WSP_MEDALLIA]")
conn_destination.commit()
print("Tabla truncada exitosamente.")

column_list = [
    "SurveyID", "TipoDeEncuesta", "Responsedate", "Unit",
    "SurveyProgram", "Subtype", "connid", "NPS",
    "Facilidad", "ISN", "verbatim", "Periodo",
    "pcrc_eac", "loginid", "vq", "tipificacion",
    "cnps", "cglobal", "cejecutivo", "rutcli",
    "RequerimientoSolucionado"
]

placeholders = ','.join(['?' for _ in column_list])

select_query = f"""
SELECT {', '.join(column_list)}
FROM Externos_Frac.dbo.WS_MEDALLIA_2
"""

insert_query = f"""
INSERT INTO [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_WSP_MEDALLIA]
({', '.join(column_list)})
VALUES ({placeholders})
"""

# Obtener tipo y largo máximo de cada columna en destino. Esto se usa para:
# 1) truncar valores que excedan el ancho real de la columna, y
# 2) fijar con setinputsizes el tamaño de buffer de cada parámetro, porque
#    fast_executemany infiere el tamaño del buffer a partir del primer valor
#    que ve en el lote; si una fila posterior trae un string más largo,
#    revienta con "String data, right truncation" aunque la columna sea
#    mucho más ancha (ese fue el bug real detrás del error reportado).
cursor_destination.execute("""
    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TBL_ENCUESTAS_WSP_MEDALLIA'
""")
column_info = {
    row.COLUMN_NAME.upper(): (row.DATA_TYPE, row.CHARACTER_MAXIMUM_LENGTH)
    for row in cursor_destination.fetchall()
}

TEXT_TYPES = {'nvarchar', 'nchar', 'varchar', 'char'}

max_lengths = []
input_sizes = []
for col in column_list:
    data_type, char_len = column_info.get(col.upper(), (None, None))
    if data_type in TEXT_TYPES and isinstance(char_len, int) and char_len > 0:
        max_lengths.append(char_len)
        input_sizes.append((pyodbc.SQL_WVARCHAR, char_len, 0))
    else:
        max_lengths.append(None)
        input_sizes.append(None)

cursor_destination.setinputsizes(input_sizes)

# rutcli llega desde el origen como texto de un float (ej. "77960408.0")
# porque una exportación previa con pandas lo convirtió así. Se limpia el
# sufijo ".0" para dejar el RUT como número entero en texto ("77960408").
float_suffix_indices = {column_list.index("rutcli")}

# Obtener total de filas para calcular progreso
print("Contando registros en origen...")
cursor_origin.execute("SELECT COUNT(*) FROM Externos_Frac.dbo.WS_MEDALLIA_2")
total_rows = cursor_origin.fetchone()[0]
print(f"Total de registros a transferir: {total_rows:,}")

cursor_origin.execute(select_query)

inserted = 0
start_time = time.time()
last_pct = -1

while True:
    raw_batch = cursor_origin.fetchmany(BATCH_SIZE)
    if not raw_batch:
        break

    batch = [clean_row(row, max_lengths, float_suffix_indices) for row in raw_batch]
    cursor_destination.executemany(insert_query, batch)
    conn_destination.commit()

    inserted += len(batch)
    pct = int(inserted * 100 / total_rows)
    elapsed = time.time() - start_time
    rows_per_sec = inserted / elapsed if elapsed > 0 else 0
    eta_sec = (total_rows - inserted) / rows_per_sec if rows_per_sec > 0 else 0

    if pct != last_pct:
        print(f"  Progreso: {pct:3d}% | {inserted:,}/{total_rows:,} filas "
              f"| {rows_per_sec:,.0f} filas/s | ETA: {eta_sec:.0f}s")
        last_pct = pct

cursor_destination.execute(
    "SELECT COUNT(*) FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_WSP_MEDALLIA]"
)
registros_en_destino = cursor_destination.fetchone()[0]
print(f"Registros copiados en la tabla destino: {registros_en_destino:,}")

cursor_origin.close()
cursor_destination.close()
conn_origin.close()
conn_destination.close()

elapsed_total = time.time() - start_time
print(f"\nDatos transferidos exitosamente. "
      f"Total: {inserted:,} filas en {elapsed_total:.1f}s "
      f"({inserted / elapsed_total:,.0f} filas/s promedio)")

time.sleep(3)
