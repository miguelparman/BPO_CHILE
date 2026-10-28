"""Sentencias T-SQL migradas literalmente desde los Execute SQL Task y los
Origenes OLE DB (modo 'SQL Command') de los 5 paquetes USUARIOS_*.dtsx. Sin
cambios de negocio salvo lo indicado en cada comentario (y en el README,
seccion "Notas de fidelidad").

Cada constante corresponde a UNA tarea/componente del Control Flow / Data
Flow original. Los placeholders '?' son parametros posicionales, en el mismo
orden y con el mismo binding (siempre User::Periodo / User::Periodo01) que
en el .dtsx original.

IMPORTANTE -- los Origenes OLE DB que consultaban Externos_Frac (marcados
'YA NO SE EJECUTA' abajo) DEJARON de correr contra SQL Server: ese origen
migro a CSV publicados en SharePoint via Microsoft Graph (ver
sharepoint/reader.py, mappings.py). Las constantes se conservan tal cual
como referencia literal de la logica de negocio (filtros, JOINs, dedup por
ROW_NUMBER) que extraccion/extractor.py replica ahora en pandas -- no se
ejecutan mas. Los DELETE/TRUNCATE/UPDATE/INSERT contra CL_USUARIOS y el
SELECT de 'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE' (CL_DATA, mismo
servidor que el destino) siguen vigentes sin cambios.
"""

from __future__ import annotations

# ===========================================================================
# USUARIOS_0101 Parque.dtsx
# ===========================================================================

# Tarea 'DELETE'. Conexion: CL_USUARIOS.
PARQUE_DELETE = """
  DELETE [CL_USUARIOS].[dbo].[ParqueTCH]
  WHERE periodo >= FORMAT(DATEADD(MONTH, -1, CAST(? + '01' AS date)), 'yyyyMM')
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB
# '55_PARQUE' del Data Flow 'PARQUE'. Conexion: Externos_Frac. 3 parametros
# posicionales, los 3 enlazados a User::Periodo en el original. Reemplazado
# por extraccion.extractor.extraer_parque (CSV 'pqe_fijtot2023.csv' /
# 'pqe_movtot2023.csv' / 'RUT_marca_cartera.csv').
PARQUE_SELECT = """
WITH
CTE_PARQUES AS
(
 --Seleccionando solo los registros de FIJA
SELECT
	[periodo]
	,CASE
		WHEN segme in ('Mediana Empresa','Mediana') THEN 'MEDIANA'
		WHEN segme in ('Peque?a','Peque?a Empresa','Pequeña','Pequeña Empresa') THEN 'PEQUEÑA'
		WHEN segme in ('Micro') THEN 'MICRO'
	END AS segme
	,cast ([q_casos] as int ) as pqe
	,CASE
		WHEN tpo_prod = 'BAF' AND [tecnologia] in ('ADSL','LTE','SAT','VDSL') THEN 'CO'
		WHEN tpo_prod = 'BAF' AND [tecnologia] = 'FIBER' THEN 'FO'
		WHEN tpo_prod = 'TV' AND [tecnologia] in ('DTH','IPTV') THEN 'TV'
		WHEN tpo_prod = 'VOZ' AND [tecnologia] in ('FWT','PSTN','TDM','TOIP','SIN TEC') THEN 'STB'
		WHEN tpo_prod = 'MTV' AND [tecnologia] in ('IPTV') THEN 'TV'
	END AS tpo_prod
	,Tipo = 'FIJO'
	,CASE
		WHEN COALESCE(m.marca, 3) IN (1, 4) THEN 'CARTERIZADOS'
		WHEN COALESCE(m.marca, 3) IN (2, 3) THEN 'TRIADAS'
		WHEN COALESCE(m.marca, 3) = 5 THEN 'TRIADAS'
		ELSE 'TRIADAS'
	END SERVICIO
FROM
	[Externos_Frac].[dbo].pqe_fijtot2023 P
LEFT JOIN
	[Externos_Frac].[dbo].[RUT_marca_cartera] M
ON
	LEFT(P.rut,LEN(P.rut)-1) = M.rutcli
WHERE
	p.periodo >= FORMAT(DATEADD(MONTH, -1, CAST(? + '01' AS date)), 'yyyyMM')

UNION ALL
--UNIENDO CON LOS REGISTROS DE MOVIL
	SELECT [periodo]
		,	CASE
			WHEN segme in ('Mediana Empresa','Mediana') THEN 'MEDIANA'
			WHEN segme in ('Peque?a','Peque?a Empresa','Pequeña','Pequeña Empresa') THEN 'PEQUEÑA'
			WHEN segme in ('Micro') THEN 'MICRO'
		END as segme
		,pqe = 1
		,[tpo_prod]
		,tipo = 'MOVIL'
		,CASE
			WHEN COALESCE(m.marca, 3) IN (1, 4) THEN 'CARTERIZADOS'
			WHEN COALESCE(m.marca, 3) IN (2, 3) THEN 'TRIADAS'
			WHEN COALESCE(m.marca, 3) = 5 THEN 'TRIADAS'
			ELSE 'TRIADAS'
		END SERVICIO
	FROM
		[Externos_Frac].[dbo].[pqe_movtot2023] P
	LEFT JOIN
		[Externos_Frac].[dbo].[RUT_marca_cartera] M
	ON
		P.rutcli = M.rutcli
	WHERE
		p.periodo >= FORMAT(DATEADD(MONTH, -1, CAST(? + '01' AS date)), 'yyyyMM')
),
CTE2 AS
(
SELECT
	[periodo],
	segme,
	tpo_prod,
	tipo,
	SERVICIO,
	SUM(pqe) as pqe
FROM
	CTE_PARQUES
GROUP BY
	[periodo],
	segme,
	tpo_prod,
	tipo,
	SERVICIO
),

