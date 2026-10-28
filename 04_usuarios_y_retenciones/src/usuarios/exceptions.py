"""Excepciones del proceso de USUARIOS. No dependen de pyodbc, pandas ni
ninguna otra libreria externa."""

from __future__ import annotations


class UsuariosError(Exception):
    """Error base de todo el proceso de carga de USUARIOS."""


class ExtraccionError(UsuariosError):
    """Fallo la lectura de un Origen: descarga/parseo de un CSV en
    SharePoint (Microsoft Graph, reemplaza a Externos_Frac) o una validacion
    de columnas/datos sobre el DataFrame leido."""


class ValidacionError(UsuariosError):
    """Un control de calidad de datos no paso (equivalente a un RAISERROR /
    a un chequeo de esquema previo a un Destino OLE DB)."""


class CargaError(UsuariosError):
    """Fallo una operacion de lectura/escritura sobre SQL Server (extraccion,
    truncados, inserts o scripts T-SQL de transformacion)."""


class PipelineError(UsuariosError):
    """Envuelve cualquier excepcion no controlada ocurrida durante un paso del
    pipeline, identificando el sub-pipeline (paquete .dtsx original) y el
    paso (Sequence Container / tarea) donde ocurrio."""

    def __init__(self, pipeline: str, paso: str, causa: Exception) -> None:
        super().__init__(f"[{pipeline}] Fallo en '{paso}': {causa}")
        self.pipeline = pipeline
        self.paso = paso
        self.causa = causa
