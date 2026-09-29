"""Value objects del proceso. Sin dependencias externas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResultadoPipeline:
    filas: dict[str, int] = field(default_factory=dict)  # tabla -> filas insertadas (o a insertar)
    periodos: dict[str, list[int]] = field(default_factory=dict)  # tabla -> ventana reemplazada
    alerta_ok: bool | None = None
    medallia_descargado: bool | None = None
    medallia_rechazadas: int = 0  # filas omitidas (Responsedate invalida o INSERT fallido)
    pasos_fallidos: list[tuple[str, str]] = field(default_factory=list)  # (paso, error)
    log_fin: bool = False

    @property
    def exitoso(self) -> bool:
        return not self.pasos_fallidos

    def __str__(self) -> str:
        filas = ", ".join(f"{k}={v}" for k, v in self.filas.items())
        periodos = ", ".join(f"{k}={v}" for k, v in self.periodos.items())
        fallidos = "; ".join(p for p, _ in self.pasos_fallidos) or "ninguno"
        return (
            f"filas: {filas} | ventanas: {periodos} | alerta_ok={self.alerta_ok} | "
            f"medallia_descargado={self.medallia_descargado} | medallia_rechazadas={self.medallia_rechazadas} | "
            f"Log_Fin={'si' if self.log_fin else 'no'} | pasos fallidos: {fallidos}"
        )
