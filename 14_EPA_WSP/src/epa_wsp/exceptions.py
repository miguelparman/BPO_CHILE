"""Excepciones del proceso EPA/WSP. No dependen de pyodbc, pandas ni ninguna
otra libreria externa."""

from __future__ import annotations


class EpaWspError(Exception):
    """Error base de todo el proceso."""


class ExtraccionError(EpaWspError):
    """Fallo la descarga o el parseo de un origen (SharePoint, portal Medallia
    o el CSV local de Medallia)."""


class ValidacionError(EpaWspError):
    """Un origen o el esquema de una tabla no cumple lo que espera el proceso
    (columnas, tipos, anchos o periodos). Se lanza ANTES de borrar nada, para
    no dejar tablas a medio cargar."""


class CargaError(EpaWspError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(EpaWspError):
    """Envuelve cualquier excepcion ocurrida durante un paso del pipeline,
    identificando el paso (tarea / Sequence Container del .dtsx) donde ocurrio."""

    def __init__(self, pipeline: str, paso: str, causa: Exception) -> None:
        super().__init__(f"[{pipeline}] Fallo en '{paso}': {causa}")
        self.pipeline = pipeline
        self.paso = paso
        self.causa = causa
