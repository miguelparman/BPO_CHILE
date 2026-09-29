import pyodbc
import polars as pl
from pathlib import Path
from typing import Optional
from datetime import datetime
import time


# ============================================================================
# CONFIGURACIÓN
# ============================================================================
# Configuración de conexión+-
DB_CONFIG = {
    'DRIVER': '{ODBC Driver 17 for SQL Server}',
    'SERVER': '172.17.0.162',
    'DATABASE': 'CL_MOVIL',
    'UID': 'mparedes',
    'PWD': 'Abr2024.'
}

# Rutas y configuraciones
CSV_PATH = Path(r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO\Reporte_Historico_Contactos_Chile.csv")
COLUMNAS_CSV = ['Id. de historial','Nombre del cliente','Modificado por','Modificado por alias','Modificado por función','Campo / Evento','Valor anterior','Valor nuevo','Fecha de modificación','Nombre','Apellidos']
ENCODINGS = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
INFER_SCHEMA_LENGTH = 0  # No inferir schema, usar dtypes directos
BATCH_SIZE = 5000  # Tamaño de lotes para inserción

TABLE_NAME = '[CL_MOVIL].[dbo].[TBL_HISTORIAL_CONTACTOS_TEMP]'
COLUMNS = ['Id. de historial','Nombre del cliente','Modificado por','Modificado por alias','Modificado por función','Campo / Evento','Valor anterior','Valor nuevo','Fecha de modificación','Nombre','Apellidos']


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


def create_temp_table_if_missing(conn) -> bool:
    """Verifica que la tabla temporal exista sin modificar su esquema si ya está creada."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT 1
        FROM [CL_MOVIL].INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = 'TBL_HISTORIAL_CONTACTOS_TEMP'
        """)
        exists = cursor.fetchone() is not None

        if exists:
            print(f"✅ La tabla {TABLE_NAME} existe y se conservará su esquema.")
            return True

        cursor.execute(f"""
        CREATE TABLE {TABLE_NAME} (
            [Id. de historial] NVARCHAR(125) NULL,
            [Nombre del cliente] NVARCHAR(512) NULL,
            [Modificado por] NVARCHAR(256) NULL,
            [Modificado por alias] NVARCHAR(25) NULL,
            [Modificado por función] NVARCHAR(256) NULL,
            [Campo / Evento] NVARCHAR(125) NULL,
            [Valor anterior] NVARCHAR(125) NULL,
            [Valor nuevo] NVARCHAR(125) NULL,
            [Fecha de modificación] DATETIME NULL,
            [Nombre] NVARCHAR(256) NULL,
            [Apellidos] NVARCHAR(256) NULL
        );
        """)
        conn.commit()
        print(f"✅ Tabla {TABLE_NAME} creada con el esquema predeterminado.")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Error al crear/verificar tabla: {e}")
        return False
    finally:
        cursor.close()


