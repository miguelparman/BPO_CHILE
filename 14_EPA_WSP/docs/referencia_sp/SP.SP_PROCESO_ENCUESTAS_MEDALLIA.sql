CREATE PROCEDURE [SP].[SP_PROCESO_ENCUESTAS_MEDALLIA] AS


DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE();
SET DATEFORMAT ymd;


BEGIN TRY
--- LOG INICIO

INSERT  INTO [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Proceso,Nombre,Estado,[Fecha Inicio],[Fecha Fin])
(
  SELECT 'SP','SP_Proceso_Medallia_Chile','exec...',@FECHA_EJECUCION_ETL,NULL
);


-- Define Variables
DECLARE @Periodo_Ant CHAR(6);
DECLARE @Periodo_Ant2 CHAR(6);
SET @Periodo_Ant = (SELECT FORMAT(DATEADD(MONTH, -1, CAST(MAX([FECHA_EVENTO]) AS DATE)), 'yyyyMM') FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_MEDALLIA]);
SET @Periodo_Ant2 = (SELECT FORMAT(DATEADD(MONTH, -2, CAST(MAX([FECHA_EVENTO]) AS DATE)), 'yyyyMM') FROM [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_MEDALLIA]);

-- Limpia temporales

	DROP TABLE IF EXISTS #TBL_CALIDAD_MEDALLIA;

-- Update del campo fecha antes de empezar

UPDATE [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_MEDALLIA]
SET [FECHA_EVENTO] = 
    CASE 
        WHEN TRY_CONVERT(DATE, [FECHA_EVENTO], 120) IS NOT NULL THEN TRY_CONVERT(VARCHAR(10), TRY_CONVERT(DATE, [FECHA_EVENTO], 120), 120) -- Si la fecha ya está en formato 'YYYY-MM-DD'
        WHEN CHARINDEX('-', [FECHA_EVENTO]) = 3 AND LEN([FECHA_EVENTO]) = 10 THEN -- Si la fecha está en formato 'DD-MM-YYYY'
            TRY_CONVERT(VARCHAR(10), CONCAT(SUBSTRING([FECHA_EVENTO], 7, 4), '-', SUBSTRING([FECHA_EVENTO], 4, 2), '-', SUBSTRING([FECHA_EVENTO], 1, 2)), 120)
        ELSE NULL
    END
WHERE 
    [FECHA_EVENTO] IS NOT NULL;

