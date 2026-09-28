"""Migracion de 101_trafico/enviar_alerta_trafico.py (Execute Process Task
'Package\\enviar_alerta_trafico').

Valida si el origen de ATENDIDA esta al dia: su START_YYYYMMDD_HHMMSS maximo
debe ser >= las 17:00 del dia anterior. Deja el resultado en resultado.txt
(carpeta sincronizada con OneDrive) para que Power Automate lo notifique.

Cambios respecto del original:
- Origen: ATENDIDA.csv de SharePoint (antes MAX() sobre [Externos_Frac].[dbo].
  [ATENDIDA] en el servidor de Chile). El CSV es la exportacion de esa tabla.
- Los textos del mensaje se conservan tal cual (Power Automate los reenvia),
  incluida la frase "18:00 del dia anterior" aunque el limite real del
  script original es HORA_LIMITE = 17 (inconsistencia preexistente).

Igual que en el .dtsx (FailTaskIfReturnCodeIsNotSuccessValue=False), un
fallo de la alerta NUNCA detiene el proceso: se registra y se sigue.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from extraccion.extractor import parsear_datetime

logger = logging.getLogger("trafico")

SCHEMA_NAME = "dbo"
TABLE_NAME = "ATENDIDA"
ARCHIVO_ORIGEN = "ATENDIDA.csv"
DATE_COLUMN = "START_YYYYMMDD_HHMMSS"
HORA_LIMITE = 17
MINUTO_LIMITE = 0


def obtener_fecha_limite(ahora: datetime) -> datetime:
    """17:00 del dia anterior."""
    ayer = ahora.date() - timedelta(days=1)
    return datetime.combine(ayer, datetime.min.time()).replace(hour=HORA_LIMITE, minute=MINUTO_LIMITE)


def obtener_fecha_maxima(df_atendida: pd.DataFrame) -> datetime | None:
    """Equivalente a SELECT MAX([START_YYYYMMDD_HHMMSS]) FROM [dbo].[ATENDIDA]."""
    valores = [parsear_datetime(v) for v in df_atendida[DATE_COLUMN].tolist() if v and v.strip()]
    return max(valores) if valores else None


def generar_mensaje(fecha_maxima: datetime | None, fecha_limite: datetime, ahora: datetime) -> str:
    nombre_tabla = f"{SCHEMA_NAME}.{TABLE_NAME}"
    fecha_limite_texto = fecha_limite.strftime("%d/%m/%Y %H:%M:%S")
    fecha_validacion_texto = ahora.strftime("%d/%m/%Y %H:%M:%S")

    if fecha_maxima is None:
        return (
            "TABLA DESACTUALIZADA ⚠️\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            "- Último registro: No se encontraron fechas válidas\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla no contiene registros válidos "
            "en la columna evaluada.\n\n"
        )

    fecha_maxima_texto = fecha_maxima.strftime("%d/%m/%Y %H:%M:%S")
    if fecha_maxima >= fecha_limite:
        return (
            "TABLA ACTUALIZADA ✅\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            f"- Último registro: {fecha_maxima_texto}\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla contiene registros posteriores "
            "o iguales a las 18:00 del día anterior."
        )
    return (
        "TABLA DESACTUALIZADA ⚠️\n\n"
        f"- Tabla: {nombre_tabla}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Último registro: {fecha_maxima_texto}\n"
        f"- Fecha mínima esperada: {fecha_limite_texto}\n"
        f"- Fecha de validación: {fecha_validacion_texto}\n\n"
        "Resultado: No se encontraron registros posteriores "
        "o iguales a las 18:00 del día anterior.\n\n"
    )


def generar_mensaje_error(detalle_error: object, ahora: datetime) -> str:
    return (
        "ERROR EN LA VALIDACIÓN ❌\n\n"
        f"- Tabla: {SCHEMA_NAME}.{TABLE_NAME}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Fecha de validación: {ahora.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        "Resultado: No fue posible completar la validación.\n\n"
        f"Detalle técnico: {detalle_error}\n\n"
        "Acción: Revisar la conexión a SharePoint (Microsoft Graph), las credenciales, "
        f"el archivo {ARCHIVO_ORIGEN} y la columna de fecha."
    )


def _eliminar_txt_existente(txt_path: Path, segundos_espera: int, dormir: Callable[[float], None]) -> None:
    """Borra resultado.txt y espera para que OneDrive/Power Automate detecten
    el borrado antes de recrearlo."""
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    if txt_path.exists():
        txt_path.unlink()
        logger.info("Alerta: resultado.txt anterior eliminado; esperando %s s.", segundos_espera)
        dormir(segundos_espera)


def _guardar(txt_path: Path, mensaje: str) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(mensaje, encoding="utf-8-sig")  # UTF-8 con BOM, igual que el original


def enviar_alerta(
    reader,
    txt_path: Path,
    segundos_espera: int = 30,
    ahora: Callable[[], datetime] = datetime.now,
    dormir: Callable[[float], None] = time.sleep,
) -> bool:
    """Devuelve True si el origen esta actualizado. Nunca lanza excepciones."""
    try:
        _eliminar_txt_existente(txt_path, segundos_espera, dormir)
        momento = ahora()
        fecha_limite = obtener_fecha_limite(momento)
        fecha_maxima = obtener_fecha_maxima(reader.read_csv(ARCHIVO_ORIGEN))
        mensaje = generar_mensaje(fecha_maxima, fecha_limite, momento)
        _guardar(txt_path, mensaje)
        logger.info("Alerta: %s (ultimo registro %s, minimo esperado %s)", mensaje.splitlines()[0], fecha_maxima, fecha_limite)
        return fecha_maxima is not None and fecha_maxima >= fecha_limite
    except Exception as exc:  # noqa: BLE001 - la alerta no debe detener el ETL
        logger.warning("Alerta: no fue posible completar la validacion: %s", exc)
        try:
            _guardar(txt_path, generar_mensaje_error(exc, ahora()))
        except Exception as exc_txt:  # noqa: BLE001
            logger.warning("Alerta: tampoco fue posible generar resultado.txt: %s", exc_txt)
        return False
