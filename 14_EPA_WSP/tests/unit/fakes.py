"""Dobles de prueba (fakes) para DatabaseGateway (db.py) y CsvReader
(sharepoint/reader.py).

Permiten testear el pipeline sin base de datos ni SharePoint, registrando
cada operacion en una lista de eventos compartida para poder aseverar el
ORDEN del Control Flow. No heredan de las clases concretas (duck typing).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Sequence

import pandas as pd

import mappings
import sql

# texto SQL -> nombre de la tarea del .dtsx (para eventos legibles)
_NOMBRE_SCRIPT = {
    sql.LOG_INICIO: "Log_Inicio",
    sql.SP_EPA_ISN_CHILE: "SP_EPA_ISN_CHILE",
    sql.SP_PROCESO_ENCUESTAS_MEDALLIA: "SP_PROCESO_ENCUESTAS_MEDALLIA",
    sql.LOG_FIN: "Log_Fin",
    sql.TRUNCATE_ENCUESTAS_MEDALLIA: "TRUNCATE TBL_ENCUESTAS_MEDALLIA",
}


def _nombre(sql_text: str) -> str:
    if sql_text in _NOMBRE_SCRIPT:
        return _NOMBRE_SCRIPT[sql_text]
    for t in mappings.TRASLADOS:
        if sql_text.startswith(f"DELETE FROM [dbo].[{t.tabla}]"):
            return f"DELETE {t.tabla}" + (" <desde" if "TRY_CAST" in sql_text else "")
    return sql_text[:40]


class FakeDatabaseGateway:
    def __init__(self, nombre: str, eventos: list | None = None) -> None:
        self.nombre = nombre
        self.eventos: list = eventos if eventos is not None else []
        self.inserted: dict[str, pd.DataFrame] = {}
        self.esquemas: dict[str, dict] = {}
        self.fallar_en: set[str] = set()  # nombres de tarea/tabla que deben fallar
        self.filas_que_fallan: set[int] = set()  # insert_tolerante
        self.commits = 0
        self.rollbacks = 0

    def _quizas_fallar(self, nombre: str) -> None:
        if nombre in self.fallar_en:
            raise RuntimeError(f"fallo simulado en {nombre}")

    @contextmanager
    def transaccion(self):
        self.eventos.append((self.nombre, "BEGIN"))
        try:
            yield
            self.commits += 1
            self.eventos.append((self.nombre, "COMMIT"))
        except Exception:
            self.rollbacks += 1
            self.eventos.append((self.nombre, "ROLLBACK"))
            raise

    def execute_script(self, sql_text: str, params: Sequence[Any] | None = None) -> None:
        nombre = _nombre(sql_text)
        self.eventos.append((self.nombre, nombre, tuple(params) if params else ()))
        self._quizas_fallar(nombre)

    def execute_autocommit(self, sql_text: str) -> None:
        nombre = _nombre(sql_text)
        self.eventos.append((self.nombre, nombre))
        self._quizas_fallar(nombre)

    def bulk_insert(self, table: str, df: pd.DataFrame, schema: str = "dbo", esquema=None) -> int:
        self.eventos.append((self.nombre, f"INSERT {table}", len(df)))
        self._quizas_fallar(f"INSERT {table}")
        self.inserted[table] = df
        return len(df)

    def insert_tolerante(self, table: str, df: pd.DataFrame, schema: str = "dbo"):
        self.eventos.append((self.nombre, f"INSERT FILA A FILA {table}", len(df)))
        errores = [(i, "fallo simulado") for i in range(1, len(df) + 1) if i in self.filas_que_fallan]
        self.inserted[table] = df
        return len(df) - len(errores), errores

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict:
        if table in self.esquemas:
            return self.esquemas[table]
        return dict(next(t for t in mappings.TRASLADOS if t.tabla == table).esquema)


class FakeCsvReader:
    def __init__(self, archivos: dict[str, pd.DataFrame]) -> None:
        self._archivos = archivos
        self.leidos: list[str] = []

    def read_csv(self, nombre_archivo: str) -> pd.DataFrame:
        self.leidos.append(nombre_archivo)
        if nombre_archivo not in self._archivos:
            raise FileNotFoundError(nombre_archivo)
        return self._archivos[nombre_archivo]


class FakeCarpeta:
    """Doble de sharepoint.carpeta.CarpetaSharePoint (en memoria)."""

    def __init__(self, archivos: dict[str, bytes] | None = None, falla_al_escribir: bool = False) -> None:
        self.archivos: dict[str, bytes] = dict(archivos or {})
        self.operaciones: list[tuple[str, str]] = []
        self.falla_al_escribir = falla_al_escribir
        self.folder_path = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA"

    def ruta(self, nombre: str) -> str:
        return f"{self.folder_path}/{nombre}"

    def url(self, nombre: str) -> str:
        return self.ruta(nombre)

    def leer(self, nombre: str) -> bytes:
        self.operaciones.append(("leer", nombre))
        if nombre not in self.archivos:
            raise FileNotFoundError(nombre)
        return self.archivos[nombre]

    def escribir(self, nombre: str, contenido: bytes) -> None:
        self.operaciones.append(("escribir", nombre))
        if self.falla_al_escribir:
            raise RuntimeError("Error Graph 503")
        self.archivos[nombre] = contenido

    def eliminar(self, nombre: str) -> bool:
        self.operaciones.append(("eliminar", nombre))
        return self.archivos.pop(nombre, None) is not None


def fila_encuesta(**valores) -> dict:
    """Fila de ENCUESTA.csv (todo texto) con valores validos por defecto."""
    base = {}
    for col, (tipo, _) in mappings.ENCUESTA.esquema.items():
        base[col] = "1" if tipo == "int" else ""
    base.update(
        id_encuesta_registro="100", periodo_evento="202609", fecha_de_evento="2026-09-28",
        hora_evento="10:00:00", pcrc="PLAT", EMPRESA="FRACTALIA_LIMA",
    )
    base.update(valores)
    return base


def fila_wsp(**valores) -> dict:
    """Fila de WS_MEDALLIA_2.csv (todo texto), con la columna extra HoraRespuesta."""
    base = {
        "SurveyID": "36068939", "TipoDeEncuesta": "WSP Asistido B2B", "Unit": "WSP Asistido B2B",
        "SurveyProgram": "WSP Asistido B2B", "rutcli": "77220662.0", "Subtype": "", "NPS": "10.00",
        "verbatim": "ok", "Facilidad": "5.00", "ISN": "-1.00", "Responsedate": "2026-09-19 10:56:00",
        "Periodo": "202609", "cglobal": "-1", "cnps": "1", "cejecutivo": "1",
        "pcrc_eac": "TRIADA NO CARTERIZADO MICRO", "loginid": "51030137",
        "vq": "VQ_Whatsapp", "tipificacion": "5.2 - Solicitud de baja", "HoraRespuesta": "10:56",
        "RequerimientoSolucionado": "Sí", "connid": "0009QaN8BE5S07B7",
    }
    base.update(valores)
    return base


def csv_de(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas, dtype=str)


def csvs_minimos() -> dict[str, pd.DataFrame]:
    return {
        mappings.ENCUESTA.archivo: csv_de([fila_encuesta(), fila_encuesta(id_encuesta_registro="101", periodo_evento="202608")]),
        mappings.WSP.archivo: csv_de([fila_wsp()]),
    }


def csv_medallia_df(filas: list[dict] | None = None) -> pd.DataFrame:
    """DataFrame como el que devuelve pd.read_csv(latin1, dtype=str) del export de Medallia."""
    base = {c: "x" for c in mappings.MEDALLIA.columnas}
    base.update({"Responsedate": "28-09-2026", "FECHA_EVENTO": "2026-09-23", "ID de encuesta": "1"})
    filas = filas if filas is not None else [{}]
    return pd.DataFrame([{**base, **f} for f in filas], dtype=str)
