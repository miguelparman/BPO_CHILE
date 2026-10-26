"""Excepciones del proceso Seguimiento. No dependen de pyodbc, pandas ni ninguna
otra libreria externa."""

from __future__ import annotations


class SeguimientoError(Exception):
    """Error base de todo el proceso."""


class ConfiguracionError(SeguimientoError):
    """Falta una variable de entorno o tiene un valor invalido."""


class ConexionError(SeguimientoError):
    """Una conexion (SQL Server o SharePoint) no respondio en la validacion
    previa, ni tras los reintentos."""


class ExtraccionError(SeguimientoError):
    """Fallo la descarga o el parseo de un archivo plano (Flat File Source)."""


class ValidacionError(SeguimientoError):
    """El archivo o el esquema de la tabla no cumple lo que declara el .dtsx
    (columnas, anchos, tipos). Equivale a un componente del Data Flow con
    errorRowDisposition/truncationRowDisposition = FailComponent."""


class CargaError(SeguimientoError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(SeguimientoError):
    """Envuelve cualquier excepcion ocurrida durante una tarea, identificando
    el paquete (.dtsx) y la tarea donde ocurrio."""

    def __init__(self, paquete: str, tarea: str, causa: Exception) -> None:
        super().__init__(f"Fallo en el paquete {paquete}, tarea '{tarea}': {causa}")
        self.paquete = paquete
        self.tarea = tarea
        self.causa = causa
