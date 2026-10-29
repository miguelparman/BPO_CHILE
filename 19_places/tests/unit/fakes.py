"""Dobles de prueba: gateway SQL que registra llamadas, SharePoint en memoria
y un generador de .xlsx en memoria."""

from __future__ import annotations

import io
from typing import Any, Sequence

import openpyxl

CABECERA = ["id", "Etiqueta", "plataforma", "RUT", "Asesor", "DNI", "Correo Electronico"]


def xlsx(filas: Sequence[Sequence[Any]], cabecera: Sequence[str] = CABECERA, hoja: str = "Hoja1") -> bytes:
    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = hoja
    ws.append(list(cabecera))
    for fila in filas:
        ws.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def fila(id_="51030001", etiqueta="Place_1", plataforma="PLAT", rut="1-9", asesor="Ana", dni="123", correo="a@b.cl") -> list:
    return [id_, etiqueta, plataforma, rut, asesor, dni, correo]


class FakeDb:
    """Gateway que registra las llamadas; 'nulos' = filas que borraria el DELETE ID IS NULL."""

    def __init__(self, falla: Exception | None = None) -> None:
        self.recargas: list[dict] = []
        self.transacciones: list[list] = []
        self._falla = falla

    def recargar_tabla(self, sql_truncate, insert_sql, filas, anchos, sql_limpia):
        if self._falla:
            raise self._falla
        self.recargas.append(
            dict(truncate=sql_truncate, insert=insert_sql, filas=list(filas), anchos=list(anchos), limpia=sql_limpia)
        )
        return len(filas), sum(1 for f in filas if f[0] is None)

    def ejecutar_en_transaccion(self, pasos):
        if self._falla:
            raise self._falla
        self.transacciones.append(list(pasos))
        return [3 for _ in pasos]


class FakeProveedor:
    def __init__(self, cliente, drive_id: str = "drive") -> None:
        self.cliente = cliente
        self.drive_id = drive_id

    def obtener(self):
        return self.cliente, self.drive_id
