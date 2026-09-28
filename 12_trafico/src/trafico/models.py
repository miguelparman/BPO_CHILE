"""Value objects del proceso. Sin dependencias externas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


DIA_CIERRE_MES_DEFAULT = 4


def calcular_periodo(hoy: date, dia_cierre_mes: int = DIA_CIERRE_MES_DEFAULT) -> int:
    """Equivalente exacto de la variable de paquete User::Periodo
    (EvaluateAsExpression=True):

        DAY(GETDATE()) <= 4
            ? YEAR(DATEADD("Month",-1,GETDATE())) * 100 + MONTH(DATEADD("Month",-1,GETDATE()))
            : YEAR(GETDATE()) * 100 + MONTH(GETDATE())

    Los primeros 'dia_cierre_mes' dias del mes (4 en el original, configurable
    con DIA_CIERRE_MES en .env) se sigue recargando el mes anterior (cierre).
    Los 7 scripts Traslado_Trafico_Servidor_55_*.py calculaban lo mismo con
    relativedelta; aqui hay una unica implementacion para todo el proceso.
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
    PERIODO (.env) > calculo automatico (User::Periodo)."""
    if periodo_cli is not None:
        return validar_periodo(periodo_cli), "--periodo"
    if periodo_env is not None:
        return validar_periodo(periodo_env), "PERIODO (.env)"
    return calcular_periodo(hoy, dia_cierre_mes), f"automatico (DIA_CIERRE_MES={dia_cierre_mes})"


@dataclass
class ResultadoPipeline:
    periodo: int
    filas_temporales: dict[str, int] = field(default_factory=dict)
    filas_cl_trafico: dict[str, int] = field(default_factory=dict)
    alerta_ok: bool | None = None

    def __str__(self) -> str:
        temp = ", ".join(f"{k}={v}" for k, v in self.filas_temporales.items())
        dest = ", ".join(f"{k}={v}" for k, v in self.filas_cl_trafico.items())
        return f"periodo={self.periodo} | temporales: {temp} | CL_TRAFICO: {dest}"
