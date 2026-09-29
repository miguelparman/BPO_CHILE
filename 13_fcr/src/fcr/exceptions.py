"""Excepciones del proceso FCR. No dependen de pyodbc, pandas ni ninguna
otra libreria externa."""

from __future__ import annotations


class FcrError(Exception):
    """Error base de todo el proceso FCR."""


class ExtraccionError(FcrError):
    """Fallo la lectura de una base de origen (TBL_LLAMADAS_ATENDIDAS_INBOUND / TBL_CHAT)."""


class ValidacionError(FcrError):
    """El esquema de una tabla o los datos no cumplen lo que espera el proceso
    (columnas, tipos, anchos). Se lanza ANTES de borrar nada de TBL_FCR."""


class CargaError(FcrError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(FcrError):
    """Envuelve cualquier excepcion ocurrida durante un paso del pipeline,
    identificando el paso (tarea del .dtsx) donde ocurrio."""

    def __init__(self, pipeline: str, paso: str, causa: Exception) -> None:
        super().__init__(f"[{pipeline}] Fallo en '{paso}': {causa}")
        self.pipeline = pipeline
        self.paso = paso
        self.causa = causa
