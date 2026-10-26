"""Excepciones del proceso Puntualidad. No dependen de pyodbc, openpyxl ni ninguna
otra libreria externa."""

from __future__ import annotations


class PuntualidadError(Exception):
    """Error base de todo el proceso."""


class ConfiguracionError(PuntualidadError):
    """Falta una variable de entorno o tiene un valor invalido."""


class ConexionError(PuntualidadError):
    """Una conexion (SQL Server o SharePoint) no respondio en la validacion
    previa, ni tras los reintentos."""


class ExtraccionError(PuntualidadError):
    """Fallo la descarga o la lectura del Excel (Excel Source)."""


class ValidacionError(PuntualidadError):
    """El archivo o el esquema de la tabla no cumple lo que declara el .dtsx
    (columnas, anchos, tipos). Equivale a un componente del Data Flow con
    errorRowDisposition/truncationRowDisposition = FailComponent."""


class CargaError(PuntualidadError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(PuntualidadError):
    """Envuelve cualquier excepcion ocurrida durante una tarea, identificando
    la tarea del .dtsx donde ocurrio."""

    def __init__(self, tarea: str, causa: Exception) -> None:
        super().__init__(f"Fallo en la tarea '{tarea}': {causa}")
        self.tarea = tarea
        self.causa = causa
