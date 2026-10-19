"""VALIDACION: los puntos donde el Data Flow del .dtsx haria FailComponent,
revisados ANTES de tocar la tabla (en SSIS el error aparece a mitad de la
carga, con la tabla ya truncada).

En la 'Conversion de datos', una columna con errorRowDisposition /
truncationRowDisposition = FailComponent detiene el Data Flow si:
  - el valor convertido no cabe en DT_STR(n) (truncamiento), o
  - el texto tiene caracteres que no existen en la code page 1252.
Si ocurre, se levanta ValidacionError con las primeras filas afectadas
(fila Excel, columna, largo) y el flujo no se carga.

Las columnas IgnoreFailure no detienen nada: se informa en el log cuantos
valores se truncaran (transformacion/transformer.py los trunca).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

from exceptions import ValidacionError
from extraccion.extractor import Fila
from logging_setup import NOMBRE_LOGGER
from mappings import CODE_PAGE, FAIL, FlujoSpec
from transformacion.transformer import convertir

logger = logging.getLogger(NOMBRE_LOGGER)

_MAX_EJEMPLOS = 10
_PRIMERA_FILA_DATOS = 2  # fila 1 = cabecera (HDR=YES)


@dataclass
class ResultadoValidacion:
    errores: list[str] = field(default_factory=list)  # FailComponent
    truncados: dict[str, int] = field(default_factory=dict)  # IgnoreFailure: columna -> cantidad

    @property
    def ok(self) -> bool:
        return not self.errores


def _cabe_en_1252(texto: str) -> bool:
    try:
        texto.encode(CODE_PAGE)
        return True
    except UnicodeEncodeError:
        return False


class Validator:
    def revisar(self, flujo: FlujoSpec, filas: Sequence[Fila]) -> ResultadoValidacion:
        resultado = ResultadoValidacion()
        for n, fila in enumerate(filas, start=_PRIMERA_FILA_DATOS):
            for c in flujo.columnas:
                if c.ancho is None:
                    continue
                valor = convertir(c, fila[c.origen])
                if not isinstance(valor, str):
                    continue
                problema = None
                if not _cabe_en_1252(valor):
                    problema = "caracteres fuera de la code page 1252"
                elif len(valor) > c.ancho:
                    problema = f"largo {len(valor)} > DT_STR({c.ancho})"
                if problema is None:
                    continue
                if c.disposicion == FAIL:
                    resultado.errores.append(f"fila {n}, columna '{c.origen}': {problema} ({valor[:60]!r})")
                elif len(valor) > c.ancho:
                    resultado.truncados[c.origen] = resultado.truncados.get(c.origen, 0) + 1
        return resultado

    def validar(self, flujo: FlujoSpec, filas: Sequence[Fila]) -> ResultadoValidacion:
        resultado = self.revisar(flujo, filas)
        for columna, cantidad in resultado.truncados.items():
            ancho = next(c.ancho for c in flujo.columnas if c.origen == columna)
            logger.warning(
                "[%s] '%s' (IgnoreFailure): %s valor(es) mayores a %s caracteres se truncan.",
                flujo.nombre,
                columna,
                cantidad,
                ancho,
            )
        if not resultado.ok:
            ejemplos = "\n  ".join(resultado.errores[:_MAX_EJEMPLOS])
            raise ValidacionError(
                f"[{flujo.nombre}] {len(resultado.errores)} valor(es) harian fallar la 'Conversion de datos' "
                f"(FailComponent) del .dtsx; no se carga la tabla:\n  {ejemplos}"
            )
        return resultado
