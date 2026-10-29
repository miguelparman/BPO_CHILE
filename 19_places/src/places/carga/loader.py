"""CARGA: contenedor 'CARGA PLACES' del .dtsx, en el orden de sus
Precedence Constraints:

    TRUNCA TABLA (Execute SQL) -> CARGA TABLA (OLE DB Destination, INSERT)
    -> LIMPIA TABLA (Execute SQL)

con el T-SQL literal del paquete (mappings.SQL_TRUNCATE / SQL_LIMPIA).

Diferencia deliberada: en SSIS las tres tareas son independientes (sin
transaccion), si el Data Flow falla la tabla queda vacia. Aqui van en UNA
transaccion: si algo falla hay rollback y la tabla conserva la carga
anterior. El resultado final ante una corrida exitosa es identico.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import mappings
from db import DatabaseGateway
from logging_setup import NOMBRE_LOGGER

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass(frozen=True)
class ResultadoCarga:
    insertadas: int
    borradas_nulos: int

    @property
    def finales(self) -> int:
        return self.insertadas - self.borradas_nulos


def insert_sql() -> str:
    columnas = ", ".join(f"[{c}]" for c in mappings.COLUMNAS_DESTINO)
    marcas = ", ".join("?" for _ in mappings.COLUMNAS)
    return f"INSERT INTO [dbo].[{mappings.TABLA_PLACES}] ({columnas}) VALUES ({marcas})"


def anchos_parametros() -> list[int]:
    return [c.ancho for c in mappings.COLUMNAS]


class PlacesLoader:
    def __init__(self, db: DatabaseGateway) -> None:
        self._db = db

    def cargar(self, filas: Sequence[tuple]) -> ResultadoCarga:
        insertadas, borradas = self._db.recargar_tabla(
            mappings.SQL_TRUNCATE, insert_sql(), filas, anchos_parametros(), mappings.SQL_LIMPIA
        )
        resultado = ResultadoCarga(insertadas, borradas)
        logger.info(
            "TRUNCATE + %s fila(s) insertadas - %s con ID NULL (LIMPIA TABLA) = %s en %s.",
            resultado.insertadas,
            resultado.borradas_nulos,
            resultado.finales,
            mappings.TABLA_PLACES,
        )
        return resultado
