CREATE PROCEDURE [SP].[EPA_ISN_CHILE] AS


-- Define Variables
DECLARE @Periodo_Ant CHAR(6);
DECLARE @Periodo_Ant2 CHAR(6);
SET @Periodo_Ant = (SELECT FORMAT(DATEADD(MONTH, -1, CAST(MAX(periodo_encuesta+'01') AS DATE)), 'yyyyMM') FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_CHILE]);
SET @Periodo_Ant2 = (SELECT FORMAT(DATEADD(MONTH, -2, CAST(MAX(periodo_encuesta+'01') AS DATE)), 'yyyyMM') FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_CHILE]);

---- PASO 1 -- QUERY RETENCIONES

BEGIN TRY

DROP TABLE IF EXISTS CL_CALIDAD.[dbo].TBL_CALIDAD_RETENCIONES

SELECT *

INTO CL_CALIDAD.[dbo].TBL_CALIDAD_RETENCIONES

FROM (
	SELECT 
			ROW_NUMBER() OVER(PARTITION BY X0.[id_conn] ORDER BY CONCAT(X0.periodo_evento, X0.dia_evento, X0.hora_evento) DESC) ORDEN
			,X0.[id_encuesta_registro]
			,X0.[pcrc]
			,REPLACE(CASE WHEN LEFT(X0.ani_evento, 2) = '56' THEN SUBSTRING(X0.ani_evento, 3, LEN(X0.ani_evento)) 
            ELSE X0.ani_evento END, '.0', '') AS [ani_evento]
			,X0.[ani_encuesta]
			,X0.[id_conn]
			,X0.[periodo_evento]
			,CAST(RIGHT('0' + X0.[dia_evento] , 2) AS VARCHAR) AS [dia_evento]
			,X0.[hora_evento]
			,CONCAT (X0.[periodo_evento], RIGHT('0' + X0.[dia_evento], 2)) AS [Fecha evento]
			,CONCAT (X0.[periodo_evento], RIGHT('0' + X0.[dia_evento], 2)) AS Fechasc
			,X0.[periodo_encuesta]
			,CONCAT (X0.[periodo_encuesta], RIGHT('0' + X0.[dia_encuesta], 2)) AS Fecha_encuesta
			,CAST(RIGHT('0' + X0.[dia_encuesta] , 2) AS VARCHAR) AS [dia_encuesta]
			,X0.[hora_encuesta]
			,CONCAT(
			RIGHT('0' + CAST(DATEPART(HH, [hora_evento]) AS VARCHAR), 2),
			' A ',
			RIGHT('0' + CAST(DATEPART(HH, [hora_evento]) + 1 AS VARCHAR), 2)
			) AS TRAMO_HORAS
			,X0.[EMPRESA]
			,X0.[r1] AS [EPA GLOBAL]
			,X0.[r2] AS [Epa Ejecutivo]
			,X0.[r3] AS [RESOLUTIVIDAD]
			,CASE 
				WHEN X0.[r1] < 3 THEN -1 
				WHEN X0.[r1] = 3 THEN 0
				ELSE 1
			END AS [MARCA EPA GLOBAL]
			,CASE 
				WHEN X0.[r1] < 3 THEN 'DETRACTOR'
				WHEN X0.[r1] = 3 THEN 'NEUTRO'
				WHEN X0.[r1] <=5 THEN 'PROMOTOR'
			END AS [EPA_TEXT]
			,CASE 
				WHEN X0.[r2] < 3 THEN -1
				WHEN X0.[r2] = 3 THEN 0
				ELSE 1
			END AS [MARCA EPA EJECUTIVO]
			,CASE 
				WHEN X0.[r3] = 2 THEN 0
				ELSE 1
			END AS [MARCA SOL]
			,X0.[id_agente]
			,X0.[tipificacion] AS [tipificacion_ddbb]
			,X1.ANI
			,X1.COLA AS [Origen]
			,X1.[TIEMPO_LLAMADA] AS TMO
			,X1.[TIPO_INGRESO] AS [TIPO_INGRESO]
			,X1.[TIPO_FINALIZACION] AS [FINALIZACIÓN]
			,CASE 
				WHEN X1.BUSINESS_RESULT = '' THEN 'NO TIPIFICADOS'
				WHEN X1.BUSINESS_RESULT IS NULL THEN 'No encontrados'
				ELSE X1.BUSINESS_RESULT 
				END AS [Tipificación]
			,X4.cod_dni AS [DNI]
			,X4.des_apellido_nombres AS [Asesor]
			,X4.coordinador AS [Coordinador]
			,X4.[Ingreso al área] AS [Fecha de ingreso al programa]
			,X4.ingreso_empresa AS [Ingreso a la empresa]
			,[programa]
			,X1.SEGMENTO_AGRUPADO
			,X1.ETIQUETA
			,X1.RUT
			,NULL AS NOMBRE_CLIENTE

			,CASE 
				WHEN (
					CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE) IN (SELECT [DIA_FESTIVO] FROM [CL_CALIDAD].[dbo].[TBL_CALENDARIO_DIAS_FESTIVOS])
				) THEN 'Horario Inhábil'
				WHEN DATENAME(WEEKDAY, CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) IN ('Sábado', 'Saturday', 'Domingo', 'Sunday') THEN 'Fin de semana'
				WHEN DATEPART(HOUR, x0.hora_evento) BETWEEN 9 AND 17 THEN 'Horario Hábil'
				ELSE 'Horario Inhábil'
			END AS [RANGO HORARIO]

			,CASE
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 30 THEN 'OJT'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 30 AND DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 90 THEN 'NUEVO'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 90 AND DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 180 THEN 'REGULAR'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 180 THEN 'ANTIGUO'
		ELSE '-'
		END AS ANTIGUEDAD

		,CASE
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 30 THEN 'OJT'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 30 AND DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 90 THEN 'NUEVO'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 90 AND DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 180 THEN 'REGULAR'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 180 THEN 'ANTIGUO'
		ELSE '-'
		END AS ANTIGUEDAD_AREA
		,NULL AS CONEXIÓN

		FROM [CL_TEMPORALES_INDICADORES].[dbo].TBL_ENCUESTAS_CHILE X0 WITH (NOLOCK)
		LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X4

		ON X0.periodo_evento = X4.periodo
			AND (
				CASE 
					WHEN RIGHT(X0.[id_agente], 2) = '.0' THEN 
						LEFT(X0.[id_agente], LEN(X0.[id_agente]) - 2)
					ELSE X0.[id_agente]
				END
			) = x4.IDPlace
		LEFT JOIN 
	[CL_TRAFICO].[dbo].[TBL_CONSOLIDADO_LLAMADAS_CHAT_CALLBACK] X1 WITH (NOLOCK)
		ON COALESCE(X1.CONNID_INTERACTION, X1.CONNID) = X0.id_conn

	WHERE X0.[EMPRESA] = 'FRACTALIA_LIMA' AND PERIODO_ENCUESTA >= 202401 AND pcrc = 'RET_PYME_INTEGRAL')A
	WHERE ORDEN = 1

-- Si la consulta fue exitosa, insertamos el log con estado OK
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Retenciones', 'OK', GETDATE());

