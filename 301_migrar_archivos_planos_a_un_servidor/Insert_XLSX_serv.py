import pandas as pd
import pyodbc
import os
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

# ==============================
# CONFIGURACIÓN
# ==============================

RUTA_XLSX  = r"D:\Descargas\Prueba\Perdida_Real_9333_clientes.xlsx"
HOJA       = "Hoja1"
SERVER     = "172.17.0.162"
DATABASE   = "CL_PRUEBA"
USUARIO    = os.environ['DB_USER']
PASSWORD   = os.environ['DB_PASSWORD']
TABLA      = "tbl_Perdida_Real_9333_clientes"

# ==============================
# FUNCIONES
# ==============================

def map_dtype(series):
    """Mapea el dtype de una columna pandas a su equivalente en SQL Server."""
    dtype = str(series.dtype)

    if "int" in dtype:
        max_val = series.dropna().abs().max() if len(series.dropna()) > 0 else 0
        return "BIGINT" if max_val > 2_147_483_647 else "INT"

    elif "float" in dtype:
        return "FLOAT"

    elif "datetime" in dtype:
        return "DATETIME"

    elif "bool" in dtype:
        return "BIT"

    else:
        # Columna de texto — calcular longitud máxima real
        max_len = series.dropna().astype(str).str.len().max()
        if pd.isna(max_len) or max_len == 0:
            max_len = 50
        if max_len > 2000:
            return "NVARCHAR(MAX)"
        return f"NVARCHAR({int(max_len) + 10})"


def leer_xlsx(ruta, hoja):
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta}")

    df = pd.read_excel(ruta, sheet_name=hoja, engine="openpyxl")

    # Normalizar nombres de columnas (sin espacios ni caracteres problemáticos)
    df.columns = [str(c).strip() for c in df.columns]

    # Reemplazar cadenas vacías y NaN por None (NULL en SQL)
    df = df.replace(r'^\s*$', None, regex=True)
    df = df.where(pd.notnull(df), None)

    print(f"Filas leídas: {len(df)} | Columnas: {list(df.columns)}")
    return df


def crear_tabla(cursor, df, tabla):
    cols_sql = []
    print("\nMapeo de tipos detectados:")

    for col in df.columns:
        tipo_sql = map_dtype(df[col])
        cols_sql.append(f"[{col}] {tipo_sql}")
        print(f"  {col:40s} -> {tipo_sql}")

    ddl = f"""
    IF OBJECT_ID('{tabla}', 'U') IS NOT NULL
        DROP TABLE {tabla};

    CREATE TABLE {tabla} (
        {',\n        '.join(cols_sql)}
    );
    """

    cursor.execute(ddl)
    print(f"\nTabla '{tabla}' creada correctamente.")


def insertar_datos(cursor, df, tabla):
    cols = ", ".join([f"[{col}]" for col in df.columns])
    placeholders = ", ".join(["?" for _ in df.columns])
    insert_sql = f"INSERT INTO {tabla} ({cols}) VALUES ({placeholders})"

    # Convertir a lista de tuplas; los datetime los convierte a native Python
    data = []
    for row in df.itertuples(index=False, name=None):
        fila = []
        for val in row:
            if isinstance(val, pd.Timestamp):
                fila.append(val.to_pydatetime() if not pd.isnull(val) else None)
            else:
                fila.append(val)
        data.append(fila)

    cursor.fast_executemany = True
    cursor.executemany(insert_sql, data)
    print(f"{len(data)} filas insertadas en '{tabla}'.")


# ==============================
# FLUJO PRINCIPAL
# ==============================

def main():
    conn_str = (
        f"DRIVER={{{_resolver_driver()}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USUARIO};"
        f"PWD={PASSWORD};"
        "Encrypt=no;"
    )

    df = leer_xlsx(RUTA_XLSX, HOJA)

    with pyodbc.connect(conn_str) as conn:
        with conn.cursor() as cursor:
            crear_tabla(cursor, df, TABLA)
            insertar_datos(cursor, df, TABLA)
            conn.commit()

    print("\nProceso finalizado con éxito.")


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes
    import sys
    from pathlib import Path

    carpeta = Path(__file__).resolve().parent
    nombre = carpeta.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    main()
