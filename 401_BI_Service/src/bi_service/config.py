"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Power BI: App Registration de Repositorio.bi@fractaliasystems.es (PBI_*),
client credentials contra https://analysis.windows.net/powerbi/api.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from exceptions import ConfiguracionError


@dataclass(frozen=True)
class PowerBISettings:
    tenant_id: str
    client_id: str
    client_secret: str
    timeout_s: int = 120


@dataclass(frozen=True)
class Settings:
    powerbi: PowerBISettings
    salida_dir: Path
    workspaces: tuple[str, ...] = ()  # vacio = todos los visibles para la app
    top_actualizaciones: int = 100
    zona_horaria: str = "America/Lima"
    dias_analisis: int = 60
    reintentos_conexion: int = 3
    espera_reintento_s: int = 300
    log_dir: Path = Path("logs")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    try:
        return int(valor)
    except ValueError as exc:
        raise ConfiguracionError(f"La variable de entorno '{nombre}' debe ser un numero entero: {valor!r}") from exc


def cargar_configuracion(base_dir: Path) -> Settings:
    """Carga '.env' (junto a main.py) y arma la configuracion."""
    load_dotenv(base_dir / ".env")

    zona = os.getenv("ZONA_HORARIA") or "America/Lima"
    try:
        ZoneInfo(zona)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfiguracionError(f"ZONA_HORARIA invalida: {zona!r}") from exc

    salida = os.getenv("SALIDA_DIR")
    return Settings(
        powerbi=PowerBISettings(
            tenant_id=_require_env("PBI_TENANT_ID"),
            client_id=_require_env("PBI_CLIENT_ID"),
            client_secret=_require_env("PBI_CLIENT_SECRET"),
            timeout_s=_env_int("PBI_TIMEOUT_S", 120),
        ),
        salida_dir=Path(salida) if salida else base_dir / "salida",
        workspaces=tuple(w.strip() for w in (os.getenv("PBI_WORKSPACES") or "").split(",") if w.strip()),
        top_actualizaciones=_env_int("PBI_TOP_ACTUALIZACIONES", 100),
        zona_horaria=zona,
        dias_analisis=_env_int("DIAS_ANALISIS", 60),
        reintentos_conexion=_env_int("REINTENTOS_CONEXION", 3),
        espera_reintento_s=_env_int("ESPERA_REINTENTO_S", 300),
        log_dir=base_dir / "logs",
    )
