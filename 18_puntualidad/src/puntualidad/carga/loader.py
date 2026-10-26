"""Carga: escritura en SQL Server.

  cargar_sla()          (SLA int -> decimal(10,2) si hace falta) + TRUNCA TABLA + OLE DB
                        Destination (TBL_SLA) + UPDATE, en UNA transaccion (en SSIS eran 3 tareas; aqui TBL_SLA nunca
                        queda vacia ni a medio actualizar, y es la tabla que leen
                        VIEW_SLA_4TIP/3TIP/1TIP).
  generar_puntualidad() la tarea PUNTUALIDAD (scripts_sql/puntualidad/), tambien en
                        UNA transaccion: DROP + SELECT INTO + ... Si algo falla, la
                        TBL_PUNTUALIDAD anterior queda intacta (SSIS la dejaba
                        borrada durante toda la ejecucion).
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

import sql
from db import DatabaseGateway, tamanos_parametros
from logging_setup import NOMBRE_LOGGER
from mappings import BD_SLA, COLUMNAS, NUMERIC_PRECISION, NUMERIC_SCALE, NUMERICO, TABLA_SLA, Destino

logger = logging.getLogger(NOMBRE_LOGGER)


class PuntualidadLoader:
    def __init__(self, db: DatabaseGateway, destino: Destino) -> None:
        self._db = db
        self.destino = destino

    def esquema_sla(self) -> dict[str, tuple[str, int | None]]:
        """Columnas reales de TBL_SLA (la tabla de prueba es su clon)."""
        return self._db.columnas_de_tabla(BD_SLA, TABLA_SLA)

    def cargar_sla(self, filas: Sequence[tuple]) -> int:
        columnas = tuple(c.destino for c in COLUMNAS)
        # [SLA] es decimal(10,2) en el destino (aunque la tabla real aun sea int: el ajuste la cambia en la transaccion)
        decimales = {c.destino: (NUMERIC_PRECISION, NUMERIC_SCALE) for c in COLUMNAS if c.tipo == NUMERICO}
        tamanos = tamanos_parametros(columnas, self.esquema_sla(), decimales)
        return self._db.cargar_en_transaccion(
            sql.scripts_antes_sla(self.destino),
            sql.insert_sla(self.destino, columnas),
            filas,
            tamanos,
            [sql.script_despues_sla(self.destino)],
        )

    def generar_puntualidad(self) -> int:
        """Ejecuta los scripts de puntualidad/ en una sesion nueva (las tablas
        auxiliares son #temporales) y una transaccion. Devuelve las filas de la
        tabla resultante."""
        self._db.nueva_sesion()
        inicio = time.monotonic()
        try:
            self._db.execute_transaccion(sql.scripts_puntualidad(self.destino))
        finally:
            self._db.nueva_sesion()  # libera las #temporales
        logger.info("  %s generada en %.1f s.", self.destino.tbl_puntualidad, time.monotonic() - inicio)
        return self.contar(self.destino.tbl_puntualidad)

    def contar(self, tabla: str) -> int:
        _, filas = self._db.run_query(f"SELECT COUNT(*) FROM {tabla}")
        return int(filas[0][0])