END TRY
BEGIN CATCH
    -- Si ocurre un error, insertamos el log con estado ERROR
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Retenciones', 'ERROR', GETDATE());

    THROW;
END CATCH
;


---- PASO 2 -- QUERY TRIADAS

-- Limpia temporales

	DROP TABLE IF EXISTS #TBL_CALIDAD_TRIADAS;

-- Empieza el proceso
WITH CTE_PASO_01_TRIADAS AS (
			SELECT 
				 X0.[id_encuesta_registro]
				,X0.[pcrc]
				,RIGHT(X0.ani_encuesta, 9) AS [ani_evento]
				,X0.[id_conn]
				,X0.[periodo_evento]
				,CONCAT(X0.[periodo_evento], FORMAT(CAST(X0.dia_evento AS INT), '00')) AS [Fecha evento]
				,FORMAT(CAST(X0.dia_evento AS INT), '00') AS [dia_evento]
				,X0.hora_evento
				,CONCAT(RIGHT('0' + CAST(DATEPART(HH, X0.hora_evento) AS VARCHAR), 2),
						' A ',
						RIGHT('0' + CAST(DATEPART(HH, X0.hora_evento) + 1 AS VARCHAR), 2)
						) AS TRAMO_HORAS
				,X0.[r1] [EPA GLOBAL]
				,X0.[r2] [Epa Ejecutivo]
				,X0.[r3] [RESOLUTIVIDAD]
				,CASE 
					WHEN X0.[r1] < 3 THEN 'DETRACTOR'
					WHEN X0.[r1] = 3 THEN 'NEUTRO'
					WHEN X0.[r1] <=5 THEN 'PROMOTOR'
				END AS [EPA_TEXT]
				,CASE
					WHEN X0.[r1] < 3 THEN -1
					WHEN X0.[r1] = 3 THEN 0
					ELSE 1
				END [%EPA GLOBAL]
				,CASE
					WHEN X0.[r2] < 3 THEN -1
					WHEN X0.[r2] = 3 THEN 0
					ELSE 1
				END [%EPA EJECUTIVO]
				,CASE
					WHEN X0.[r3] = 1 THEN 1
					ELSE 0
				END [%_RESOLUTIVIDAD]
				,TRIM(X0.[id_agente]) AS [id_agente]
				,RUT_CLIENTE
				,fecha_de_evento
			FROM 
				[CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_CHILE] X0 WITH (NOLOCK)
			WHERE
				X0.[EMPRESA] = 'FRACTALIA_LIMA'
				AND pcrc = 'TRIADA NO CARTERIZADO MICRO'
				AND periodo_evento >= @Periodo_Ant), --- Solo traemos los 2 ultimos meses

	CTE_PASO_02_TRIADAS AS (

				SELECT
					ROW_NUMBER () OVER (PARTITION BY X0.id_encuesta_registro ORDER BY X4.PERIODO DESC) AS ORDEN
				   ,X0.*
				   ,CASE
						--WHEN X1.Programa LIKE '%Carte%' THEN 'Revisar Place'
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NOT NULL  THEN X4.[DNI] 
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NULL  THEN 'OJT'
						WHEN X1.[DNI] IS NULL  THEN 'OJT'
						ELSE X1.[DNI]
					END AS [DNI]
				   ,CASE
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NOT NULL  THEN X4.[Nombre Completo]
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NULL  THEN 'OJT'
						WHEN X1.[Nombre Completo] IS NULL THEN 'OJT'
						ELSE X1.[Nombre Completo] 
					END AS [Asesor]
				   ,CASE
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NOT NULL  THEN X4.[Nombre Completo Coordinador]
						WHEN X1.Programa LIKE '%Carte%' and X4.[ID Place] IS NULL  THEN 'OJT - Coordinador en proceso'
						WHEN X1.[Nombre Completo Coordinador] IS NULL THEN 'OJT - Coordinador en proceso'
						ELSE X1.[Nombre Completo Coordinador] END AS [Coordinador]
				   ,CASE WHEN X1.Programa LIKE '%Carte%'  THEN X4.[Fecha Ingreso al Àrea]
				         ELSE X1.[Fecha Ingreso al Àrea]
					END AS [Fecha de ingreso al programa]
				   ,CASE WHEN X1.Programa LIKE '%Carte%'  THEN X4.[Fecha Ingreso a la Empresa]
				         ELSE X1.[Fecha Ingreso a la Empresa]
					END AS [Ingreso a la empresa]
				   ,CASE
						WHEN X5.SEGMENTO = 'TRIADAS' THEN 'TRIADAS'
						ELSE 'OTRO PROGRAMA' 
					END AS [programa]
				   ,CASE 
						WHEN X2.COLA IS NULL THEN 'No encontrados'
						WHEN X2.BUSINESS_RESULT = '' THEN 'NO TIPIFICADOS'
						ELSE X2.BUSINESS_RESULT END AS [Tipificación]
				   ,X2.COLA [Origen]
				   ,X2.RUT
				   ,X2.[TIEMPO_LLAMADA] TMO
				   ,X2.ETIQUETA
				   ,X2.[SEGMENTO COLA] [SEGMENTO_AGRUPADO]
				   ,X2.[TIPO_FINALIZACION] [FINALIZACIÓN]
				   ,X3.[NOMBRE_CLIENTE]
				   ,X3.SEGME
				   ,X7.[NOM_SM] AS [ASESOR FINAL]
				   ,X7.[NOM_SUP] AS [COORDINADOR FINAL]
				   ,X7.COD_DNI AS [DNI ASESOR FINAL]
		
	
				FROM CTE_PASO_01_TRIADAS X0
				LEFT JOIN BBDD_GENERAL.DBO.TBL_PERSONAL_CONSOLIDADO X1
					ON X0.id_agente = X1.[ID Place]
					AND X0.periodo_evento = X1.periodo -- Cruce con BD General para obtener registros pero solo del programa Triadas

				LEFT JOIN [CL_TRAFICO].[dbo].[TBL_LLAMADAS_ATENDIDAS_INBOUND] X2
					ON COALESCE (X2.CONNID, X2.CONNID_INTERACTION)  = X0.id_conn -- Cruce con trafico para obtner tipificación, TMO y Segmento.

				LEFT JOIN (SELECT DISTINCT RUT_SIN_DV, NOMBRE_CLIENTE, SEGME FROM [CL_CARTERA].[dbo].[TBL_HISTORIAL_CARTERA]) X3
					ON LEFT(X2.RUT,8) = LEFT(X3.RUT_SIN_DV,8) --- Cruce con cartera para obtener nombre del cliente

				LEFT JOIN (SELECT * FROM BBDD_GENERAL.DBO.TBL_PERSONAL_CONSOLIDADO WHERE Jefatura = 'Triadas' AND Programa LIKE '%Chile%' AND Periodo >= @Periodo_Ant2) X4
					ON X0.id_agente = X4.[ID Place]
					AND X1.Programa LIKE '%Carte%' --- Asigna ultimo programa de Triadas para aquellos que en bd general sean carterizados

				LEFT JOIN CL_DATA.dbo.TBL_PLACES_POR_SEGMENTO X5
					ON X0.id_agente = X5.ID --- Determimar el place si es de otro Segmento distinto a Triadas

				LEFT JOIN CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA X7
					ON LEFT(X2.RUT,8) = LEFT(X7.RUT_SIN_DV,8)
					AND X0.fecha_de_evento BETWEEN X7.fecha_inicio AND X7.fecha_fin), -- Cruce con cartera para obtener datos del SM
							
	CTE_PASO_03_TRIADAS AS (

		SELECT
			X1.*,
			CASE
				WHEN DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) < 30 THEN 'OJT'
				WHEN DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) >= 30 AND DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) < 90 THEN 'NUEVO'
				WHEN DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) >= 90 AND DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) < 180 THEN 'REGULAR'
				WHEN DATEDIFF(day, X1.[Fecha de ingreso al programa], CAST(X1.[Fecha evento] AS DATE)) >= 180 THEN 'ANTIGUO'
				ELSE 'OJT'
			END AS ANTIGUEDAD

		FROM CTE_PASO_02_TRIADAS X1)

	SELECT
	   [id_encuesta_registro]
      ,[pcrc]
      ,[ani_evento]
      ,[id_conn]
      ,[periodo_evento]
      ,[Fecha evento]
      ,[dia_evento]
      ,[hora_evento]
      ,[TRAMO_HORAS]
      ,[EPA GLOBAL]
      ,[Epa Ejecutivo]
      ,[RESOLUTIVIDAD]
      ,[EPA_TEXT]
      ,[%EPA GLOBAL]
      ,[%EPA EJECUTIVO]
      ,[%_RESOLUTIVIDAD]
      ,[id_agente]
      ,[DNI]
      ,[Asesor]
      ,[Coordinador]
      ,[Fecha de ingreso al programa]
      ,[Ingreso a la empresa]
      ,[programa]
      ,[ANTIGUEDAD]
      ,[Tipificación]
      ,[Origen]
      ,[RUT]
      ,[TMO]
      ,[ETIQUETA]
      ,[SEGMENTO_AGRUPADO]
      ,[FINALIZACIÓN]
      ,[NOMBRE_CLIENTE]
	  ,SEGME
	  ,[ASESOR FINAL]
	  ,[COORDINADOR FINAL]
	  ,[DNI ASESOR FINAL]
	INTO #TBL_CALIDAD_TRIADAS --- Insertamos en tabla temporal
	FROM CTE_PASO_03_TRIADAS X0
	WHERE ORDEN = 1;

