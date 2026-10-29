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

hoy = datetime.today()
periodo = (hoy - relativedelta(months=1)).strftime("%Y%m") if hoy.day <= 4 else hoy.strftime("%Y%m")
print(f"Período a cargar: {periodo}")


def formato_duracion(segundos):
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


BATCH_SIZE = 5000

INSERT_SQL = """
INSERT INTO [CL_TEMPORALES].[dbo].[TBL_TRAFICO_ABANDONO](
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

conn_src = conn_dest = cursor_src = cursor_dest = None

try:
    conn_src = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=sqlclu01lis01.tchile.local;"
        "DATABASE=Externos_Frac;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;",
        autocommit=True
    )
    print("Conexión al servidor TCH exitosa.")

    conn_dest = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=172.17.0.162;"
        "DATABASE=CL_TEMPORALES;"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']}"
    )
    print("Conexión al servidor FRACTALIA exitosa.")

    cursor_src = conn_src.cursor()
    cursor_dest = conn_dest.cursor()
    cursor_dest.fast_executemany = True  # carga masiva optimizada para SQL Server

    cursor_dest.execute(
        "DELETE FROM [CL_TEMPORALES].[dbo].[TBL_TRAFICO_ABANDONO] WHERE DATE_YYYYMM >= ?",
        (periodo,)
    )
    print(f"Registros previos eliminados para período >= {periodo}.")

    # Contar total de registros a cargar
    cursor_src.execute(
        "SELECT COUNT(*) FROM [Externos_Frac].[dbo].[ABANDONO] WHERE DATE_YYYYMM >= ?",
        (periodo,)
    )
    total_registros = cursor_src.fetchone()[0]
    print(f"Total de registros a cargar: {total_registros:,}")

    cursor_src.execute(
        "SELECT * FROM [Externos_Frac].[dbo].[ABANDONO] WHERE DATE_YYYYMM >= ?",
        (periodo,)
    )

    tiempo_inicio = datetime.now()
    print(f"Inicio de carga:    {tiempo_inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print("-" * 50)

    total = 0
    while True:
        rows = cursor_src.fetchmany(BATCH_SIZE)
        if not rows:
            break
        batch = [
            (
                row.DATE_YYYYMM, row.DATE_YYYYMMDD, row.MEDIA, row.INTERACTION_TYPE,
                row.CONNID, row.CONNID_INTERACTION, row.INTERACTION_ID,
                row.START_YYYYMMDD_HHMMSS, row.END_YYYYMMDD_HHMMSS,
                row.QUEUE_START_YYYYMMDD_HHMMSS, row.QUEUE_END_YYYYMMDD_HHMMSS,
                row.AGENT_START_YYYYMMDD_HHMMSS, row.AGENT_END_YYYYMMDD_HHMMSS,
                row.ANI, row.CALC_NUM_TELEFONO, row.DNIS, row.T_QUEUE,
                row.T_RING, row.T_TALK, row.T_HOLD_CUSTOMER, row.INCOMING_TYPE,
                row.ENDING_TYPE, row.CATEGORY, row.STOP_ACTION, row.STOP_ACTION_DESC,
                row.PLACE, row.AGENT_NAME, row.AGENT_NAME_SOURCE, row.AGENT_NAME_TARGET,
                row.LOGINID, row.LOGINID_SOURCE, row.LOGINID_TARGET,
                row.SKILL, row.SKILL_SOURCE, row.SKILL_TARGET,
                row.VIRTUAL_QUEUE, row.VIRTUAL_QUEUE_SOURCE, row.VIRTUAL_QUEUE_TARGET,
                row.AGENT_GROUP, row.RUT_USUARIO, row.BUSINESS_RESULT,
                row.PCRC_COLA, row.PCRC_EAC, row.CALLCENTER, row.SITE, row.TIPO_PCRC
            )
            for row in rows
        ]
        cursor_dest.executemany(INSERT_SQL, batch)
        total += len(batch)
        pct = (total / total_registros * 100) if total_registros else 0
        transcurrido = (datetime.now() - tiempo_inicio).total_seconds()
        print(f"  {total:>{len(str(total_registros))},} / {total_registros:,}  ({pct:5.1f}%)  Transcurrido: {formato_duracion(transcurrido)}")

    conn_dest.commit()

    tiempo_fin = datetime.now()
    transcurrido_total = (tiempo_fin - tiempo_inicio).total_seconds()
    print("-" * 50)
    print(f"Inicio:             {tiempo_inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Fin:                {tiempo_fin.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Tiempo transcurrido:{formato_duracion(transcurrido_total)}")
    print(f"Total filas cargadas: {total:,}")

except pyodbc.Error as e:
    print(f"Error en la conexión o en la operación SQL: {e}")
    if conn_dest:
        conn_dest.rollback()

finally:
    for obj in [cursor_src, cursor_dest, conn_src, conn_dest]:
        try:
            if obj:
                obj.close()
        except Exception:
            pass
    print("Conexiones cerradas.")
