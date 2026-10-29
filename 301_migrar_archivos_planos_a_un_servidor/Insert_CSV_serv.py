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
# FUNCIONES
# ==============================

def map_dtype(series):
    dtype = series.dtype

    if "int" in str(dtype):
        return "INT"
    elif "float" in str(dtype):
        return "FLOAT"
    elif "datetime" in str(dtype):
        return "DATETIME"
    else:
        max_len = series.astype(str).str.len().max()

        if pd.isna(max_len):
            max_len = 50

        if max_len > 2000:
            return "NVARCHAR(MAX)"
        else:
            return f"NVARCHAR({int(max_len) + 10})"

def leer_y_limpiar_csv(ruta_csv):
    if not os.path.exists(ruta_csv):
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_csv}")

    df = pd.read_csv(
        ruta_csv,
        sep=";",
        encoding="utf-8"
    )

    # Reemplazar valores inválidos
    df = df.replace(r'^\s*$', None, regex=True)
    df = df.replace(['nan', np.nan], None)

    print(f"Filas leídas: {len(df)}")
    return df

def crear_tabla(cursor, df, tabla):
    cols_sql = []

    for col in df.columns:
        tipo_sql = map_dtype(df[col])
        cols_sql.append(f"[{col}] {tipo_sql}")

    create_table_sql = f"""
    IF OBJECT_ID('{tabla}', 'U') IS NOT NULL
        DROP TABLE {tabla};

    CREATE TABLE {tabla} (
        {', '.join(cols_sql)}
    )
    """

    cursor.execute(create_table_sql)
    print("Tabla creada correctamente")

def insertar_datos(cursor, df, tabla):
    cols = ", ".join([f"[{col}]" for col in df.columns])
    placeholders = ", ".join(["?" for _ in df.columns])

    insert_sql = f"INSERT INTO {tabla} ({cols}) VALUES ({placeholders})"

    data = df.where(pd.notnull(df), None).values.tolist()

    cursor.fast_executemany = True
    cursor.executemany(insert_sql, data)
    print("Datos insertados correctamente")

# ==============================
# FLUJO PRINCIPAL
# ==============================

def main():
    # Configuración
    ruta_csv = r"D:\OneDrive - IRISCENE ENGINEERING CORPORATION SLU\Insumos Chile\Informes\RETENCIONES\Registros retención primera linea\INTENCIONES.csv"
    server = "172.17.0.162"
    database = "CL_USUARIOS"
    usuario = os.environ['DB_USER']
    password = os.environ['DB_PASSWORD']
    tabla = "TBL_RETENCION_PRIMERA_LINEA"

    conn_str = (
        f"DRIVER={{{_resolver_driver()}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={usuario};"
        f"PWD={password};"
        "Encrypt=no;"
    )

    # Leer y limpiar CSV
    df = leer_y_limpiar_csv(ruta_csv)

    # Ajustar fechas si existe
    if "fecha_opn" in df.columns:
        df["fecha_opn"] = pd.to_datetime(df["fecha_opn"], errors="coerce")

    # Conectar e insertar
    with pyodbc.connect(conn_str) as conn:
        with conn.cursor() as cursor:
            crear_tabla(cursor, df, tabla)
            insertar_datos(cursor, df, tabla)
            conn.commit()

    print("Proceso finalizado con éxito")

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