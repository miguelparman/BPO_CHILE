"""Frescura de los CSV de SharePoint ANTES de cargar (decision del usuario
2026-10-26): un archivo que no esta actualizado o viene vacio NO se carga;
se omiten solo los bloques de tareas que lo usan (paquetes/base.Bloque) y la
corrida continua con los demas.

201_bot_salesforce publica los 7 archivos de lunes a viernes a las 06:30,
08:00, 09:30, 11:00, 12:30, 14:00 y 15:30; cada publicacion tarda ~5 min.
En las corridas (07, 10, 13 y 16 h) lo normal es una antiguedad de ~30 min.

Reglas:
  - no actualizado: modificado hace mas de FRESCURA_MAX_MIN (150) minutos
                    (tolera que se pierda UNA publicacion del bot);
  - vacio:          0 bytes (metadatos) o sin filas de datos (al descargarlo,
                    pipeline._sin_filas).
No se espera a que el bot termine una publicacion en curso: se toma lo que
haya (decision del usuario). SharePoint reemplaza el archivo completo al
terminar de subirlo, asi que nunca se lee uno a medio escribir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from logging_setup import NOMBRE_LOGGER
from mappings import ArchivoSpec

logger = logging.getLogger(NOMBRE_LOGGER)


@dataclass(frozen=True)
class EstadoArchivo:
    archivo: ArchivoSpec
    modificado: datetime | None  # UTC
    tamano: int | None
    error: str | None = None  # no se pudo leer el metadato (no existe, sin permiso...)


def evaluar(estados: Sequence[EstadoArchivo], ahora: datetime, max_min: int) -> dict[ArchivoSpec, str]:
    """Archivos que no se cargan -> motivo."""
    omitir: dict[ArchivoSpec, str] = {}
    for e in estados:
        if e.error or e.modificado is None:
            omitir[e.archivo] = f"no se pudieron leer sus datos en SharePoint ({e.error or 'sin fecha'})"
            continue
        edad = (ahora - e.modificado).total_seconds() / 60
        if e.tamano == 0:
            omitir[e.archivo] = "archivo vacio (0 bytes)"
        elif edad > max_min:
            omitir[e.archivo] = f"no actualizado: modificado hace {edad:.0f} min ({_local(e.modificado)}), maximo {max_min} min"
    return omitir


def _local(fecha: datetime) -> str:
    return fecha.astimezone().strftime("%d/%m %H:%M")


def revisar(
    leer_estados: Callable[[], Sequence[EstadoArchivo]],
    max_min: int,
    ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[ArchivoSpec, str]:
    """Lee los metadatos una vez, registra el estado de cada archivo y
    devuelve los que no se cargan -> motivo."""
    estados = leer_estados()
    momento = ahora()
    omitir = evaluar(estados, momento, max_min)
    logger.info("Frescura de los archivos (maximo %s min de antiguedad):", max_min)
    for e in estados:
        if e.archivo in omitir:
            logger.warning("  [OMITIR] %s: %s", e.archivo.nombre, omitir[e.archivo])
        else:
            edad = (momento - e.modificado).total_seconds() / 60
            logger.info("  [OK]     %s: %s (hace %.0f min, %s bytes)", e.archivo.nombre, _local(e.modificado), edad, f"{e.tamano:,}")
    return omitir


def estados_sharepoint(cliente, drive_id: str, carpetas: dict[str, str], archivos: Sequence[ArchivoSpec]) -> list[EstadoArchivo]:
    """Metadatos (fecha de modificacion y tamano) de cada archivo, sin descargarlo."""
    estados = []
    for archivo in archivos:
        try:
            item = cliente.get_item(drive_id, f"{carpetas[archivo.carpeta]}/{archivo.nombre}")
            modificado = datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00"))
            estados.append(EstadoArchivo(archivo, modificado, item.get("size")))
        except Exception as exc:  # noqa: BLE001 - se informa y el bloque se omite
            estados.append(EstadoArchivo(archivo, None, None, str(exc)[:200]))
    return estados
