import pyodbc
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


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

# Obtener la fecha actual
hoy = datetime.today()

# Formatear la fecha actual a "YYYYMM"
periodo_actual = hoy.strftime("%Y%m")

# Restar dos meses a la fecha actual
dos_meses_atras = hoy - relativedelta(months=1)
periodo_anterior = dos_meses_atras.strftime("%Y%m")

# Si hoy es día 1, considerar el periodo dos meses atrás completo
if hoy.day <= 4:
    periodo = periodo_anterior
else:
    periodo = periodo_actual

print(periodo)

try:
    # Conexión al Servidor 55

    #conn_src = pyodbc.connect(
    #    "DRIVER={ODBC Driver 17 for SQL Server};"
    #    "SERVER=18.230.10.223;"
    #    "DATABASE=Externos_Frac;"
    #    "UID=BPOSERV;"
    #    "PWD=<ver .env>",
    #    autocommit=True
    #)
    
    conn_src = pyodbc.connect(
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=sqlclu01lis01.tchile.local;"
    "DATABASE=Externos_Frac;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
    autocommit=True
    )
    
    print("Conexión al servidor Chile exitosa.")
    #print("Conexión al servidor Fractalia exitosa.")
    
    # Conexión al segundo servidor (destino)
    conn_dest = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=172.17.0.162;"
        "DATABASE=CL_TEMPORALES;"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']}"
    )
    print("Conexión al servidor Fractalia exitosa.")
    
    # Consultas y ejecución
    cursor_src = conn_src.cursor()
    cursor_dest = conn_dest.cursor()

    # Consultar datos del servidor origen
    cursor_src.execute("SELECT * FROM [Externos_Frac].[dbo].[cross_inbound] WHERE DATE_YYYYMM >= ?", (periodo,))
    rows = cursor_src.fetchall()

    # Insertar datos en la tabla destino en el segundo servidor usando CASE WHEN
    for row in rows:
        try:
            cursor_dest.execute(
                """
                INSERT INTO [CL_TEMPORALES].[dbo].[TBL_TRAFICO_CROSS_INBOUND](
                    [DATE_YYYYMM],[DATE_YYYYMMDD],[MEDIA],[INTERACTION_TYPE],[CONNID],[CONNID_INTERACTION],[INTERACTION_ID],
                    [START_YYYYMMDD_HHMMSS],[END_YYYYMMDD_HHMMSS],[QUEUE_START_YYYYMMDD_HHMMSS],[QUEUE_END_YYYYMMDD_HHMMSS],
                    [AGENT_START_YYYYMMDD_HHMMSS],[AGENT_END_YYYYMMDD_HHMMSS],[ANI],[CALC_NUM_TELEFONO],[DNIS],[T_QUEUE],
                    [T_RING],[T_TALK],[T_HOLD_CUSTOMER],[INCOMING_TYPE],[ENDING_TYPE],[CATEGORY],[STOP_ACTION],
                    [STOP_ACTION_DESC],[PLACE],[AGENT_NAME],[AGENT_NAME_SOURCE],[AGENT_NAME_TARGET],[LOGINID],
                    [LOGINID_SOURCE],[LOGINID_TARGET],[SKILL],[SKILL_SOURCE],[SKILL_TARGET],[VIRTUAL_QUEUE],
                    [VIRTUAL_QUEUE_SOURCE],[VIRTUAL_QUEUE_TARGET],[AGENT_GROUP],[RUT_USUARIO],[BUSINESS_RESULT],
                    [PCRC_COLA],[PCRC_EAC],[CALLCENTER],[SITE],[TIPO_PCRC]
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                row.DATE_YYYYMM,row.DATE_YYYYMMDD,row.MEDIA,row.INTERACTION_TYPE,row.CONNID,row.CONNID_INTERACTION,row.INTERACTION_ID,
                row.START_YYYYMMDD_HHMMSS,row.END_YYYYMMDD_HHMMSS,row.QUEUE_START_YYYYMMDD_HHMMSS,row.QUEUE_END_YYYYMMDD_HHMMSS,
                row.AGENT_START_YYYYMMDD_HHMMSS,row.AGENT_END_YYYYMMDD_HHMMSS,row.ANI,row.CALC_NUM_TELEFONO,row.DNIS,row.T_QUEUE,
                row.T_RING,row.T_TALK,row.T_HOLD_CUSTOMER,row.INCOMING_TYPE,row.ENDING_TYPE,row.CATEGORY,row.STOP_ACTION,
                row.STOP_ACTION_DESC,row.PLACE,row.AGENT_NAME,row.AGENT_NAME_SOURCE,row.AGENT_NAME_TARGET,row.LOGINID,
                row.LOGINID_SOURCE,row.LOGINID_TARGET,row.SKILL,row.SKILL_SOURCE,row.SKILL_TARGET,row.VIRTUAL_QUEUE,
                row.VIRTUAL_QUEUE_SOURCE,row.VIRTUAL_QUEUE_TARGET,row.AGENT_GROUP,row.RUT_USUARIO,row.BUSINESS_RESULT,
                row.PCRC_COLA,row.PCRC_EAC,row.CALLCENTER,row.SITE,row.TIPO_PCRC
            )
        except pyodbc.Error as insert_err:
            print(f"Error al insertar el registro {row}: {insert_err}")

    # Confirmar las inserciones
    conn_dest.commit()
    print("Datos insertados exitosamente.")

except pyodbc.Error as e:
    print(f"Error en la conexión o en la operación SQL: {e}")

finally:
    # Cerrar conexiones
    for conn in [cursor_src, conn_src, cursor_dest, conn_dest]:
        if conn:
            conn.close()
    print("Conexiones cerradas.")
