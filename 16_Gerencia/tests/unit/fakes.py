"""Dobles de prueba: SharePoint en memoria, gateway SQL que registra llamadas
y un generador de .xlsx en memoria."""

from __future__ import annotations

import io
from typing import Any, Sequence

import openpyxl

from exceptions import SharePointResolutionError

CABECERA = ["Nro", "Fecha", "Caso SF", "RUT", "Causa Raiz", "Motivo C/R", "Derivado", "cargo", "SM Quiebre",
            "Coordinador de Quiebre"]


def xlsx(filas: Sequence[Sequence[Any]], cabecera: Sequence[str] = CABECERA, hoja: str = "Hoja1",
         otras_hojas: Sequence[str] = ()) -> bytes:
    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = hoja
    ws.append(list(cabecera))
    for fila in filas:
        ws.append(list(fila))
    for nombre in otras_hojas:
        libro.create_sheet(nombre)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def fila(fecha=None, caso=None, causa="c", motivo="m", derivado="d", cargo="g", sm="s", coord="k") -> list:
    return [1, fecha, caso, "rut", causa, motivo, derivado, cargo, sm, coord]


class FakeSharePoint:
    """Drive en memoria: {ruta: bytes}. 'transformar_subida' simula que
    SharePoint reescribe el archivo al subirlo."""

    def __init__(self, archivos: dict[str, bytes] | None = None, carpetas: Sequence[str] = (),
                 falla_descarga: Sequence[str] = (), transformar_subida=None) -> None:
        self.archivos = dict(archivos or {})
        self.carpetas = set(carpetas)
        self.falla_descarga = set(falla_descarga)
        self.subidas: list[tuple[str, str]] = []
        self._transformar = transformar_subida or (lambda b: b)

    def download_file(self, drive_id: str, ruta: str) -> bytes:
        if ruta in self.falla_descarga or ruta not in self.archivos:
            raise SharePointResolutionError(f"Archivo no encontrado en Graph: {ruta}")
        return self.archivos[ruta]

    def resolve_folder(self, drive_id: str, carpeta: str) -> str:
        if carpeta not in self.carpetas:
            raise SharePointResolutionError(f"Recurso no encontrado: {carpeta}")
        return carpeta

    def upload_file(self, drive_id: str, folder_id: str, nombre: str, contenido: bytes) -> None:
        self.subidas.append((folder_id, nombre))
        self.archivos[f"{folder_id}/{nombre}"] = self._transformar(contenido)

    def get_item(self, drive_id: str, ruta: str) -> dict:
        if ruta not in self.archivos:
            raise SharePointResolutionError(f"Recurso no encontrado: {ruta}")
        return {"name": ruta.rsplit("/", 1)[-1], "size": len(self.archivos[ruta]), "file": {}}


class FakeProveedor:
    def __init__(self, cliente: FakeSharePoint) -> None:
        self.cliente = cliente

    def obtener(self):
        return self.cliente, "drive"


class FakeDb:
    """Gateway que registra recargar_tabla; 'nulos' = filas que borraria el DELETE."""

    def __init__(self, falla: Exception | None = None) -> None:
        self.llamadas: list[dict] = []
        self._falla = falla

    def recargar_tabla(self, sql_truncate, insert_sql, filas, tipos, sql_delete):
        if self._falla:
            raise self._falla
        self.llamadas.append(dict(truncate=sql_truncate, insert=insert_sql, filas=list(filas), tipos=list(tipos),
                                  delete=sql_delete))
        return len(filas), sum(1 for f in filas if f[0] is None)
