"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usan
las capas validacion/carga.

Reutilizado de 12_trafico/13_fcr (separacion de batches 'GO', transacciones,
reconexion ante conexiones cortadas por inactividad). Agrega:
  - execute_autocommit: los procedimientos almacenados y los logs se
    ejecutan con la semantica del Connection Manager OLE DB de SSIS
    (autocommit): si un SP falla a la mitad, lo que ya confirmo queda
    confirmado (p.ej. su propio registro 'ERROR' en LOGS_PROCESOS_SQL).
  - bulk_insert(..., esquema=): fija el tamano del buffer de cada parametro
    de texto con setinputsizes (fast_executemany lo infiere del primer valor
    del lote: ese era el bug "String data, right truncation" que resolvia
    Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py).
  - insert_tolerante: INSERT fila a fila que registra y omite las filas que
    fallan (CL_Carga_de_encuestas_MEDALLIA.py).

Una instancia de DatabaseGateway equivale a un Connection Manager del .dtsx:
'162.BBDD_GENERAL', '162.CL_CALIDAD' y '162.CL_TEMPORALES_INDICADORES'.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

import numpy as np
import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CargaError

logger = logging.getLogger("epa_wsp")

# 'GO' no es T-SQL: es el separador de batches de SSMS/sqlcmd. El Execute SQL
# Task de SSIS lo interpreta y ejecuta cada batch por separado; pyodbc no, y
# falla con "Incorrect syntax near 'GO'". Se reconoce solo en su propia linea.
_GO_RE = re.compile(r"^[ \t]*GO[ \t]*(?:--[^\r\n]*)?\r?$", re.IGNORECASE | re.MULTILINE)

_TIPOS_TEXTO = {"varchar", "nvarchar", "char", "nchar"}


_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str) -> str:
    """Devuelve el driver ODBC a usar: el configurado (DB_DRIVER) si esta
    instalado en esta maquina; si no, el mas nuevo de los instalados. Evita
    tener que fijar la version en el .env de cada equipo."""
    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Driver ODBC '%s' no instalado; se usa '%s'.", nombre, candidato
            )
            return candidato
    return nombre


def dividir_en_batches(sql: str) -> list[str]:
    """Divide un script por sus separadores 'GO', igual que el Execute SQL
    Task. Descarta los batches vacios (p.ej. el que queda tras un GO final)."""
    return [b for b in (parte.strip() for parte in _GO_RE.split(sql)) if b]


def _fila_a_parametros(fila: tuple) -> tuple:
    """Sanea una fila antes de bindearla en pyodbc: NaN/NaT/pd.NA -> None (el
    driver no acepta NaN crudo) y escalares numpy -> tipo nativo de Python
    (pyodbc no los sabe describir). Mismo helper que 04_usuarios_y_retenciones/db.py."""
    saneada = []
    for valor in fila:
        if valor is None or (not isinstance(valor, (str, bytes)) and pd.isna(valor)):
            saneada.append(None)
        elif isinstance(valor, np.generic):
            saneada.append(valor.item())
        elif isinstance(valor, pd.Timestamp):
            saneada.append(valor.to_pydatetime())
        else:
            saneada.append(valor)
    return tuple(saneada)


def tamanos_parametros(columnas: Sequence[str], esquema: dict[str, tuple[str, int | None]]) -> list:
    """setinputsizes para cada columna: texto -> (SQL_WVARCHAR, largo, 0)
    (largo 0 = MAX); el resto lo infiere pyodbc (None)."""
    tamanos = []
    for col in columnas:
        tipo, largo = esquema.get(col, (None, None))
        if tipo in _TIPOS_TEXTO:
            tamanos.append((pyodbc.SQL_WVARCHAR, 0 if largo in (None, -1) else int(largo), 0))
        else:
            tamanos.append(None)
    return tamanos


def _rollback_silencioso(conn: pyodbc.Connection) -> None:
    """Rollback que no tapa el error original si la conexion ya esta caida
    (en ese caso SQL Server ya descarto la transaccion)."""
    try:
        conn.rollback()
    except pyodbc.Error as exc:
        logger.warning("No se pudo hacer rollback (conexion caida, el servidor descarta la transaccion): %s", exc)


