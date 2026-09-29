"""Migracion de 102_calidad/enviar_alerta_encuesta.py (Execute Process Task
'Package\\enviar_alerta_encuesta_py').

Valida si el origen ENCUESTA esta al dia: MAX(Fecha_de_evento + hora_evento)
debe ser >= las 17:00 del dia habil anterior (lunes -> viernes; resto de
dias -> ayer). Deja el resultado en resultado.txt para que Power Automate lo
notifique.

Cambios respecto del original:
- Origen: ENCUESTA.csv de SharePoint (antes el MAX() se calculaba sobre
  [Externos_Frac].[dbo].[ENCUESTA] en sqlclu01lis01.tchile.local). El CSV es
  la exportacion de esa tabla (sus 2 ultimos meses, que contienen el maximo).
- Destino: resultado.txt se escribe por Microsoft Graph en SharePoint
  (Data Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA), antes en
  la carpeta local sincronizada '...\\Gestion Indicadores MDS - Cl_encuesta'
  (OneDrive de gestionindicadoresmds). Se conserva la secuencia del original:
  eliminar el archivo, esperar ALERTA_SEGUNDOS_ESPERA y crearlo de nuevo
  (UTF-8 con BOM), para que el disparador de Power Automate lo detecte.
- Los textos del mensaje se conservan tal cual (Power Automate los reenvia),
  incluida la "Columna evaluada: Fecha_de_evento". Solo cambia la
  "Accion" del mensaje de error, que ahora menciona SharePoint.

Igual que en el .dtsx (FailTaskIfReturnCodeIsNotSuccessValue=False), un
fallo de la alerta NUNCA detiene el proceso: se registra y se sigue.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd

import mappings

logger = logging.getLogger("epa_wsp")

SCHEMA_NAME = "dbo"
TABLE_NAME = "ENCUESTA"
DATE_COLUMN = "Fecha_de_evento"  # texto del mensaje (igual que el original)
HORA_LIMITE = 17
MINUTO_LIMITE = 0
_FMT = "%d/%m/%Y %H:%M:%S"


def obtener_fecha_limite(hoy: date) -> datetime:
    """Lunes: viernes a las 17:00. Martes a domingo: dia anterior a las 17:00.
    (El docstring original dice 18:00, pero HORA_LIMITE = 17.)"""
    referencia = hoy - timedelta(days=3) if hoy.weekday() == 0 else hoy - timedelta(days=1)
    return datetime.combine(referencia, datetime.min.time()).replace(hour=HORA_LIMITE, minute=MINUTO_LIMITE)


def _combinar(fecha: str, hora: str) -> datetime | None:
    """DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', hora), CAST(fecha AS datetime)).
    Un NULL en cualquiera de las dos da NULL (MAX lo ignora)."""
    fecha, hora = (fecha or "").strip(), (hora or "").strip()
    if not fecha or not hora:
        return None
    base = datetime.fromisoformat(fecha[:10])
    partes = hora.split(":")
    horas, minutos = int(partes[0]), int(partes[1]) if len(partes) > 1 else 0
    segundos = int(float(partes[2])) if len(partes) > 2 else 0  # DATEDIFF(SECOND) descarta fracciones
    return base + timedelta(hours=horas, minutes=minutos, seconds=segundos)


def obtener_fecha_maxima(df_encuesta: pd.DataFrame) -> datetime | None:
    valores = [
        v
        for v in (
            _combinar(f, h)
            for f, h in zip(df_encuesta[mappings.ALERTA_COLUMNA_FECHA], df_encuesta[mappings.ALERTA_COLUMNA_HORA])
        )
        if v is not None
    ]
    return max(valores) if valores else None


def generar_mensaje(fecha_maxima: datetime | None, fecha_limite: datetime, ahora: datetime) -> str:
    """Textos identicos a generar_mensaje() del script original."""
    nombre_tabla = f"{SCHEMA_NAME}.{TABLE_NAME}"
    fecha_limite_texto = fecha_limite.strftime(_FMT)
    fecha_validacion_texto = ahora.strftime(_FMT)

    if fecha_maxima is None:
        return (
            "TABLA ENCUESTA DESACTUALIZADA ⚠️\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            "- Último registro: No se encontraron fechas válidas\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla no contiene registros válidos "
            "en la columna evaluada.\n\n"
        )

    fecha_maxima_texto = fecha_maxima.strftime(_FMT)
    if fecha_maxima >= fecha_limite:
        return (
            "TABLA ENCUESTA ACTUALIZADA ✅\n\n"
            f"- Tabla: {nombre_tabla}\n"
            f"- Columna evaluada: {DATE_COLUMN}\n"
            f"- Último registro: {fecha_maxima_texto}\n"
            f"- Fecha mínima esperada: {fecha_limite_texto}\n"
            f"- Fecha de validación: {fecha_validacion_texto}\n\n"
            "Resultado: La tabla contiene registros posteriores "
            "o iguales a la fecha mínima esperada."
        )
    return (
        "TABLA ENCUESTA DESACTUALIZADA ⚠️\n\n"
        f"- Tabla: {nombre_tabla}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Último registro: {fecha_maxima_texto}\n"
        f"- Fecha mínima esperada: {fecha_limite_texto}\n"
        f"- Fecha de validación: {fecha_validacion_texto}\n\n"
        "Resultado: No se encontraron registros posteriores "
        "o iguales a la fecha mínima esperada..\n\n"
    )


def generar_mensaje_error(detalle_error: object, ahora: datetime) -> str:
    return (
        "ERROR EN LA VALIDACIÓN ❌\n\n"
        f"- Tabla: {SCHEMA_NAME}.{TABLE_NAME}\n"
        f"- Columna evaluada: {DATE_COLUMN}\n"
        f"- Fecha de validación: {ahora.strftime(_FMT)}\n\n"
        "Resultado: No fue posible completar la validación.\n\n"
        f"Detalle técnico: {detalle_error}\n\n"
        "Acción: Revisar la conexión a SharePoint (Microsoft Graph), las credenciales, "
        f"el archivo {mappings.ALERTA_ARCHIVO_ORIGEN} y la columna de fecha."
    )


def _eliminar_txt_existente(carpeta, archivo: str, segundos_espera: int, dormir: Callable[[float], None]) -> None:
    """Borra resultado.txt de SharePoint y espera para que Power Automate
    detecte el borrado antes de recrearlo."""
    if carpeta.eliminar(archivo):
        logger.info("Alerta: %s anterior eliminado; esperando %s s.", archivo, segundos_espera)
        dormir(segundos_espera)


def _guardar(carpeta, archivo: str, mensaje: str) -> None:
    carpeta.escribir(archivo, mensaje.encode("utf-8-sig"))  # UTF-8 con BOM, igual que el original


def enviar_alerta(
    reader,
    carpeta,
    archivo: str = "resultado.txt",
    segundos_espera: int = 30,
    ahora: Callable[[], datetime] = datetime.now,
    dormir: Callable[[float], None] = time.sleep,
) -> bool:
    """Devuelve True si el origen esta actualizado. Nunca lanza excepciones.
    'carpeta' es la carpeta de SharePoint destino (sharepoint.carpeta.CarpetaSharePoint)."""
    try:
        _eliminar_txt_existente(carpeta, archivo, segundos_espera, dormir)
        fecha_limite = obtener_fecha_limite(ahora().date())
        fecha_maxima = obtener_fecha_maxima(reader.read_csv(mappings.ALERTA_ARCHIVO_ORIGEN))
        mensaje = generar_mensaje(fecha_maxima, fecha_limite, ahora())
        _guardar(carpeta, archivo, mensaje)
        logger.info(
            "Alerta: %s (ultimo registro %s, minimo esperado %s) -> %s",
            mensaje.splitlines()[0], fecha_maxima, fecha_limite, carpeta.url(archivo),
        )
        return fecha_maxima is not None and fecha_maxima >= fecha_limite
    except Exception as exc:  # noqa: BLE001 - la alerta no debe detener el ETL
        logger.warning("Alerta: no fue posible completar la validacion: %s", exc)
        try:
            _guardar(carpeta, archivo, generar_mensaje_error(exc, ahora()))
        except Exception as exc_txt:  # noqa: BLE001
            logger.warning("Alerta: tampoco fue posible generar %s: %s", archivo, exc_txt)
        return False
