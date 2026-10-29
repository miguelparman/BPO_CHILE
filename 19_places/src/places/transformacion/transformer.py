"""TRANSFORMACION: equivalente a la 'Conversion de datos' del Data Flow.

Cada columna DT_WSTR(255) pasa a DT_STR(n) code page 1252 (n en
mappings.COLUMNAS). Las 6 columnas son FailComponent en error y truncamiento:
aqui no se trunca ni se reemplaza nada; validacion/validator.py ya detuvo el
proceso si algun valor no cabe o no existe en 1252.

'Correo Electronico' se lee pero no se convierte (sin salida en la conversion).

Devuelve las filas en el orden de mappings.COLUMNAS (= columnas del INSERT).
"""

from __future__ import annotations

from typing import Sequence

import mappings
from extraccion.extractor import Fila


class Transformer:
    def transformar(self, filas: Sequence[Fila]) -> list[tuple]:
        return [tuple(fila[c.origen] for c in mappings.COLUMNAS) for fila in filas]
