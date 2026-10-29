import pyodbc
import polars as pl
from pathlib import Path
from typing import Optional


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

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
DB_CONFIG = {
    'DRIVER': '{' + _resolver_driver() + '}',
    'SERVER': '172.17.0.162',
    'DATABASE': 'CL_FACTURACION',
    'UID': os.environ['DB_UID'],
    'PWD': os.environ['DB_PWD'],
    'Encrypt': 'no',
    'TrustServerCertificate': 'yes'
}

EXCEL_PATH = Path(r"D:\OneDrive - IRISCENE ENGINEERING CORPORATION SLU\Insumos Chile\Informes\NC\DB\NC_.xlsx")
TABLE_NAME = '[CL_FACTURACION].[dbo].[TBL_NC_Temp]'
COLUMNS = ['RUT', 'RAZON_SOCIAL', 'FOLIO_NC', 'FECHA_NC', 'NETO_NC', 'IVA_NC', 'TOTAL_NC', 'EJECUTIVO']

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================
def get_connection():
    """Crea y retorna una conexión a SQL Server."""
    try:
        conn_str = ';'.join([f'{k}={v}' for k, v in DB_CONFIG.items()])
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"❌ Error de conexión a SQL Server: {e}")
        raise

def truncate_table(conn) -> bool:
    """Vacía la tabla TBL_NC_Temp."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"TRUNCATE TABLE {TABLE_NAME}")
        conn.commit()
        print(f"✅ Tabla {TABLE_NAME} truncada correctamente.")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al truncar tabla: {e}")
        return False
    finally:
        cursor.close()

def read_and_clean_excel(file_path: Path) -> Optional[pl.DataFrame]:
    """Lee el archivo Excel, elimina últimas 3 filas y valida datos."""
    try:
        df = pl.read_excel(file_path)
        print(f"✅ Archivo leído: {len(df)} filas")

        # Eliminar últimas 3 filas
        if len(df) >= 3:
            df = df.slice(0, len(df) - 3)
        else:
            print("⚠️ Archivo tiene menos de 3 filas")

        print(f"✅ Después de limpiar: {len(df)} filas")
        return df

    except Exception as e:
        print(f"❌ Error al leer Excel: {e}")
        return None

def convert_data_types(df: pl.DataFrame) -> Optional[pl.DataFrame]:
    """Convierte los tipos de datos del DataFrame."""
    try:
        type_mapping = {
            "RUT": pl.String,
            "RAZON_SOCIAL": pl.String,
            "FOLIO_NC": pl.String,
            "FECHA_NC": pl.Date,
            "NETO_NC": pl.Float64,
            "IVA_NC": pl.Float64,
            "TOTAL_NC": pl.Float64,
            "EJECUTIVO": pl.String
        }

        for col, dtype in type_mapping.items():
            df = df.with_columns(pl.col(col).cast(dtype))

        print("✅ Tipos de datos convertidos correctamente")
        return df

    except Exception as e:
        print(f"❌ Error al convertir tipos de datos: {e}")
        return None

def insert_data_batch(conn, df: pl.DataFrame, batch_size: int = 100) -> bool:
    """Inserta datos en lotes (más eficiente que uno por uno)."""
    try:
        cursor = conn.cursor()
        # Habilitar fast_executemany si está disponible (mejora rendimiento con pyodbc)
        try:
            cursor.fast_executemany = True
        except Exception:
            pass

        insert_sql = f"""
                    INSERT INTO {TABLE_NAME}
                    ({', '.join([f'[{col}]' for col in COLUMNS])})
                    VALUES ({', '.join(['?' for _ in COLUMNS])})
                    """

        for i in range(0, len(df), batch_size):
            batch = df.slice(i, batch_size)
            # Construir lista de tuplas de parámetros para executemany
            params = [tuple(row[col] for col in COLUMNS) for row in batch.iter_rows(named=True)]
            if not params:
                continue

            cursor.executemany(insert_sql, params)
            conn.commit()
            print(f"📦 Lote {i//batch_size + 1}: {len(batch)} filas insertadas")

        print(f"✅ {len(df)} filas insertadas correctamente en {TABLE_NAME}")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Error al insertar datos: {e}")
        return False
    finally:
        cursor.close()

def verify_data(conn) -> bool:
    """Verifica que los datos se insertaron correctamente."""
    try:
        query = f"""
        SELECT COUNT(*) as total,
               MIN(FECHA_NC) as fecha_min,
               MAX(FECHA_NC) as fecha_max
        FROM {TABLE_NAME}
        """

        result = pl.read_database(query=query, connection=conn)
        print(f"\n✅ Verificación de datos:")
        #print(result)
        return True

    except Exception as e:
        print(f"❌ Error al verificar datos: {e}")
        return False

# ============================================================================
# FLUJO PRINCIPAL
# ============================================================================
if __name__ == "__main__":
    conn = None
    try:
        # Conexión
        conn = get_connection()

        # Truncar tabla
        if not truncate_table(conn):
            raise Exception("No se pudo truncar la tabla")

        # Leer y limpiar Excel
        df = read_and_clean_excel(EXCEL_PATH)
        if df is None or df.is_empty():
            raise Exception("No hay datos para insertar")

        # Convertir tipos
        df = convert_data_types(df)
        if df is None:
            raise Exception("No se pudieron convertir los tipos de datos")

        # Insertar datos
        if not insert_data_batch(conn, df):
            raise Exception("No se pudieron insertar los datos")

        # Verificar
        verify_data(conn)

        print("\n✅ ¡PROCESO COMPLETADO EXITOSAMENTE!")

    except Exception as e:
        print(f"\n❌ Error general: {e}")

    finally:
        if conn:
            conn.close()
            print("✅ Conexión cerrada")
