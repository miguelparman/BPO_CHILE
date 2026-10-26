"""Paquetes migrados, en el orden en que se ejecutan (el orden declarado de
los .dtsx). El 05 (Historial Asignaciones) esta fuera de alcance."""

from __future__ import annotations

from typing import Sequence

from exceptions import ConfiguracionError
from mappings import ARCHIVO_DESCRIPCIONES_NC, ArchivoSpec
from paquetes import p02_casos, p03_correos, p04_historial_casos, p06_historial_comentarios, p07_seguimiento
from paquetes.base import Paquete, TareaDataFlow, TareaDescripcionesNC

PAQUETES: tuple[Paquete, ...] = (
    p02_casos.PAQUETE,
    p03_correos.PAQUETE,
    p04_historial_casos.PAQUETE,
    p06_historial_comentarios.PAQUETE,
    p07_seguimiento.PAQUETE,
)
CODIGOS = tuple(p.codigo for p in PAQUETES)


def archivos_de(paquetes: Sequence[Paquete]) -> list[ArchivoSpec]:
    """CSV que leen los paquetes (incluye los archivos de los cruces), sin repetir."""
    archivos: list[ArchivoSpec] = []
    for p in paquetes:
        for tarea in p.tareas:
            if isinstance(tarea, TareaDataFlow):
                for f in tarea.flujos:
                    archivos.append(f.archivo)
                    if f.cruce:
                        archivos.append(f.cruce.flujo.archivo)
            elif isinstance(tarea, TareaDescripcionesNC):
                archivos.append(ARCHIVO_DESCRIPCIONES_NC)
    return list(dict.fromkeys(archivos))


def seleccionar(desde: str | None = None, solo: list[str] | None = None) -> tuple[Paquete, ...]:
    """Todos (por defecto), desde un paquete en adelante, o solo algunos
    (siempre en el orden declarado)."""
    if desde and solo:
        raise ConfiguracionError("Use --desde o --solo, no ambos.")
    if desde:
        if desde not in CODIGOS:
            raise ConfiguracionError(f"Paquete desconocido '{desde}'. Validos: {', '.join(CODIGOS)}")
        return PAQUETES[CODIGOS.index(desde) :]
    if solo:
        desconocidos = [c for c in solo if c not in CODIGOS]
        if desconocidos:
            raise ConfiguracionError(f"Paquete(s) desconocido(s) {desconocidos}. Validos: {', '.join(CODIGOS)}")
        return tuple(p for p in PAQUETES if p.codigo in solo)
    return PAQUETES
