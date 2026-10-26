r"""Constantes del .dtsx SSIS_CL_Puntualidad.dtsx: tablas, columnas, anchos y tipos.

Control Flow del paquete:

    SLA PRUEBA (Sequence Container)
        TRUNCA TABLA  ->  TBL_SLA_CHILE (Data Flow)  ->  UPDATE
    -> PUNTUALIDAD (Execute SQL Task)

Data Flow 'TBL_SLA_CHILE': Excel Source 'SLA' (hoja 'SLA - Carterizado$') ->
Data Conversion -> OLE DB Destination [CL_ANALISIS].[dbo].[TBL_SLA].
El Excel era ...\BPO - Insumos\Chile\INDICADORES CHILE\SLA Puntualidad\DB.xlsx;
ahora se lee de SharePoint (08 PUNTUALIDAD).
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Tablas
# --------------------------------------------------------------------------- #
BD_SLA = "CL_ANALISIS"
BD_PUNTUALIDAD = "CL_MOVIL"
ESQUEMA = "dbo"
TABLA_SLA = "TBL_SLA"
TABLA_PUNTUALIDAD = "TBL_PUNTUALIDAD"
FUENTE_PUNTUALIDAD = "CL_VISTAS.dbo.VIEW_FACT_SEGUIMIENTO_VOL_GENERAL"
TABLA_FESTIVOS = f"[{BD_PUNTUALIDAD}].[{ESQUEMA}].[TBL_CALENDARIO_DIAS_FESTIVOS]"

# Modo prueba: las mismas tablas con este sufijo (no se toca produccion).
SUFIJO_PRUEBA = "_PY"

MODO_PRUEBA = "prueba"
MODO_PRODUCCION = "produccion"
MODOS = (MODO_PRUEBA, MODO_PRODUCCION)


def _tabla(bd: str, tabla: str) -> str:
    return f"[{bd}].[{ESQUEMA}].[{tabla}]"


@dataclass(frozen=True)
class Destino:
    """Tablas que escribe una corrida."""

    modo: str
    tbl_sla: str
    tbl_puntualidad: str
    fuente: str = FUENTE_PUNTUALIDAD

    @property
    def es_prueba(self) -> bool:
        return self.modo == MODO_PRUEBA


def destino_para(modo: str) -> Destino:
    if modo == MODO_PRODUCCION:
        return Destino(modo, _tabla(BD_SLA, TABLA_SLA), _tabla(BD_PUNTUALIDAD, TABLA_PUNTUALIDAD))
    if modo == MODO_PRUEBA:
        return Destino(
            modo,
            _tabla(BD_SLA, TABLA_SLA + SUFIJO_PRUEBA),
            _tabla(BD_PUNTUALIDAD, TABLA_PUNTUALIDAD + SUFIJO_PRUEBA),
        )
    raise ValueError(f"Modo desconocido: {modo!r}")


# La tabla real: molde de la de prueba y de los tipos de parametro del INSERT.
TBL_SLA_REAL = _tabla(BD_SLA, TABLA_SLA)

# --------------------------------------------------------------------------- #
# Origen: Excel en SharePoint
# --------------------------------------------------------------------------- #
CARPETA_DEFAULT = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/08 PUNTUALIDAD"
ARCHIVO_DEFAULT = "DB.xlsx"
HOJA_DEFAULT = "SLA - Carterizado"  # OpenRowset = 'SLA - Carterizado$'

TEXTO = "texto"
NUMERICO = "numerico"


@dataclass(frozen=True)
class ColumnaSpec:
    """Una columna del Data Flow: Excel Source -> Data Conversion -> destino."""

    origen: str  # columna del Excel
    destino: str  # columna de TBL_SLA
    tipo: str  # TEXTO (wstr -> str cp1252) | NUMERICO (r8 -> numeric(10,2); destino decimal(10,2))
    largo: int | None = None  # ancho de la columna convertida (Data Conversion); TEXTO


# Orden de las columnas del OLE DB Destination (las 8 mapeadas; 'Llave' no se
# carga y queda NULL). Los anchos son los de las columnas 'Copy of ...' del
# Data Conversion; el destino real puede ser mas ancho (Tipologia 150).
COLUMNAS = (
    ColumnaSpec("Tipología", "Tipología", TEXTO, 100),
    ColumnaSpec("Dia/Hora", "Día/Hora", TEXTO, 10),
    ColumnaSpec("SLA Real", "SLA", NUMERICO),
    ColumnaSpec("Condicion", "Calendario/Laboral", TEXTO, 15),
    ColumnaSpec("Estado", "Estado", TEXTO, 15),
    ColumnaSpec("Línea de Negocio", "Línea de Negocio", TEXTO, 15),
    ColumnaSpec("Motivo de contacto", "Motivo de contacto", TEXTO, 50),
    ColumnaSpec("Subtipología", "Subtipología", TEXTO, 200),
)

# numeric(10,2): precision 10, escala 2
NUMERIC_PRECISION = 10
NUMERIC_SCALE = 2
CODIFICACION_DESTINO = "cp1252"  # code page de las columnas 'str' del Data Conversion
