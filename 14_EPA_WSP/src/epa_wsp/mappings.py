"""Constantes de negocio: los 3 traslados del paquete y el esquema de sus
tablas destino en [CL_TEMPORALES_INDICADORES].[dbo].

El .dtsx no tiene Data Flow (no declara columnas ni tipos): los tipos de
datos son los de las tablas destino, tomados de INFORMATION_SCHEMA el
2026-09-29 y verificados en cada corrida por validacion/validator.py.
Cada valor del CSV (texto) se convierte al tipo de su columna destino, igual
que hacia pyodbc al insertar los valores tipados que leia de [Externos_Frac].

Una columna es (nombre, tipo SQL, largo): largo -1 = MAX, None = no aplica.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA = "dbo"


def _nv(largo: int) -> tuple[str, int]:
    return ("nvarchar", largo)


_INT = ("int", None)

# --------------------------------------------------------------------------- #
# TBL_ENCUESTAS_CHILE  <-  ENCUESTA.csv  (Traslado_Calidad_Servidor_55_EPA_ISN.py)
# Mismo orden que 'column_list' del script original (= orden de la tabla).
# --------------------------------------------------------------------------- #
_ENCUESTA: list[tuple[str, tuple[str, int | None]]] = [
    ("id_encuesta_registro", _nv(50)), ("INFORME", _nv(50)), ("tipo_encuesta", _nv(50)),
    ("nom_encuesta", _nv(255)), ("pcrc", _nv(50)), ("skill_agente", _nv(50)),
    ("ani_evento", ("varchar", 50)), ("ani_encuesta", ("varchar", 50)), ("id_conn", _nv(50)),
    ("segundos_encuesta", _nv(10)), ("periodo_evento", _nv(10)), ("dia_evento", _nv(10)),
    ("hora_evento", _nv(16)), ("periodo_envio", _nv(10)), ("dia_envio", _nv(10)),
    ("hora_envio", _nv(16)), ("periodo_encuesta", _nv(10)), ("dia_encuesta", _nv(10)),
    ("hora_encuesta", _nv(50)),
    ("p1", _nv(50)), ("p2", _nv(50)), ("p3", _nv(50)), ("p4", _nv(50)), ("p5", _nv(50)), ("p6", _nv(50)),
    ("r1", _INT), ("r2", _INT), ("r3", _INT), ("r4", _INT), ("r5", _INT), ("r6", _INT),
    ("c1", _INT), ("c2", _INT), ("c3", _INT), ("c4", _INT), ("c5", _INT), ("c6", _INT),
    ("rGLOBAL", _INT), ("cGLOBAL", _INT), ("rNPS", _INT), ("cNPS", _INT), ("rEJECUTIVO", _INT), ("cEJECUTIVO", _INT),
    ("encuestas_ok", _nv(50)), ("fl_calificacion", _nv(50)), ("fl_detractor", _nv(50)),
    ("fl_neutro", _nv(50)), ("fl_promotor", _nv(50)), ("id_proveedor", _nv(50)), ("NEGOCIO", _nv(50)),
    ("PROCESO_NIVEL1", _nv(50)), ("PROCESO_NIVEL2", _nv(50)), ("PROCESO_NIVEL3", _nv(50)),
    ("PROCESO_NIVEL4", _nv(50)), ("PROCESO_NIVEL5", _nv(50)), ("EMPRESA", _nv(255)), ("ZONA", _nv(50)),
    ("REGION", _nv(50)), ("COMUNA", _nv(50)), ("AGENCIA", _nv(50)), ("SUBSEGMENTO", _nv(50)),
    ("TIPO_CONTRATO", _nv(50)), ("PRODUCTO", _nv(50)), ("TECNOLOGIA", _nv(50)), ("RUT_CLIENTE", _nv(50)),
    ("NOMBRE_CLIENTE", _nv(255)), ("RUT_EJECUTIVO", _nv(50)), ("NOMBRE_EJECUTIVO", _nv(255)),
    ("RUT_TECNICO", _nv(50)), ("NOMBRE_TECNICO", _nv(50)), ("id_agente", _nv(50)), ("GERENCIA", _nv(50)),
    ("SUBGERENCIA", _nv(50)), ("fecha_de_encuesta", _nv(10)), ("año_encuesta", _nv(10)),
    ("mes_encuesta", _nv(10)), ("año_evento", _nv(10)), ("mes_evento", _nv(10)),
    ("fecha_de_evento", _nv(10)), ("tipificacion", ("varchar", 255)), ("vq", ("varchar", 250)),
    ("ENDING_TYPE", ("varchar", 50)), ("IV", ("varchar", 3)), ("pcrc_agente", _nv(255)),
]

# --------------------------------------------------------------------------- #
# TBL_ENCUESTAS_WSP_MEDALLIA  <-  WS_MEDALLIA_2.csv
# (Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py). Esquema COMPLETO de la
# tabla: SourceOfThisSurvey y Ejecutivo no se alimentan (quedan NULL, igual
# que en el script original).
# --------------------------------------------------------------------------- #
_WSP: list[tuple[str, tuple[str, int | None]]] = [
    ("SurveyID", _INT), ("TipoDeEncuesta", _nv(255)), ("Responsedate", ("datetime", None)),
    ("Unit", _nv(255)), ("SurveyProgram", _nv(255)), ("SourceOfThisSurvey", _nv(255)),
    ("Subtype", _nv(255)), ("CONNID", _nv(255)), ("NPS", _INT), ("Ejecutivo", _INT),
    ("Facilidad", _INT), ("ISN", _INT), ("verbatim", _nv(-1)), ("Periodo", _INT),
    ("pcrc_eac", _nv(50)), ("loginid", _nv(15)), ("vq", _nv(100)), ("tipificacion", _nv(100)),
    ("cnps", _INT), ("cglobal", _INT), ("cejecutivo", _INT), ("rutcli", _nv(20)),
    ("RequerimientoSolucionado", _nv(55)),
]

# 'column_list' del script original, en su orden (nombre en el CSV == nombre
# en WS_MEDALLIA_2). En la tabla destino 'connid' se llama 'CONNID' (SQL
# Server no distingue mayusculas en los nombres de columna).
WSP_COLUMNAS_ORIGEN = (
    "SurveyID", "TipoDeEncuesta", "Responsedate", "Unit",
    "SurveyProgram", "Subtype", "connid", "NPS",
    "Facilidad", "ISN", "verbatim", "Periodo",
    "pcrc_eac", "loginid", "vq", "tipificacion",
    "cnps", "cglobal", "cejecutivo", "rutcli",
    "RequerimientoSolucionado",
)

# --------------------------------------------------------------------------- #
# TBL_ENCUESTAS_MEDALLIA  <-  Encuestas_Medallia.csv (portal Medallia)
# (CL_Carga_de_encuestas_MEDALLIA.py). Lista 'columnas' del script original.
# --------------------------------------------------------------------------- #
_MEDALLIA: list[tuple[str, tuple[str, int | None]]] = [
    ("ID de encuesta", _nv(255)), ("Tipo de Encuesta", _nv(255)), ("ANI_CONTACTO", _nv(255)),
    ("Responsedate", ("datetime", None)), ("FECHA_EVENTO", _nv(255)), ("NPS", _nv(255)),
    ("¿Lograste resolver tu requerimiento?", _nv(255)), ("SAT - Asesor", _nv(255)),
    ("Facilidad de gestión", _nv(255)), ("SAT - Satisfacción General", _nv(255)),
    ("Estado de encuesta", _nv(255)), ("¿Podrías contarnos las razones de tu respuesta?", _nv(-1)),
    ("ID_CLIENTE_BIEN", _nv(255)), ("PLATAFORMA", _nv(255)), ("CATEGORIA_EMPRESA", _nv(20)),
    ("NOMBRE_EMPRESA", _nv(255)),
]
MEDALLIA_COLUMNA_DUPLICADA = "¿Podrías contarnos las razones de tu respuesta?"


@dataclass(frozen=True)
class Traslado:
    """Un traslado origen -> tabla temporal de CL_TEMPORALES_INDICADORES."""

    paso: str  # nombre de la tarea Execute Process del .dtsx
    script_original: str
    archivo: str  # CSV de origen
    tabla: str  # tabla destino
    esquema: dict[str, tuple[str, int | None]]  # esquema COMPLETO de la tabla destino
    columnas: dict[str, str]  # columna origen (CSV) -> columna destino, en el orden del INSERT
    columna_periodo: str = ""  # columna destino que define la ventana (DELETE por periodo)
    tipo_periodo: str = "int"  # tipo SQL de columna_periodo (para bindear el DELETE)

    @property
    def columnas_destino(self) -> list[str]:
        return list(self.columnas.values())


ENCUESTA = Traslado(
    paso="Traslado_Calidad_Servidor_55_EPA_ISN_py",
    script_original="Traslado_Calidad_Servidor_55_EPA_ISN.py",
    archivo="ENCUESTA.csv",
    tabla="TBL_ENCUESTAS_CHILE",
    esquema=dict(_ENCUESTA),
    columnas={c: c for c, _ in _ENCUESTA},
    columna_periodo="periodo_evento",
    tipo_periodo="nvarchar",
)

_DESTINO_WSP = {c.lower(): c for c, _ in _WSP}
WSP = Traslado(
    paso="Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA_py",
    script_original="Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py",
    archivo="WS_MEDALLIA_2.csv",
    tabla="TBL_ENCUESTAS_WSP_MEDALLIA",
    esquema=dict(_WSP),
    columnas={c: _DESTINO_WSP[c.lower()] for c in WSP_COLUMNAS_ORIGEN},
    columna_periodo="Periodo",
    tipo_periodo="int",
)

MEDALLIA = Traslado(
    paso="CARGA BASE CL_Carga_de_encuestas_MEDALLIA_py",
    script_original="CL_Carga_de_encuestas_MEDALLIA.py",
    archivo="Encuestas_Medallia.csv",
    tabla="TBL_ENCUESTAS_MEDALLIA",
    esquema=dict(_MEDALLIA),
    columnas={c: c for c, _ in _MEDALLIA},
)

TRASLADOS = (WSP, ENCUESTA, MEDALLIA)

# Reglas de limpieza del traslado WSP (clean_row del script original).
WSP_COLUMNA_SUFIJO_FLOAT = "rutcli"  # "77960408.0" -> "77960408"

# Celdas vacias del CSV: csv.writer (01_servidor_chile) escribe igual un NULL
# y un '' del origen. Regla derivada de los datos reales (ver
# docs/EQUIVALENCIA.md): en WS_MEDALLIA_2 'tipificacion' es '' cuando la
# encuesta cruzo con la interaccion (pcrc_eac informado) y NULL cuando no
# (131 de 131 filas historicas); el resto de columnas vacias son NULL.
WSP_TEXTO_VACIO_SI_INFORMADA = {"tipificacion": "pcrc_eac"}

# Alerta (enviar_alerta_encuesta.py)
ALERTA_ARCHIVO_ORIGEN = ENCUESTA.archivo
ALERTA_COLUMNA_FECHA = "fecha_de_evento"  # DATE_COLUMN = "Fecha_de_evento" (SQL no distingue mayusculas)
ALERTA_COLUMNA_HORA = "hora_evento"


@dataclass(frozen=True)
class ProcedimientoAlmacenado:
    paso: str
    nombre: str
    base: str = "CL_CALIDAD"
    lee: tuple[str, ...] = field(default_factory=tuple)


SP_EPA_ISN_CHILE = ProcedimientoAlmacenado(
    paso="SP_EPA_ISN_CHILE", nombre="SP.EPA_ISN_CHILE", lee=(ENCUESTA.tabla, WSP.tabla)
)
SP_PROCESO_ENCUESTAS_MEDALLIA = ProcedimientoAlmacenado(
    paso="SP_PROCESO_ENCUESTAS_MEDALLIA", nombre="SP.SP_PROCESO_ENCUESTAS_MEDALLIA", lee=(MEDALLIA.tabla,)
)