---- Limpiamos datos e insertamos datos en tabla final eliminando lo existente para insertar lo mas reciente

	DELETE FROM CL_CALIDAD.[dbo].TBL_CALIDAD_TRIADAS
	WHERE id_encuesta_registro IN (SELECT id_encuesta_registro FROM #TBL_CALIDAD_TRIADAS); --- Limpia

	INSERT INTO CL_CALIDAD.[dbo].TBL_CALIDAD_TRIADAS
	SELECT
	*
	FROM #TBL_CALIDAD_TRIADAS; -- Inserta

-- Limpia temporal

	DROP TABLE IF EXISTS  #TBL_CALIDAD_TRIADAS;

--Update momentaneo
UPDATE A SET DNI='OJT',
Asesor='OJT',
Coordinador='OJT - Coordinador en proceso'

from CL_CALIDAD.dbo.TBL_CALIDAD_TRIADAS A where periodo_evento='202506' and id_encuesta_registro='197085507';

---- PASO 3 -- QUERY USUARIOS

BEGIN TRY

--ACTUALIZA PLACE

UPDATE [CL_TEMPORALES_INDICADORES].[dbo].TBL_ENCUESTAS_CHILE
SET [id_agente] = '51030010'
WHERE id_encuesta_registro = '162375183'

--- -- REALIZA CONSULTA

DELETE FROM CL_CALIDAD.[dbo].TBL_CALIDAD_USUARIOS
WHERE PERIODO_ENCUESTA >= 202510;

INSERT INTO CL_CALIDAD.[dbo].TBL_CALIDAD_USUARIOS

SELECT *
FROM(

SELECT A.*,
	   CASE 
		WHEN [Asesor] = 'Cardenas Zavaleta Leidy Karen' AND periodo_evento = 202401 THEN 'ANTIGUO'
		ELSE ANTIGUEDAD_END END AS ANTIGUEDAD,
		CASE 
		WHEN [Asesor] = 'Cardenas Zavaleta Leidy Karen' AND periodo_evento = 202401 THEN 'ANTIGUO'
		ELSE ANTIGUEDAD_A END AS ANTIGUEDAD_AREA

FROM (
	SELECT 
			ROW_NUMBER() OVER(PARTITION BY X0.ID_ENCUESTA_REGISTRO ORDER BY X0.[periodo_encuesta] ASC, X0.[dia_encuesta] ASC, X0.[hora_encuesta] ASC) ORDEN
			,X0.[id_encuesta_registro]
			,X0.[pcrc]
			,REPLACE(CASE WHEN LEFT(X0.ani_evento, 2) = '56' THEN SUBSTRING(X0.ani_evento, 3, LEN(X0.ani_evento)) 
            ELSE X0.ani_evento END, '.0', '') AS [ani_evento]
			,X0.[ani_encuesta]
			,X0.[id_conn]
			,X0.[periodo_evento]
			,CAST(RIGHT('0' + X0.[dia_evento] , 2) AS VARCHAR) AS [dia_evento]
			,X0.[hora_evento]
			,CONCAT (X0.[periodo_evento], RIGHT('0' + X0.[dia_evento], 2)) AS Fechasc
			,X0.[periodo_encuesta]
			,CONCAT (X0.[periodo_encuesta], RIGHT('0' + X0.[dia_encuesta], 2)) AS Fecha_encuesta
			,CAST(RIGHT('0' + X0.[dia_encuesta] , 2) AS VARCHAR) AS [dia_encuesta]
			,X0.[hora_encuesta]
			,CONCAT(
			RIGHT('0' + CAST(DATEPART(HH, [hora_evento]) AS VARCHAR), 2),
			' A ',
			RIGHT('0' + CAST(DATEPART(HH, [hora_evento]) + 1 AS VARCHAR), 2)
			) AS TRAMO_HORAS
			,X0.[EMPRESA]
			,X0.[r1] AS [EPA GLOBAL]
			,X0.[r2] AS [Epa Ejecutivo]
			,X0.[r3] AS [RESOLUTIVIDAD]
			,CASE 
				WHEN X0.[r1] < 3 THEN -1 
				WHEN X0.[r1] = 3 THEN 0
				ELSE 1
			END AS [MARCA EPA GLOBAL]
			,CASE 
				WHEN X0.[r1] < 3 THEN 'DETRACTOR'
				WHEN X0.[r1] = 3 THEN 'NEUTRO'
				WHEN X0.[r1] <=5 THEN 'PROMOTOR'
			END AS [EPA_TEXT]
			,CASE 
				WHEN X0.[r2] < 3 THEN -1
				WHEN X0.[r2] = 3 THEN 0
				ELSE 1
			END AS [MARCA EPA EJECUTIVO]
			,CASE 
				WHEN X0.[r3] = 2 THEN 0
				ELSE 1
			END AS [MARCA SOL]
			,X0.[id_agente]
			,X0.[tipificacion] AS [tipificacion_ddbb]
			,X1.ANI
			,X1.COLA AS [Origen]
			,X1.[TIEMPO_LLAMADA] AS TMO
			,X1.[TIPO_INGRESO] AS [TIPO_INGRESO]
			,X1.[TIPO_FINALIZACION] AS [FINALIZACIÓN]
			,CASE 
				WHEN X1.BUSINESS_RESULT = '' THEN 'NO TIPIFICADOS'
				WHEN X1.BUSINESS_RESULT IS NULL THEN 'No encontrados'
				ELSE X1.BUSINESS_RESULT 
				END AS [Tipificación]
			,X4.cod_dni AS [DNI]
			,X4.des_apellido_nombres AS [Asesor]
			,X4.coordinador AS [Coordinador]
			,X4.[Ingreso al área]
			,CASE 
				WHEN X4.[jefatura] = 'Usuarios' 
					OR (X4.des_apellido_nombres = 'Galvez Salinas Lady Diana' 
					AND x0.periodo_evento = '202310') 
					THEN 'USUARIOS'
				ELSE 'OTRO PROGRAMA'
			END AS [programa]
			,CASE 
				WHEN (
					CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE) IN (SELECT [DIA_FESTIVO] FROM [CL_MOVIL].[dbo].[TBL_CALENDARIO_DIAS_FESTIVOS])
				) THEN 'Horario Inhábil'
				WHEN DATENAME(WEEKDAY, CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) IN ('Sábado', 'Saturday', 'Domingo', 'Sunday') THEN 'Fin de semana'
				WHEN CAST(x0.hora_evento AS TIME) >= '09:00:00'AND CAST(x0.hora_evento AS TIME) <= '18:00:00' THEN 'Horario Hábil'
				ELSE 'Horario Inhábil'
			END AS [RANGO HORARIO]

			,CASE
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 30 THEN 'OJT'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 30 AND DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 90 THEN 'NUEVO'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 90 AND DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) < 180 THEN 'REGULAR'
			WHEN DATEDIFF(day, X4.[Ingreso al área], CAST(LEFT(x0.periodo_evento, 4) + '-' + RIGHT(x0.periodo_evento, 2) + '-' + x0.dia_evento AS DATE)) >= 180 THEN 'ANTIGUO'
		ELSE '-'
		END AS ANTIGUEDAD_END

		,CASE
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 30 THEN 'OJT'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 30 AND DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 90 THEN 'NUEVO'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 90 AND DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) < 180 THEN 'REGULAR'
			WHEN DATEDIFF(day, X4.[Ingreso al área], COALESCE (X4.[Fecha de baja], GETDATE())) >= 180 THEN 'ANTIGUO'
		ELSE '-'
		END AS ANTIGUEDAD_A

		FROM [CL_TEMPORALES_INDICADORES].[dbo].TBL_ENCUESTAS_CHILE X0 WITH (NOLOCK)
		LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X4

		ON X0.periodo_evento = X4.periodo
			AND (
				CASE 
					WHEN RIGHT(X0.[id_agente], 2) = '.0' THEN 
						LEFT(X0.[id_agente], LEN(X0.[id_agente]) - 2)
					ELSE X0.[id_agente]
				END
			) = x4.IDPlace
		LEFT JOIN 
	[CL_TRAFICO].[dbo].[TBL_CONSOLIDADO_LLAMADAS_CHAT_CALLBACK] X1 WITH (NOLOCK)
		ON COALESCE(X1.CONNID_INTERACTION, X1.CONNID) = X0.id_conn

	WHERE X0.[EMPRESA] = 'FRACTALIA_LIMA' AND PERIODO_ENCUESTA >= 202510 AND pcrc = 'PLAT USUARIOS EMPRESA')A
	WHERE ORDEN = 1)E