ultimo_parque AS (
	SELECT
				CASE
					WHEN [periodo] = '202312' THEN '202401'
					WHEN [periodo] = '202412' THEN '202501'
					WHEN [periodo] = '202512' THEN '202601'
					ELSE [periodo]+1
				END as [periodo],
				segme,
				tpo_prod,
				tipo,
				SERVICIO,
				pqe
FROM
	CTE2
WHERE
	periodo = (SELECT MAX([periodo]) FROM CTE2)
)
SELECT
		periodo,
		segme,
		tpo_prod,
		tipo,
		SERVICIO,
		pqe,
		cast(periodo as varchar(6))+segme+tpo_prod+tipo+SERVICIO as PQE_llave
FROM
	ultimo_parque

UNION ALL

SELECT
	periodo,
	segme,
	tpo_prod,
	tipo,
	SERVICIO,
	pqe,
	cast(periodo as varchar(6))+segme+tpo_prod+tipo+SERVICIO as PQE_llave
FROM
	CTE2
order by
	periodo desc
"""

# ===========================================================================
# USUARIOS_0201 SSIS_CL_Retenciones.dtsx
# ===========================================================================

# --- Sequence Container "BAJAS FRAUDE" ---

# Tarea 'DELETE'. Conexion: CL_USUARIOS.
RETENCIONES_BAJAS_FRAUDE_DELETE = """
  DELETE [CL_USUARIOS].[dbo].[TBL_SERVCH_BAJAS_FRAUDE]
  WHERE CAST(PERIODO AS int) >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB
# 'BAJAS_FRAUDE 233' del Data Flow 'TBL_SERVCH_BAJAS_FRAUDE'. Conexion:
# Externos_Frac. Sin transformaciones (copia directa 1:1). Reemplazado por
# extraccion.extractor.extraer_bajas_fraude (CSV 'BAJAS_FRAUDE.csv').
RETENCIONES_BAJAS_FRAUDE_SELECT = """
SELECT
	[PERIODO]
      ,[REPORT_DATE]
      ,[RUT_CLIENTE]
      ,[NOMBRE_CLIENTE]
      ,[SUBSEGMENTO]
      ,[SUBSCRIBER_KEY]
      ,[LINEA]
      ,[TIPO_PRODUCTO]
      ,[tipobaja]
      ,[q_movimiento]
      ,[MANAGEMENT_INITIAL]
      ,[AGENT_DESC_INITIAL]
      ,[AGENT_BAJA]
      ,[subgerente_atencion]
      ,[jefe_atencion]
      ,[service_manager]
      ,[gerente]
      ,[SUBGERENTE_COMERCIAL]
      ,[JEFE_COMERCIAL]
      ,[ACCOUNT_MANAGER]
      ,[SALES_CHANNEL_NAME]
      ,[SALES_CHANNEL_NAME_INITIAL]
      ,[SALES_SUBCHANNEL_NAME_INITIAL]
      ,[SITE_NAME_INITIAL]
      ,[REFERENCE_NUMBER]
      ,[DESC_MOVIMIENTO]
      ,[ORDER_ACTION_REASON_DESC]
  FROM [Externos_Frac].[dbo].[BAJAS_FRAUDE]
  WHERE
	CAST(PERIODO AS int) >=?
"""

# --- Sequence Container "BAJAS POR ALTA" ---

