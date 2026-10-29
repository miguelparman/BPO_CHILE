import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pyodbc


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


# ============================================================
# CONFIGURACIÓN DE AZURE SQL
# ============================================================

SERVER = "sqlclu01lis01.tchile.local"
DATABASE = "Externos_Frac"


# ============================================================
# CONFIGURACIÓN DE LA TABLA
# ============================================================

SCHEMA_NAME = "dbo"
TABLE_NAME = "ENCUESTA"

# IMPORTANTE:
# Cambiar por el nombre real de la columna que contiene
# la fecha y hora del registro.
DATE_COLUMN = "Fecha_de_evento"
TIME_COLUMN = "hora_evento"

# ============================================================
# CONFIGURACIÓN DEL ARCHIVO TXT
# ============================================================

TXT_PATH = Path(
    r"D:\IRISCENE ENGINEERING CORPORATION SLU\Gestión Indicadores MDS - Cl_encuesta\resultado.txt"
)

# Tiempo de espera entre la eliminación y recreación del archivo.
# Esto ayuda a que OneDrive y Power Automate detecten la eliminación.
SEGUNDOS_ESPERA = 30


# ============================================================
# REGLA DE VALIDACIÓN
# ============================================================

# La tabla debe tener registros posteriores o iguales
# a las 17:00 del día anterior.
HORA_LIMITE = 17
MINUTO_LIMITE = 0


# ============================================================
# CONEXIÓN A AZURE SQL
# ============================================================

