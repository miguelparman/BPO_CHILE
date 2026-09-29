"""Constantes de negocio de la tarea 'Alimenta Tabla' de CL_Proc_Trafico_FCR_02.dtsx.

El T-SQL original repite 5 veces el mismo bloque (una tabla temporal por
base) cambiando solo la tabla de origen, el SERVICIO y la etiqueta BASE. Aqui
cada bloque es una entrada de BASES, y todas pasan por la misma
transformacion (transformacion/transformer.py). La prueba
tests/equivalencia/test_equivalencia_dtsx.py extrae estas constantes del
.dtsx y verifica que coinciden.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "dbo"
TABLA_DESTINO = "TBL_FCR"

# Columna de la que salen FECHA, HORA y [FECHA/HORA], y por la que se filtra el periodo.
COLUMNA_INICIO = "AGENT_START_YYYYMMDD_HHMMSS"


@dataclass(frozen=True)
class BaseFCR:
    """Un bloque SELECT ... INTO #TBL_TMP_* del T-SQL original."""

    tabla_temporal: str  # nombre de la #temp en el .dtsx (solo trazabilidad)
    tabla_origen: str  # CL_TRAFICO.dbo.<tabla_origen>
    servicio: str  # WHERE SERVICIO IN ('<servicio>')
    base: str  # literal 'LLAMADAS' / 'WHATSAPP' de la columna BASE


# En el orden del UNION ALL final. WHATSAPP 'USUARIOS' no existe en el
# original (solo TRIADAS y CARTERIZADOS en TBL_CHAT) y no se agrega.
BASES: tuple[BaseFCR, ...] = (
    BaseFCR("#TBL_TMP_LLAMADAS_TRIADAS", "TBL_LLAMADAS_ATENDIDAS_INBOUND", "TRIADAS", "LLAMADAS"),
    BaseFCR("#TBL_TMP_LLAMADAS_CARTERIZADOS", "TBL_LLAMADAS_ATENDIDAS_INBOUND", "CARTERIZADOS", "LLAMADAS"),
    BaseFCR("#TBL_TMP_LLAMADAS_USUARIOS", "TBL_LLAMADAS_ATENDIDAS_INBOUND", "USUARIOS", "LLAMADAS"),
    BaseFCR("#TBL_TMP_CHAT_TRIADAS", "TBL_CHAT", "TRIADAS", "WHATSAPP"),
    BaseFCR("#TBL_TMP_CHAT_CARTERIZADOS", "TBL_CHAT", "CARTERIZADOS", "WHATSAPP"),
)


@dataclass(frozen=True)
class Umbral:
    """CASE WHEN DATEDIFF(SECOND, [FECHA/HORA], [FECHA/HORA-PROXIMO]) <= segundos
    THEN 0 ELSE 1 END <columna>, y su etiqueta en TRAMO_QUIEBRE."""

    columna: str
    segundos: int
    tramo: str


# En el orden de las columnas y del CASE de TRAMO_QUIEBRE.
UMBRALES: tuple[Umbral, ...] = (
    Umbral("FCR_30min", 1800, "Quiebre en 30 Min"),
    Umbral("FCR_1h", 3600, "Quiebre en 1 Hora"),
    Umbral("FCR_2h", 7200, "Quiebre en 2 Horas"),
    Umbral("FCR_3h", 10800, "Quiebre en 3 Horas"),
    Umbral("FCR_4h", 14400, "Quiebre en 4 Horas"),
    Umbral("FCR_6h", 21600, "Quiebre en 6 Horas"),
    Umbral("FCR_8h", 28800, "Quiebre en 8 Horas"),
    Umbral("FCR_10h", 36000, "Quiebre en 10 Horas"),
    Umbral("FCR_12h", 43200, "Quiebre en 12 Horas"),
    Umbral("FCR_24h", 86400, "Quiebre en 24 Horas"),
    Umbral("FCR_48h", 172800, "Quiebre en 48 Horas"),
    Umbral("FCR_72h", 259200, "Quiebre en 72 Horas"),
    Umbral("FCR_7D", 604800, "Quiebre en 7 Días"),
    Umbral("FCR_15d", 1296000, "Quiebre en 15 Días"),
)
SIN_QUIEBRE = "Sin Quiebre"

# Columnas que se leen de cada tabla de origen y su tipo real en CL_TRAFICO.
# AGENT_START debe ser 'datetime': asi CAST(... AS DATETIME) es la identidad y
# [FECHA/HORA] conserva exactamente el valor de origen.
COLUMNAS_ORIGEN: dict[str, tuple[str, int | None]] = {
    COLUMNA_INICIO: ("datetime", None),
    "ANI": ("varchar", 25),
    "SERVICIO": ("varchar", 15),
    "LOGINID": ("varchar", 15),
}

# Esquema de [CL_TRAFICO].[dbo].[TBL_FCR] en ORDEN DE POSICION. El original
# hace 'INSERT INTO TBL_FCR SELECT A.*, ... TRAMO_QUIEBRE' sin lista de
# columnas (carga posicional): el orden del SELECT es el de esta tupla.
COLUMNAS_DESTINO: tuple[tuple[str, str, int | None], ...] = (
    ("FECHA", "date", None),  # CAST(AGENT_START AS DATE)
    ("HORA", "varchar", 8),  # CAST(CAST(AGENT_START AS TIME) AS VARCHAR(8))
    ("ANI", "varchar", 25),
    ("SERVICIO", "varchar", 15),
    ("LOGINID", "varchar", 15),
    ("BASE", "varchar", 8),  # literal; NOT NULL
    ("FECHA/HORA", "datetime", None),  # CAST(AGENT_START AS DATETIME)
    ("FECHA/HORA-PROXIMO", "datetime", None),  # LEAD(...) OVER (PARTITION BY ANI,SERVICIO ...)
    *((u.columna, "int", None) for u in UMBRALES),  # NOT NULL
    ("TRAMO_QUIEBRE", "nvarchar", 255),
)
NOMBRES_DESTINO: tuple[str, ...] = tuple(c for c, _, _ in COLUMNAS_DESTINO)
COLUMNAS_NO_NULAS = ("BASE", *(u.columna for u in UMBRALES))
