"""Value objects del proceso. Sin dependencias externas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


DIA_CIERRE_MES_DEFAULT = 4


def calcular_periodo(hoy: date, dia_cierre_mes: int = DIA_CIERRE_MES_DEFAULT) -> int:
    """Periodo automatico, mismo criterio que 12_trafico (User::Periodo de
    CL_Proc_Trafico_01.dtsx):

        DAY(GETDATE()) <= 4 ? mes anterior : mes actual

    En CL_Proc_Trafico_FCR_02.dtsx la variable User::Periodo (Int32) tenia la
    expresion constante "202608", que se editaba a mano; por decision del
    usuario se reemplaza por este calculo (se puede fijar con PERIODO o
    --periodo para recargar un mes puntual).
    """
    if hoy.day <= dia_cierre_mes:
        anio, mes = (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)
    else:
        anio, mes = hoy.year, hoy.month
    return anio * 100 + mes


def validar_periodo(periodo: int) -> int:
    """Valida un periodo YYYYMM (p.ej. 202609)."""
    if not (190001 <= periodo <= 999912 and 1 <= periodo % 100 <= 12):
        raise ValueError(f"periodo invalido {periodo!r}: formato esperado YYYYMM, p.ej. 202609")
    return periodo


def resolver_periodo(
    hoy: date, periodo_cli: int | None, periodo_env: int | None, dia_cierre_mes: int = DIA_CIERRE_MES_DEFAULT
) -> tuple[int, str]:
    """Periodo a procesar y de donde salio. Prioridad: --periodo (CLI) >
    PERIODO (.env) > calculo automatico."""
    if periodo_cli is not None:
        return validar_periodo(periodo_cli), "--periodo"
    if periodo_env is not None:
        return validar_periodo(periodo_env), "PERIODO (.env)"
    return calcular_periodo(hoy, dia_cierre_mes), f"automatico (DIA_CIERRE_MES={dia_cierre_mes})"


@dataclass
class ResultadoPipeline:
    periodo: int
    filas_por_base: dict[str, int] = field(default_factory=dict)
    filas_borradas: int | None = None
    filas_insertadas: int | None = None

    def __str__(self) -> str:
        bases = ", ".join(f"{k}={v}" for k, v in self.filas_por_base.items())
        return (
            f"periodo={self.periodo} | bases: {bases} | TBL_FCR: borradas={self.filas_borradas}, "
            f"insertadas={self.filas_insertadas}"
        )
