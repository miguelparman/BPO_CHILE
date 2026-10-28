"""Lector de CSV publicados en SharePoint via Microsoft Graph.

Reemplaza al Connection Manager OLE DB 'Externos_Frac' de los 5 .dtsx
originales: en vez de una consulta SQL contra una tabla de esa base
(Externos_Frac.dbo.BAJAS_FRAUDE, Externos_Frac.dbo.BD_RETEN_V2, etc.), el
origen es el mismo archivo pero exportado como CSV a SharePoint, con el mismo
nombre que la tabla (ver mappings.py) -- identico al patron ya usado en
30_parque/sharepoint/reader.py, que lee ese mismo folder de SharePoint para
pqe_fijtot2023/pqe_movtot2023.

'keep_default_na=False' + 'na_values=[""]' evita que pandas interprete
valores de texto legitimos (p.ej. un RUT que por coincidencia sea 'NA',
'NULL', 'None', etc.) como nulos -- el origen original es texto plano
(DT_STR/DT_WSTR sin tipado real), asi que solo una celda vacia se trata como
nulo; los 'NULL' literales que el .dtsx limpiaba con REPLACE(...,'NULL','')
se preservan como el string 'NULL' y siguen limpiandose en extraccion.py.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from exceptions import ExtraccionError
from sharepoint.client import SharePointClient


class SharePointCsvReader:
    def __init__(
        self,
        client: SharePointClient,
        drive_id: str,
        folder_path: str,
        delimiter: str = ",",
    ) -> None:
        self._client = client
        self._drive_id = drive_id
        self._folder_path = folder_path.strip("/")
        self._delimiter = delimiter

    def leer_csv(self, nombre_archivo: str) -> pd.DataFrame:
        ruta = f"{self._folder_path}/{nombre_archivo}"
        try:
            contenido = self._client.download_file(self._drive_id, ruta)
        except Exception as exc:
            raise ExtraccionError(f"No se pudo descargar '{ruta}' desde SharePoint: {exc}") from exc

        try:
            return pd.read_csv(
                BytesIO(contenido),
                dtype=str,
                sep=self._delimiter,
                keep_default_na=False,
                na_values=[""],
            )
        except Exception as exc:
            raise ExtraccionError(f"No se pudo parsear el CSV '{nombre_archivo}': {exc}") from exc