# Tarea 'DELETE LOCAL'. Conexion: CL_USUARIOS.
RETENCIONES_BAJAS_POR_ALTA_DELETE = """
DELETE [CL_USUARIOS].[dbo].[TBL_SERVCH_BAJAS_POR_ALTA_FO]
WHERE
PERIODO >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB
# '223_BAJAS_POR_ALTA_FO' del Data Flow 'TBL_SERVCH_BAJAS_POR_ALTA_FO'.
# Conexion: Externos_Frac. Sin transformaciones (copia directa 1:1).
# Reemplazado por extraccion.extractor.extraer_bajas_por_alta (CSV
# 'BAJAS_POR_ALTA_FO.csv').
RETENCIONES_BAJAS_POR_ALTA_SELECT = """
SELECT [PARK_EFFECT_DESC]
      ,[PARK_EFFECT_VALUE]
      ,[SUBSCRIBER_KEY]
      ,[ACCESS_ID]
      ,[RUT]
      ,[MAIN_PRODUCT_FAMILY]
      ,[SERVICE_TYPE]
      ,[SUBSEGMENTO]
      ,[PERIODO]
      ,[combinacion origen]
,[MODELO]
  FROM [Externos_Frac].[dbo].[BAJAS_POR_ALTA_FO]
  WHERE PERIODO >= ?
"""

# --- Sequence Container "Find new records or for updating" ---

# Tarea 'DELETE BD_RETEN'. Conexion: CL_USUARIOS.
RETENCIONES_BD_RETEN_DELETE = """
DELETE [CL_USUARIOS].[dbo].[BD_RETEN]
WHERE [periodo] >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB
# 'BD_RETEN_V2 (223)' del Data Flow 'BD_RETEN'. Conexion: Externos_Frac.
# Dedup por (PERIODO,RUT,TPO_SERV,TPO_PROD,TPO_TECNO,submotivo) quedandose
# con ROWNO=1; ademas del parametro '?' (User::Periodo) hay un piso fijo
# 'periodo >= 202601' dentro del CTE -- se preservan ambos filtros tal cual
# el original. Reemplazado por
# extraccion.extractor.extraer_bd_reten/_construir_bd_reten (CSV
# 'BD_RETEN_V2.csv').
RETENCIONES_BD_RETEN_SELECT = """
WITH CTE_BD_RETEN AS
(
SELECT
		ROW_NUMBER() OVER( PARTITION BY PERIODO,RUT,TPO_SERV,TPO_PROD,TPO_TECNO,[submotivo] ORDER BY PERIODO  ) AS ROWNO
		,try_CAST([periodo] AS INT) as [periodo]
		,replace(rut,		 'NULL','') rut
		,try_CAST(LEFT(REPLACE(REPLACE(replace([rut],		 'NULL','') ,'-',''), 'k', ''),LEN(RUT)-1) AS  INT) as rutcli
		,replace([nomcli],		 'NULL','') [nomcli]
		,replace([segme],		 'NULL','') [segme]
		,replace([nom_sm],		 'NULL','') [nom_sm]
		,replace([nom_sup],		 'NULL','') [nom_sup]
		,replace([sub_segme],	 'NULL','') [sub_segme]
		,[tpo_serv]
		,[tpo_prod]
		,[tpo_tecno]
		,CAST([q_parque] AS int) [q_parque]
		,CAST([q_riesgo]  AS int) [q_riesgo]
		,CAST([q_baja_v] AS int) [q_baja_v]
		,CAST([q_baja_p] AS int) [q_baja_p]
		,CAST([q_baja_m] AS int) [q_baja_m]
		,replace([motivo],		 'NULL','') [motivo]
		,replace([submotivo],		 'NULL','') [submotivo]
		,replace([submotivo2],		 'NULL','') [submotivo2]
		,replace([canal_ing],		 'NULL','') [canal_ing]
		,replace([subcan_ing],		 'NULL','') [subcan_ing]
		,replace([canal_res],		 'NULL','') [canal_res]
		,replace([subcan_res],		 'NULL','') [subcan_res]
		,replace([cargo_res],		 'NULL','') [cargo_res]
		,replace([canal_hres],		 'NULL','') [canal_hres]
		,[fecha_ultima_actualizacion] [last_modified]
		,CASE
			WHEN cons_estados = 'NULL' THEN ''
			ELSE
		 SUBSTRING([cons_estados],
          CHARINDEX('{', [cons_estados]) + 1,
          CHARINDEX(':', [cons_estados]) - CHARINDEX('{', [cons_estados]) - 1)
		  END [case_idnum]
		,1 [Evaluacion]
		,CONCAT(periodo, rutcli, tpo_serv, tpo_prod, tpo_tecno) [LLAVE]

	FROM
		[Externos_Frac].[dbo].[BD_RETEN_V2]
	WHERE
		periodo >= 202601
)



SELECT
	*
FROM
	CTE_BD_RETEN x0
WHERE
	ROWNO = 1
	AND periodo >= ?
"""

