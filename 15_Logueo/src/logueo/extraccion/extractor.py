"""Extraccion: equivalente al Flat File Source 'Logueo' del Data Flow.

Formato declarado en el Flat File Connection Manager 'Logueo':
  - Delimited, CodePage 1252, sin calificador de texto (<none>);
  - cabecera en la primera fila (ColumnNamesInFirstDataRow=True);
  - separador de columna ';' y CRLF como delimitador de la ULTIMA columna
    (es decir, de fila);
  - 45 columnas DT_STR(100), mapeadas por POSICION;
  - RetainNulls=True: un campo vacio llega como NULL.

El origen cambia: en vez de la ruta local (variable User::Ruta_General_Whatsapp)
el archivo se descarga de SharePoint via Microsoft Graph (FuenteSharePoint).
FuenteLocal se conserva para contingencia y para las pruebas de equivalencia.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

import mappings
from exceptions import ExtraccionError
from sharepoint.client import SharePointClient


def _byte_crudo(error: UnicodeDecodeError):
    """Los 5 bytes que cp1252 no define (0x81, 0x8D, 0x8F, 0x90, 0x9D) SSIS los
    pasa tal cual a la columna varchar; Python fallaria. Se mapean al mismo
    punto de codigo (como latin-1) para no perder la fila."""
    return "".join(chr(b) for b in error.object[error.start : error.end]), error.end


codecs.register_error("logueo_cp1252", _byte_crudo)


class FuenteArchivo(Protocol):
    descripcion: str

    def leer(self) -> bytes: ...


class FuenteSharePoint:
    """Archivo en una carpeta de SharePoint (Microsoft Graph)."""

    def __init__(self, client: SharePointClient, drive_id: str, folder_path: str, archivo: str, web_base: str = "") -> None:
        self._client = client
        self._drive_id = drive_id
        self._ruta = f"{folder_path.strip('/')}/{archivo}"
        self.descripcion = f"{web_base.rstrip('/')}/{self._ruta}" if web_base else self._ruta

    def leer(self) -> bytes:
        return self._client.download_file(self._drive_id, self._ruta)


class FuenteLocal:
    """Archivo en disco (contingencia / pruebas de equivalencia)."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = Path(ruta)
        self.descripcion = str(self._ruta)

    def leer(self) -> bytes:
        try:
            return self._ruta.read_bytes()
        except OSError as exc:
            raise ExtraccionError(f"No se pudo leer el archivo local '{self._ruta}': {exc}") from exc


@dataclass(frozen=True)
class ArchivoPlano:
    """Contenido parseado, todavia sin validar. Cada fila es la lista de sus
    campos ('' = vacio); puede tener menos de 45 si el archivo esta mal formado."""

    cabecera: list[str]
    filas: list[list[str]]

    def a_dataframe(self) -> pd.DataFrame:
        """DataFrame de 45 columnas (dtype object) con RetainNulls: '' -> None.
        Asume que el archivo ya paso validacion/validator.validar_archivo."""
        datos = [[None if v == "" else v for v in fila] for fila in self.filas]
        return pd.DataFrame(datos, columns=list(mappings.COLUMNAS_ORIGEN), dtype=object)


def parsear_archivo_plano(contenido: bytes) -> ArchivoPlano:
    """Parsea el archivo como lo hace el Flat File Source:
    - filas separadas por CRLF (un LF suelto queda dentro del dato);
    - cada fila se corta en ';' a lo sumo 44 veces: la ultima columna se
      delimita con CRLF, asi que un ';' de mas queda dentro de T_NOTR_603;
    - sin calificador de texto: las comillas son parte del dato."""
    if not contenido:
        raise ExtraccionError("El archivo esta vacio.")
    texto = contenido.decode(mappings.CODE_PAGE, errors="logueo_cp1252")
    lineas = texto.split(mappings.SEPARADOR_FILA)
    while lineas and lineas[-1] == "":  # CRLF final
        lineas.pop()
    if not lineas:
        raise ExtraccionError("El archivo no tiene cabecera.")
    maximo = len(mappings.COLUMNAS_ORIGEN) - 1
    cabecera = lineas[0].split(mappings.SEPARADOR_COLUMNA, maximo)
    filas = [linea.split(mappings.SEPARADOR_COLUMNA, maximo) for linea in lineas[1:]]
    return ArchivoPlano(cabecera=cabecera, filas=filas)


def extraer(fuente: FuenteArchivo) -> ArchivoPlano:
    try:
        contenido = fuente.leer()
    except ExtraccionError:
        raise
    except Exception as exc:  # noqa: BLE001 - Graph / red
        raise ExtraccionError(f"No se pudo descargar '{fuente.descripcion}': {exc}") from exc
    return parsear_archivo_plano(contenido)
