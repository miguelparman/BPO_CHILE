"""Constantes de negocio declaradas en Cl_Proc_Logueo.dtsx (Data Flow 'CARGA TABLA').

Todo lo que esta aqui sale del .dtsx; tests/equivalencia/test_equivalencia_dtsx.py
lo verifica contra el paquete original.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Flat File Connection Manager 'Logueo'
# --------------------------------------------------------------------------- #
ARCHIVO = "REPORTE_AGENTES_FRACTALIA_SEM.csv"  # variable User::Ruta_General_Whatsapp
CODE_PAGE = "cp1252"  # DTS:CodePage="1252"
SEPARADOR_COLUMNA = ";"  # _x003B_
SEPARADOR_FILA = "\r\n"  # _x000D__x000A_ (HeaderRowDelimiter y delimitador de la ultima columna)
ANCHO_ORIGEN = 100  # DT_STR(100) en las 45 columnas (DataType 129, MaximumWidth 100)

# Orden posicional de las columnas del archivo (SSIS mapea por POSICION).
COLUMNAS_ORIGEN: tuple[str, ...] = (
    "AÑO", "MES", "DIA", "INTERVALO", "PRIME", "CANAL", "PCRC", "MEDIA", "FAMILIA",
    "CALLCENTER", "SITE", "AGENT_LOGIN", "AGENT_NOMBRE", "Q_ATE", "Q_ATE_DIRECT",
    "Q_TRANSF", "Q_ABN_RING", "Q_OUTBOUND", "Q_CHAT", "Q_ANI_TOT", "T_LOGIN",
    "T_WAITING", "T_TALK", "T_HOLD", "T_ACW", "T_OUTBOUND", "T_CONSULT", "TMO",
    "TMO_REAL", "T_RING", "T_DIALING", "T_INTERNAL", "T_NOTR_BACKOFFICE",
    "T_NOTR_BAÑO", "T_NOTR_CAPACITACION", "T_NOTR_TRABADM", "T_NOTR_COLACION",
    "T_NOTR_BREAK", "T_NOTR_RETROALIMENTACION", "T_NOTR_DEDICACION_PERSONAL",
    "T_NOTR_PROBLEMA_TEC", "T_NOTR_CORTE", "T_NOTR_CONTINGENCIA", "T_NOTR_480",
    "T_NOTR_603",
)

# --------------------------------------------------------------------------- #
# Derived Columns y Data Conversion
# --------------------------------------------------------------------------- #
COLUMNA_FECHA_ANSI = "FechaAnsi"  # Derived Column 'FechaAnsi' (DT_WSTR)
ANCHO_CONVERSION = 50  # Data Conversion: todas a DT_STR(50), FailComponent ante truncamiento

# --------------------------------------------------------------------------- #
# OLE DB Destination 'Destino de OLE DB' -> [CL_LOGUEO].[dbo].[TBL_CONEXIONES]
# --------------------------------------------------------------------------- #
SCHEMA = "dbo"
TABLA_DESTINO = "TBL_CONEXIONES"

# Columna del flujo (antes del prefijo 'Copy of ') -> columna de TBL_CONEXIONES.
# Todas mapean con el mismo nombre salvo estas 3.
_RENOMBRES = {"INTERVALO": "HORA", "AGENT_LOGIN": "ID CONEXION", COLUMNA_FECHA_ANSI: "FECHA ANSI"}
MAPEO_DESTINO: dict[str, str] = {
    c: _RENOMBRES.get(c, c) for c in (*COLUMNAS_ORIGEN, COLUMNA_FECHA_ANSI)
}

# Orden fisico de TBL_CONEXIONES (INFORMATION_SCHEMA). [DNI] varchar(15) no
# esta mapeada en el destino: entra NULL y la completa la tarea 'AGREGA DNI'.
COLUMNAS_DESTINO: tuple[str, ...] = (
    "FECHA ANSI", "AÑO", "MES", "DIA", "HORA", "PRIME", "CANAL", "PCRC", "MEDIA",
    "FAMILIA", "CALLCENTER", "SITE", "ID CONEXION", "AGENT_NOMBRE", "Q_ATE",
    "Q_ATE_DIRECT", "Q_TRANSF", "Q_ABN_RING", "Q_OUTBOUND", "Q_CHAT", "Q_ANI_TOT",
    "T_LOGIN", "T_WAITING", "T_TALK", "T_HOLD", "T_ACW", "T_OUTBOUND", "T_CONSULT",
    "TMO", "TMO_REAL", "T_RING", "T_DIALING", "T_INTERNAL", "T_NOTR_BACKOFFICE",
    "T_NOTR_BAÑO", "T_NOTR_CAPACITACION", "T_NOTR_TRABADM", "T_NOTR_COLACION",
    "T_NOTR_BREAK", "T_NOTR_RETROALIMENTACION", "T_NOTR_DEDICACION_PERSONAL",
    "T_NOTR_PROBLEMA_TEC", "T_NOTR_CORTE", "T_NOTR_CONTINGENCIA", "T_NOTR_480",
    "T_NOTR_603", "DNI",
)
COLUMNAS_INSERT: tuple[str, ...] = tuple(c for c in COLUMNAS_DESTINO if c != "DNI")

# Esquema esperado de TBL_CONEXIONES (lo valida validacion/validator.py).
ESQUEMA_DESTINO: dict[str, tuple[str, int]] = {
    **{c: ("varchar", ANCHO_CONVERSION) for c in COLUMNAS_INSERT},
    "DNI": ("varchar", 15),
}

# --------------------------------------------------------------------------- #
# Lookup 'Busqueda' (Full Cache, salida de NO coincidentes -> destino)
# --------------------------------------------------------------------------- #
# Columna del flujo -> columna de referencia (JoinToReferenceColumn)
CLAVE_LOOKUP: tuple[tuple[str, str], ...] = (
    ("FECHA ANSI", "FECHA ANSI"),  # Copy of FechaAnsi
    ("HORA", "HORA"),  # Copy of INTERVALO
    ("ID CONEXION", "ID CONEXION"),  # Copy of AGENT_LOGIN
)