def get_table_schema_info(conn, table_name: str = TABLE_NAME) -> dict:
    """Obtiene el esquema de columnas y tamaños de la tabla temporal."""
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT COLUMN_NAME,
               DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH
        FROM [CL_MOVIL].INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = 'TBL_HISTORIAL_CONTACTOS_TEMP'
        """)
        schema_info = {}
        for row in cursor.fetchall():
            schema_info[row[0]] = {
                'data_type': row[1],
                'max_length': row[2] if row[2] is not None else -1
            }
        return schema_info
    except Exception as e:
        print(f"❌ Error al leer esquema de tabla: {e}")
        return {}
    finally:
        cursor.close()


def normalize_value(value, column_info):
    """Ajusta el valor al tipo/longitud de la columna destino."""
    data_type = column_info.get('data_type', '').lower()
    max_length = column_info.get('max_length', -1)

    if value is None:
        if data_type in ('nvarchar', 'varchar', 'char', 'nchar', 'text', 'ntext'):
            return ''
        return None

    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8')
        except Exception:
            value = value.decode('latin-1', errors='ignore')

    if isinstance(value, str):
        stripped = value.strip()
        if stripped == '':
            if data_type in ('nvarchar', 'varchar', 'char', 'nchar', 'text', 'ntext'):
                return ''
            return None

        if data_type in ('nvarchar', 'varchar', 'char', 'nchar') and max_length > 0:
            return stripped[:max_length]

        if data_type in ('datetime', 'datetime2', 'smalldatetime', 'date', 'time', 'datetimeoffset'):
            normalized = stripped.replace('T', ' ').replace('/', '-').replace('.', ':')
            for fmt in (
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d',
                '%d-%m-%Y %H:%M:%S.%f',
                '%d-%m-%Y %H:%M:%S',
                '%d-%m-%Y %H:%M',
                '%d-%m-%Y',
                '%d/%m/%Y %H:%M:%S.%f',
                '%d/%m/%Y %H:%M:%S',
                '%d/%m/%Y %H:%M',
                '%d/%m/%Y',
                '%Y/%m/%d %H:%M:%S',
            ):
                try:
                    return datetime.strptime(normalized, fmt)
                except Exception:
                    continue
            try:
                return datetime.fromisoformat(stripped)
            except Exception:
                return stripped

    return value


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

            if 'Fecha de modificación' in df.columns:
                try:
                    df = df.with_columns(
                        pl.col('Fecha de modificación')
                        .str.strptime(pl.Datetime, fmt=None, strict=False)
                    )
                    print("✅ Columna 'Fecha de modificación' convertida a datetime en Polars")
                except Exception as e:
                    print(f"⚠️ No se pudo convertir 'Fecha de modificación' a datetime en Polars: {e}")

            return df
        except Exception:
            continue
    
    print(f"❌ No se pudo cargar el CSV con ninguna codificación probada")
    return None
    
def truncate_table(conn) -> bool:
    """Vacía la tabla TBL_HISTORIAL_CONTACTOS_Temp."""
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
    schema_info = get_table_schema_info(conn)
    if not schema_info:
        print("❌ No se pudo obtener el esquema de la tabla temporal.")
        return False

    try:
        cursor = conn.cursor()
        cursor.fast_executemany = True

        insert_sql = (
            f"INSERT INTO {TABLE_NAME} ({', '.join([f'[{col}]' for col in COLUMNAS_CSV])}) "
            f"VALUES ({', '.join(['?' for _ in COLUMNAS_CSV])})"
        )

        total = 0
        for i in range(0, len(df), batch_size):
            batch = df.slice(i, batch_size)
            params = []

            for row in batch.iter_rows(named=True):
                normalized = []
                for col in COLUMNAS_CSV:
                    value = row[col]
                    column_info = schema_info.get(col, {})
                    normalized.append(normalize_value(value, column_info))
                params.append(tuple(normalized))

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
    MERGE [CL_MOVIL].[dbo].[TBL_HISTORIAL_CONTACTOS] AS Target
    USING [CL_MOVIL].[dbo].[TBL_HISTORIAL_CONTACTOS_TEMP]	AS Source
    ON Source.[Id. de historial] COLLATE Latin1_General_100_CS_AS = Target.[Id. de historial] COLLATE Latin1_General_100_CS_AS
        
    -- For Inserts
    WHEN NOT MATCHED BY Target THEN
        INSERT ([Id. de historial],[Nombre del cliente],[Modificado por],[Modificado por alias],[Modificado por función],[Campo / Evento],[Valor anterior],[Valor nuevo],[Fecha de modificación],[Nombre],[Apellidos]) 
        VALUES (Source.[Id. de historial],Source.[Nombre del cliente],Source.[Modificado por],Source.[Modificado por alias],Source.[Modificado por función],Source.[Campo / Evento],Source.[Valor anterior],Source.[Valor nuevo],Source.[Fecha de modificación],Source.[Nombre],Source.[Apellidos])
        
    -- For Updates
    WHEN MATCHED THEN UPDATE SET
        Target.[Id. de historial]	= Source.[Id. de historial],
        Target.[Nombre del cliente]	= Source.[Nombre del cliente],
        Target.[Modificado por]	= Source.[Modificado por],
        Target.[Modificado por alias]	= Source.[Modificado por alias],
        Target.[Modificado por función]	= Source.[Modificado por función],
        Target.[Campo / Evento]= Source.[Campo / Evento],
        Target.[Valor anterior]= Source.[Valor anterior],
        Target.[Valor nuevo]	= Source.[Valor nuevo],
        Target.[Fecha de modificación]	= Source.[Fecha de modificación],
        Target.[Nombre]	= Source.[Nombre],
        Target.[Apellidos]	= Source.[Apellidos]
        ;
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
            
            # Verificar/crear tabla temporal
            if not create_temp_table_if_missing(conn):
                raise Exception("No se pudo crear o verificar la tabla temporal")

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
            
            # Truncar tabla HISTORIAL_CONTACTOS_TEMP después del MERGE
            if not truncate_table(conn):
                raise Exception("No se pudo truncar la tabla")
            
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