def obtener_conexion():
    """
    Crea y devuelve una conexión a Azure SQL.
    """

    connection_string = (
        f"DRIVER={{{_resolver_driver()}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    print("🔌 Conectando a Azure SQL...")

    conexion = pyodbc.connect(connection_string)

    print("✅ Conexión establecida correctamente.")

    return conexion


# ============================================================
# ELIMINACIÓN DEL TXT ANTERIOR
# ============================================================

def eliminar_txt_existente():
    """
    Elimina resultado.txt si ya existe.

    Después espera unos segundos para que OneDrive sincronice
    la eliminación antes de volver a crear el archivo.
    """

    TXT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if TXT_PATH.exists():
        TXT_PATH.unlink()

        print(f"🗑️ Archivo anterior eliminado: {TXT_PATH}")
        print(
            f"⏳ Esperando {SEGUNDOS_ESPERA} segundos "
            "antes de recrear el archivo..."
        )

        time.sleep(SEGUNDOS_ESPERA)

    else:
        print("ℹ️ No existe un resultado.txt anterior para eliminar.")


# ============================================================
# OBTENER LA FECHA MÁXIMA
# ============================================================

def obtener_fecha_maxima(conexion):
    """
    Consulta la fecha y hora máxima combinando las columnas
    de fecha y hora de la tabla.
    """

    consulta = f"""
        SELECT
            MAX(
                DATEADD(
                    SECOND,
                    DATEDIFF(SECOND, '00:00:00', [{TIME_COLUMN}]),
                    CAST([{DATE_COLUMN}] AS datetime)
                )
            ) AS fecha_maxima
        FROM [{SCHEMA_NAME}].[{TABLE_NAME}];
    """

    print(
        f"🔎 Consultando fecha y hora máxima "
        f"([{DATE_COLUMN}] + [{TIME_COLUMN}]) "
        f"de [{SCHEMA_NAME}].[{TABLE_NAME}]..."
    )

    cursor = conexion.cursor()

    try:
        cursor.execute(consulta)
        resultado = cursor.fetchone()

        if resultado is None or resultado.fecha_maxima is None:
            return None

        return resultado.fecha_maxima

    finally:
        cursor.close()


# ============================================================
# CALCULAR LA FECHA LÍMITE
# ============================================================

def obtener_fecha_limite():
    """
    Calcula la fecha límite de validación.

    Reglas:
    - Lunes: valida el viernes a las 18:00.
    - Martes a domingo: valida el día anterior a las 18:00.
    """

    hoy = datetime.now().date()

    # weekday():
    # Lunes = 0
    # Martes = 1
    # ...
    # Domingo = 6

    if hoy.weekday() == 0:  # Lunes
        fecha_referencia = hoy - timedelta(days=3)  # Viernes
        
    else:
        fecha_referencia = hoy - timedelta(days=1)  # Día anterior

    fecha_limite = datetime.combine(
        fecha_referencia,
        datetime.min.time()
    ).replace(
        hour=HORA_LIMITE,
        minute=MINUTO_LIMITE,
        second=0,
        microsecond=0
    )

    return fecha_limite


# ============================================================
# GENERAR MENSAJE
# ============================================================

def generar_mensaje(fecha_maxima, fecha_limite):
    """
    Genera el mensaje que será guardado en resultado.txt.
    El estado aparece al inicio y el icono al final de la primera línea.
    """

    nombre_tabla = f"{SCHEMA_NAME}.{TABLE_NAME}"
    fecha_validacion = datetime.now()

    fecha_limite_texto = fecha_limite.strftime("%d/%m/%Y %H:%M:%S")
    fecha_validacion_texto = fecha_validacion.strftime("%d/%m/%Y %H:%M:%S")

    # No se encontraron registros válidos
    if fecha_maxima is None:
        return (
            "TABLA ENCUESTA DESACTUALIZADA ⚠️\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            "- Último registro: No se encontraron fechas válidas\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla no contiene registros válidos "
            "en la columna evaluada.\n\n"
            #"Acción: Revisar la ejecución del proceso ETL."
        )

    fecha_maxima = convertir_a_datetime(fecha_maxima)
    fecha_maxima_texto = fecha_maxima.strftime("%d/%m/%Y %H:%M:%S")

    # Tabla actualizada
    if fecha_maxima >= fecha_limite:
        return (
            "TABLA ENCUESTA ACTUALIZADA ✅\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            f"- Último registro: {fecha_maxima_texto}\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla contiene registros posteriores "
            "o iguales a la fecha mínima esperada."
        )

    # Tabla desactualizada
    return (
        "TABLA ENCUESTA DESACTUALIZADA ⚠️\n\n"
        f"- Tabla: {nombre_tabla}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Último registro: {fecha_maxima_texto}\n"
        f"- Fecha mínima esperada: {fecha_limite_texto}\n"
        f"- Fecha de validación: {fecha_validacion_texto}\n\n"
        "Resultado: No se encontraron registros posteriores "
        "o iguales a la fecha mínima esperada..\n\n"
        #"Acción: Revisar la ejecución del proceso ETL."
    )


# ============================================================
# CONVERTIR FECHA
# ============================================================

def convertir_a_datetime(valor):
    """
    Convierte el valor obtenido desde SQL Server a datetime.
    """

    if isinstance(valor, datetime):
        return valor

    if hasattr(valor, "to_pydatetime"):
        return valor.to_pydatetime()

    return datetime.fromisoformat(str(valor))


# ============================================================
# CREAR EL TXT
# ============================================================

def guardar_resultado(mensaje):
    """
    Crea nuevamente resultado.txt.

    Se utiliza UTF-8 con BOM para mejorar la compatibilidad
    con OneDrive, Power Automate y los caracteres especiales.
    """

    TXT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(TXT_PATH, "w", encoding="utf-8-sig") as archivo:
        archivo.write(mensaje)

    print(f"📄 Archivo creado correctamente: {TXT_PATH}")


# ============================================================
# GENERAR TXT DE ERROR
# ============================================================

def generar_txt_error(detalle_error):
    """
    Genera resultado.txt cuando ocurre un error.
    El estado aparece al inicio y el icono al final.
    """

    nombre_tabla = f"{SCHEMA_NAME}.{TABLE_NAME}"
    fecha_validacion_texto = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    mensaje_error = (
        "ERROR EN LA VALIDACIÓN ❌\n\n"
        f"- Tabla: {nombre_tabla}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Fecha de validación: {fecha_validacion_texto}\n\n"
        "Resultado: No fue posible completar la validación.\n\n"
        f"Detalle técnico: {detalle_error}\n\n"
        "Acción: Revisar la conexión a Azure SQL, las credenciales, "
        "el nombre de la tabla y la columna de fecha."
    )

    try:
        guardar_resultado(mensaje_error)
    except Exception as error_txt:
        print(
            "❌ Tampoco fue posible generar resultado.txt: "
            f"{error_txt}"
        )

    return mensaje_error


# ============================================================
# PROCESO PRINCIPAL
# ============================================================

def main():
    conexion = None

    try:
        print("=" * 70)
        print("🚀 INICIANDO VALIDACIÓN DE ACTUALIZACIÓN DE TABLA")
        print("=" * 70)

        # 1. Eliminar el TXT anterior
        eliminar_txt_existente()

        # 2. Calcular las 18:00 del día anterior
        fecha_limite = obtener_fecha_limite()

        print(
            "🕕 Fecha mínima esperada: "
            f"{fecha_limite.strftime('%d/%m/%Y %H:%M:%S')}"
        )

        # 3. Conectar a Azure SQL
        conexion = obtener_conexion()

        # 4. Consultar la fecha máxima
        fecha_maxima = obtener_fecha_maxima(conexion)

        if fecha_maxima is not None:
            fecha_maxima_convertida = convertir_a_datetime(fecha_maxima)

            print(
                "📅 Fecha máxima encontrada: "
                f"{fecha_maxima_convertida.strftime('%d/%m/%Y %H:%M:%S')}"
            )
        else:
            print("⚠️ No se encontró una fecha máxima válida.")

        # 5. Generar mensaje
        mensaje = generar_mensaje(
            fecha_maxima=fecha_maxima,
            fecha_limite=fecha_limite
        )

        # 6. Crear nuevamente resultado.txt
        guardar_resultado(mensaje)

        print()
        print("=" * 70)
        print(mensaje)
        print("=" * 70)
        print("✅ Proceso finalizado correctamente.")

        return 0

    except pyodbc.Error as error_bd:
        print("❌ Error al conectar o consultar Azure SQL.")

        mensaje_error = generar_txt_error(error_bd)

        print()
        print(mensaje_error)

        return 1

    except Exception as error:
        print(f"❌ Error general durante la ejecución: {error}")

        mensaje_error = generar_txt_error(error)

        print()
        print(mensaje_error)

        return 1

    finally:
        if conexion is not None:
            conexion.close()
            print("🔒 Conexión a Azure SQL cerrada.")


# ============================================================
# EJECUCIÓN
# ============================================================

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
    sys.exit(main())