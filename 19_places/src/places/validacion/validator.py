"""VALIDACION: los puntos donde la 'Conversion de datos' del .dtsx haria
FailComponent, revisados ANTES de tocar la tabla (en SSIS el error aparece
a mitad de la carga, con TBL_PLACES ya truncada).

Todas las columnas convertidas son FailComponent (error y truncamiento):
  - el valor no cabe en DT_STR(n) (truncamiento), o
  - el texto tiene caracteres que no existen en la code page 1252.
Si ocurre, se levanta ValidacionError con las primeras filas afectadas
(fila Excel, columna, largo) y no se carga nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import mappings
from exceptions import ValidacionError
from extraccion.extractor import Fila

_MAX_EJEMPLOS = 10
_PRIMERA_FILA_DATOS = 2  # fila 1 = cabecera (HDR=YES)


@dataclass
class ResultadoValidacion:
    errores: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


def _cabe_en_1252(texto: str) -> bool:
    try:
        texto.encode(mappings.CODE_PAGE)
        return True
    except UnicodeEncodeError:
        return False


class Validator:
    def revisar(self, filas: Sequence[Fila]) -> ResultadoValidacion:
        resultado = ResultadoValidacion()
        for n, fila in enumerate(filas, start=_PRIMERA_FILA_DATOS):
            for c in mappings.COLUMNAS:
                valor = fila[c.origen]
                if not isinstance(valor, str):
                    continue
                if not _cabe_en_1252(valor):
                    problema = "caracteres fuera de la code page 1252"
                elif len(valor) > c.ancho:
                    problema = f"largo {len(valor)} > DT_STR({c.ancho})"
                else:
                    continue
                resultado.errores.append(f"fila {n}, columna '{c.origen}': {problema} ({valor[:60]!r})")
        return resultado

    def validar(self, filas: Sequence[Fila]) -> ResultadoValidacion:
        resultado = self.revisar(filas)
        if not resultado.ok:
            ejemplos = "\n  ".join(resultado.errores[:_MAX_EJEMPLOS])
            raise ValidacionError(
                f"{len(resultado.errores)} valor(es) harian fallar la 'Conversion de datos' (FailComponent) "
                f"del .dtsx; no se carga la tabla:\n  {ejemplos}"
            )
        return resultado
