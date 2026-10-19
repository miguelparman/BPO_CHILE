"""CARGA: las 3 tareas de cada contenedor del .dtsx, en el orden de sus
Precedence Constraints:

    TRUNCATE (Execute SQL) -> OLE DB Destination (INSERT) -> DELETE (Execute SQL)

con el T-SQL literal del paquete (mappings.FlujoSpec.sql_truncate /
sql_delete) y el INSERT sobre las columnas del mapeo del destino.

Diferencia deliberada (decision a): en SSIS las tres tareas son
independientes (sin transaccion), si el Data Flow falla la tabla queda
vacia. Aqui van en UNA transaccion: si algo falla hay rollback y la tabla
conserva la carga anterior. El resultado final ante una corrida exitosa es
identico.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from db import PARAM_FECHA, PARAM_TEXTO, DatabaseGateway
from logging_setup import NOMBRE_LOGGER
from mappings import FECHA, FlujoSpec

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass(frozen=True)
class ResultadoCarga:
    insertadas: int
    borradas_nulos: int

    @property
    def finales(self) -> int:
        return self.insertadas - self.borradas_nulos


def insert_sql(flujo: FlujoSpec) -> str:
    columnas = ", ".join(f"[{c}]" for c in flujo.columnas_destino)
    marcas = ", ".join("?" for _ in flujo.columnas)
    return f"INSERT INTO [dbo].[{flujo.tabla}] ({columnas}) VALUES ({marcas})"


def tipos_parametros(flujo: FlujoSpec) -> list[tuple[str, int | None]]:
    return [(PARAM_FECHA, None) if c.tipo == FECHA else (PARAM_TEXTO, c.ancho) for c in flujo.columnas]


class VolumetriaLoader:
    def __init__(self, db: DatabaseGateway) -> None:
        self._db = db

    def cargar(self, flujo: FlujoSpec, filas: Sequence[tuple]) -> ResultadoCarga:
        insertadas, borradas = self._db.recargar_tabla(
            flujo.sql_truncate, insert_sql(flujo), filas, tipos_parametros(flujo), flujo.sql_delete
        )
        resultado = ResultadoCarga(insertadas, max(borradas, 0))
        logger.info(
            "[%s] TRUNCATE + %s fila(s) insertadas - %s sin [Número del caso] (DELETE) = %s en %s.",
            flujo.nombre,
            resultado.insertadas,
            resultado.borradas_nulos,
            resultado.finales,
            flujo.tabla,
        )
        return resultado
