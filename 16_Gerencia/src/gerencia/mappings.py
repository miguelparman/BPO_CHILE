"""Especificacion declarativa de los 4 flujos de CL_Proc_Volumetria_Gerencia.dtsx.

Los cuatro contenedores del paquete (GERENCIA, ESCALAMIENTO, CLOSE THE LOOP,
T-ATIENDO) tienen la MISMA forma:

    TRUNCATE -> Data Flow [Excel Source 'Hoja1$' -> Conversion de datos ->
    OLE DB Destination] -> DELETE ... WHERE [Numero del caso] IS NULL

y solo difieren en el archivo, la tabla, los anchos DT_STR de la
'Conversion de datos', la disposicion de error de cada columna y el nombre de
algunas columnas destino. Todo eso vive aqui como datos; los componentes
(extractor, validator, transformer, loader) son unicos y se parametrizan con
un FlujoSpec. tests/equivalencia verifica este archivo contra el .dtsx.

Tipos del .dtsx:
  - Excel Source: 'Caso SF' DT_R8, 'Fecha' DT_DATE, el resto DT_WSTR(255).
  - Conversion de datos: 'Caso SF' -> DT_STR(n), 'Fecha' -> DT_DBDATE,
    texto -> DT_STR(n) code page 1252.
"""

from __future__ import annotations

from dataclasses import dataclass

HOJA = "Hoja1"  # OpenRowset 'Hoja1$' (HDR=YES) en los 4 Excel Source
CODE_PAGE = "cp1252"

# Tipo de origen (Excel Source) -> como lo entrega el driver ACE.
CASO = "caso"  # DT_R8 -> DT_STR(n)
FECHA = "fecha"  # DT_DATE -> DT_DBDATE
TEXTO = "texto"  # DT_WSTR(255) -> DT_STR(n) cp1252

# errorRowDisposition / truncationRowDisposition de la Conversion de datos.
FAIL = "FailComponent"
IGNORE = "IgnoreFailure"

# Carpetas (relativas al drive) de origen y destino.
CARPETA_BPO = "Planificación y Control/Insumos/Chile/Especializados"
CARPETA_REPORTING = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/02 ESPECIALIZADOS"


@dataclass(frozen=True)
class ColumnaSpec:
    origen: str  # columna del Excel (Excel Source)
    destino: str  # columna de la tabla (OLE DB Destination)
    tipo: str  # CASO | FECHA | TEXTO
    ancho: int | None  # DT_STR(n); None para DT_DBDATE
    disposicion: str  # FAIL | IGNORE


@dataclass(frozen=True)
class FlujoSpec:
    nombre: str  # contenedor del .dtsx
    subcarpeta: str  # igual en BPO y en ReportingFractalia
    archivo: str
    tabla: str  # [CL_MOVIL].[dbo].<tabla>
    columnas: tuple[ColumnaSpec, ...]
    fast_load: bool  # AccessMode 3 (fast load) / 0 (tabla, fila a fila)
    sql_truncate: str  # Execute SQL Task 'TRUNCATE' (literal del .dtsx)
    sql_delete: str  # Execute SQL Task 'DELETE' (literal del .dtsx)

    @property
    def ruta_bpo(self) -> str:
        return f"{CARPETA_BPO}/{self.subcarpeta}/{self.archivo}"

    @property
    def carpeta_reporting(self) -> str:
        return f"{CARPETA_REPORTING}/{self.subcarpeta}"

    @property
    def ruta_reporting(self) -> str:
        return f"{self.carpeta_reporting}/{self.archivo}"

    @property
    def columnas_origen(self) -> tuple[str, ...]:
        return tuple(c.origen for c in self.columnas)

    @property
    def columnas_destino(self) -> tuple[str, ...]:
        return tuple(c.destino for c in self.columnas)


def _c(origen: str, destino: str, tipo: str, ancho: int | None, disposicion: str) -> ColumnaSpec:
    return ColumnaSpec(origen, destino, tipo, ancho, disposicion)


_NUM = "Número del caso"

GERENCIA = FlujoSpec(
    nombre="GERENCIA",
    subcarpeta="ALTA GERENCIA TCH",
    archivo="ALTA GERENCIA_NVO ARCHIVO.xlsx",
    tabla="TBL_VOLUMETRIA_GERENCIA",
    columnas=(
        _c("Caso SF", _NUM, CASO, 50, FAIL),
        _c("Fecha", "Fecha", FECHA, None, IGNORE),
        _c("Causa Raiz", "Causa Raiz", TEXTO, 255, FAIL),
        _c("Motivo C/R", "Motivo C/R", TEXTO, 255, FAIL),
        _c("Derivado", "Derivado", TEXTO, 255, FAIL),
        _c("cargo", "Cargo", TEXTO, 255, FAIL),
        _c("SM Quiebre", "SM Quiebre", TEXTO, 255, FAIL),
        _c("Coordinador de Quiebre", "Coordinador Quiebre", TEXTO, 255, FAIL),
    ),
    fast_load=False,
    sql_truncate="TRUNCATE TABLE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_GERENCIA]",
    sql_delete="DELETE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_GERENCIA]\nWHERE [Número del caso] IS NULL",
)

