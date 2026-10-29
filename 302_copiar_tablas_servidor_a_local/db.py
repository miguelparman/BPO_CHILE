"""Acceso a SQL Server: fabrica de conexiones (pyodbc) y el gateway que usa
main.py para inspeccionar el esquema de origen, crear/eliminar la tabla en el
destino y copiar los datos.

Cada tabla se identifica por su ruta completa de 3 partes
'[BASE].[schema].[tabla]', por lo que una misma conexion (un mismo servidor)
puede copiar tablas de distintas bases de datos sin reabrir la conexion: no
hace falta que 'BASE' coincida con la base de datos inicial del connection
string, todas las consultas van calificadas con el nombre completo.

Una instancia de DatabaseGateway equivale a una conexion: el proceso usa dos,
'origen' (172.17.0.162, autenticacion SQL) y 'destino' (servidor local, por
defecto con autenticacion Windows integrada).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

import pandas as pd
import pyodbc

from config import DbSettings
from exceptions import CopiaTablaError

logger = logging.getLogger("copiar_tablas")

# Tipos de columna cuya definicion SQL necesita longitud/precision/escala
# ademas del nombre para que el CREATE TABLE quede equivalente al de origen.
_TIPOS_CON_LONGITUD = {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}
_TIPOS_CON_PRECISION = {"decimal", "numeric"}
_TIPOS_CON_ESCALA_SOLO = {"datetime2", "time", "datetimeoffset"}

# 'BASE', 'schema' y 'tabla' se interpolan directamente en el texto SQL (no
# se pueden parametrizar nombres de objeto), por lo que se validan contra
# este patron antes de usarse en cualquier consulta.
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def crear_conexion(settings: DbSettings) -> pyodbc.Connection:
    """Arma la cadena de conexion: SQL Server (UID/PWD) si 'settings.user'
    esta definido, o Windows integrada (Trusted_Connection) si no lo esta.
    'settings.database' es solo la base de datos inicial de la conexion; no
    limita de que base se pueden copiar tablas (ver modulo)."""
    if settings.user:
        auth = f"UID={settings.user};PWD={settings.password};Persist Security Info=True;"
    else:
        auth = "Trusted_Connection=yes;"

    conn_str = (
        f"DRIVER={{{_resolver_driver(settings.driver)}}};"
        f"SERVER={settings.server};"
        f"DATABASE={settings.database};"
        f"{auth}"
        f"Encrypt={settings.encrypt};"
        f"TrustServerCertificate={settings.trust_server_certificate}"
    )
    return pyodbc.connect(conn_str)


def _validar_identificador(valor: str, etiqueta: str) -> str:
    if not _IDENTIFICADOR_VALIDO.match(valor):
        raise CopiaTablaError(
            f"{etiqueta} invalido: '{valor}'. Solo se permiten letras, digitos y guion bajo."
        )
    return valor


def _ruta_calificada(base: str, schema: str, tabla: str) -> str:
    _validar_identificador(base, "Nombre de base de datos")
    _validar_identificador(schema, "Nombre de schema")
    _validar_identificador(tabla, "Nombre de tabla")
    return f"[{base}].[{schema}].[{tabla}]"


def parsear_ruta_tabla(ruta: str) -> tuple[str, str, str]:
    """Parsea una ruta de 3 partes '[BASE].[schema].[tabla]' (los corchetes
    son opcionales, p.ej. 'CL_CARTERA.dbo.TBL_X' tambien es valido) en sus
    componentes ya validados."""
    partes = [parte.strip().strip("[]") for parte in ruta.strip().split(".")]
    if len(partes) != 3 or not all(partes):
        raise CopiaTablaError(
            f"Ruta de tabla invalida: '{ruta}'. Formato esperado: [BASE].[schema].[tabla]."
        )
    base, schema, tabla = partes
    return (
        _validar_identificador(base, "Nombre de base de datos"),
        _validar_identificador(schema, "Nombre de schema"),
        _validar_identificador(tabla, "Nombre de tabla"),
    )


def _tipo_sql(columna: pyodbc.Row) -> str:
    tipo = columna.tipo
    if tipo in _TIPOS_CON_LONGITUD:
        longitud = columna.max_length
        if longitud == -1:
            return f"{tipo}(MAX)"
        if tipo in ("nvarchar", "nchar"):
            longitud //= 2
        return f"{tipo}({longitud})"
    if tipo in _TIPOS_CON_PRECISION:
        return f"{tipo}({columna.precision},{columna.scale})"
    if tipo in _TIPOS_CON_ESCALA_SOLO:
        return f"{tipo}({columna.scale})"
    return tipo


def generar_create_table_sql(ruta: str, columnas: Sequence[pyodbc.Row]) -> str:
    definiciones = []
    for columna in columnas:
        partes = [f"[{columna.nombre}]", _tipo_sql(columna)]
        if columna.is_identity:
            partes.append(f"IDENTITY({int(columna.seed_value)},{int(columna.increment_value)})")
        partes.append("NULL" if columna.is_nullable else "NOT NULL")
        definiciones.append(" ".join(partes))

    columnas_sql = ",\n    ".join(definiciones)
    return f"CREATE TABLE {ruta} (\n    {columnas_sql}\n)"


class DatabaseGateway:
    """Envuelve una conexion pyodbc con las operaciones que el proceso de
    copia necesita: inspeccionar el esquema, crear/eliminar la tabla y leer o
    insertar los datos. Todos los metodos reciben (base, schema, tabla) por
    separado y arman la ruta calificada internamente."""

    def __init__(self, conn: pyodbc.Connection, batch_size: int = 5000) -> None:
        self._conn = conn
        self._batch_size = batch_size

    def base_existe(self, base: str) -> bool:
        _validar_identificador(base, "Nombre de base de datos")
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT DB_ID(?)", (base,))
            return cursor.fetchone()[0] is not None
        finally:
            cursor.close()

    def tabla_existe(self, base: str, schema: str, tabla: str) -> bool:
        ruta = _ruta_calificada(base, schema, tabla)
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT OBJECT_ID(?)", (ruta,))
            return cursor.fetchone()[0] is not None
        finally:
            cursor.close()

    def obtener_definicion_columnas(self, base: str, schema: str, tabla: str) -> list[pyodbc.Row]:
        ruta = _ruta_calificada(base, schema, tabla)
        sql = f"""
        SELECT
            c.name AS nombre,
            ty.name AS tipo,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable,
            c.is_identity,
            ic.seed_value,
            ic.increment_value
        FROM [{base}].sys.columns c
        JOIN [{base}].sys.types ty ON c.user_type_id = ty.user_type_id
        LEFT JOIN [{base}].sys.identity_columns ic
            ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE c.object_id = OBJECT_ID(?)
        ORDER BY c.column_id
        """
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(sql, (ruta,))
                columnas = cursor.fetchall()
            finally:
                cursor.close()
        except Exception as exc:
            raise CopiaTablaError(f"No se pudo leer el esquema de {ruta} en el origen: {exc}") from exc

        if not columnas:
            raise CopiaTablaError(
                f"No se encontro la tabla {ruta} en el servidor origen "
                "(¿existe la base de datos, la tabla, y hay permisos de lectura sobre sys.columns?)."
            )
        return columnas

    def crear_tabla(self, base: str, schema: str, tabla: str, columnas: Sequence[pyodbc.Row]) -> None:
        ruta = _ruta_calificada(base, schema, tabla)
        sql = generar_create_table_sql(ruta, columnas)
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(sql)
                self._conn.commit()
            finally:
                cursor.close()
        except Exception as exc:
            self._conn.rollback()
            raise CopiaTablaError(f"No se pudo crear la tabla {ruta} en el destino: {exc}") from exc

    def eliminar_tabla(self, base: str, schema: str, tabla: str) -> None:
        ruta = _ruta_calificada(base, schema, tabla)
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"DROP TABLE {ruta}")
                self._conn.commit()
            finally:
                cursor.close()
        except Exception as exc:
            self._conn.rollback()
            raise CopiaTablaError(f"No se pudo eliminar la tabla {ruta} en el destino: {exc}") from exc

    def leer_tabla(self, base: str, schema: str, tabla: str) -> pd.DataFrame:
        ruta = _ruta_calificada(base, schema, tabla)
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"SELECT * FROM {ruta}")
                columnas = [col[0] for col in cursor.description]
                filas = cursor.fetchall()
                return pd.DataFrame.from_records(filas, columns=columnas)
            finally:
                cursor.close()
        except Exception as exc:
            raise CopiaTablaError(f"No se pudo leer {ruta} en el origen: {exc}") from exc

    def insertar_datos(
        self,
        base: str,
        schema: str,
        tabla: str,
        df: pd.DataFrame,
        columnas: Sequence[pyodbc.Row],
    ) -> int:
        """Inserta el DataFrame por lotes. Activa IDENTITY_INSERT mientras
        dure la carga si la tabla tiene alguna columna identity, para
        preservar los valores originales del servidor origen."""
        ruta = _ruta_calificada(base, schema, tabla)

        if df.empty:
            logger.warning("Sin filas para copiar en %s.", ruta)
            return 0

        tiene_identity = any(columna.is_identity for columna in columnas)
        columnas_nombres = list(df.columns)
        columnas_sql = ", ".join(f"[{c}]" for c in columnas_nombres)
        placeholders = ", ".join("?" for _ in columnas_nombres)
        insert_sql = f"INSERT INTO {ruta} ({columnas_sql}) VALUES ({placeholders})"

        cursor = self._conn.cursor()
        total_insertadas = 0
        try:
            if tiene_identity:
                cursor.execute(f"SET IDENTITY_INSERT {ruta} ON")

            try:
                cursor.fast_executemany = True
            except Exception:
                pass

            try:
                for inicio in range(0, len(df), self._batch_size):
                    lote = df.iloc[inicio : inicio + self._batch_size]
                    params = [
                        tuple(None if pd.isna(valor) else valor for valor in fila)
                        for fila in lote.itertuples(index=False, name=None)
                    ]
                    cursor.executemany(insert_sql, params)
                    self._conn.commit()
                    total_insertadas += len(params)
            finally:
                if tiene_identity:
                    cursor.execute(f"SET IDENTITY_INSERT {ruta} OFF")
                    self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            raise CopiaTablaError(f"No se pudieron insertar filas en {ruta}: {exc}") from exc
        finally:
            cursor.close()

        logger.info("%s filas insertadas en %s.", total_insertadas, ruta)
        return total_insertadas