# Tareas 'UPDATE' (dentro de "Find new records or for updating"). En el
# .dtsx original iban en un unico Execute SQL Task separadas por 'GO' --
# 'GO' no es un separador real de batch para Execute SQL Task, asi que se
# ejecutan como 2 sentencias independientes, igual que corrian en la
# practica. Corrigen un defecto preexistente de tildes ('BAJA SIN RETENCION'
# -> 'BAJA SIN RETENCIÓN') en 2 columnas -- se preserva tal cual.
RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO = """
UPDATE [CL_USUARIOS].[dbo].[BD_RETEN]
SET
    submotivo = 'BAJA SIN RETENCIÓN'
WHERE
    submotivo = 'BAJA SIN RETENCION'
"""

RETENCIONES_CORRIGE_ACENTO_SUBMOTIVO2 = """
UPDATE [CL_USUARIOS].[dbo].[BD_RETEN]
SET
    submotivo2 = 'BAJA SIN RETENCIÓN'
WHERE
    submotivo2 = 'BAJA SIN RETENCION'
"""

# ===========================================================================
# USUARIOS_0300 ETL_INTENCIONES.dtsx
# ===========================================================================

# --- Sequence Container "CARGA BAJAS" ---

# Tareas 'DELETE FIJO' / 'DELETE MOVIL'. Conexion: CL_USUARIOS. Sin
# precedencia entre si (corrian en paralelo en el original).
INTENCIONES_DELETE_BAJAS_FIJO = """
DELETE [CL_USUARIOS].[dbo].[TBL_CH_BAJAS_FIJO]
WHERE
	CAST([YEAR_MONTH] AS INT)  >= ?
"""

INTENCIONES_DELETE_BAJAS_MOVIL = """
DELETE [CL_USUARIOS].[dbo].[TBL_CH_BAJAS_MOVIL]
WHERE
 CAST(PERIODO AS INT)  >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origenes OLE DB del
# Data Flow 'TBL_CH_BAJAS' (2 pipes independientes, sin interaccion entre si,
# ambos sin transformaciones). Conexion: Externos_Frac. Reemplazado por
# extraccion.extractor.extraer_bajas_fijo (CSV 'BAJAS_FIJO.csv').
INTENCIONES_BAJAS_FIJO_SELECT = """
SELECT
	[CLOSE_DATE]
    ,[MOVEMENT_TYPE_DESC]
    ,[CNT_IDENTIFICATION_DOC_NUMBER]
    ,[SUBSCRIBER_KEY]
    ,[SERVICE_ID]
    ,[MAIN_PRODUCT_FAMILY]
    ,[SERVICE_TYPE]
    ,[CUSTOMER_SUB_TYPE_DESC]
    ,[YEAR_MONTH]
	,[MOVEMENT_DESC]
FROM
	[Externos_Frac].[dbo].[BAJAS_FIJO]
WHERE
	CAST([YEAR_MONTH] AS INT)  >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- reemplazado por
# extraccion.extractor.extraer_bajas_movil (CSV 'BAJAS_MOVIL.csv').
INTENCIONES_BAJAS_MOVIL_SELECT = """
SELECT [LLAVE]
      ,[FECHA_BAJA]
      ,[PERIODO]
      ,[RUT_CLIENTE]
      ,[RAZON_SOCIAL]
      ,[SEGMENTO_CG]
      ,[NUMERO_TELEFONO]
      ,[TIPO_PRODUCTO]
      ,[TIPOBAJA]
      ,[Q_MOVIMIENTO]
      ,[GERENTE_COMERCIAL]
      ,[SUBGERENTE_COMERCIAL]
      ,[JEFE_COMERCIAL]
      ,[ACCOUNT_MANAGER]
      ,[SUBGERENTE_POSTVENTA]
      ,[JEFE_POSTVENTA]
      ,[SERVICE_MANAGER]
      ,[RECEPTORA]
  FROM [Externos_Frac].[dbo].[BAJAS_MOVIL]
  WHERE
	CAST(PERIODO AS INT)  >= ?
"""

# NOTA: la Sequence Container "Contenedor de secuencias" ('TRUNCATE' +
# Origen OLE DB de 'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE' contra
# CL_DATA.VIEW_USUARIOS_CON_DETALLE + Destino OLE DB
# 'TBL_FRACTALIA_USER_RETENCIONES' en Externos_Frac) se dio de baja por ser
# un trabajo obsoleto -- ya no forma parte de 'intenciones' (ver
# pipeline.py). Sus 2 constantes SQL (TRUNCATE + SELECT) se eliminaron.

