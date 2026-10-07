import csv
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from sql_domain_auth import conectar_dominio
from tables_config import TABLES
from sharepoint.auth import get_graph_token
from sharepoint.client import SharePointClient
from sharepoint.uploader import SharePointUploader

load_dotenv()

# --- SQL Server ---
SERVER   = os.environ["SQL_SERVER"]
DATABASE = os.environ["SQL_DATABASE"]
DOMAIN   = os.environ["SQL_DOMAIN"]
USER     = os.environ["SQL_USER"]
PASSWORD = os.environ["SQL_PASSWORD"]
DRIVER   = os.environ.get("SQL_DRIVER", "ODBC Driver 17 for SQL Server")

# --- Microsoft Graph / SharePoint ---
TENANT_ID     = os.environ["TENANT_ID"]
CLIENT_ID     = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
GRAPH_TIMEOUT_MS = int(os.environ.get("GRAPH_TIMEOUT", "120000"))

SHAREPOINT_HOSTNAME   = os.environ.get("SHAREPOINT_HOSTNAME", "fractaliagroup.sharepoint.com")
SHAREPOINT_SITE_PATH  = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/ReportingFractalia")
SHAREPOINT_DRIVE_NAME = os.environ.get("SHAREPOINT_DRIVE_NAME", "Data Reporting")
SHAREPOINT_FOLDER_PATH = os.environ["SHAREPOINT_FOLDER_PATH"]

EXPORTS_DIR = Path(__file__).parent / "exports"

PERIODOS_POR_DEFECTO = 2

_TABLE_NAME_RE = re.compile(r"\[([^\]]+)\]")


def nombre_archivo(tabla: str) -> str:
    """[Externos_Frac].[dbo].[ATENDIDA] -> ATENDIDA.csv"""
    return f"{_TABLE_NAME_RE.findall(tabla)[-1]}.csv"


def ultimos_periodos(cursor, tabla: str, campo_fecha: str, n: int, es_datetime: bool = False) -> list:
    """Devuelve los codigos YYYYMM (o valores de campo_fecha) de los n
    ultimos periodos con datos.

    Si es_datetime es True, campo_fecha es un datetime completo (con hora):
    se agrupa por mes con FORMAT(..., 'yyyyMM') antes de tomar el TOP (n),
    porque los valores exactos casi nunca se repiten entre filas.
    """
    campo = f"FORMAT({campo_fecha}, 'yyyyMM')" if es_datetime else campo_fecha
    cursor.execute(
        f"SELECT DISTINCT TOP ({n}) {campo} FROM {tabla} "
        f"WHERE {campo_fecha} IS NOT NULL ORDER BY {campo} DESC"
    )
    return [fila[0] for fila in cursor.fetchall()]


def formatear_meses(meses: list) -> list:
    """Para campos datetime muestra solo la fecha, sin la hora, para que el
    aviso de estado quede compacto."""
    return [v.strftime("%Y-%m-%d") if isinstance(v, datetime) else v for v in meses]


def formatear_duracion(segundos: float) -> str:
    return str(timedelta(seconds=round(segundos)))


def exportar_tabla(cursor, tabla: str, campo_fecha: str, ruta_csv: Path, n: int, es_datetime: bool = False):
    """Exporta la tabla a CSV y devuelve (filas_totales, meses).

    meses es None si fue una descarga completa (sin date_field), o la lista
    de los n ultimos periodos filtrados; una lista vacia significa que el campo de fecha
    no tiene datos y no se genero archivo.
    """
    if campo_fecha:
        meses = ultimos_periodos(cursor, tabla, campo_fecha, n, es_datetime)
        if not meses:
            return 0, []
        placeholders = ",".join("?" for _ in meses)
        if es_datetime:
            condicion = f"FORMAT({campo_fecha}, 'yyyyMM') IN ({placeholders})"
        else:
            condicion = f"{campo_fecha} IN ({placeholders})"
        cursor.execute(f"SELECT * FROM {tabla} WHERE {condicion}", meses)
    else:
        meses = None
        cursor.execute(f"SELECT * FROM {tabla}")

    columnas = [col[0] for col in cursor.description]

    filas_totales = 0
    with ruta_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columnas)
        while True:
            filas = cursor.fetchmany(5000)
            if not filas:
                break
            writer.writerows(filas)
            filas_totales += len(filas)

    return filas_totales, meses


def main():
    EXPORTS_DIR.mkdir(exist_ok=True)
    inicio_total = time.perf_counter()

    print(f"Conectando a {SERVER}/{DATABASE} como {DOMAIN}\\{USER}...")
    conn = conectar_dominio(SERVER, DATABASE, DOMAIN, USER, PASSWORD, driver=DRIVER)

    print("Autenticando contra Microsoft Graph / SharePoint...")
    token = get_graph_token(TENANT_ID, CLIENT_ID, CLIENT_SECRET, GRAPH_TIMEOUT_MS)
    client = SharePointClient(token, GRAPH_TIMEOUT_MS)
    target = client.resolve_target(
        SHAREPOINT_HOSTNAME, SHAREPOINT_SITE_PATH, SHAREPOINT_DRIVE_NAME, SHAREPOINT_FOLDER_PATH
    )
    uploader = SharePointUploader(token, target.drive_id, target.folder_id, GRAPH_TIMEOUT_MS)

    resumen = []
    try:
        cursor = conn.cursor()
        for tabla_cfg in TABLES:
            tabla = tabla_cfg["table"]
            campo_fecha = tabla_cfg["date_field"]
            es_datetime = tabla_cfg.get("is_datetime", False)
            n = tabla_cfg.get("periods", PERIODOS_POR_DEFECTO)
            ruta_csv = EXPORTS_DIR / nombre_archivo(tabla)

            print(f"[{datetime.now():%H:%M:%S}] INICIO  {tabla}")
            inicio = time.perf_counter()
            filas_totales = 0
            try:
                if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                    raise ValueError(f"periods invalido: {n!r} (debe ser entero >= 1)")
                filas_totales, meses = exportar_tabla(cursor, tabla, campo_fecha, ruta_csv, n, es_datetime)
                if meses == []:
                    estado = "SIN DATOS"
                else:
                    uploader.upload(ruta_csv)
                    estado = "OK (tabla completa)" if meses is None else f"OK ({n} periodos: {formatear_meses(meses)})"
            except Exception as exc:
                estado = f"ERROR: {exc}"

            duracion = time.perf_counter() - inicio
            resumen.append((tabla, estado, filas_totales, duracion))
            print(
                f"[{datetime.now():%H:%M:%S}] FIN     {tabla} - {estado} "
                f"- {filas_totales} filas - {formatear_duracion(duracion)}"
            )
    finally:
        conn.close()

    duracion_total = time.perf_counter() - inicio_total
    ok = sum(1 for _, estado, _, _ in resumen if estado.startswith("OK"))

    print("\nResumen general")
    print("-" * 90)
    for tabla, estado, filas, duracion in resumen:
        print(f"  {tabla:50} {filas:>8} filas  {formatear_duracion(duracion):>10}  {estado}")
    print("-" * 90)
    print(f"Tablas procesadas: {len(resumen)} | OK: {ok} | Con problemas: {len(resumen) - ok}")
    print(f"Tiempo total: {formatear_duracion(duracion_total)}")


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
