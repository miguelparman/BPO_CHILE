"""Arma la configuracion a partir de variables de entorno (archivo '.env').
Ninguna credencial vive en el codigo ni en este repositorio.

Equivalente al unico Connection Manager de CL_Proc_Trafico_FCR_02.dtsx
('PEOPEDESK0328.CL_TRAFICO'). Su password estaba encriptada por
usuario/maquina (DPAPI, ProtectionLevel=EncryptSensitiveWithUserKey) y no
es reutilizable: se declara en '.env'.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from exceptions import FcrError


@dataclass(frozen=True)
class DbSettings:
    """Equivalente a un Connection Manager OLE DB (Provider MSOLEDBSQL.1)."""

    server: str
    database: str
    user: str
    password: str
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"


@dataclass(frozen=True)
class Settings:
    db_trafico: DbSettings  # Connection Manager 'PEOPEDESK0328.CL_TRAFICO'
    periodo: int | None = None  # PERIODO: fija User::Periodo (None = calculo automatico)
    dia_cierre_mes: int = 4  # DIA_CIERRE_MES: hasta que dia se recarga el mes anterior
    batch_size: int = 5000
    log_dir: Path = Path("logs")


def _require_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise FcrError(f"La variable de entorno '{nombre}' es obligatoria. Ver .env.example.")
    return valor


def _env_int(nombre: str, default: int) -> int:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return default
    return int(valor)


def _env_int_opcional(nombre: str) -> int | None:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return None
    try:
        return int(valor)
    except ValueError as exc:
        raise FcrError(f"La variable de entorno '{nombre}' debe ser un numero entero: {valor!r}") from exc


def cargar_configuracion(base_dir: Path) -> Settings:
    """Carga '.env' (junto a main.py) y arma la configuracion."""
    load_dotenv(base_dir / ".env")

    return Settings(
        db_trafico=DbSettings(
            server=_require_env("DB_SERVER"),
            database=os.getenv("DB_NAME_TRAFICO", "CL_TRAFICO"),
            user=_require_env("DB_USER"),
            password=_require_env("DB_PASSWORD"),
            driver=os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
            encrypt=os.getenv("DB_ENCRYPT", "no"),
            trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes"),
        ),
        periodo=_env_int_opcional("PERIODO"),
        dia_cierre_mes=_env_int_opcional("DIA_CIERRE_MES") or 4,
        batch_size=_env_int("BATCH_SIZE", 5000),
        log_dir=base_dir / "logs",
    )