# --- Sequence Container "TBL_INTENCIONES" ---

# Tarea 'DELETE'. Conexion: CL_USUARIOS.
INTENCIONES_TBL_DELETE = """
DELETE [CL_USUARIOS].[dbo].[INTENCIONES]
WHERE
	YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB del
# Data Flow 'INTENCIONES'. Conexion: Externos_Frac. Sigue el componente
# 'Data Conversion 1' (ver mappings.py) y el Destino OLE DB 'INTENCIONES
# LOCAL', que es el UNICO de los 5 paquetes con disposicion de error
# 'IgnoreFailure' (ver db.bulk_insert_ignorando_errores). Reemplazado por
# extraccion.extractor.extraer_intenciones_v2 (CSV 'INTENCIONES_V2.csv').
INTENCIONES_V2_SELECT = """
SELECT
    [CASE_ID_NUMBER]
    ,[CASE_OPEN_TIME]
    ,[CASE_NOTE]
FROM
	[Externos_Frac].[dbo].[INTENCIONES_V2]
WHERE
	YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) >= ?
"""

# --- Sequence Container "TABULANDO INTENCIONES" ---
#
# Los 4 Data Flow TEMP_01..TEMP_04 y el Data Flow final 'INTENCIONES_TAB'
# tienen origen Y destino en la MISMA instancia (CL_USUARIOS): se preservan
# como sentencias 'INSERT INTO ... SELECT ...' literales, ejecutadas tal
# cual contra esa unica conexion (ver transformer.py). No se reimplementa en
# pandas el shredding XML ('CROSS APPLY .nodes()'), el UDF
# 'FUNC_CH_limpiacaracteresXML' (SERVICIOS_GENERALES, no incluido en el
# .dtsx) ni el parseo de fecha/usuario basado en PATINDEX -- ver README,
# "Notas de fidelidad".

# Tarea 'TRUNCATE TEMP_01' -> Data Flow 'TEMP_01'.
INTENCIONES_TEMP01_INSERT = """
INSERT INTO [CL_USUARIOS].[dbo].[INTENCIONES_TEMP01_NotasLimpias] ([CASE_ID_NUMBER],[CASE_OPEN_TIME],[NOTAS_LIMPIAS])
SELECT
        [CASE_ID_NUMBER]
		,CASE_OPEN_TIME
		,[SERVICIOS_GENERALES].[dbo].[FUNC_CH_limpiacaracteresXML]([CASE_NOTE]) AS NOTAS_LIMPIAS
    FROM
		[CL_USUARIOS].[dbo].[INTENCIONES]
	WHERE
		YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) >= ?
"""

# Tarea 'TRUNCATE TABLE TEMP_02' -> Data Flow 'TEMP_02'. Envuelve cada nota
# separada por '*' como un elemento XML '<nota>' (prepara el shredding de
# TEMP_03).
INTENCIONES_TEMP02_INSERT = """
INSERT INTO [CL_USUARIOS].[dbo].[INTENCIONES_TEMP02_NotasDivididas] ([CASE_ID_NUMBER],[CASE_OPEN_TIME],[NotasXML])
SELECT
        [CASE_ID_NUMBER]
		,CASE_OPEN_TIME
		,CAST('<nota>' + REPLACE(NOTAS_LIMPIAS, '*', '</nota><nota>') + '</nota>' AS XML) AS NotasXML
    FROM
        [CL_USUARIOS].[dbo].[INTENCIONES_TEMP01_NotasLimpias]
"""

# Tarea 'TRUNCATE TABLE TEMP_03' -> Data Flow 'TEMP_03'. 'CROSS APPLY
# .nodes('/nota')' separa el XML de TEMP_02 en una fila por nota.
INTENCIONES_TEMP03_INSERT = """
INSERT INTO [CL_USUARIOS].[dbo].[INTENCIONES_TEMP03_NotasSeparadas] ([CASE_ID_NUMBER],[CASE_OPEN_TIME],[Nota])
SELECT
        [CASE_ID_NUMBER]
		,CASE_OPEN_TIME
		,Notas.value('.', 'NVARCHAR(MAX)') AS Nota
    FROM
        [CL_USUARIOS].[dbo].[INTENCIONES_TEMP02_NotasDivididas]
        CROSS APPLY NotasXML.nodes('/nota') AS X(Notas)
