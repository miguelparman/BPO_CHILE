"""Value objects del proceso de USUARIOS, sin dependencias externas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FORMATO_YYYYMM = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class Periodo:
    """Periodo de proceso (YYYYMM), equivalente a la variable de paquete
    'User::Periodo' / 'User::Periodo01' presente en los 5 .dtsx originales.

    En los paquetes originales era un valor literal fijo escrito a mano en la
    expresion de la variable (p.ej. '202608'), editado antes de cada corrida.
    Aqui se recibe siempre como parametro explicito (CLI/.env), nunca se
    calcula solo ni tiene un default de negocio embebido en el codigo.
    """

    valor: str

    def __post_init__(self) -> None:
        if not _FORMATO_YYYYMM.match(self.valor):
            raise ValueError(f"Periodo debe tener formato YYYYMM (6 digitos): {self.valor!r}")

    @property
    def como_int(self) -> int:
        return int(self.valor)

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class ResultadoSubPipeline:
    """Resumen de la ejecucion de UN paquete .dtsx migrado (una de las
    funciones 'ejecutar_*' de pipeline.py), para logging/reporting y para los
    tests que demuestran equivalencia con el proceso SSIS original."""

    nombre: str
    filas_por_paso: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoPipeline:
    """Resumen de 'ejecutar_todo()': un ResultadoSubPipeline por cada uno de
    los 5 paquetes, en el orden original (0101, 0201, 0300, 0301, 0302)."""

    periodo: Periodo
    resultados: tuple[ResultadoSubPipeline, ...]
