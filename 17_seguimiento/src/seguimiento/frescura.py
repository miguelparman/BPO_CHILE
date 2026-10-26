"""Frescura de los CSV de SharePoint ANTES de cargar (decision del usuario
2026-10-26): un archivo viejo, a medio publicar o vacio NO se carga; se
omiten solo los bloques de tareas que lo usan (paquetes/base.Bloque) y la
corrida continua con los demas.

201_bot_salesforce publica los 7 archivos de lunes a viernes a las 06:30,
08:00, 09:30, 11:00, 12:30, 14:00 y 15:30; cada publicacion tarda ~5 min.
En las corridas (07, 10, 13 y 16 h) lo normal es una antiguedad de ~30 min.

Reglas (umbrales en el .env):
  - viejo:       modificado hace mas de FRESCURA_MAX_MIN (150) minutos
                 (tolera que se pierda UNA publicacion del bot);
  - publicando:  modificado hace menos de FRESCURA_RECIENTE_MIN (10) min, o
                 quedo mas de FRESCURA_VENTANA_MIN (15) min antes que el mas
                 nuevo (version anterior mientras el bot sube los demas).
                 Se espera ESPERA_REINTENTO_S y se vuelve a mirar, hasta
                 REINTENTOS_CONEXION veces; si persiste, se omite;
  - vacio:       0 bytes (metadatos) o sin filas de datos (al descargarlo).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


@dataclass(frozen=True)
class ReglasFrescura:
    max_min: int = 150
    ventana_min: int = 15
    reciente_min: int = 10


@dataclass(frozen=True)
class Evaluacion:
    omitir: dict[ArchivoSpec, str]  # archivo -> motivo (viejo, vacio, sin metadatos)
    publicando: dict[ArchivoSpec, str]  # archivo -> motivo (publicacion en curso)


def evaluar(estados: Sequence[EstadoArchivo], ahora: datetime, reglas: ReglasFrescura) -> Evaluacion:
    omitir: dict[ArchivoSpec, str] = {}
    publicando: dict[ArchivoSpec, str] = {}
    fechas = [e.modificado for e in estados if e.modificado is not None]
    mas_nuevo = max(fechas) if fechas else None
    for e in estados:
        if e.error or e.modificado is None:
            omitir[e.archivo] = f"no se pudieron leer sus datos en SharePoint ({e.error or 'sin fecha'})"
            continue
        edad = (ahora - e.modificado).total_seconds() / 60
        if e.tamano == 0:
            omitir[e.archivo] = "archivo vacio (0 bytes)"
        elif edad > reglas.max_min:
            omitir[e.archivo] = f"datos viejos: modificado hace {edad:.0f} min ({_local(e.modificado)}), maximo {reglas.max_min} min"
        elif edad < reglas.reciente_min:
            publicando[e.archivo] = f"modificado hace {edad:.1f} min: el bot lo esta publicando"
        elif mas_nuevo - e.modificado > timedelta(minutes=reglas.ventana_min):
            atraso = (mas_nuevo - e.modificado).total_seconds() / 60
            publicando[e.archivo] = (
                f"version anterior ({_local(e.modificado)}), {atraso:.0f} min antes que el archivo mas nuevo: "
                "publicacion del bot en curso o incompleta"
            )
    return Evaluacion(omitir, publicando)


def _local(fecha: datetime) -> str:
    return fecha.astimezone().strftime("%d/%m %H:%M")


def revisar(
    leer_estados: Callable[[], Sequence[EstadoArchivo]],
    reglas: ReglasFrescura,
    reintentos: int = 3,
    espera_s: float = 300,
    esperar: Callable[[float], None] = time.sleep,
    ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[ArchivoSpec, str]:
    """Archivos a omitir -> motivo. Si el bot esta publicando, espera y
    vuelve a mirar (hasta 'reintentos' veces); lo que siga a medio publicar
    tambien se omite."""
    for intento in range(reintentos + 1):
        estados = leer_estados()
        ev = evaluar(estados, ahora(), reglas)
        _registrar(estados, ev, ahora(), reglas)
        if not ev.publicando or intento == reintentos:
            break
        logger.warning(
            "Publicacion del bot en curso (%s archivo(s)); se espera %s s y se vuelve a revisar (%s de %s).",
            len(ev.publicando), espera_s, intento + 1, reintentos,
        )
        esperar(espera_s)
    omitir = dict(ev.omitir)
    omitir.update({a: f"{m} (tras {reintentos} reintento(s))" for a, m in ev.publicando.items()})
    return omitir


def _registrar(estados: Sequence[EstadoArchivo], ev: Evaluacion, ahora: datetime, reglas: ReglasFrescura) -> None:
    logger.info("Frescura de los archivos (maximo %s min de antiguedad):", reglas.max_min)
    for e in estados:
        if e.archivo in ev.omitir:
            logger.warning("  [OMITIR]     %s: %s", e.archivo.nombre, ev.omitir[e.archivo])
        elif e.archivo in ev.publicando:
            logger.warning("  [PUBLICANDO] %s: %s", e.archivo.nombre, ev.publicando[e.archivo])
        else:
            edad = (ahora - e.modificado).total_seconds() / 60
            logger.info("  [OK]         %s: %s (hace %.0f min, %s bytes)", e.archivo.nombre, _local(e.modificado), edad, f"{e.tamano:,}")


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