-- Si la consulta fue exitosa, insertamos el log con estado OK
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Usuarios', 'OK', GETDATE());

END TRY
BEGIN CATCH
    -- Si ocurre un error, insertamos el log con estado ERROR
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Usuarios', 'ERROR', GETDATE());

    THROW;
END CATCH
;

BEGIN TRY

---- PASO 4 -- QUERY CARTERIZADOS
  
-- Limpia temporales

	DROP TABLE IF EXISTS #TBL_CALIDAD_CARTERIZADOS;

-- Empieza el proceso
WITH CTE_PASO_01_CARTERIZADOS AS (
			SELECT
				'ISN' AS BASE
				,X0.[id_encuesta_registro]
				,X0.[pcrc]
				,RIGHT(LEFT(X0.ani_encuesta, CHARINDEX('.', X0.ani_encuesta + '.') - 1),9) AS [ani_encuesta]
				,X0.[periodo_evento]
				,CONCAT(X0.[periodo_evento], FORMAT(CAST(X0.dia_evento AS INT), '00')) AS [fecha_evento]
				,FORMAT(CAST(X0.dia_evento AS INT), '00') AS [dia_evento]
				,X0.hora_evento
				,X0.[periodo_encuesta]
				,REPLACE(X0.fecha_de_encuesta, '-','') AS [Fecha_encuesta]
			    ,FORMAT(CAST(X0.dia_encuesta AS INT), '00') [dia_encuesta]
			    ,X0.[hora_encuesta]
				,CONCAT(RIGHT('0' + CAST(DATEPART(HH, X0.hora_evento) AS VARCHAR), 2),
						' A ',
						RIGHT('0' + CAST(DATEPART(HH, X0.hora_evento) + 1 AS VARCHAR), 2)
						) AS TRAMO_HORAS
				,CONCAT(RIGHT('0' + CAST(DATEPART(HH, X0.hora_encuesta) AS VARCHAR), 2),
						' A ',
						RIGHT('0' + CAST(DATEPART(HH, X0.hora_encuesta) + 1 AS VARCHAR), 2)
						) AS TRAMO_ENCUESTA

				,X0.[rGLOBAL] AS [ISN GLOBAL]
				,X0.[r2] AS [ISN EJECUTIVO]
				,X0.[rNPS] AS [NPS]
				,CASE 
					WHEN X0.[rGLOBAL] < 3 THEN 'DETRACTOR'
					WHEN X0.[rGLOBAL] = 3 THEN 'NEUTRO'
					WHEN X0.[rGLOBAL] <=5 THEN 'PROMOTOR'
				END AS [TIPO ISN]
				,CASE
					WHEN X0.[rGLOBAL] <= 2 THEN -1
					WHEN X0.[rGLOBAL] = 3 THEN 0
					WHEN X0.[rGLOBAL] >= 3 THEN 1
					END AS [%ISN GLOBAL]
				,CASE
					WHEN X0.[r2] <= 2 THEN -1
					WHEN X0.[r2] = 3 THEN 0
					WHEN X0.[r2] > 3 THEN 1
					END AS [%ISN EJECUTIVO]
				,CASE
					WHEN X0.[r2] <= 2 THEN -1
					WHEN X0.[r2] = 3 THEN 0
					WHEN X0.[r2] >= 3 THEN 1
				 END AS [% NECESIDAD]
				,CASE
					WHEN X0.[r4] = 1 THEN 1
					WHEN X0.[r4] = 2 THEN 0
				 END AS [%RESOLUTIVIDAD]
				 ,CASE 
					WHEN [r1] <= 2 THEN -1
					WHEN [r1] = 3 THEN 0
					WHEN [r1] >= 3 THEN 1
				  END AS  [% NPS]
				,TRIM(X0.[id_agente]) AS [id_agente]
				,LTRIM(X0.RUT_CLIENTE,'0') AS RUT
				,UPPER(X0.NOMBRE_CLIENTE) AS NOMBRE_CLIENTE
			FROM 
				[CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_CHILE] X0 WITH (NOLOCK)
			WHERE
				X0.[EMPRESA] = 'FRACTALIA'
				AND pcrc = 'EMPRESA'
				AND periodo_encuesta >= @Periodo_Ant),--- Solo traemos los 2 ultimos meses

	CTE_PASO_02_CARTERIZADOS AS (
				SELECT
					ROW_NUMBER() OVER (PARTITION BY id_encuesta_registro ORDER BY periodo_encuesta DESC) AS ORDEN
				   ,X0.*
				   ,CASE 
						WHEN X1.BASE IN ('ATENDIDAS IN', 'INBOUND', 'Llamada') THEN 'INBOUND'
						WHEN X1.BASE IN ('Chat/WhatsApp') THEN 'CHAT'
						WHEN X1.BASE IN ('Correo', 'Email2case') THEN 'CORREOS'
					END AS [Chat_Llamada]
					,X2.COD_DNI AS [DNI ASESOR]
					,X2.NOM_SM AS [ASESOR_FINAL]
					,UPPER(COALESCE(X3.coordinador, X2.NOM_SUP)) AS COORDINADOR
					,COALESCE(X3.[Ingreso al área], X4.[Ingreso al área]) AS [Ingreso al área]
					,COALESCE(X3.ingreso_empresa, X4.ingreso_empresa) AS ingreso_empresa
					,COALESCE(X3.jefatura, X4.jefatura) AS jefatura
					,COALESCE(X3.jefatura_anterior, X4.jefatura_anterior) AS jefatura_anterior
					,CONCAT(X5.NOMBRE,' ',X5.APELLIDOS) AS Nombre_IV
					,X2.SUB_SEGME [SubSegmento_Cliente]
					,CASE WHEN X0.periodo_encuesta >= 202504 THEN UPPER(X2.ing_sspp) ELSE NULL END AS SSPP
					,X6.[Número del caso] AS CONNID_FINAL
					,X6.[Fecha/Hora de apertura]
					,X6.[Fecha/hora de resolución]
					,X6.Tipología
					,X6.Subtipología
					,X6.[Tipo del caso]
					,X6.[Asesor Responsable DNI] AS [DNI ASESOR RESPONSABLE]
					,X7.[Nombre Completo] AS [ASESOR RESPONSABLE]
					,X7.[Nombre Completo Coordinador] AS [COORDINADOR RESPONSABLE]
					,X1.[FECHA DE CARGA]
					,X6.[Número del caso] numero_del_caso_sf
					,X6.[Origen del caso] origen_del_caso_sf
					,X6.[Linea de negocio general] linea_de_negocio_sf
					,CASE
					WHEN X6.[Asesor Responsable DNI] = 'Externo'
						THEN X6.[Asesor Creador DNI]
					ELSE X6.[Asesor Responsable DNI]
				 END AS [DNI ASESOR RESPONSABLE/CREADOR]

				,X8.[Nombre Completo] AS [ASESOR RESPONSABLE/CREADOR]

				,X8.[Nombre Completo Coordinador] AS [COORDINADOR RESPONSABLE/CREADOR]
				FROM CTE_PASO_01_CARTERIZADOS X0

				LEFT JOIN [CL_CALIDAD].[dbo].[TBL_ISN_ENVIOS_CONSOLIDADO] X1
				  ON CONCAT(X0.fecha_evento, X0.ani_encuesta, LEFT(CONVERT(VARCHAR, X0.hora_evento, 108), 5))
				  = CONCAT (X1.FECHA_EVENTO, RIGHT(X1.ANI_EVENTO,9), LEFT(CONVERT(VARCHAR, X1.HORA_EVENTO, 108), 5)) -- Cruce con tabla de envios para saber origen de la interacción

				LEFT JOIN CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA X2
					ON LEFT(X0.RUT, 8) = LEFT(X2.RUT_SIN_DV, 8)
					AND X0.fecha_evento BETWEEN X2.fecha_inicio AND X2.fecha_fin -- Cruce con cartera para obtener datos del SM

				LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X3 -- Cruce con BD General para saber quien es el coordinador de Cartera del SM como la fecha para su antiguedad
					ON X2.COD_DNI = X3.cod_dni
					AND X0.[periodo_encuesta] = X3.periodo

				LEFT JOIN (SELECT * FROM (SELECT
											ROW_NUMBER() OVER (PARTITION BY cod_dni ORDER BY periodo DESC) AS ORDEN,
											cod_dni,
											[Ingreso al área],
											ingreso_empresa,
											jefatura,
											jefatura_anterior
										FROM [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO]
										WHERE programa LIKE '%Chile%' AND periodo >= @Periodo_Ant2 AND [Fecha de baja] IS NOT NULL) A
										WHERE ORDEN = 1)X4 -- Cruce con BD General para obtener ultima fecha de ingreso al area del asesor dado de baja y resultado es en blanco en cruce de X2
					ON X2.COD_DNI = X4.cod_dni
					AND X3.cod_dni IS NULL

				LEFT JOIN [CL_ANALISIS].[dbo].[TBL_CONTACTOS_AUTORIZADOS_CHILE] X5
					ON LEFT(X5.RUC, 8) = LEFT(X0.RUT, 8)
					AND	X0.ani_encuesta = COALESCE(X5.MÓVIL, X5.TELÉFONO) --- Cruce con base CCAA para conocer el IV

				LEFT JOIN [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO] X6
					ON X1.[Número del caso] = X6.[Número del caso] --- Cruce con seguimiento para obtener tipolologias, apertura, asesor responsable, etc.

				LEFT JOIN BBDD_GENERAL.DBO.TBL_PERSONAL_CONSOLIDADO X7
					ON X6.[Asesor Responsable DNI] = X7.DNI
					AND X0.periodo_encuesta = X7.Periodo --- Cruce para obtener asesor - coordinador responsable
				LEFT JOIN (
				SELECT *
				FROM (
					SELECT
						DNI,
						[Nombre Completo],
						[Nombre Completo Coordinador],
						ROW_NUMBER() OVER(PARTITION BY DNI ORDER BY periodo DESC) AS RN
					FROM [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO]
				) A
				WHERE RN = 1
			) X8
				ON X8.DNI =
					CASE
						WHEN X6.[Asesor Responsable DNI] = 'Externo'
							THEN X6.[Asesor Creador DNI]
						ELSE X6.[Asesor Responsable DNI]
					END)

	SELECT
       X0.[BASE]
      ,X0.[id_encuesta_registro]
      ,X0.[pcrc]
      ,X0.[ani_encuesta]
	  ,X0.CONNID_FINAL
      ,X0.[periodo_evento]
      ,X0.[fecha_evento]
      ,X0.[dia_evento]
      ,X0.[hora_evento]
      ,X0.[periodo_encuesta]
      ,X0.[Fecha_encuesta]
      ,X0.[dia_encuesta]
      ,X0.[hora_encuesta]
      ,X0.[TRAMO_HORAS]
      ,X0.[TRAMO_ENCUESTA]
	  ,X0.[Tipología] AS [Tipificación]
      ,X0.[ISN GLOBAL]
      ,X0.[NPS]
      ,X0.[TIPO ISN]
      ,X0.[%ISN GLOBAL]
	  ,CASE
			WHEN X0.SSPP = 'NO' THEN X0.[%ISN GLOBAL] * 0.4
			WHEN X0.SSPP = 'SI' THEN X0.[%ISN GLOBAL] * 0.6
			ELSE NULL END AS [%ISN SSPP]
      ,X0.[% NECESIDAD]
      ,X0.[%RESOLUTIVIDAD]
      ,X0.[% NPS]
      ,X0.[id_agente]
      ,X0.[RUT]
      ,X0.[NOMBRE_CLIENTE]
	  ,X0.[SubSegmento_Cliente]
	  ,X0.[SSPP]
      ,X0.[Chat_Llamada]
      ,X0.[DNI ASESOR]
      ,X0.[ASESOR_FINAL]
      ,X0.[COORDINADOR]
      ,X0.[Ingreso al área]
      ,X0.[ingreso_empresa]
      ,X0.[Nombre_IV]
      ,X0.[Fecha/Hora de apertura]
      ,X0.[Fecha/hora de resolución]
      ,X0.[Tipología]
      ,X0.[Subtipología]
      ,X0.[Tipo del caso]
      ,X0.[DNI ASESOR RESPONSABLE]
      ,X0.[ASESOR RESPONSABLE]
      ,X0.[COORDINADOR RESPONSABLE]
	  ,CASE
			WHEN DATEDIFF(day, [Ingreso al área], [Fecha_evento]) < 30 AND [jefatura_anterior] <> [jefatura] THEN 'TRASLADO'
			WHEN DATEDIFF(day, [Ingreso al área], [Fecha_evento]) < 30 THEN 'OJT'
			WHEN DATEDIFF(day, [Ingreso al área], [Fecha_evento]) >= 30 AND DATEDIFF(day, [Ingreso al área], [Fecha_evento]) < 90 THEN 'NUEVO'
			WHEN DATEDIFF(day, [Ingreso al área], [Fecha_evento]) >= 90 AND DATEDIFF(day, [Ingreso al área], [Fecha_evento]) < 180 THEN 'REGULAR'
			WHEN DATEDIFF(day, [Ingreso al área], [Fecha_evento]) >= 180 THEN 'ANTIGUO'
       END AS ANTIGUEDAD
	  ,X0.[FECHA DE CARGA]
	  ,X0.numero_del_caso_sf
	  ,X0.origen_del_caso_sf
	  ,X0.linea_de_negocio_sf
	  ,null TERMOMETRO
	  ,null NOTA_TERMOMETRO
	  ,X0.[ISN EJECUTIVO]
	  ,X0.[%ISN EJECUTIVO]
	  ,X0.[DNI ASESOR RESPONSABLE/CREADOR]
	  ,X0.[ASESOR RESPONSABLE/CREADOR]
	  ,X0.[COORDINADOR RESPONSABLE/CREADOR]
	INTO #TBL_CALIDAD_CARTERIZADOS --- Insertamos en tabla temporal
	FROM CTE_PASO_02_CARTERIZADOS X0
	WHERE ORDEN = 1

