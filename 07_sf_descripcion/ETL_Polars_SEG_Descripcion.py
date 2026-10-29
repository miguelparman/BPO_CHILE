import pyodbc
import polars as pl
from pathlib import Path
from typing import Optional
from datetime import datetime
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


# ============================================================================
# CONFIGURACIÓN
# ============================================================================
# Configuración de conexión+-
DB_CONFIG = {
    'DRIVER': '{' + _resolver_driver() + '}',
    'SERVER': '172.17.0.162',
    'DATABASE': 'CL_TEMPORALES',
    'UID': os.environ['DB_USER'],
    'PWD': os.environ['DB_PASSWORD']
}

# Rutas y configuraciones
CSV_PATH = Path(r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO\Reporte_Descripciones_Chile.csv")
COLUMNAS_CSV = ['Número del caso', 'Descripción']
ENCODINGS = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
INFER_SCHEMA_LENGTH = 0  # No inferir schema, usar dtypes directos
BATCH_SIZE = 5000  # Tamaño de lotes para inserción

TABLE_NAME = '[CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_TEMP]'
COLUMNS = ['Número del caso', 'Descripción']


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================
def get_connection() -> pyodbc.Connection:
    """Crea y retorna una conexión a SQL Server."""
    try:
        conn_str = ';'.join([f'{k}={v}' for k, v in DB_CONFIG.items()])
        conn = pyodbc.connect(conn_str)
        print("✅ Conexión exitosa a SQL Server")
        return conn
    except Exception as e:
        print(f"❌ Error de conexión: {e} | Servidor: {DB_CONFIG['SERVER']} | Usuario: {DB_CONFIG['UID']}")
        raise


def test_connection() -> bool:
    """Prueba la conexión a la base de datos."""
    try:
        with get_connection() as conn:
            conn.cursor().execute("SELECT 1")
        print("✅ Prueba de conexión completada exitosamente")
        return True
    except Exception as e:
        print(f"❌ Prueba de conexión fallida: {e}")
        return False


def load_csv(file_path: Path, columnas: list = None, encodings: list = None) -> Optional[pl.DataFrame]:
    """Carga el archivo CSV de forma optimizada para grandes volúmenes."""
    import time
    
    if not file_path.exists():
        print(f"❌ El archivo no existe: {file_path}")
        return None
    
    columnas = columnas or COLUMNAS_CSV
    encodings = encodings or ENCODINGS
    schema_overrides = {col: pl.String for col in columnas}
    
    inicio = time.time()
    
    for encoding in encodings:
        try:
            df = pl.read_csv(
                file_path, 
                separator=",", 
                quote_char='"', 
                encoding=encoding,
                columns=columnas,
                schema_overrides=schema_overrides,
                infer_schema_length=INFER_SCHEMA_LENGTH,
                ignore_errors=False
            )
            duracion = time.time() - inicio
            print(f"✅ CSV cargado con {encoding}: {df.shape[0]} filas × {df.shape[1]} columnas en {duracion:.2f}s")
            return df
        except Exception:
            continue
    
    print(f"❌ No se pudo cargar el CSV con ninguna codificación probada")
    return None
    
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

def insert_data_batch(conn, df: pl.DataFrame, batch_size: int = None) -> bool:
    """Inserta datos en lotes usando bulk insert (más eficiente)."""
    batch_size = batch_size or BATCH_SIZE
    try:
        cursor = conn.cursor()
        # Usar fast_executemany para mejorar rendimiento en inserciones masivas
        cursor.fast_executemany = True

        insert_sql = (
            f"INSERT INTO {TABLE_NAME} ({', '.join([f'[{col}]' for col in COLUMNAS_CSV])}) "
            f"VALUES ({', '.join(['?' for _ in COLUMNAS_CSV])})"
        )

        total = 0
        for i in range(0, len(df), batch_size):
            batch = df.slice(i, batch_size)

            # Construir lista de tuplas de parámetros
            params = [tuple(row[col] for col in COLUMNAS_CSV) for row in batch.iter_rows(named=True)]

            if params:
                cursor.executemany(insert_sql, params)
                conn.commit()
                total += len(params)
                print(f"📦 Lote {i//batch_size + 1}: {len(params)} filas insertadas")

        print(f"✅ {total} filas insertadas correctamente en {TABLE_NAME}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al insertar datos: {e}")
        return False
    finally:
        cursor.close()


def execute_merge_operation(conn) -> bool:
    """Ejecuta la operación MERGE para sincronizar datos entre tablas."""
    merge_query = """
    -- MERGE
    MERGE [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES] AS Target
    USING [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_TEMP]	AS Source
    ON Source.[Número del caso] = Target.[Número del caso]
        
    -- For Inserts
    WHEN NOT MATCHED BY Target THEN
        INSERT ([Número del caso],[Descripción]) 
        VALUES (Source.[Número del caso], Source.[Descripción])
        
    -- For Updates
    WHEN MATCHED THEN UPDATE SET
        Target.[Descripción]	= Source.[Descripción];
    """
    
    try:
        cursor = conn.cursor()
        cursor.execute(merge_query)
        conn.commit()
        
        # Obtener el número de registros afectados
        rows_affected = cursor.rowcount
        print(f"✅ Operación MERGE completada exitosamente")
        print(f"   Registros afectados: {rows_affected}")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en la operación MERGE: {e}")
        return False
    finally:
        cursor.close()

# ============================================================================
# FLUJO PRINCIPAL
# ============================================================================
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
    MAX_INTENTOS = 3
    intento = 0
    proceso_exitoso = False
    
    while intento < MAX_INTENTOS and not proceso_exitoso:
        intento += 1
        
        # Registro de tiempos
        hora_inicio = datetime.now()
        tiempo_inicio = time.time()
        
        print("=" * 80)
        print(f"⏰ PROCESO INICIADO (Intento {intento}/{MAX_INTENTOS}): {hora_inicio.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        try:
             # Conexión
            conn = get_connection()
            # Cargar CSV
            print("\n📁 Cargando CSV...")
            df = load_csv(CSV_PATH)
            if df is None:
                raise Exception("No se pudo cargar el CSV")
            
            #print(f"\n📊 Información del DataFrame: {df.shape[0]} filas × {df.shape[1]} columnas")
            #print(f"   Tipos: {df.dtypes}")
            #print(f"\n📋 Primeras 5 filas:\n{df.head()}")

            # Prueba de conexión
            print("\n🔗 Probando conexión a SQL Server...")
            if test_connection():
                print("✅ El script está listo para usar")
            else:
                raise Exception("Fallo en la prueba de conexión")
            
            # Truncar tabla
            if not truncate_table(conn):
                raise Exception("No se pudo truncar la tabla")
            
            # Insertar datos
            if not insert_data_batch(conn, df):
                raise Exception("No se pudieron insertar los datos")
            
            # Ejecutar operación MERGE
            print("\n🔄 Ejecutando operación MERGE...")
            if not execute_merge_operation(conn):
                raise Exception("Falló la operación MERGE")
            
            # Registro de finalización exitosa
            hora_fin = datetime.now()
            tiempo_fin = time.time()
            duracion_segundos = tiempo_fin - tiempo_inicio
            
            # Convertir a horas, minutos y segundos
            horas = int(duracion_segundos // 3600)
            minutos = int((duracion_segundos % 3600) // 60)
            segundos = int(duracion_segundos % 60)
            
            print("\n" + "=" * 80)
            print(f"✅ PROCESO COMPLETADO EXITOSAMENTE (Intento {intento}/{MAX_INTENTOS})")
            print(f"⏰ Hora de inicio:  {hora_inicio.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏰ Hora de fin:     {hora_fin.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏱️  Duración total:  {horas}h {minutos}m {segundos}s ({duracion_segundos:.2f} segundos)")
            print("=" * 80)
            
            proceso_exitoso = True

        except Exception as e:
            hora_fin = datetime.now()
            tiempo_fin = time.time()
            duracion_segundos = tiempo_fin - tiempo_inicio
            
            # Convertir a horas, minutos y segundos
            horas = int(duracion_segundos // 3600)
            minutos = int((duracion_segundos % 3600) // 60)
            segundos = int(duracion_segundos % 60)
            
            print("\n" + "=" * 80)
            print(f"❌ Error (Intento {intento}/{MAX_INTENTOS}): {e}")
            print(f"⏰ Hora de inicio:  {hora_inicio.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏰ Hora de error:   {hora_fin.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏱️  Duración hasta error: {horas}h {minutos}m {segundos}s ({duracion_segundos:.2f} segundos)")
            
            if intento < MAX_INTENTOS:
                print(f"\n🔄 Reintentando... ({MAX_INTENTOS - intento} intentos restantes)")
                print("=" * 80)
                time.sleep(2)  # Esperar 2 segundos antes de reintentar
            else:
                print(f"\n⛔ Se alcanzó el máximo de intentos ({MAX_INTENTOS})")
                print("=" * 80)