"""

# Tarea 'TRUNCATE TABLE TEMP_04' -> Data Flow 'TEMP_04'. Extrae fecha
# (formato 'dd-MM-yyyy hh:mm:ss AM/PM frp...', ajustando PM a 24h) y usuario
# (patron 'frp_xxxxx') de cada nota via PATINDEX/SUBSTRING. Los patrones de
# 'test' (PATINDEX de existencia) y de 'extraccion' (PATINDEX de posicion)
# difieren levemente entre si en el .dtsx original -- se preservan tal cual.
INTENCIONES_TEMP04_INSERT = """
INSERT INTO [CL_USUARIOS].[dbo].[INTENCIONES_TEMP04_NotasConFechaUsuario] ([CASE_ID_NUMBER],[CASE_OPEN_TIME],[Nota],[Fecha],[Usuario])
SELECT
	[CASE_ID_NUMBER]
	,CASE_OPEN_TIME
	,Nota
		-- Extraemos los 19 caracteres anteriores a " PM" o " AM" como fecha
	,CASE
        WHEN PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] AM frp%', Nota) > 0 THEN
           CONVERT(DATETIME,SUBSTRING(
                Nota,
                PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] AM frp%', Nota),
                19
            ),105)
		WHEN PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] PM frp%', Nota) > 0 THEN
           CASE
			   WHEN
				DATEPART(HOUR,
					CONVERT(DATETIME,SUBSTRING(Nota,
					PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] PM frp%', Nota),
					19),105))<12 THEN
				DATEADD(HOUR,12,CONVERT(DATETIME,SUBSTRING(Nota,
					PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] PM frp%', Nota),
					19
				),105))
				ELSE
				CONVERT(DATETIME,SUBSTRING(Nota,
					PATINDEX('%[0-3][0-9]-[0-1][0-9]-[0-9][0-9][0-9][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9] PM frp%', Nota),
					19),105)
				END
        ELSE NULL
    END Fecha
	,CASE
		WHEN PATINDEX('%frp_[a-z][a-z][a-z][a-z][a-z]%', Nota) > 0 THEN SUBSTRING(Nota,PATINDEX('%frp_[a-z][a-z][a-z][a-z][a-z ][a-z ]%', Nota),10)
		ELSE NULL
	END Usuario
FROM
    [CL_USUARIOS].[dbo].[INTENCIONES_TEMP03_NotasSeparadas]
where Nota<>''
"""

# Tarea 'DELETE INTENCIONES_TAB' -> Data Flow 'INTENCIONES_TAB'.
INTENCIONES_TAB_DELETE = """
DELETE
	[CL_USUARIOS].[dbo].[INTENCIONES_TAB]
WHERE
	YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) >= ?
"""

INTENCIONES_TAB_INSERT = """
INSERT INTO [CL_USUARIOS].[dbo].[INTENCIONES_TAB] ([CASE_ID_NUMBER],[CASE_OPEN_TIME],[Nota],[Fecha],[Usuario],[PERIODO])
SELECT
    [CASE_ID_NUMBER]
	,CASE_OPEN_TIME
    ,Nota
    ,Fecha
    ,TRIM(REPLACE(Usuario, 'Tipo', '')) AS Usuario
	,YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) [PERIODO]
FROM
    [CL_USUARIOS].[dbo].[INTENCIONES_TEMP04_NotasConFechaUsuario]
WHERE
    Nota <> ''
"""

# ===========================================================================
# USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx
# ===========================================================================

# --- Sequence Container "Loading to the Staging" ---

# Tarea 'DELETE'. Conexion: CL_USUARIOS.
ITEM_AMDOCS_DELETE = """
  DELETE [CL_USUARIOS].[dbo].[INTEN_AMDOCS]
  WHERE periodo >= ?
