"""Dobles de prueba para LogueoLoader y FuenteArchivo.

Permiten testear el pipeline sin base de datos ni SharePoint, registrando cada
operacion en una lista de eventos para poder aseverar el ORDEN del Control Flow.
"""

from __future__ import annotations

import pandas as pd

import mappings

CABECERA = ";".join(mappings.COLUMNAS_ORIGEN)


def fila_csv(anio="2026", mes="9", dia="23", intervalo="08:30", login="51030151", nombre="Pérez, Ana", resto="0") -> str:
    valores = dict.fromkeys(mappings.COLUMNAS_ORIGEN, resto)
    valores.update({"AÑO": anio, "MES": mes, "DIA": dia, "INTERVALO": intervalo, "AGENT_LOGIN": login, "AGENT_NOMBRE": nombre})
    return ";".join(valores[c] for c in mappings.COLUMNAS_ORIGEN)


def csv_bytes(*filas: str) -> bytes:
    return ("\r\n".join([CABECERA, *filas]) + "\r\n").encode("cp1252")


class FakeFuente:
    descripcion = "fake://REPORTE_AGENTES_FRACTALIA_SEM.csv"

    def __init__(self, contenido: bytes, eventos: list | None = None) -> None:
        self._contenido = contenido
        self.eventos = eventos if eventos is not None else []

    def leer(self) -> bytes:
        self.eventos.append("leer archivo")
        return self._contenido


class FakeLoader:
    def __init__(self, eventos: list | None = None, referencia: list[tuple] | None = None) -> None:
        self.eventos: list = eventos if eventos is not None else []
        self.referencia = referencia or []
        self.fallar_en: set[str] = set()
        self.insertado: pd.DataFrame | None = None
        self.periodo_dni: int | None = None
        self.esquema = dict(mappings.ESQUEMA_DESTINO)

    def _evento(self, nombre: str) -> None:
        self.eventos.append(nombre)
        if nombre in self.fallar_en:
            raise RuntimeError(f"fallo simulado en {nombre}")

    def log_inicio(self) -> None:
        self._evento("Log Inicio")

    def esquema_destino(self):
        self._evento("esquema destino")
        return self.esquema

    def leer_referencia(self) -> pd.DataFrame:
        self._evento("referencia Lookup")
        return pd.DataFrame(self.referencia, columns=["FECHA ANSI", "HORA", "ID CONEXION"], dtype=object)

    def insertar(self, df: pd.DataFrame, esquema) -> int:
        self._evento("INSERT TBL_CONEXIONES")
        self.insertado = df
        return len(df)

    def agregar_dni(self, periodo: int) -> int:
        self._evento("AGREGA DNI")
        self.periodo_dni = periodo
        return 7

    def log_fin(self) -> None:
        self._evento("Log Fin")

    def sp_logueo(self) -> None:
        self._evento("SP")
