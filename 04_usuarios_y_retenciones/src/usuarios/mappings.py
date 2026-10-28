"""Nombres de tabla/columna y especificaciones de conversion/truncamiento de
los componentes 'Data Conversion' de los 5 paquetes USUARIOS_*.dtsx.

Cada seccion cita el .dtsx y el Data Flow de origen.
"""

from __future__ import annotations

# ===========================================================================
# Origenes SharePoint (reemplazan al Connection Manager OLE DB 'Externos_Frac')
# ===========================================================================
#
# El nombre de archivo CSV coincide, a proposito, con el nombre de la tabla
# de origen SQL Server que reemplaza -- identico al criterio ya usado en
# 30_parque/mappings.py para 'pqe_fijtot2023.csv'/'pqe_movtot2023.csv' (que
# vienen del MISMO folder de SharePoint, ver sharepoint/reader.py). Las
# consultas SQL originales (ahora reemplazadas por extraccion+pandas, ver
# extraccion/extractor.py) quedan documentadas en sql.py como referencia de
# la logica de negocio migrada.

# Delimitador de los CSV publicados en SharePoint. Se asume ';' por
# consistencia con 30_parque (confirmado alli contra el archivo real de
# 'pqe_fijtot2023.csv'/'pqe_movtot2023.csv', que se leen del mismo folder) --
# a confirmar contra los archivos reales del resto de las tablas.
CSV_DELIMITER = ";"

PARQUE_FIJO_ARCHIVO = "pqe_fijtot2023.csv"
PARQUE_MOVIL_ARCHIVO = "pqe_movtot2023.csv"
RUT_MARCA_CARTERA_ARCHIVO = "RUT_marca_cartera.csv"
RETENCIONES_BAJAS_FRAUDE_ARCHIVO = "BAJAS_FRAUDE.csv"
RETENCIONES_BAJAS_POR_ALTA_ARCHIVO = "BAJAS_POR_ALTA_FO.csv"
RETENCIONES_BD_RETEN_ARCHIVO = "BD_RETEN_V2.csv"
INTENCIONES_BAJAS_FIJO_ARCHIVO = "BAJAS_FIJO.csv"
INTENCIONES_BAJAS_MOVIL_ARCHIVO = "BAJAS_MOVIL.csv"
INTENCIONES_V2_ARCHIVO = "INTENCIONES_V2.csv"
ITEM_AMDOCS_ARCHIVO = "INTEN_AMDOCS.csv"
SAIP_ARCHIVO = "base_saip.csv"

# ===========================================================================
# USUARIOS_0101 Parque.dtsx -- Data Flow 'PARQUE'
# ===========================================================================

# Destino OLE DB 'ParqueTCH' (CL_USUARIOS.dbo.ParqueTCH). Sin componente
# 'Data Conversion': las 7 columnas del Origen OLE DB '55_PARQUE' se mapean
# 1:1 por nombre, sin casteos ni truncamientos adicionales en Python (los
# unicos limites de ancho son los de las columnas destino en SQL Server).
PARQUE_TABLE = "ParqueTCH"

# ===========================================================================
# USUARIOS_0201 SSIS_CL_Retenciones.dtsx
# ===========================================================================

# Destinos OLE DB de 'TBL_SERVCH_BAJAS_FRAUDE' y
# 'TBL_SERVCH_BAJAS_POR_ALTA_FO': sin componente 'Data Conversion', copia 1:1.
RETENCIONES_BAJAS_FRAUDE_TABLE = "TBL_SERVCH_BAJAS_FRAUDE"
RETENCIONES_BAJAS_POR_ALTA_TABLE = "TBL_SERVCH_BAJAS_POR_ALTA_FO"

# Destino OLE DB 'BD_RETEN (Local)' del Data Flow 'BD_RETEN'.
RETENCIONES_BD_RETEN_TABLE = "BD_RETEN"

# Columnas del Origen OLE DB 'BD_RETEN_V2 (223)' que el componente 'Data
# Conversion' NO lleva al destino: 'ROWNO' (solo sirve para el filtro
# ROWNO=1 de la consulta, nunca se inserta) y 'motivo' (se selecciona en el
# CTE pero no se le crea columna de salida "Copy of ..." -- queda sin usar
# en el .dtsx original).
BD_RETEN_COLUMNAS_DESCARTADAS: tuple[str, ...] = ("ROWNO", "motivo")

# Anchos de truncamiento del componente 'Data Conversion' (BD_RETEN_V2 ->
# BD_RETEN). 'Evaluacion' llega como literal entero 1 desde el CTE y se
# convierte a string(5) -- se preserva ese cambio de tipo.
BD_RETEN_TRUNCATION_LENGTHS: dict[str, int] = {
    "case_idnum": 50,
    "rut": 50,
    "rutcli": 50,
    "nomcli": 100,
    "segme": 50,
    "nom_sm": 100,
    "nom_sup": 100,
    "sub_segme": 50,
    "tpo_serv": 50,
    "tpo_prod": 50,
    "tpo_tecno": 50,
    "submotivo": 500,
    "submotivo2": 100,
    "canal_ing": 100,
    "subcan_ing": 100,
    "canal_res": 100,
    "subcan_res": 100,
    "cargo_res": 100,
    "canal_hres": 100,
    "Evaluacion": 5,
    "LLAVE": 250,
}

# ===========================================================================
# USUARIOS_0300 ETL_INTENCIONES.dtsx
# ===========================================================================