"""

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB del
# Data Flow 'INTEN_AMDOCS'. Conexion: Externos_Frac. Dedup por case_idnum
# (ROWNO=1, ordenado por case_optim); ademas del parametro '?'
# (User::Periodo01) hay un piso fijo 'periodo >= 202601' dentro del CTE -- se
# preservan ambos filtros tal cual el original. Sigue el componente 'Data
# Conversion' (ver mappings.py, disposicion IgnoreFailure -- casteos
# tolerantes, no abortan fila) y el Destino OLE DB, que mapea 'ROWNO' a la
# columna 'Evaluacion' y descarta 'rutcli' (ver extraccion/extractor.py).
# Reemplazado por
# extraccion.extractor.extraer_item_amdocs/_construir_item_amdocs (CSV
# 'INTEN_AMDOCS.csv').
ITEM_AMDOCS_SELECT = """
WITH CTE_ITEM_AMDOCS AS
(
	SELECT
	ROW_NUMBER() OVER(PARTITION BY [case_idnum] ORDER BY case_optim ) as ROWNO
	,cast(replace(replace(left([rut],len(rut)-1),'-',''),'.','') as int) as rut
	,cast([case_idnum] as int) as [case_idnum]
	,[type1]
	,[type2]
	,[sub_motivo]
	,[case_desc]
	,[case_resol]
	,CONVERT(datetime,case_optim) as case_optim
	,cast([agent_orig] as INT ) [agent_orig]
	,try_cast([agent_reso] as int) [agent_reso]
	,[canal_ing]
	,[subcan_ing]
	,CASE
		WHEN case_cltim = '' THEN NULL
		ELSE TRY_CONVERT(datetime,
       CONCAT(
           '20', SUBSTRING(case_cltim, 8, 2), '-',          -- año
           CASE SUBSTRING(case_cltim, 4, 3)                 -- mes
                WHEN 'JAN' THEN '01'
                WHEN 'FEB' THEN '02'
                WHEN 'MAR' THEN '03'
                WHEN 'APR' THEN '04'
                WHEN 'MAY' THEN '05'
                WHEN 'JUN' THEN '06'
                WHEN 'JUL' THEN '07'
                WHEN 'AUG' THEN '08'
                WHEN 'SEP' THEN '09'
                WHEN 'OCT' THEN '10'
                WHEN 'NOV' THEN '11'
                WHEN 'DEC' THEN '12'
           END, '-',
           SUBSTRING(case_cltim, 1, 2), ' ',                -- día
           REPLACE(SUBSTRING(case_cltim, 11, 8), '.', ':'), -- hora
           RIGHT(case_cltim, 3)                             -- AM/PM
		)
	) END case_cltim
	,[segmento]
	,[subtype]
	,[line_buss]
	,[motivo]
	,[servicio]
	,[cantidad]
	,[prod_type]
	,[ser_stat_r]
	,CAST([periodo] AS INT) [periodo]
	,[tpo_serv]
	,[rutcli]
	,[pqe_stb]
	,[pqe_baf]
	,[pqe_tv]
	,[pqe_voz]
	,[pqe_bam]
	,[tecno_stb]
	,[tecno_baf]
	,[tecno_tv]
	,[tpo_t_stb]
	,[tpo_t_baf]
	,[tpo_t_tv]
	,[origen]
	,[canal_res]
	,[subcan_res]
	,[cargo_res]
	,[canal_hres]
	,GETDATE() as ValidFrom
FROM
	[Externos_Frac].[dbo].[INTEN_AMDOCS]
where
	case_idnum NOT IN ('','0')
	AND case_idnum IS NOT NULL
	AND periodo >= 202601
)


SELECT
	X0.*
FROM
	CTE_ITEM_AMDOCS x0
WHERE
	x0.ROWNO = 1
	AND periodo >= ?