-- Empieza el proceso
WITH CTE_PASO_01_MEDALLIA AS (
			SELECT
				'MEDALLIA' AS BASE
				,ROW_NUMBER() OVER(PARTITION BY X0.[ID de encuesta] ORDER BY [ID de encuesta]) AS ORDEN
				,X0.[ID de encuesta] AS [id_encuesta_registro]
				,UPPER(X0.[PLATAFORMA]) AS [pcrc]
				,RIGHT(X0.ANI_CONTACTO, 9) AS [ani_encuesta]
				,LEFT(REPLACE(X0.FECHA_EVENTO, '-',''),6) AS [periodo_evento]
				,REPLACE(X0.FECHA_EVENTO, '-','') AS [fecha_evento]
				,FORMAT(CAST(X0.FECHA_EVENTO AS DATE) ,'dd') AS [dia_evento]
				,NULL AS [hora_evento]
				,FORMAT(X0.[Responsedate], 'yyyyMM') AS [periodo_encuesta]
				,CAST(X0.[Responsedate] AS DATE) AS [Fecha_encuesta]
				,FORMAT(X0.[Responsedate], 'dd') AS [dia_encuesta]
				,NULL AS [hora_encuesta]
				,NULL AS TRAMO_HORAS
				,NULL AS TRAMO_ENCUESTA
				,X0.NPS AS [ISN GLOBAL]
				,NULL AS [NPS]
				,CASE 
					WHEN X0.[NPS] <= 6 THEN 'DETRACTOR'
					WHEN X0.[NPS] <= 8  THEN 'NEUTRO'
					WHEN X0.[NPS] <=10 THEN 'PROMOTOR'
				END AS [TIPO ISN]
				,CASE
					WHEN X0.[NPS] <= 6 THEN -1
					WHEN X0.[NPS] <= 8 THEN 0
					WHEN X0.[NPS] <= 10 THEN 1
					END AS [%ISN GLOBAL]
				,NULL AS [% NECESIDAD]
				,CASE	
					WHEN X0.[¿Lograste resolver tu requerimiento?] = 'Sí' THEN '1'
					WHEN X0.[¿Lograste resolver tu requerimiento?] = 'No' THEN '0'
				 END AS [%RESOLUTIVIDAD]
				,NULL AS [% NPS]
				,X0.[SAT - Asesor]
				,X0.[Facilidad de gestión]
				,X0.[SAT - Satisfacción General]
				,X0.[¿Podrías contarnos las razones de tu respuesta?] AS VERBATIM
				,X3.IDPlace AS [id_agente]
				,X2.RUT_SIN_DV AS RUT
				,X0.[NOMBRE_EMPRESA] AS NOMBRE_CLIENTE    --UPPER(X2.NOMBRE_CLIENTE) AS NOMBRE_CLIENTE
				--,CASE 
				--		WHEN X1.BASE IN ('ATENDIDAS IN', 'INBOUND', 'Llamada') THEN 'INBOUND'
				--		WHEN X1.BASE IN ('Chat/WhatsApp') THEN 'CHAT'
				--		WHEN X1.BASE IN ('Correo', 'Email2case') THEN 'CORREOS'
				--END AS [Chat_Llamada]
				,CASE 
						WHEN X6.[Origen] IN ('ATENDIDAS IN', 'INBOUND', 'Llamada') THEN 'INBOUND'
						WHEN X6.[Origen] IN ('Chat/WhatsApp') THEN 'CHAT'
						WHEN X6.[Origen] IN ('Correo', 'Email2case') THEN 'CORREOS'
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
				--,X6.[Número del caso] AS CONNID_FINAL
				,X0.CATEGORIA_EMPRESA  AS CONNID_FINAL
				,X6.[Fecha/Hora de apertura]
				,X6.[Fecha/hora de resolución]
				,X6.Tipología
				,X6.Subtipología
				,X6.[Tipo del caso]
				,X6.[Asesor Responsable DNI] AS [DNI ASESOR RESPONSABLE]
				,X7.[Nombre Completo] AS [ASESOR RESPONSABLE]
				,X7.[Nombre Completo Coordinador] AS [COORDINADOR RESPONSABLE]
				,CONVERT(DATE,GETDATE(),103) [FECHA DE CARGA] --X1.[FECHA DE CARGA]
				,X2.SEGME SEGMENTO
				,X2.SUB_SEGME SUB_SEGMENTO
				,X2.Etiqueta ETIQUETA

				,CASE
					WHEN X6.[Asesor Responsable DNI] = 'Externo'
						THEN X6.[Asesor Creador DNI]
					ELSE X6.[Asesor Responsable DNI]
				 END AS [DNI ASESOR RESPONSABLE/CREADOR]

				,X8.[Nombre Completo] AS [ASESOR RESPONSABLE/CREADOR]

				,X8.[Nombre Completo Coordinador] AS [COORDINADOR RESPONSABLE/CREADOR]
			FROM 
				[CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_MEDALLIA] X0 WITH (NOLOCK)
			--LEFT JOIN [CL_CALIDAD].[dbo].[TBL_MEDALLIA_ENVIOS_CONSOLIDADO] X1
			--	ON X0.ID_CLIENTE_BIEN = X1.ID_CLIENTE_BIEN
			--	AND X0.FECHA_EVENTO = X1.FECHA_EVENTO --- Cruce con tabla de envios realizados para identificar el caso

			--LEFT JOIN CL_SEGUIMIENTO_ACTUAL.dbo.TBL_SEGUIMIENTO X6 --- Cruce con seguimiento para obtener tipolologias, apertura, asesor responsable, etc.
			--	ON X1.[Número del caso]	 = X6.[Número del caso]
			LEFT JOIN CL_SEGUIMIENTO_ACTUAL.dbo.TBL_SEGUIMIENTO X6 --- Cruce con seguimiento para obtener tipolologias, apertura, asesor responsable, etc.
				ON X0.CATEGORIA_EMPRESA = X6.[Número del caso]

			LEFT JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X7
				ON X6.[Asesor Responsable DNI] = X7.DNI
				AND LEFT(REPLACE(X0.FECHA_EVENTO, '-',''),6) = X7.periodo -- Cruce para obtener asesor - coordinador responsable

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
					END

			LEFT JOIN CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA X2
			   ON LEFT(REPLACE(X6.[No. identificación fiscal], '-', ''),8) = LEFT(X2.RUT_SIN_DV,8)
			   AND REPLACE(X0.FECHA_EVENTO, '-','') BETWEEN X2.fecha_inicio AND X2.fecha_fin -- Cruce con cartera para obtener datos del SM

			LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X3 -- Cruce con BD General para saber quien es el coordinador de Cartera del SM como la fecha para su antiguedad
					ON X2.COD_DNI = X3.cod_dni
					AND LEFT(REPLACE(X0.FECHA_EVENTO, '-',''),6) = X3.periodo

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
					ON LEFT(X5.RUC, 8) = LEFT(X2.RUT_SIN_DV,8)
					AND	X0.ANI_CONTACTO = COALESCE(X5.MÓVIL, X5.TELÉFONO)) --- Cruce con base CCAA para conocer el IV

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
      ,X0.[% NECESIDAD]
      ,X0.[%RESOLUTIVIDAD]
      ,X0.[% NPS]
	  ,X0.[SAT - Asesor]
	  ,X0.[Facilidad de gestión]
	  ,X0.[SAT - Satisfacción General]
	  ,X0.[VERBATIM]
      ,X0.[id_agente]
      ,X0.[RUT]
      ,X0.[NOMBRE_CLIENTE]
	  ,X0.[SubSegmento_Cliente]
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
	  ,X0.SEGMENTO
	  ,X0.SUB_SEGMENTO
	  ,X0.ETIQUETA
	  ,X0.[DNI ASESOR RESPONSABLE/CREADOR]
	  ,X0.[ASESOR RESPONSABLE/CREADOR]
	  ,X0.[COORDINADOR RESPONSABLE/CREADOR]
	  

	INTO #TBL_CALIDAD_MEDALLIA --- Insertamos en tabla temporal
	FROM CTE_PASO_01_MEDALLIA X0
	WHERE ORDEN = 1;

	--ALTER TABLE CL_CALIDAD.[dbo].TBL_ENCUESTAS_MEDALLIA ADD SEGMENTO VARCHAR(50);
	--ALTER TABLE CL_CALIDAD.[dbo].TBL_ENCUESTAS_MEDALLIA ADD SUB_SEGMENTO VARCHAR(50);
	--ALTER TABLE CL_CALIDAD.[dbo].TBL_ENCUESTAS_MEDALLIA ADD ETIQUETA VARCHAR(50);


