import pyodbc
from datetime import datetime
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

BATCH_SIZE = 2000

# Determinar periodo
hoy = datetime.today()
periodo_actual = hoy.strftime("%Y%m")
periodo_anterior = (hoy - relativedelta(months=1)).strftime("%Y%m")
periodo = periodo_anterior if hoy.day <= 4 else periodo_actual
print(f"Periodo: {periodo}")

INSERT_SQL = """
    INSERT INTO [CL_TEMPORALES].[dbo].[TBL_TRAFICO_TRANSFER](
        [DATE_YYYYMM],[DATE_YYYYMMDD],[MEDIA],[INTERACTION_TYPE],[CONNID],[CONNID_INTERACTION],[INTERACTION_ID],
        [START_YYYYMMDD_HHMMSS],[END_YYYYMMDD_HHMMSS],[QUEUE_START_YYYYMMDD_HHMMSS],[QUEUE_END_YYYYMMDD_HHMMSS],
        [AGENT_START_YYYYMMDD_HHMMSS],[AGENT_END_YYYYMMDD_HHMMSS],[ANI],[CALC_NUM_TELEFONO],[DNIS],[T_QUEUE],
        [T_RING],[T_TALK],[T_HOLD_CUSTOMER],[INCOMING_TYPE],[ENDING_TYPE],[CATEGORY],[STOP_ACTION],
        [STOP_ACTION_DESC],[PLACE],[AGENT_NAME],[AGENT_NAME_SOURCE],[AGENT_NAME_TARGET],[LOGINID],
        [LOGINID_SOURCE],[LOGINID_TARGET],[SKILL],[SKILL_SOURCE],[SKILL_TARGET],[VIRTUAL_QUEUE],
        [VIRTUAL_QUEUE_SOURCE],[VIRTUAL_QUEUE_TARGET],[AGENT_GROUP],[RUT_USUARIO],[BUSINESS_RESULT],
        [PCRC_COLA],[PCRC_EAC],[CALLCENTER],[SITE],[TIPO_PCRC]
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

COLS = [
    "DATE_YYYYMM","DATE_YYYYMMDD","MEDIA","INTERACTION_TYPE","CONNID","CONNID_INTERACTION","INTERACTION_ID",
    "START_YYYYMMDD_HHMMSS","END_YYYYMMDD_HHMMSS","QUEUE_START_YYYYMMDD_HHMMSS","QUEUE_END_YYYYMMDD_HHMMSS",
    "AGENT_START_YYYYMMDD_HHMMSS","AGENT_END_YYYYMMDD_HHMMSS","ANI","CALC_NUM_TELEFONO","DNIS","T_QUEUE",
    "T_RING","T_TALK","T_HOLD_CUSTOMER","INCOMING_TYPE","ENDING_TYPE","CATEGORY","STOP_ACTION",
    "STOP_ACTION_DESC","PLACE","AGENT_NAME","AGENT_NAME_SOURCE","AGENT_NAME_TARGET","LOGINID",
    "LOGINID_SOURCE","LOGINID_TARGET","SKILL","SKILL_SOURCE","SKILL_TARGET","VIRTUAL_QUEUE",
    "VIRTUAL_QUEUE_SOURCE","VIRTUAL_QUEUE_TARGET","AGENT_GROUP","RUT_USUARIO","BUSINESS_RESULT",
    "PCRC_COLA","PCRC_EAC","CALLCENTER","SITE","TIPO_PCRC"
]

cursor_src = cursor_dest = conn_src = conn_dest = None

try:
    conn_src = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=sqlclu01lis01.tchile.local;"
        "DATABASE=Externos_Frac;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;",
        autocommit=True
    )
    print("Conexion al servidor Chile exitosa.")

    conn_dest = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=172.17.0.162;"
        "DATABASE=CL_TEMPORALES;"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']}"
    )
    print("Conexion al servidor FRACTALIA exitosa.")

    cursor_src = conn_src.cursor()
    cursor_dest = conn_dest.cursor()
    cursor_dest.fast_executemany = True

    # Total de registros
    cursor_src.execute(
        "SELECT COUNT(*) FROM [Externos_Frac].[dbo].[TRANSFER] WHERE DATE_YYYYMM >= ?", (periodo,)
    )
    total = cursor_src.fetchone()[0]
    print(f"Total de registros a cargar: {total:,}")

    if total == 0:
        print("No hay registros para cargar.")
    else:
        inicio = datetime.now()
        print(f"Inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")

        cursor_src.execute(
            "SELECT * FROM [Externos_Frac].[dbo].[TRANSFER] WHERE DATE_YYYYMM >= ?", (periodo,)
        )

        insertados = 0
        errores = 0

        while True:
            rows = cursor_src.fetchmany(BATCH_SIZE)
            if not rows:
                break

            batch = [tuple(getattr(r, c) for c in COLS) for r in rows]
            try:
                cursor_dest.executemany(INSERT_SQL, batch)
                conn_dest.commit()
                insertados += len(batch)
            except pyodbc.Error as e:
                conn_dest.rollback()
                errores += len(batch)
                print(f"  Error en lote (registros {insertados+1}-{insertados+len(batch)}): {e}")

            pct = insertados / total * 100
            elapsed = datetime.now() - inicio
            print(f"  Progreso: {insertados:,}/{total:,} ({pct:.1f}%) | Tiempo: {str(elapsed).split('.')[0]}", end="\r")

        fin = datetime.now()
        elapsed_total = fin - inicio
        print()
        print(f"Fin:              {fin.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Tiempo transcurrido: {str(elapsed_total).split('.')[0]}")
        print(f"Registros insertados: {insertados:,}")
        if errores:
            print(f"Registros con error:  {errores:,}")

except pyodbc.Error as e:
    print(f"Error en la conexion o en la operacion SQL: {e}")

finally:
    for obj in [cursor_src, conn_src, cursor_dest, conn_dest]:
        try:
            if obj:
                obj.close()
        except Exception:
            pass
    print("Conexiones cerradas.")
