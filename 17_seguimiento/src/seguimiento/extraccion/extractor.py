r"""Extraccion: los CSV CRUDOS que publica 201_bot_salesforce, tomados TAL CUAL.

En SSIS la cadena era:
  bot -> ...\SEGUIMIENTO\*.csv (cp1252, LF)
      -> paquete 01 'Convierte CSV' (Transforma_archivos_csv_seguimiento_chile.py)
      -> ...\SEGUIMIENTO\Nuevo\*.csv (UTF-8 con BOM, CRLF)
      -> Flat File Source
Aqui no hay archivo intermedio ni conversion del archivo: se lee el crudo
directamente (leer_csv). Sobre los crudos actuales, las reglas del script del
01 ('";"' -> '","', '\r' suelto) no cambian nada (el bot publica con coma);
la re-codificacion a UTF-8 no cambia los caracteres; y lo unico que si
cambiaba -los saltos de linea DENTRO de un texto pasaban a CRLF- se aplica
por columna en transformacion/transformer.py (saltos_crlf), que es donde el
dato se transforma para la carga.

  - FuenteSharePoint / FuenteLocal entregan los bytes del CSV;
    FuentePrecargada los descarga todos en paralelo al iniciar la corrida.
  - leer_csv() es el Flat File Source.
"""

from __future__ import annotations

import codecs
import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from exceptions import ExtraccionError
from logging_setup import NOMBRE_LOGGER
from mappings import ArchivoSpec

logger = logging.getLogger(NOMBRE_LOGGER)


class FuenteArchivo(Protocol):
    def leer(self, archivo: ArchivoSpec) -> bytes: ...

    def describir(self, archivo: ArchivoSpec) -> str: ...


class FuenteSharePoint:
    """CSV publicados por 201_bot_salesforce en ReportingFractalia."""

    def __init__(self, cliente, drive_id: str, carpetas: dict[str, str], web_drive: str = "") -> None:
        self._cliente = cliente
        self._drive_id = drive_id
        self.cliente, self.drive_id = cliente, drive_id  # tambien para leer metadatos (frescura.py)
        self._carpetas = carpetas
        self._web_drive = web_drive

    def ruta(self, archivo: ArchivoSpec) -> str:
        return f"{self._carpetas[archivo.carpeta]}/{archivo.nombre}"

    def leer(self, archivo: ArchivoSpec) -> bytes:
        try:
            return self._cliente.download_file(self._drive_id, self.ruta(archivo))
        except Exception as exc:
            raise ExtraccionError(f"No se pudo descargar '{self.ruta(archivo)}' de SharePoint: {exc}") from exc

    def describir(self, archivo: ArchivoSpec) -> str:
        return f"{self._web_drive}/{self.ruta(archivo)}"


class FuenteLocal:
    """Contingencia / pruebas: CSV crudos en una carpeta local (p.ej.
    ...\\BPO - Insumos\\Chile\\SEGUIMIENTO, donde el bot deja la copia local)."""

    def __init__(self, carpeta: Path) -> None:
        self._carpeta = Path(carpeta)

    def leer(self, archivo: ArchivoSpec) -> bytes:
        ruta = self._carpeta / archivo.nombre
        try:
            return ruta.read_bytes()
        except OSError as exc:
            raise ExtraccionError(f"No se pudo leer '{ruta}': {exc}") from exc

    def describir(self, archivo: ArchivoSpec) -> str:
        return str(self._carpeta / archivo.nombre)


class FuentePrecargada:
    """Descarga EN PARALELO todos los archivos de la corrida al crearse y los
    entrega desde memoria. Un error de descarga se guarda y se levanta recien
    cuando un paquete pide ese archivo (los paquetes anteriores corren igual,
    y Descripciones NC lo trata como advertencia, como antes)."""

    def __init__(self, fuente: FuenteArchivo, archivos: list[ArchivoSpec], paralelas: int = 4) -> None:
        self._fuente = fuente
        self._datos: dict[ArchivoSpec, bytes | Exception] = {}
        if archivos:
            with ThreadPoolExecutor(max_workers=max(1, paralelas)) as pool:
                futuros = {a: pool.submit(fuente.leer, a) for a in archivos}
            for archivo, futuro in futuros.items():
                exc = futuro.exception()
                self._datos[archivo] = exc if exc is not None else futuro.result()

    def leer(self, archivo: ArchivoSpec) -> bytes:
        if archivo not in self._datos:
            self._datos[archivo] = self._fuente.leer(archivo)
        dato = self._datos[archivo]
        if isinstance(dato, Exception):
            raise dato
        return dato

    def describir(self, archivo: ArchivoSpec) -> str:
        return self._fuente.describir(archivo)


# --------------------------------------------------------------------------- #
# Flat File Source sobre el CSV crudo del bot
# --------------------------------------------------------------------------- #
CODIFICACION_BOT = "cp1252"
CONSERVAR_BYTES = "seguimiento_conservar_bytes"


def _conservar(error: UnicodeDecodeError):
    """Manejador de decodificacion: un byte sin caracter en cp1252 (0x81,
    0x8D, 0x8F, 0x90, 0x9D) se conserva como el caracter de control latin-1
    del mismo valor, para que transformacion/codificacion.py pueda reparar la
    tilde de la que forma parte (SSIS lo perdia como U+FFFD)."""
    return error.object[error.start : error.end].decode("latin-1"), error.end


codecs.register_error(CONSERVAR_BYTES, _conservar)


def leer_csv(crudo: bytes, archivo: ArchivoSpec) -> list[list[str]]:
    """Filas de datos del CSV CRUDO tal como lo publica 201_bot_salesforce
    (cp1252, delimitado ',', calificador '"', comillas escapadas como "",
    filas terminadas en LF), sin la fila de encabezado
    (ColumnNamesInFirstDataRow = True). Los saltos de linea dentro de un
    campo calificado se conservan tal cual. RetainNulls = false: una celda
    vacia queda como '' (no NULL).

    Bytes no definidos en cp1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D) se conservan
    (CONSERVAR_BYTES); la transformacion repara la tilde de la que forman parte."""
    texto = crudo.decode(CODIFICACION_BOT, errors=CONSERVAR_BYTES)
    try:
        filas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=",", quotechar='"', doublequote=True))
    except csv.Error as exc:
        raise ExtraccionError(f"'{archivo.nombre}' no se pudo leer como CSV: {exc}") from exc
    if not filas:
        raise ExtraccionError(f"'{archivo.nombre}' esta vacio (sin fila de encabezado).")
    datos = filas[1:]
    vacias = sum(1 for f in datos if not f)
    if vacias:
        logger.warning("'%s': se ignoran %s linea(s) en blanco.", archivo.nombre, vacias)
        datos = [f for f in datos if f]
    return datos