"""

# --- Las 9 sentencias 'UPDATE' que siguen a la carga, en el orden exacto de
# las Precedence Constraints del .dtsx original. Todas contra CL_USUARIOS
# (misma instancia que el Destino OLE DB); 3 de ellas llaman UDFs de
# [SERVICIOS_GENERALES] (base de datos distinta, MISMO servidor 172.17.0.162,
# referencia de 3 partes) cuya definicion no forma parte del .dtsx y no hace
# falta conocer para preservar el comportamiento -- se ejecutan tal cual
# (ver README, "Notas de fidelidad"). ---

ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_NULL = """
UPDATE [CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET [PRIMER USUARIO POR BASE INTENCION] = NULL
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_PRIMER_USUARIO_JOIN = """
UPDATE
	x0
SET
	x0.[PRIMER USUARIO POR BASE INTENCION] = x1.Usuario
FROM
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS] x0
INNER JOIN
	[CL_USUARIOS].[dbo].[VIEW_INTENCIONES_TAB_PRIMER_USUARIO_RETENCIONES] x1
ON
    x0.case_idnum = x1.CASE_ID_NUMBER
	and x0.periodo = x1.PERIODO
WHERE
	CAST(x0.periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_FECHA_INICIO_CALENDARIO = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[FECHA INICIO CALENDARIO]= [SERVICIOS_GENERALES].[dbo].[FUNC_CH_FECHA_INICIO](case_optim)
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[TIEMPO DE ATENCION HABIL (MINUTOS)]= [SERVICIOS_GENERALES].[dbo].[FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS]([FECHA INICIO CALENDARIO],case_cltim)
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_MINUTOS_SETEO = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[TIEMPO DE ATENCION HABIL (MINUTOS)]= 0
WHERE
	[TIEMPO DE ATENCION HABIL (MINUTOS)]<0
AND
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_DIAS_HORAS = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[TIEMPO DE ATENCION HABIL (HORAS)]= [TIEMPO DE ATENCION HABIL (MINUTOS)]*1.00/60
	,[TIEMPO DE ATENCION HABIL (DIAS)]= [TIEMPO DE ATENCION HABIL (MINUTOS)]*1.00/1440
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_TIEMPO_ATENCION_CALENDARIO_DIAS = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[TIEMPO DE ATENCION CALENDARIO (DIAS)] =
				CASE
					WHEN case_cltim IS NULL THEN NULL
					WHEN CAST([FECHA INICIO CALENDARIO] AS DATE) > case_cltim THEN 0
					ELSE [SERVICIOS_GENERALES].[dbo].[FUNC_CH_DIAS_LABORABLES](CAST([FECHA INICIO CALENDARIO] AS DATE),case_cltim) -1
				END
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_2_DIAS = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[ESTADO ATENDIDO 2 DIAS]=
									CASE
										WHEN [TIEMPO DE ATENCION CALENDARIO (DIAS)] IS NULL THEN 'NO'
										WHEN [TIEMPO DE ATENCION CALENDARIO (DIAS)]<=2 THEN 'SI'
										ELSE 'NO'
									END
WHERE
	CAST(periodo AS int) >=?
"""

ITEM_AMDOCS_UPDATE_ESTADO_ATENDIDO_15_DIAS = """
UPDATE
	[CL_USUARIOS].[dbo].[INTEN_AMDOCS]
SET
	[ESTADO ATENDIDO 15 DIAS]=
									CASE
										WHEN [TIEMPO DE ATENCION CALENDARIO (DIAS)] IS NULL THEN 'NO'
										WHEN [TIEMPO DE ATENCION CALENDARIO (DIAS)]<=15 THEN 'SI'
										ELSE 'NO'
									END
WHERE
	CAST(periodo AS int) >=?
"""

# ===========================================================================
# USUARIOS_0302 ETL_BASE_SAIP.dtsx
# ===========================================================================
#
# Unico de los 5 paquetes sin variable de periodo: ninguna de sus 3 tareas
# usa un parametro '?'.

# Tarea 'TRUNCATE SAIP'. Conexion: CL_USUARIOS. Se ejecuta via
# db.truncate_table(mappings.SAIP_TABLE) (equivalente a 'TRUNCATE TABLE
# [dbo].[BASE_SAIP]'; el .dtsx original omitia el schema, que por defecto ya
# es 'dbo'), igual que TEMP_01..TEMP_04 -- no necesita una constante propia.

# YA NO SE EJECUTA (ver nota al inicio del archivo) -- Origen OLE DB '223
# SAIP' del Data Flow 'SAIP'. Conexion: Externos_Frac. Sin parametros. Sigue
# el componente 'Conversion de datos' (fec_ingr y FECHA a fecha -- ver
# mappings.py) y el Destino OLE DB 'Local SAIP'; las columnas
# 'fec_saip_a'/'fec_saip_b' se seleccionan pero no llegan al destino (ver
# extraccion/extractor.py). Reemplazado por extraccion.extractor.extraer_saip
# (CSV 'base_saip.csv').
SAIP_SELECT = """
/****** Script for SelectTopNRows command from SSMS  ******/
SELECT  [rut_ej]
      ,[dv_ej]
      ,[nombres]
      ,[ap_pat]
      ,[ap_mat]
      ,[sexo]
      ,[fec_ingr]
      ,[rut_empr]
      ,[dv_empr]
      ,[desc_empr]
      ,[desc_tip]
      ,[desc_unida]
      ,[desc_estad]
      ,[desc_esta1]
      ,[desc_suc]
      ,[desc_subge]
      ,[desc_geren]
      ,[desc_cargo]
      ,[desc_funci]
      ,[posicion_f]
	  ,[fec_saip_a]
	  ,FORMAT(CONVERT(DATE, [fec_saip_a], 3), 'dd/MM/yyyy') AS FECHA
      ,[fec_saip_b]
      ,[autentica]
      ,[siscel]
      ,[rrss]
      ,[red]
      ,[citrix]
      ,[id_genesys]
      ,[comuna_pto]
  FROM [Externos_Frac].[dbo].[base_saip]
  WHERE
	[fec_saip_a] IS NULL
	OR
	FORMAT(CONVERT(DATE, [fec_saip_a], 3), 'dd/MM/yyyy') >= '2022-01-01'
"""

# Tarea 'SP_RETENCIONES_EFECTIVIDAD_ASESOR'. Conexion: CL_USUARIOS. En el
# .dtsx original tenia un 'GO' final -- no es un separador real de batch
# para Execute SQL Task, se omite (ver 08_cartera/README, mismo criterio ya
# aplicado alli).
SAIP_EXEC_SP = "EXEC [CL_USUARIOS].[dbo].[SP_RETENCIONES_EFECTIVIDAD_ASESOR]"
