"""Variable SSIS User::Periodo.

Expresion del .dtsx (EvaluateAsExpression=True):

    DAY(GETDATE()) <= 4
    ? (YEAR(DATEADD("Month",-1,GETDATE()))*100 + MONTH(DATEADD("Month",-1,GETDATE())))
    : (YEAR(GETDATE())*100 + MONTH(GETDATE()))

GETDATE() de una expresion SSIS es el reloj de la MAQUINA que ejecuta el
paquete (no el del SQL Server). Solo la usa la tarea 'AGREGA DNI' (parametro
'?', tipo 131 = numerico).

Prioridad del valor: --periodo (linea de comandos) > PERIODO (.env) > regla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from exceptions import ConfiguracionError

_FORMATO = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class Periodo:
    valor: int  # YYYYMM
    origen: str  # 'linea de comandos', '.env' o 'regla dia<=4'

    def __str__(self) -> str:
        return f"{self.valor} (origen: {self.origen})"


def calcular_periodo(hoy: date) -> int:
    """Regla del .dtsx: hasta el dia 4 inclusive se toma el mes anterior."""
    if hoy.day <= 4:
        anio, mes = (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)
    else:
        anio, mes = hoy.year, hoy.month
    return anio * 100 + mes


def validar_periodo(texto: str, origen: str) -> int:
    valor = texto.strip()
    if not _FORMATO.match(valor) or not 1 <= int(valor[4:]) <= 12:
        raise ConfiguracionError(f"Periodo invalido en {origen}: {texto!r}. Formato esperado YYYYMM (mes 01-12).")
    return int(valor)


def resolver_periodo(cli: str | None, env: str | None, hoy: date) -> Periodo:
    if cli is not None and cli.strip():
        return Periodo(validar_periodo(cli, "--periodo"), "linea de comandos")
    if env is not None and env.strip():
        return Periodo(validar_periodo(env, "PERIODO (.env)"), ".env")
    return Periodo(calcular_periodo(hoy), "regla dia<=4")
