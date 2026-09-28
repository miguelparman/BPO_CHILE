"""Excepciones del proceso de Trafico. No dependen de pyodbc, pandas ni
ninguna otra libreria externa."""

from __future__ import annotations


class TraficoError(Exception):
    """Error base de todo el proceso de Trafico."""


class ExtraccionError(TraficoError):
    """Fallo la descarga o el parseo de un CSV de origen (SharePoint)."""


class ValidacionError(TraficoError):
    """Un CSV de origen o el esquema de una tabla no cumple lo que espera el
    proceso (columnas, tipos o anchos). Se lanza ANTES de truncar/borrar
    nada, para no dejar tablas a medio cargar."""


class ConversionError(TraficoError):
    """Equivalente a una fila redirigida al error output con disposicion
    'FailComponent' en el Data Flow 'CARGA' (Data Conversion, Conditional
    Split o OLE DB Destination): SSIS aborta el componente y el paquete."""


class CargaError(TraficoError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(TraficoError):
    """Envuelve cualquier excepcion ocurrida durante un paso del pipeline,
    identificando el paso (Sequence Container / tarea del .dtsx) donde ocurrio."""

    def __init__(self, pipeline: str, paso: str, causa: Exception) -> None:
        super().__init__(f"[{pipeline}] Fallo en '{paso}': {causa}")
        self.pipeline = pipeline
        self.paso = paso
        self.causa = causa
