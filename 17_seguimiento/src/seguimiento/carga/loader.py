"""Carga: Execute SQL Tasks (T-SQL literal del .dtsx, redirigido a las
#temporales), carga de las staging en #temporales de la sesion del paquete,
y la carga de TBL_DESCRIPCIONES_NC (permanente: la lee SP_FOLIOS_NC).

Un paquete = una sesion (ver db.py): iniciar_paquete() abre la sesion y toma
su DATEFORMAT por defecto, que se restablece antes de cada tarea (en SSIS
cada tarea abria su propia conexion y no heredaba los SET de la anterior).
"""

from __future__ import annotations

from typing import Sequence

import sql
from db import DatabaseGateway, tamanos_parametros
from exceptions import CargaError
from mappings import (
    BD_STAGING,
    COLUMNAS_DESCRIPCIONES_NC,
    SP_FOLIOS_NC,
    TABLA_DESCRIPCIONES_NC,
    FlujoSpec,
)


class SeguimientoLoader:
    def __init__(self, db: DatabaseGateway) -> None:
        self._db = db
        self._esquemas: dict[str, dict[str, tuple[str, int | None]]] = {}
        self._sesion: int | None = None
        self._dateformat = "mdy"

    def esquema(self, tabla: str) -> dict[str, tuple[str, int | None]]:
        """Columnas reales de [CL_TEMPORALES].[dbo].[tabla] (cacheado por corrida)."""
        if tabla not in self._esquemas:
            self._esquemas[tabla] = self._db.columnas_de_tabla(BD_STAGING, tabla)
        return self._esquemas[tabla]

    # ------------------------------------------------------------------ #
    # Sesion del paquete
    # ------------------------------------------------------------------ #
    def iniciar_paquete(self) -> None:
        self._db.nueva_sesion()
        _, filas = self._db.run_query("SELECT date_format FROM sys.dm_exec_sessions WHERE session_id = @@SPID")
        self._dateformat = filas[0][0]
        self._sesion = self._db.sesion

    def _verificar_sesion(self) -> None:
        if self._sesion is None or self._db.sesion != self._sesion:
            raise CargaError(
                "La conexion se reabrio durante el paquete y las #temporales de la sesion se perdieron; "
                "vuelva a ejecutar el paquete."
            )

    def _restablecer(self) -> None:
        self._verificar_sesion()
        self._db.execute_autocommit(f"SET DATEFORMAT {self._dateformat}")
        self._verificar_sesion()

    # ------------------------------------------------------------------ #
    # Tareas
    # ------------------------------------------------------------------ #
    def ejecutar_sql(self, script: str) -> int:
        """Execute SQL Task."""
        self._restablecer()
        filas = self._db.execute_autocommit(sql.a_temporal(script))
        self._verificar_sesion()
        return filas

    def ejecutar_transaccion(self, scripts: Sequence[str]) -> list[int]:
        """Varias Execute SQL Tasks seguidas, en una sola transaccion."""
        self._restablecer()
        filas = self._db.execute_transaccion([sql.a_temporal(s) for s in scripts])
        self._verificar_sesion()
        return filas

    def cargar_temporal(self, flujo: FlujoSpec, filas: Sequence[tuple]) -> int:
        """OLE DB Destination -> #temporal con la estructura de la staging."""
        self._restablecer()
        self._db.execute_autocommit(sql.crear_temporal(flujo.tabla, flujo.tipos_temporal))
        insertadas = self._db.insertar_todo_o_nada(
            sql.insert_temporal(flujo), filas, tamanos_parametros(flujo.columnas_insert, self.esquema(flujo.tabla))
        )
        self._verificar_sesion()
        return insertadas

    def cargar_descripciones_nc(self, filas: Sequence[tuple]) -> int:
        """df.to_sql('TBL_DESCRIPCIONES_NC', if_exists='append')."""
        self._restablecer()
        return self._db.insertar_todo_o_nada(
            sql.insert_tabla(TABLA_DESCRIPCIONES_NC, COLUMNAS_DESCRIPCIONES_NC),
            filas,
            tamanos_parametros(COLUMNAS_DESCRIPCIONES_NC, self.esquema(TABLA_DESCRIPCIONES_NC)),
        )

    def ejecutar_sp_folios_nc(self) -> None:
        self.ejecutar_sql(SP_FOLIOS_NC)
