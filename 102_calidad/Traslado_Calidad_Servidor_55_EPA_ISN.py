import pyodbc
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

BATCH_SIZE = 5000

conn_origin = pyodbc.connect(
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=sqlclu01lis01.tchile.local;"
    "DATABASE=Externos_Frac;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
    autocommit=True
)

conn_destination = pyodbc.connect(
    f"DRIVER={{{_resolver_driver()}}};"
    "SERVER=172.17.0.162;"
    "DATABASE=CL_TEMPORALES_INDICADORES;"
    f"UID={os.environ['DB_USER']};"
    f"PWD={os.environ['DB_PASSWORD']}",
    autocommit=False  # transacción única: todo o nada
)

column_list = (
    "id_encuesta_registro, INFORME, tipo_encuesta, nom_encuesta, pcrc, skill_agente, ani_evento, ani_encuesta, "
    "id_conn, segundos_encuesta, periodo_evento, dia_evento, hora_evento, periodo_envio, dia_envio, hora_envio, "
    "periodo_encuesta, dia_encuesta, hora_encuesta, p1, p2, p3, p4, p5, p6, r1, r2, r3, r4, r5, r6, c1, c2, c3, "
    "c4, c5, c6, rGLOBAL, cGLOBAL, rNPS, cNPS, rEJECUTIVO, cEJECUTIVO, encuestas_ok, fl_calificacion, "
    "fl_detractor, fl_neutro, fl_promotor, id_proveedor, NEGOCIO, PROCESO_NIVEL1, PROCESO_NIVEL2, PROCESO_NIVEL3, "
    "PROCESO_NIVEL4, PROCESO_NIVEL5, EMPRESA, ZONA, REGION, COMUNA, AGENCIA, SUBSEGMENTO, TIPO_CONTRATO, PRODUCTO, "
    "TECNOLOGIA, RUT_CLIENTE, NOMBRE_CLIENTE, RUT_EJECUTIVO, NOMBRE_EJECUTIVO, RUT_TECNICO, NOMBRE_TECNICO, "
    "id_agente, GERENCIA, SUBGERENCIA, fecha_de_encuesta, año_encuesta, mes_encuesta, año_evento, mes_evento, "
    "fecha_de_evento, tipificacion, vq, ENDING_TYPE, IV, pcrc_agente"
)

placeholders = ', '.join(['?'] * len(column_list.split(',')))
insert_query = f"INSERT INTO TBL_ENCUESTAS_CHILE ({column_list}) VALUES ({placeholders})"

try:
    cursor_origin = conn_origin.cursor()
    cursor_destination = conn_destination.cursor()
    cursor_destination.fast_executemany = True

    cursor_origin.execute("SELECT COUNT(*) FROM ENCUESTA WHERE periodo_evento >= 202601")
    total = cursor_origin.fetchone()[0]
    print(f"Total de filas a transferir: {total:,}")

    cursor_origin.execute("SELECT * FROM ENCUESTA WHERE periodo_evento >= 202601")
    insertados = 0
    inicio = time.time()

    while True:
        lote = cursor_origin.fetchmany(BATCH_SIZE)
        if not lote:
            break
        cursor_destination.executemany(insert_query, lote)
        insertados += len(lote)
        elapsed = time.time() - inicio
        pct = insertados / total * 100
        velocidad = insertados / elapsed if elapsed > 0 else 0
        restante = (total - insertados) / velocidad if velocidad > 0 else 0
        print(f"  {pct:5.1f}%  |  {insertados:,} / {total:,} filas  |  {elapsed:.1f}s  |  ~{restante:.1f}s restantes")

    conn_destination.commit()

    cursor_destination.execute("SELECT COUNT(*) FROM TBL_ENCUESTAS_CHILE WHERE periodo_evento >= 202601")
    total_destino = cursor_destination.fetchone()[0]

    print(f"\nTransferencia completada en {time.time() - inicio:.1f}s.")
    print(f"Registros en tabla fuente: {total:,}")
    print(f"Registros copiados en tabla destino: {total_destino:,}")
    time.sleep(3)

except Exception as e:
    conn_destination.rollback()
    print(f"\nError durante la transferencia: {e}")
    raise

finally:
    cursor_origin.close()
    cursor_destination.close()
    conn_origin.close()
    conn_destination.close()