-- Limpiamos datos e insertamos datos en tabla final eliminando lo existente para insertar lo mas reciente

	DELETE FROM CL_CALIDAD.[dbo].TBL_ENCUESTAS_MEDALLIA
	WHERE id_encuesta_registro IN (SELECT id_encuesta_registro FROM #TBL_CALIDAD_MEDALLIA); --- Limpia

	INSERT INTO CL_CALIDAD.[dbo].TBL_ENCUESTAS_MEDALLIA
	SELECT
	*
	FROM #TBL_CALIDAD_MEDALLIA; -- Inserta



-- Modificaciones
update a 
set a.[DNI ASESOR]=coalesce(x2.COD_DNI,c.COD_DNI) , 
a.ASESOR_FINAL=coalesce(x2.NOM_SM,c.NOM_SM),
a.COORDINADOR=coalesce(x2.NOM_SUP,c.NOM_SUP),
a.id_agente=  CAST(CAST(coalesce(x2.ID_GENESM,c.ID_GENESM) AS INT) AS VARCHAR(25))

from CL_CALIDAD.dbo.TBL_ENCUESTAS_MEDALLIA A 
	LEFT JOIN CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA X2
				   ON A.NOMBRE_CLIENTE = X2.NOMBRE_CLIENTE
				   AND A.fecha_evento BETWEEN X2.fecha_inicio AND X2.fecha_fin -- Cruce con cartera para obtener datos del SM
	LEFT JOIN (SELECT * FROM (
	SELECT *, ROW_NUMBER() OVER(PARTITION BY NOMBRE_CLIENTE ORDER BY FECHA_FIN DESC) N FROM CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA 
	 ) W WHERE N=1) C ON A.NOMBRE_CLIENTE=C.NOMBRE_CLIENTE AND X2.NOMBRE_CLIENTE IS NULL

--LEFT JOIN [PE_CALIDAD].[dbo].[BASE_GENERAL_CONSOLIDADO] X3 -- Cruce con BD General para saber quien es el coordinador de Cartera del SM como la fecha para su antiguedad
--					ON X2.COD_DNI = X3.cod_dni
--					AND LEFT(REPLACE(X0.FECHA_EVENTO, '-',''),6) = X3.periodo
where A.periodo_encuesta>='202508' and A.id_agente is null --AND pcrc='CARTERIZADOS';

-- Update de asesor final y coordinador usando la última cartera de agosto 2025 MEDALLIA

UPDATE A
SET 
    A.ASESOR_FINAL = C.NOM_SM,
    A.COORDINADOR  = C.NOM_SUP
FROM CL_CALIDAD.dbo.TBL_ENCUESTAS_MEDALLIA A
LEFT JOIN (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY NOMBRE_CLIENTE ORDER BY fecha_fin DESC) AS rn
    FROM CL_CARTERA.DBO.TBL_HISTORIAL_CARTERA
    WHERE fecha_inicio <= '20250831'AND fecha_fin   >= '20250801') C
    ON (A.RUT = C.RUT_SIN_DV OR A.NOMBRE_CLIENTE = C.NOMBRE_CLIENTE)
   AND C.rn = 1
WHERE A.periodo_evento = '202508';


-- Limpia temporal

	DROP TABLE IF EXISTS  #TBL_CALIDAD_MEDALLIA;
	TRUNCATE TABLE [CL_TEMPORALES_INDICADORES].[dbo].[TBL_ENCUESTAS_MEDALLIA];

-- LOG FIN
UPDATE [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
    SET [Estado] = 'OK',
        [Fecha Fin] = GETDATE()
    WHERE [Fecha Inicio] = (SELECT MAX([Fecha Inicio]) 
                            FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] 
                            WHERE [Nombre] = 'SP_Proceso_Medallia_Chile')
    AND [Nombre] = 'SP_Proceso_Medallia_Chile';

END TRY
BEGIN CATCH

END CATCH;