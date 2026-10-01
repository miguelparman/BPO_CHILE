"""Excepciones del proceso Logueo. No dependen de pyodbc, pandas ni ninguna
otra libreria externa."""

from __future__ import annotations


class LogueoError(Exception):
    """Error base de todo el proceso."""


class ConfiguracionError(LogueoError):
    """Falta una variable de entorno o tiene un valor invalido (p.ej. PERIODO)."""


class ExtraccionError(LogueoError):
    """Fallo la descarga o el parseo del archivo plano (Flat File Source)."""


class ValidacionError(LogueoError):
    """El archivo o el esquema de la tabla destino no cumple lo que declara el
    .dtsx (columnas, anchos, tipos). Equivale a un componente del Data Flow con
    errorRowDisposition/truncationRowDisposition = FailComponent."""


class CargaError(LogueoError):
    """Fallo una operacion de lectura/escritura sobre SQL Server."""


class PipelineError(LogueoError):
    """Envuelve cualquier excepcion ocurrida durante un paso del pipeline,
    identificando la tarea del .dtsx donde ocurrio."""

    def __init__(self, paso: str, causa: Exception) -> None:
        super().__init__(f"Fallo en '{paso}': {causa}")
        self.paso = paso
        self.causa = causa