def crear_conexion(
    settings: DbSettings,
    reintentos: int = 1,
    espera_s: float = 5,
    dormir: Callable[[float], None] = time.sleep,
    conectar: Callable[..., pyodbc.Connection] = pyodbc.connect,
) -> pyodbc.Connection:
    """Abre la conexion con el mismo reintento que los Connection Managers del
    .dtsx (ConnectRetryCount=1, ConnectRetryInterval=5): visto en la primera
    prueba, un login puede fallar puntualmente (error 4060) y funcionar al
    segundo intento."""
    conn_str = (
        f"DRIVER={{{_resolver_driver(settings.driver)}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"UID={settings.user};"
        f"PWD={settings.password};"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )
    for intento in range(reintentos + 1):
        try:
            conn = conectar(conn_str, autocommit=False)
            break
        except pyodbc.Error as exc:
            if intento >= reintentos:
                raise
            logger.warning("No se pudo conectar a %s (%s); reintento en %s s.", settings.database, exc, espera_s)
            dormir(espera_s)
    conn.timeout = 0  # sin limite por consulta: SP.EPA_ISN_CHILE tarda varios minutos
    return conn


def _consumir_resultados(cursor: pyodbc.Cursor) -> None:
    """Un batch con varias sentencias (o un SP) devuelve un resultado por
    sentencia; pyodbc solo levanta el error de una sentencia posterior a la
    primera al avanzar con nextset()."""
    while cursor.nextset():
        pass


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones que el pipeline
    necesita (Execute SQL Task y los INSERT de los scripts .py).

    Recibe una FABRICA de conexiones, no una conexion: el servidor (o la red)
    corta las conexiones inactivas (visto en 12_trafico: error 08S01 / 10054
    tras ~30 s mientras se descargaban los CSV). Antes de cada operacion FUERA
    de una transaccion se verifica la conexion con 'SELECT 1' y, si esta
    caida, se abre una nueva. Dentro de una transaccion nunca se reconecta.
    """

    def __init__(
        self, fabrica_conexion: Callable[[], pyodbc.Connection], batch_size: int = 5000, nombre: str = ""
    ) -> None:
        self._fabrica = fabrica_conexion
        self._conn: pyodbc.Connection | None = None
        self._batch_size = batch_size
        self._en_transaccion = False
        self.nombre = nombre

    # ------------------------------------------------------------------ #
    # Conexion
    # ------------------------------------------------------------------ #
    def _asegurar_conexion(self) -> pyodbc.Connection:
        if self._en_transaccion:
            return self._conn
        if self._conn is not None:
            try:
                cursor = self._conn.cursor()
                try:
                    cursor.execute("SELECT 1").fetchall()
                finally:
                    cursor.close()
                return self._conn
            except pyodbc.Error as exc:
                logger.warning("Conexion a %s caida (%s); se abre una nueva.", self.nombre or "SQL Server", exc)
                self.cerrar()
        self._conn = self._fabrica()
        return self._conn

    def cerrar(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pyodbc.Error:
                pass
            self._conn = None

    # ------------------------------------------------------------------ #
    # Transacciones
    # ------------------------------------------------------------------ #
    @contextmanager
    def transaccion(self) -> Iterator[None]:
        """Agrupa varias operaciones en una sola transaccion: commit al final
        o rollback completo si cualquiera falla."""
        if self._en_transaccion:
            yield
            return
        conn = self._asegurar_conexion()
        self._en_transaccion = True
        try:
            yield
            conn.commit()
        except Exception:
            _rollback_silencioso(conn)
            raise
        finally:
            self._en_transaccion = False

    def _commit(self) -> None:
        if not self._en_transaccion:
            self._conn.commit()

    def _rollback(self) -> None:
        if not self._en_transaccion and self._conn is not None:
            _rollback_silencioso(self._conn)

    # ------------------------------------------------------------------ #
    # Execute SQL Task
    # ------------------------------------------------------------------ #
    def execute_script(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """Ejecuta un script T-SQL completo, batch por batch (separados por
        'GO'), como el Execute SQL Task. Los parametros '?' se bindean en el
        batch que los contiene."""
        batches = dividir_en_batches(sql)
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                for i, batch in enumerate(batches, start=1):
                    if params and "?" in batch:
                        cursor.execute(batch, tuple(params))
                    else:
                        cursor.execute(batch)
                    _consumir_resultados(cursor)
                    logger.debug("batch %s/%s ejecutado", i, len(batches))
            finally:
                cursor.close()
            self._commit()
        except Exception as exc:
            self._rollback()
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc

    def execute_autocommit(self, sql: str) -> None:
        """Execute SQL Task con la semantica de SSIS (autocommit): cada
        sentencia se confirma al ejecutarse. Para los SP y los logs."""
        if self._en_transaccion:
            raise CargaError("execute_autocommit no puede usarse dentro de una transaccion")
        conn = self._asegurar_conexion()
        conn.autocommit = True
        try:
            cursor = conn.cursor()
            try:
                for batch in dividir_en_batches(sql):
                    cursor.execute(batch)
                    _consumir_resultados(cursor)
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la ejecucion del script T-SQL: {exc}") from exc
        finally:
            try:
                conn.autocommit = False
            except pyodbc.Error:
                self.cerrar()

    def fetch_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                fila = cursor.fetchone()
                return fila[0] if fila is not None else None
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta escalar: {exc}") from exc

    def run_query(self, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        """Devuelve el resultado como DataFrame de dtype 'object': los valores
        quedan tal cual los entrega pyodbc (int, str, date, datetime, None)."""
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
            finally:
                cursor.close()
        except Exception as exc:
            raise CargaError(f"Fallo la consulta: {exc}") from exc
        datos = {c: pd.Series([f[i] for f in filas], dtype=object) for i, c in enumerate(columnas)}
        return pd.DataFrame(datos, columns=columnas)

    def columnas_de_tabla(self, table: str, schema: str = "dbo") -> dict[str, tuple[str, int | None]]:
        """{columna: (tipo, largo)} segun INFORMATION_SCHEMA (largo -1 = MAX)."""
        df = self.run_query(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return {
            r.COLUMN_NAME: (r.DATA_TYPE, None if r.CHARACTER_MAXIMUM_LENGTH is None else int(r.CHARACTER_MAXIMUM_LENGTH))
            for r in df.itertuples(index=False)
        }

    # ------------------------------------------------------------------ #
    # INSERT
    # ------------------------------------------------------------------ #
    @staticmethod
    def _insert_sql(table: str, columnas: Sequence[str], schema: str) -> str:
        columnas_sql = ", ".join(f"[{c}]" for c in columnas)
        placeholders = ", ".join("?" for _ in columnas)
        return f"INSERT INTO [{schema}].[{table}] ({columnas_sql}) VALUES ({placeholders})"

    def bulk_insert(
        self,
        table: str,
        df: pd.DataFrame,
        schema: str = "dbo",
        esquema: dict[str, tuple[str, int | None]] | None = None,
    ) -> int:
        """Inserta el DataFrame completo (fast_executemany, por lotes). Dentro
        de transaccion() no hace commit por lote: todo o nada."""
        if df.empty:
            logger.info("[%s].[%s]: 0 filas para insertar.", schema, table)
            return 0

        columnas = list(df.columns)
        insert_sql = self._insert_sql(table, columnas, schema)
        try:
            cursor = self._asegurar_conexion().cursor()
            try:
                cursor.fast_executemany = True
                if esquema:
                    cursor.setinputsizes(tamanos_parametros(columnas, esquema))
                total = 0
                for inicio in range(0, len(df), self._batch_size):
                    lote = df.iloc[inicio : inicio + self._batch_size]
                    params = [_fila_a_parametros(f) for f in lote.itertuples(index=False, name=None)]
                    cursor.executemany(insert_sql, params)
                    total += len(params)
            finally:
                cursor.close()
            self._commit()
        except Exception as exc:
            self._rollback()
            raise CargaError(f"No se pudieron insertar filas en [{schema}].[{table}]: {exc}") from exc

        logger.info("%s filas insertadas en [%s].[%s].", total, schema, table)
        return total

    def insert_tolerante(self, table: str, df: pd.DataFrame, schema: str = "dbo") -> tuple[int, list[tuple[int, str]]]:
        """INSERT fila a fila en autocommit: una fila que falla se registra y
        se omite, el resto se inserta. Devuelve (insertadas, [(fila, error)])."""
        if self._en_transaccion:
            raise CargaError("insert_tolerante no puede usarse dentro de una transaccion")
        insert_sql = self._insert_sql(table, list(df.columns), schema)
        conn = self._asegurar_conexion()
        conn.autocommit = True
        errores: list[tuple[int, str]] = []
        insertadas = 0
        try:
            cursor = conn.cursor()
            try:
                for i, fila in enumerate(df.itertuples(index=False, name=None), start=1):
                    try:
                        cursor.execute(insert_sql, _fila_a_parametros(fila))
                        insertadas += 1
                    except pyodbc.Error as exc:
                        errores.append((i, str(exc)))
            finally:
                cursor.close()
        finally:
            try:
                conn.autocommit = False
            except pyodbc.Error:
                self.cerrar()
        return insertadas, errores