ESCALAMIENTO = FlujoSpec(
    nombre="ESCALAMIENTO",
    subcarpeta="ALTA GERENCIA TCH",
    archivo="Escalamiento.xlsx",
    tabla="TBL_VOLUMETRIA_ESCALAMIENTO",
    columnas=(
        _c("Caso SF", _NUM, CASO, 15, FAIL),
        _c("Fecha", "Fecha", FECHA, None, FAIL),
        _c("Causa Raiz", "Causa Raiz", TEXTO, 30, FAIL),
        _c("Motivo C/R", "Motivo C/R", TEXTO, 100, FAIL),
        _c("Derivado", "Derivado", TEXTO, 50, FAIL),
        _c("cargo", "Cargo", TEXTO, 255, IGNORE),  # dtsx: 30 (ver ANCHOS_AMPLIADOS)
        _c("SM Quiebre", "SM Quiebre", TEXTO, 50, FAIL),
        _c("Coordinador de Quiebre", "Coordinador Quiebre", TEXTO, 50, FAIL),
    ),
    fast_load=True,
    sql_truncate="TRUNCATE TABLE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_ESCALAMIENTO]",
    sql_delete="DELETE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_ESCALAMIENTO]\nWHERE [Número del caso] IS NULL\n",
)

CLOSE_THE_LOOP = FlujoSpec(
    nombre="CLOSE THE LOOP",
    subcarpeta="CLOSE THE LOOP",
    archivo="CASOS SALESFORCE - CLOSE THE LOOP.xlsx",
    tabla="TBL_VOLUMETRIA_CLOSE_THE_LOOP",
    columnas=(
        _c("Caso SF", _NUM, CASO, 15, IGNORE),
        _c("Fecha", "Fecha", FECHA, None, IGNORE),
        _c("Causa Raiz", "Causa Raiz", TEXTO, 255, IGNORE),  # dtsx: 30 (ver ANCHOS_AMPLIADOS)
        _c("Motivo C/R", "Motivo C/R", TEXTO, 255, IGNORE),
        _c("Derivado", "Derivado por", TEXTO, 100, IGNORE),
        _c("cargo", "Cargo", TEXTO, 255, IGNORE),
        _c("SM Quiebre", "SM Quiebre", TEXTO, 255, IGNORE),
        _c("Coordinador de Quiebre", "Coordinador Quiebre", TEXTO, 255, IGNORE),
    ),
    fast_load=True,
    sql_truncate="TRUNCATE TABLE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_CLOSE_THE_LOOP]",
    sql_delete="DELETE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_CLOSE_THE_LOOP]\nWHERE [Número del caso] IS NULL",
)

T_ATIENDO = FlujoSpec(
    nombre="T-ATIENDO",
    subcarpeta="T-ATIENDO",
    archivo="CASOS SALESFORCE - T-ATIENDO.xlsx",
    tabla="TBL_VOLUMETRIA_T_ATIENDO",
    columnas=(
        _c("Caso SF", _NUM, CASO, 15, FAIL),
        _c("Fecha", "Fecha", FECHA, None, FAIL),
        _c("Causa Raiz", "Causa Raiz", TEXTO, 30, FAIL),  # la tabla admite 256; la conversion corta en 30
        _c("Motivo C/R", "Motivo C/R", TEXTO, 255, FAIL),
        _c("Derivado", "Derivado por", TEXTO, 100, FAIL),
        _c("cargo", "Cargo", TEXTO, 255, FAIL),
        _c("SM Quiebre", "SM Quiebre", TEXTO, 255, FAIL),
        _c("Coordinador de Quiebre", "Coordinador Quiebre", TEXTO, 255, FAIL),
    ),
    fast_load=True,
    sql_truncate="TRUNCATE TABLE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_T_ATIENDO]",
    sql_delete="DELETE [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_T_ATIENDO]\nWHERE [Número del caso] IS NULL\n",
)

# Columnas ampliadas respecto del .dtsx porque truncaban datos reales
# (decision del usuario 2026-10-19: ampliar en vez de truncar). La tabla se
# amplio con sql/01_ampliar_columnas.sql. {(flujo, columna origen): ancho del .dtsx}
ANCHOS_AMPLIADOS: dict[tuple[str, str], int] = {
    ("ESCALAMIENTO", "cargo"): 30,
    ("CLOSE THE LOOP", "Causa Raiz"): 30,
}

FLUJOS: tuple[FlujoSpec, ...] = (GERENCIA, ESCALAMIENTO, CLOSE_THE_LOOP, T_ATIENDO)
FLUJOS_POR_NOMBRE: dict[str, FlujoSpec] = {f.nombre: f for f in FLUJOS}