---- Limpiamos datos e insertamos datos en tabla final eliminando lo existente para insertar lo mas reciente

	DELETE FROM CL_CALIDAD.[dbo].TBL_CALIDAD_ISN_CARTERIZADOS
	WHERE id_encuesta_registro IN (SELECT id_encuesta_registro FROM #TBL_CALIDAD_CARTERIZADOS); --- Limpia

	INSERT INTO CL_CALIDAD.[dbo].TBL_CALIDAD_ISN_CARTERIZADOS
	SELECT
	*
	FROM #TBL_CALIDAD_CARTERIZADOS; -- Inserta

-- Limpia temporal

	DROP TABLE IF EXISTS  #TBL_CALIDAD_CARTERIZADOS;

-- Update de asesor final y coordinador usando la última cartera de agosto 2025 ISN
UPDATE A
SET 
    A.ASESOR_FINAL = C.NOM_SM,
    A.COORDINADOR = C.NOM_SUP
FROM [CL_CALIDAD].[dbo].[TBL_CALIDAD_ISN_CARTERIZADOS] A
LEFT JOIN (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY NOMBRE_CLIENTE ORDER BY fecha_fin DESC) AS rn
    FROM CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA
    WHERE fecha_inicio <= '20250831'AND fecha_fin   >= '20250801'
) C
     ON (A.RUT = C.RUT_SIN_DV OR A.NOMBRE_CLIENTE = C.NOMBRE_CLIENTE)
	AND C.rn = 1
