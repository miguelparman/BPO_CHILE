"""INGESTA: copia los 4 Excel de 'Planificación y Control/Insumos/Chile/
Especializados' (sitio 'BPO') hacia 'REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/
02 ESPECIALIZADOS' (sitio 'ReportingFractalia'), de donde los lee el ETL.

'BPO' y 'ReportingFractalia' son tenants DISTINTOS, cada uno con su propio
App Registration: no sirve el endpoint de copia nativo de Graph ('POST
.../copy', mismo tenant/token). Se descarga con el token de 'BPO' y se sube
(reemplazando) con el de 'ReportingFractalia', como 11_correos/ingesta.

Tras subir se vuelve a descargar del destino y se comparan los datos de
Hoja1 (las 8 columnas del flujo) con los del archivo de BPO. Un archivo que falla no detiene los demas: su flujo no se carga (la tabla
conserva su contenido) y la corrida termina con exit 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from exceptions import CopiaError, GerenciaError
from extraccion.extractor import leer_hoja
from logging_setup import NOMBRE_LOGGER
from mappings import FlujoSpec
from sharepoint.client import SharePointClient

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass(frozen=True)
class ResultadoCopia:
    flujo: str
    archivo: str
    bytes_copiados: int | None  # None si fallo
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ProveedorGraph(Protocol):
    def obtener(self) -> tuple[SharePointClient, str]: ...


class CopiadorSharePoint:
    def __init__(
        self,
        origen: ProveedorGraph,
        destino: ProveedorGraph,
        huella: Callable[[bytes, FlujoSpec], Any] = leer_hoja,
    ) -> None:
        """origen: sitio 'BPO'; destino: sitio 'ReportingFractalia'
        (sharepoint.client.ConexionGraph). 'huella' resume el contenido que
        usa el ETL, para verificar la copia."""
        self._origen = origen
        self._destino = destino
        self._huella = huella

    def copiar_uno(self, flujo: FlujoSpec) -> int:
        cli_o, drive_o = self._origen.obtener()
        cli_d, drive_d = self._destino.obtener()
        contenido = cli_o.download_file(drive_o, flujo.ruta_bpo)
        folder_id = cli_d.resolve_folder(drive_d, flujo.carpeta_reporting)
        cli_d.upload_file(drive_d, folder_id, flujo.archivo, contenido)
        # SharePoint reescribe las propiedades de los archivos Office al
        # subirlos (el destino queda ~1 KB mas grande): no se compara el
        # tamano sino los datos de Hoja1 que lee el ETL.
        copiado = cli_d.download_file(drive_d, flujo.ruta_reporting)
        if self._huella(copiado, flujo) != self._huella(contenido, flujo):
            raise CopiaError("Los datos de Hoja1 en ReportingFractalia no coinciden con los de BPO tras la copia.")
        return len(contenido)

    def copiar(self, flujos: Sequence[FlujoSpec]) -> list[ResultadoCopia]:
        resultados: list[ResultadoCopia] = []
        for flujo in flujos:
            try:
                n = self.copiar_uno(flujo)
                logger.info("[%s] Copiado '%s' BPO -> ReportingFractalia (%s bytes).", flujo.nombre, flujo.archivo, n)
                resultados.append(ResultadoCopia(flujo.nombre, flujo.archivo, n))
            except GerenciaError as exc:
                logger.error("[%s] Fallo copiando '%s': %s", flujo.nombre, flujo.archivo, exc)
                resultados.append(ResultadoCopia(flujo.nombre, flujo.archivo, None, str(exc)))
        return resultados