# Destinos OLE DB de 'TBL_CH_BAJAS' (2 pipes, ambos sin 'Data Conversion').
INTENCIONES_BAJAS_FIJO_TABLE = "TBL_CH_BAJAS_FIJO"
INTENCIONES_BAJAS_MOVIL_TABLE = "TBL_CH_BAJAS_MOVIL"

# Destino OLE DB 'INTENCIONES LOCAL' del Data Flow 'INTENCIONES'
# (disposicion de error IgnoreFailure -- ver db.bulk_insert_ignorando_errores).
INTENCIONES_TABLE = "INTENCIONES"

# Ancho de truncamiento del componente 'Data Conversion 1' del Data Flow
# 'INTENCIONES': 'CASE_ID_NUMBER' (str/255 en el origen) se convierte a
# str(15). 'CASE_NOTE' se convierte a nText (sin limite practico en Python).
INTENCIONES_V2_TRUNCATION_LENGTHS: dict[str, int] = {
    "CASE_ID_NUMBER": 15,
}

# Tablas de la Sequence "TABULANDO INTENCIONES" (todas en CL_USUARIOS).
INTENCIONES_TEMP01_TABLE = "INTENCIONES_TEMP01_NotasLimpias"
INTENCIONES_TEMP02_TABLE = "INTENCIONES_TEMP02_NotasDivididas"
INTENCIONES_TEMP03_TABLE = "INTENCIONES_TEMP03_NotasSeparadas"
INTENCIONES_TEMP04_TABLE = "INTENCIONES_TEMP04_NotasConFechaUsuario"
INTENCIONES_TAB_TABLE = "INTENCIONES_TAB"

# ===========================================================================
# USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx -- Data Flow 'INTEN_AMDOCS'
# ===========================================================================

ITEM_AMDOCS_TABLE = "INTEN_AMDOCS"

# Columnas del Origen OLE DB que el componente 'Data Conversion' NO lleva al
# destino ('rutcli' se convierte pero nunca se mapea) o que se renombran al
# destino ('ROWNO' -- siempre 1, dado el filtro ROWNO=1 -- se mapea a la
# columna 'Evaluacion', un nombre de columna reutilizado/legado).
ITEM_AMDOCS_COLUMNAS_DESCARTADAS: tuple[str, ...] = ("rutcli",)
ITEM_AMDOCS_RENOMBRES: dict[str, str] = {"ROWNO": "Evaluacion"}

# Columnas enteras (i4) del componente 'Data Conversion'. Disposicion
# IgnoreFailure: un valor que no castea no aborta la fila, queda NULL.
ITEM_AMDOCS_INT_COLUMNS: tuple[str, ...] = (
    "rut",
    "case_idnum",
    "agent_orig",
    "agent_reso",
    "periodo",
    "pqe_stb",
    "pqe_baf",
    "pqe_tv",
    "pqe_voz",
    "pqe_bam",
    "cantidad",
)

# Columnas de fecha/hora (dbTimeStamp) del componente 'Data Conversion'.
# Disposicion IgnoreFailure: un valor que no castea no aborta la fila, queda
# NULL (NaT).
ITEM_AMDOCS_DATETIME_COLUMNS: tuple[str, ...] = ("case_optim", "case_cltim", "ValidFrom")

# Anchos de truncamiento (str) del componente 'Data Conversion'. Disposicion
# IgnoreFailure: se trunca en silencio, nunca aborta la fila (a diferencia de
# BD_RETEN/INTENCIONES_V2, que abortan por defecto -- ver README, "Notas de
# fidelidad", sobre por que este Data Flow es distinto).
#
# Confirmados contra el esquema REAL de [CL_USUARIOS].[dbo].[INTEN_AMDOCS]
# (INFORMATION_SCHEMA.COLUMNS, 2026-09-16) -- varios de estos valores no
# coincidian con el ancho real de la columna destino (algunos mas angostos,
# lo que abortaba el insert con 'String data, right truncation'; otros mas
# anchos, lo que truncaba datos validos de mas sin necesidad).
ITEM_AMDOCS_TRUNCATION_LENGTHS: dict[str, int] = {
    "type1": 40,
    "type2": 30,
    "sub_motivo": 50,
    "case_desc": 450,
    "case_resol": 50,
    "canal_ing": 30,
    "subcan_ing": 35,
    "segmento": 10,
    "subtype": 20,
    "line_buss": 10,
    "motivo": 35,
    "servicio": 10,
    "prod_type": 15,
    "ser_stat_r": 25,
    "tpo_serv": 10,
    "tecno_stb": 5,
    "tecno_baf": 10,
    "tecno_tv": 5,
    "tpo_t_stb": 50,
    "tpo_t_baf": 50,
    "tpo_t_tv": 50,
    "origen": 50,
    "canal_res": 50,
    "subcan_res": 50,
    "cargo_res": 50,
    "canal_hres": 50,
}

# ===========================================================================
# USUARIOS_0302 ETL_BASE_SAIP.dtsx -- Data Flow 'SAIP'
# ===========================================================================

SAIP_TABLE = "BASE_SAIP"

# Columnas del Origen OLE DB que se seleccionan pero nunca llegan al destino
# (solo se usan para derivar 'FECHA' via FORMAT/CONVERT en el propio query).
SAIP_COLUMNAS_DESCARTADAS: tuple[str, ...] = ("fec_saip_a", "fec_saip_b")

# 'fec_ingr' y 'FECHA' se convierten a fecha por el componente 'Conversion de
# datos' (FastParse=false) -- cada una con su propio parseo, ver
# extraccion/extractor.py._aplicar_conversion_saip.