WHERE A.periodo_evento = '202508';

-- Si la consulta fue exitosa, insertamos el log con estado OK
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Carterizados', 'OK', GETDATE());

END TRY
BEGIN CATCH
    -- Si ocurre un error, insertamos el log con estado ERROR
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Carterizados', 'ERROR', GETDATE());

    THROW;
END CATCH
;

---- PASO 5 -- QUERY ISN_WSP

BEGIN TRY

--DROP TABLE IF EXISTS 
--CL_CALIDAD.dbo.TBL_EPA_WSP_TRIADAS_CARTERIZADOS_MEDALLIA 

delete from CL_CALIDAD.dbo.TBL_EPA_WSP_TRIADAS_CARTERIZADOS_MEDALLIA where PERIODO >= (SELECT CONVERT(VARCHAR(6), EOMONTH(DATEADD(HOUR, -5, GETDATE()), -1), 112));

--------NUEVA BASE WSP----------
INSERT INTO CL_CALIDAD.dbo.TBL_EPA_WSP_TRIADAS_CARTERIZADOS_MEDALLIA
SELECT *

FROM (

----primer select hasta 202507
--SELECT
--ROW_NUMBER() OVER (PARTITION BY CONCAT(FORMAT(CONVERT(datetime, Responsedate, 103), 'yyyyMM'), X0.CAMPO1) ORDER BY X0.Responsedate ASC) AS ORDEN
                  
--	   ,X0.[SurveyID] AS [id_encuesta_registro]
--	    ,CAST(X0.Responsedate AS DATE) AS [FECHA_ENCUESTA]
--      ,format (X0.Responsedate, 'HH:mm') AS [HORA]
--      ,X0.Responsedate as [SEND_DATE]
--	  ,format (X0.Responsedate, 'yyyMM') AS PERIODO
--	  ,X0.CAMPO1 AS [CONNID]
--	  ,X0.[NPS] AS [MARCACION_NPS]
--	  ,X0.[verbatim] AS [VERBATIM]
--	  ,X0.[Ejecutivo] AS [IST_AGENTE]
--	  ,[RequerimientoSolucionado] AS [RESOLUTIVIDAD]
--	  ,'' AS [IST_CANAL]
--	  ,X0.[ISN] AS [GLOBAL_ISN]
	  
--	  ,CASE
--			when X0.[NPS]<= 6 then -1
--			when X0.[NPS] <= 8 then 0
--			when X0.[NPS] >= 9 then 1
--	   END AS [% NPS]

--	   ,CASE
--				WHEN X0.[ISN] <= 6  THEN 'DETRACTOR'
--				WHEN X0.[ISN] <= 8 THEN 'NEUTRO'
--				when X0.[ISN] >= 9 then 'PROMOTOR'
--				ELSE ''
--		END AS [TIPO_ISN]

--		,CASE
--			when X0.[ISN] <= 6 then -1
--			when X0.[ISN] <= 8 then 0
--			when X0.[ISN] >= 9 then 1
--	   END AS [% ISN_GLOBAL]
		
--		,CASE
--			when X0.[Ejecutivo] <= 6 then -1
--			when X0.[Ejecutivo] <= 8 then 0
--			when X0.[Ejecutivo] >= 9 then 1
--	   END AS [% IST_AGENTE]
       
--	   ,CASE
--			when X0.[RequerimientoSolucionado] = 'Sí' then 1
--			when X0.[RequerimientoSolucionado] = 'No' then 0
--			else ''
--		END AS [% RESOLUTIVIDAD]
		
--		,CASE
--				WHEN X0.[pcrc_eac] LIKE '%TRIADA%' THEN 'TRIADAS'
--				WHEN X0.[pcrc_eac] LIKE '%CARTERIZADO%' THEN 'CARTERIZADOS'
--				ELSE 'OTRO PROGRAMA'
--		END AS [PROGRAMA]

--		,X0.[loginid] AS [ID_AGENTE]
--		,X0.[tipificacion]
			
--					,X1.RUT
--                  ,X1.[ANI]
--                  ,X1.[TIPO_FINALIZACION]
--                  ,X1.[COLA]
--                  ,X1.[TIPO_INGRESO]
--                  ,X1.ETIQUETA
--                  ,X1.[SEGMENTO COLA] as SEGMENTO_AGRUPADO
--			      ,CAST(YEAR(X1.FECHA) AS VARCHAR(4)) + RIGHT('00' + CAST(MONTH(X1.FECHA) AS VARCHAR(2)), 2) AS [PERIODO_TRAFICO]
			
--			,CASE
--				 WHEN X1.[BUSINESS_RESULT] = '' THEN 'NO TIPIFICADOS'
--				 WHEN X1.[BUSINESS_RESULT] IS NOT NULL THEN X1.[BUSINESS_RESULT]
--				 ELSE 'No encontrados'
--			END AS [TIPIFICACION TRAFICO]
--				,X1.[ETIQUETA] AS [TRIADA]
--                ,X1.LOGINID
--                ,X1.[COD_DNI]
--                  ,CONCAT(X2.[COD_DNI], FORMAT(CONVERT(datetime, Responsedate, 103), 'yyyyMM')) AS LLAVE_DNI
--                 ,CONCAT(X2.IDPlace, FORMAT(CONVERT(datetime, Responsedate, 103), 'yyyyMM')) AS LLAVE_PLACE
--                  ,X1.[FECHA] AS [FECHA_INTERACCIÓN]
--                  ,X1.[HORA] AS [HORA_INTERACCIÓN]

--                  ,CONCAT(
--                  RIGHT('0' + CAST(DATEPART(HH, X1.HORA) AS VARCHAR), 2),
--                  ' A ',
--                  RIGHT('0' + CAST(DATEPART(HH, X1.HORA) + 1 AS VARCHAR), 2)
--                  ) AS TRAMO_HORAS

-- 				,X1.[LLAMA CCAA?]
--                  ,X2.[des_apellido_nombres] AS [NOMBRE_AGENTE]
--                  ,X2.[coordinador]  AS [COORDINADOR]
--                  ,x2.jefatura
--                  ,x2.jefatura_anterior
--                  ,X2.[Ingreso al área]
--                  ,CASE
--                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 30 AND X2.jefatura_anterior <> X2.jefatura THEN 'TRASLADO'
--                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 30 THEN 'OJT'
--                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 30 AND DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 90 THEN 'NUEVO'
--                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 90 AND DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 180 THEN 'REGULAR'
--                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 180 THEN 'ANTIGUO'
--                  ELSE '-'
      
--                  END AS ANTIGUEDAD

--  FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_WSP_MEDALLIA] X0
--              LEFT JOIN
--                  [CL_TRAFICO].[dbo].[TBL_CHAT] X1 WITH (NOLOCK)
--                  ON
--                        X0.[CAMPO1] = X1.[CONNID]

--LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X2
--                  ON
--                        COALESCE (CAST(X0.[loginid] AS INT), CAST(X1.LOGINID AS INT)) = CAST(X2.IDPlace AS INT)
--                 AND
--                        FORMAT(Responsedate, 'yyyyMM') = X2.periodo
-- WHERE X0.[pcrc_eac] IN ('PYMES CARTERIZADOS', 'TRIADA NO CARTERIZADO MICRO') and convert(date,X0.Responsedate,103)<='2025-07-31'

--UNION ALL
--segundo select desde 202508
SELECT
ROW_NUMBER() OVER (PARTITION BY  X0.[CONNID],X0.verbatim,X0.tipificacion ORDER BY X0.[CONNID] ASC)  AS ORDEN
                  
	   ,X0.[SurveyID] AS [id_encuesta_registro]
	    ,CAST(X0.Responsedate AS DATE) AS [FECHA_ENCUESTA]
      ,format (X0.Responsedate, 'HH:mm') AS [HORA]
      ,X0.Responsedate as [SEND_DATE]
	  ,format (X0.Responsedate, 'yyyMM') AS PERIODO
	  ,X0.[CONNID]
	  ,X0.[NPS] AS [MARCACION_NPS]
	  ,X0.[verbatim] AS [VERBATIM]
	  ,X0.[cejecutivo] AS [IST_AGENTE]
	  ,[RequerimientoSolucionado] AS [RESOLUTIVIDAD]
	  ,'' AS [IST_CANAL]
	  ,X0.[ISN] AS [GLOBAL_ISN]
	  
	  ,CASE
			when X0.[NPS]<= 6 then -1
			when X0.[NPS] <= 8 then 0
			when X0.[NPS] >= 9 then 1
	   END AS [% NPS]

	   ,CASE
				WHEN X0.[ISN] = -1  THEN 'DETRACTOR'
				WHEN X0.[ISN] = 0 THEN 'NEUTRO'
				when X0.[ISN] = 1 then 'PROMOTOR'
				ELSE ''
		END AS [TIPO_ISN]

		,X0.[ISN] AS [% ISN_GLOBAL]
		
		,--CASE
			--when X0.[cejecutivo] <= 6 then -1
			--when X0.[cejecutivo] <= 8 then 0
			--when X0.[cejecutivo] >= 9 then 1
	   --END 
	   [cejecutivo] AS [% IST_AGENTE]
       
	   ,CASE
			when X0.[RequerimientoSolucionado] = 'Sí' then 1
			when X0.[RequerimientoSolucionado] = 'No' then 0
			else ''
		END AS [% RESOLUTIVIDAD]
		
		,CASE
				WHEN X0.[pcrc_eac] LIKE '%TRIADA%' THEN 'TRIADAS'
				WHEN X0.[pcrc_eac] LIKE '%CARTERIZADO%' THEN 'CARTERIZADOS'
				ELSE 'OTRO PROGRAMA'
		END AS [PROGRAMA]

		,X0.[loginid] AS [ID_AGENTE]
		,X0.[tipificacion]
			
					,X1.RUT
                  ,X1.[ANI]
                  ,X1.[TIPO_FINALIZACION]
                  ,X1.[COLA]
                  ,X1.[TIPO_INGRESO]
                  ,X1.ETIQUETA
                  ,X1.[SEGMENTO COLA] as SEGMENTO_AGRUPADO
			      ,CAST(YEAR(X1.FECHA) AS VARCHAR(4)) + RIGHT('00' + CAST(MONTH(X1.FECHA) AS VARCHAR(2)), 2) AS [PERIODO_TRAFICO]
			
			,CASE
				 WHEN X1.[BUSINESS_RESULT] = '' THEN 'NO TIPIFICADOS'
				 WHEN X1.[BUSINESS_RESULT] IS NOT NULL THEN X1.[BUSINESS_RESULT]
				 ELSE 'No encontrados'
			END AS [TIPIFICACION TRAFICO]
				,X1.[ETIQUETA] AS [TRIADA]
                ,X1.LOGINID
                ,X1.[COD_DNI]
                  ,CONCAT(X2.[COD_DNI], FORMAT(CONVERT(datetime, Responsedate, 103), 'yyyyMM')) AS LLAVE_DNI
                 ,CONCAT(X2.IDPlace, FORMAT(CONVERT(datetime, Responsedate, 103), 'yyyyMM')) AS LLAVE_PLACE
                  ,X1.[FECHA] AS [FECHA_INTERACCIÓN]
                  ,X1.[HORA] AS [HORA_INTERACCIÓN]

                  ,CONCAT(
                  RIGHT('0' + CAST(DATEPART(HH, X1.HORA) AS VARCHAR), 2),
                  ' A ',
                  RIGHT('0' + CAST(DATEPART(HH, X1.HORA) + 1 AS VARCHAR), 2)
                  ) AS TRAMO_HORAS

 				,X1.[LLAMA CCAA?]
                  ,X2.[des_apellido_nombres] AS [NOMBRE_AGENTE]
                  ,X2.[coordinador]  AS [COORDINADOR]
                  ,x2.jefatura
                  ,x2.jefatura_anterior
                  ,X2.[Ingreso al área]
                  ,CASE
                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 30 AND X2.jefatura_anterior <> X2.jefatura THEN 'TRASLADO'
                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 30 THEN 'OJT'
                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 30 AND DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 90 THEN 'NUEVO'
                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 90 AND DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) < 180 THEN 'REGULAR'
                        WHEN DATEDIFF(day, X2.[Ingreso al área], X1.[FECHA]) >= 180 THEN 'ANTIGUO'
                  ELSE '-'
      
                  END AS ANTIGUEDAD

  FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_WSP_MEDALLIA] X0
              LEFT JOIN
                  [CL_TRAFICO].[dbo].[TBL_CHAT] X1 WITH (NOLOCK)
                  ON
                        X0.[CONNID] = X1.[CONNID]

LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X2
                  ON
                        COALESCE (CAST(X0.[loginid] AS INT), CAST(X1.LOGINID AS INT)) = CAST(X2.IDPlace AS INT)
                 AND
                        FORMAT(Responsedate, 'yyyyMM') = X2.periodo
 WHERE X0.[pcrc_eac] IN ('PYMES CARTERIZADOS', 'TRIADA NO CARTERIZADO MICRO') /*and  convert(date,X0.Responsedate,103)>='2025-08-01'*/
and FORMAT(Responsedate, 'yyyyMM') >= (SELECT CONVERT(VARCHAR(6), EOMONTH(DATEADD(HOUR, -5, GETDATE()), -1), 112))



) A

 WHERE A.ORDEN = 1

--DE AQUELLOS REGISTRSO DE ABRIL Y MAYO QUE NO TIENEN SSPP
UPDATE X0 SET SSPP=
(SELECT TOP 1 UPPER(ing_sspp) FROM CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA X2 WHERE ing_sspp IS NOT NULL AND LEFT(X0.RUT, 8) = LEFT(X2.RUT_SIN_DV, 8) ORDER BY fecha_fin ASC ) 
from CL_CALIDAD.dbo.TBL_CALIDAD_ISN_CARTERIZADOS  X0
where X0.periodo_encuesta IN ('202504','202505','202507') and X0.BASE='isn' and X0.[%ISN SSPP] is null

update X0 set [%ISN SSPP]=CASE
			WHEN X0.SSPP = 'NO' THEN X0.[%ISN GLOBAL] * 0.4
			WHEN X0.SSPP = 'SI' THEN X0.[%ISN GLOBAL] * 0.6
			ELSE NULL END
from CL_CALIDAD.dbo.TBL_CALIDAD_ISN_CARTERIZADOS  X0
where X0.periodo_encuesta IN ('202504','202505','202507') and X0.BASE='isn' and X0.[%ISN SSPP] IS NULL

--UPDATE DE NOTA TERMÓMETRO EN ISN
--ALTER TABLE CL_CALIDAD.DBO.TBL_CALIDAD_ISN_CARTERIZADOS ADD TERMOMETRO INT NULL
--ALTER TABLE CL_CALIDAD.DBO.TBL_CALIDAD_ISN_CARTERIZADOS ADD NOTA_TERMOMETRO INT NULL

UPDATE A SET A.NOTA_TERMOMETRO =
	 (
		  SELECT top 1 convert(int,[Prom 14.]) FROM [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO] B WHERE A.RUT = B.RUT_SIN_DV AND B.Estado='CAMPAÑA OK' AND [Prom 14.] IS NOT NULL AND 
		  (B.PERIODO BETWEEN CONVERT(varchar(6), DATEADD(MONTH,-3, CONVERT(DATE,Fecha_encuesta)),112) AND a.periodo_encuesta) and b.[Fecha de la encuesta]<=convert(date,a.Fecha_encuesta)
		  order by b.[Fecha de la encuesta] desc
	  ) 
  --SELECT *
FROM CL_CALIDAD.DBO.TBL_CALIDAD_ISN_CARTERIZADOS A WHERE A.periodo_encuesta>=202501;

UPDATE A SET CON_TERMOMETRO=CASE WHEN NOTA_TERMOMETRO IS NOT NULL THEN 1 ELSE 0 END 
FROM CL_CALIDAD.DBO.TBL_CALIDAD_ISN_CARTERIZADOS A WHERE A.periodo_encuesta>=202501;



-- Si la consulta fue exitosa, insertamos el log con estado OK
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Calidad_WSP', 'OK', GETDATE());

END TRY
BEGIN CATCH
    -- Si ocurre un error, insertamos el log con estado ERROR
    INSERT INTO PE_CALIDAD.[dbo].LOGS_PROCESOS_SQL (proceso, nombre, estado, fecha_ejecucion) 
    VALUES ('SP', 'Update_Chile_Calidad_WSP', 'ERROR', GETDATE());

    THROW;
END CATCH;


-- Limpia tabla temporal

--TRUNCATE TABLE [CL_TEMPORALES_INDICADORES].[dbo].TBL_ENCUESTAS_CHILE