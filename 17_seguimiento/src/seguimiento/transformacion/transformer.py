"""Transformacion de un Data Flow: de las filas del Flat File a las filas que
recibe el OLE DB Destination, columna por columna segun mappings.FlujoSpec.

Orden por columna (el mismo que el Data Flow):
  0a. Tildes mal codificadas en el dato de Salesforce -> reparadas
     (transformacion/codificacion.py; desviacion intencional de SSIS, que las
     dejaba como '?'). Se registra en el log cuantas se repararon.
  0b. Saltos de linea dentro del texto -> CRLF (saltos_crlf). Es lo unico del
     paso 'Convierte CSV' del paquete 01 que cambiaba datos: SSIS veia CRLF
     dentro de comentarios, soluciones, valores del historial, etc. Sin esto
     el LIMPIA de Comentarios daria 1 espacio en vez de 2 y el MERGE
     reinsertaria todos los comentarios multilinea.
  1. Flat File Source: ancho de la columna de salida (DT_STR) y, si la salida
     es DT_DATE, el parseo de la fecha.
  2. Derived Column que reemplaza la columna (REPLACE de Correos).
  3. Derived Column LEFT(n) (Casos B, Comentarios).
  4. Data Conversion: DT_WSTR(n), DT_STR(n,1252), DT_NTEXT, DT_DATE,
     DT_NUMERIC(18,0), con su errorRowDisposition / truncationRowDisposition:
       FailComponent -> el componente falla y el paquete se detiene
                        (aqui: ValidacionError, no se carga nada).
       IgnoreFailure -> truncamiento: el valor se trunca al ancho;
                        error: el valor queda NULL.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence

import mappings
from exceptions import ValidacionError
from logging_setup import NOMBRE_LOGGER
from mappings import ColumnaDestino, FlujoSpec
from transformacion.codificacion import reparar_codificacion
from transformacion.fechas import fecha_a_texto, parsear_fecha

logger = logging.getLogger(NOMBRE_LOGGER)

MAX_ERRORES_REPORTADOS = 10


_SALTO = re.compile(r"\r\n|\r|\n")


def saltos_crlf(valor: str) -> str:
    """Todo salto de linea (LF, CR o CRLF) dentro de un valor -> CRLF."""
    return _SALTO.sub("\r\n", valor) if ("\n" in valor or "\r" in valor) else valor


class _ErrorColumna(Exception):
    def __init__(self, componente: str, detalle: str) -> None:
        super().__init__(detalle)
        self.componente = componente
        self.detalle = detalle


def _numerico(texto: str) -> Decimal:
    """DT_NUMERIC(18,0) desde texto."""
    try:
        valor = Decimal(texto.strip()).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"'{texto}' no es numerico") from exc
    if len(valor.as_tuple().digits) > 18:
        raise ValueError(f"'{texto}' excede la precision 18")
    return valor


def _convertir(valor: Any, col: ColumnaDestino) -> Any:
    conv = col.conversion
    if conv.tipo == mappings.NTEXT:
        return valor
    if conv.tipo == mappings.WSTR:
        if isinstance(valor, datetime):
            valor = fecha_a_texto(valor)
        if valor is not None and len(valor) > conv.ancho:
            if conv.truncamiento_ignora:
                return valor[: conv.ancho]
            raise _ErrorColumna("Data Conversion", f"truncamiento: {len(valor)} caracteres > DT_WSTR({conv.ancho})")
        return valor
    if conv.tipo == mappings.STR1252:
        try:
            valor.encode("cp1252")
        except UnicodeEncodeError as exc:
            if conv.error_ignora:
                return None
            raise _ErrorColumna("Data Conversion", f"caracter no representable en DT_STR 1252: {exc}") from exc
        if len(valor) > conv.ancho:
            if conv.truncamiento_ignora:
                return valor[: conv.ancho]
            raise _ErrorColumna("Data Conversion", f"truncamiento: {len(valor)} caracteres > DT_STR({conv.ancho})")
        return valor
    if conv.tipo in (mappings.FECHA, mappings.NUMERICO):
        try:
            return parsear_fecha(valor) if conv.tipo == mappings.FECHA else _numerico(valor)
        except ValueError as exc:
            if conv.error_ignora:
                return None
            raise _ErrorColumna("Data Conversion", f"no se pudo convertir a {conv.tipo}: {exc}") from exc
    raise ValueError(f"Tipo de conversion desconocido: {conv.tipo}")


def transformar_valor(fila: Sequence[str], col: ColumnaDestino, flujo: FlujoSpec) -> Any:
    return _transformar_texto(reparar_codificacion(fila[col.origen]), col, flujo)


def _transformar_texto(texto: str, col: ColumnaDestino, flujo: FlujoSpec) -> Any:
    origen = flujo.archivo.columnas[col.origen]
    valor: Any = saltos_crlf(texto)

    # 1. Flat File Source
    if origen.tipo == mappings.FF_FECHA:
        if valor == "":
            valor = None
        else:
            try:
                valor = parsear_fecha(valor)
            except ValueError as exc:
                raise _ErrorColumna("Flat File Source", f"conversion a DT_DATE: {exc}") from exc
    elif origen.tipo == mappings.FF_STR and len(valor) > origen.ancho:
        raise _ErrorColumna("Flat File Source", f"truncamiento: {len(valor)} caracteres > DT_STR({origen.ancho})")

    # 2. Derived Column (reemplaza la columna)
    for posicion, buscar, reemplazar in flujo.reemplazos:
        if posicion == col.origen and isinstance(valor, str):
            valor = valor.replace(buscar, reemplazar)

    # 3. Derived Column LEFT(n)
    if col.left is not None and isinstance(valor, str):
        valor = valor[: col.left]

    # 4. Data Conversion
    return _convertir(valor, col)


def transformar(flujo: FlujoSpec, filas: Sequence[Sequence[str]]) -> list[tuple]:
    """Filas listas para el INSERT (en el orden de flujo.columnas). Levanta
    ValidacionError si alguna columna FailComponent falla (reporta las
    primeras MAX_ERRORES_REPORTADOS)."""
    salida: list[tuple] = []
    errores: list[str] = []
    total_errores = 0
    reparados: dict[str, list] = {}  # columna -> [cantidad, ejemplo (antes, despues)]
    for numero, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        valores = []
        for col in flujo.columnas:
            original = fila[col.origen]
            texto = reparar_codificacion(original)
            if texto != original:
                r = reparados.setdefault(col.destino, [0, (original, texto)])
                r[0] += 1
            try:
                valores.append(_transformar_texto(texto, col, flujo))
            except _ErrorColumna as exc:
                total_errores += 1
                if len(errores) < MAX_ERRORES_REPORTADOS:
                    muestra = fila[col.origen][:60]
                    errores.append(
                        f"fila {numero}, columna '{flujo.archivo.columnas[col.origen].nombre}' -> [{col.destino}] "
                        f"({exc.componente}): {exc.detalle} (valor: {muestra!r})"
                    )
                valores.append(None)
        salida.append(tuple(valores))
    if total_errores:
        raise ValidacionError(
            f"{flujo.componente} ({flujo.archivo.nombre}): {total_errores} error(es) de conversion "
            "(FailComponent en el .dtsx):\n  " + "\n  ".join(errores)
        )
    for columna, (cantidad, (antes, despues)) in reparados.items():
        logger.info(
            "  %s [%s]: %s valor(es) con tildes mal codificadas reparados, p.ej. %s -> %s",
            flujo.archivo.nombre, columna, cantidad, *_contexto(antes, despues),
        )
    return salida


def _contexto(antes: str, despues: str, largo: int = 40) -> tuple[str, str]:
    """Tramo de ambos textos alrededor de la primera reparacion (para el log)."""
    i = next((k for k, ch in enumerate(antes) if ch in "\x81\x8d\x8f\x90\x9dÃÂ"), 0)
    desde = max(0, i - largo // 2)
    return ascii(antes[desde : i + largo // 2]), ascii(despues[desde : i + largo // 2 - 1])
