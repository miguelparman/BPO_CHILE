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

# --- Período a procesar ---
hoy = datetime.today()
periodo_actual = hoy.strftime("%Y%m")
periodo_anterior = (hoy - relativedelta(months=1)).strftime("%Y%m")
periodo = periodo_anterior if hoy.day <= 4 else periodo_actual

print(f"Período a procesar: {periodo}")

BATCH_SIZE = 5000

INSERT_SQL = """
INSERT INTO [CL_TEMPORALES].[dbo].[TBL_TRAFICO_OUTBOUND](
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

conn_src = None
conn_dest = None
cursor_src = None
cursor_dest = None

try:
    # Conexión origen (Chile)
    conn_src = pyodbc.connect(
        f"DRIVER={{{_resolver_driver()}}};"
        "SERVER=sqlclu01lis01.tchile.local;"
        "DATABASE=Externos_Frac;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    print("Conexión al servidor Chile exitosa.")

    # Conexión destino (Fractalia)
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
    cursor_dest.fast_executemany = True  # Carga masiva optimizada (10-100x más rápido)

    # Total de registros a cargar
    cursor_src.execute(
        "SELECT COUNT(*) FROM [Externos_Frac].[dbo].[OUTBOUND] WHERE DATE_YYYYMM >= ?",
        (periodo,)
    )
    total = cursor_src.fetchone()[0]
    print(f"Total de registros a cargar: {total:,}")

    if total == 0:
        print("No hay registros para el período indicado.")
    else:
        tiempo_inicio = datetime.now()
        print(f"Inicio: {tiempo_inicio.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)

        cursor_src.execute(
            """SELECT
                [DATE_YYYYMM],[DATE_YYYYMMDD],[MEDIA],[INTERACTION_TYPE],[CONNID],[CONNID_INTERACTION],[INTERACTION_ID],
                [START_YYYYMMDD_HHMMSS],[END_YYYYMMDD_HHMMSS],[QUEUE_START_YYYYMMDD_HHMMSS],[QUEUE_END_YYYYMMDD_HHMMSS],
                [AGENT_START_YYYYMMDD_HHMMSS],[AGENT_END_YYYYMMDD_HHMMSS],[ANI],[CALC_NUM_TELEFONO],[DNIS],[T_QUEUE],
                [T_RING],[T_TALK],[T_HOLD_CUSTOMER],[INCOMING_TYPE],[ENDING_TYPE],[CATEGORY],[STOP_ACTION],
                [STOP_ACTION_DESC],[PLACE],[AGENT_NAME],[AGENT_NAME_SOURCE],[AGENT_NAME_TARGET],[LOGINID],
                [LOGINID_SOURCE],[LOGINID_TARGET],[SKILL],[SKILL_SOURCE],[SKILL_TARGET],[VIRTUAL_QUEUE],
                [VIRTUAL_QUEUE_SOURCE],[VIRTUAL_QUEUE_TARGET],[AGENT_GROUP],[RUT_USUARIO],[BUSINESS_RESULT],
                [PCRC_COLA],[PCRC_EAC],[CALLCENTER],[SITE],[TIPO_PCRC]
            FROM [Externos_Frac].[dbo].[OUTBOUND] WHERE DATE_YYYYMM >= ?""",
            (periodo,)
        )

        procesados = 0
        errores = 0

        while True:
            batch = cursor_src.fetchmany(BATCH_SIZE)
            if not batch:
                break

            try:
                params = [tuple(row) for row in batch]
                cursor_dest.executemany(INSERT_SQL, params)
                conn_dest.commit()
                procesados += len(batch)
            except pyodbc.Error as insert_err:
                conn_dest.rollback()
                errores += len(batch)
                print(f"\nError en lote ({len(batch)} filas): {insert_err}")
                print(f"  Columnas en fila: {len(batch[0])} | Placeholders INSERT: 46")

            pct = (procesados / total) * 100
            elapsed = datetime.now() - tiempo_inicio
            elapsed_str = str(elapsed).split(".")[0]
            print(
                f"\rProcesados: {procesados:,} / {total:,}  |  {pct:5.1f}%  |  Transcurrido: {elapsed_str}   ",
                end="",
                flush=True
            )

        tiempo_fin = datetime.now()
        duracion = tiempo_fin - tiempo_inicio

        print("\n" + "=" * 60)
        print(f"  Inicio      : {tiempo_inicio.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Fin         : {tiempo_fin.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Duración    : {str(duracion).split('.')[0]}")
        print(f"  Insertados  : {procesados:,}")
        if errores:
            print(f"  Con error   : {errores:,}")
        print("=" * 60)

except pyodbc.Error as e:
    print(f"\nError en la conexión o en la operación SQL: {e}")

finally:
    for obj in [cursor_src, cursor_dest, conn_src, conn_dest]:
        if obj:
            try:
                obj.close()
            except Exception:
                pass
    print("Conexiones cerradas.")
