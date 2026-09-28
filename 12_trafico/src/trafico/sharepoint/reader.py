"""CsvReader: descarga un CSV de SharePoint y lo parsea con pandas.

Formato que publica 01_servidor_chile (csv.writer de Python): separador ';',
comillas '"' minimas, UTF-8 con BOM, primera fila = nombres de columna.
Todo se lee como texto (dtype=str) sin convertir celdas vacias a NaN: la
tipificacion la hace extraccion/extractor.py columna a columna, segun el
esquema real de la tabla temporal.
"""

from __future__ import annotations

import io

import pandas as pd

from sharepoint.client import SharePointClient


class CsvReader:
    def __init__(self, client: SharePointClient, drive_id: str, folder_path: str) -> None:
        self._client = client
        self._drive_id = drive_id
        self._folder_path = folder_path.strip("/")
        self._cache: dict[str, pd.DataFrame] = {}

    def read_csv(self, nombre_archivo: str) -> pd.DataFrame:
        """Devuelve el CSV como DataFrame de strings. Se descarga una sola vez
        por corrida (la alerta y la extraccion leen el mismo ATENDIDA.csv)."""
        if nombre_archivo not in self._cache:
            contenido = self._client.download_file(self._drive_id, f"{self._folder_path}/{nombre_archivo}")
            self._cache[nombre_archivo] = pd.read_csv(
                io.BytesIO(contenido),
                sep=";",
                quotechar='"',
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            )
        return self._cache[nombre_archivo]
