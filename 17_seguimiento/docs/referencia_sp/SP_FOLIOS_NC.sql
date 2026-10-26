CREATE PROCEDURE [dbo].[SP_FOLIOS_NC] AS

DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE() 

BEGIN TRY

-- LOG INICIO

INSERT  INTO [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Proceso,Nombre,Estado,[Fecha Inicio],[Fecha Fin])
(SELECT 'SP','CL_Folios_Causa_Responsable','exec...',@FECHA_EJECUCION_ETL,NULL);


--- Borra tablas temporales antes de empezar

DROP TABLE IF EXISTS #TBL_TEMP_00;
DROP TABLE IF EXISTS #TBL_TEMP_01;
DROP TABLE IF EXISTS #TBL_TEMP_02;
DROP TABLE IF EXISTS [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_FOLIOS_NC];
DROP TABLE IF EXISTS CL_SEGUIMIENTO_ACTUAL.dbo.TBL_CAUSA_RESPONSABLE_NC;

------------------------------------------ FOLIOS NC -------------------------------------------------------------------

-- PASO 0: Normalización del campo [Descripción] para eliminar inconsistencias y manejar caracteres especiales
WITH CTE_PASO_0 AS (
    SELECT 
        [Número del caso],
        TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE([Descripción],'-', ''),'][', '],['),',[]',''),', []', ''),'__', ''),'?', ''), ':', ''),';', ','), CHAR(160), ' '), CHAR(9), ''), 'FOLIO NC', 'FOLIO_NC'),'FOLIO-NC', 'FOLIO_NC')) AS [Descripción]
    
    FROM [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC]
)

-- Guardamos el resultado en una tabla temporal
SELECT * 
INTO #TBL_TEMP_00
FROM CTE_PASO_0;

--SELECT * 
--FROM #TBL_TEMP_00

-- PASO 01: Extraemos todo lo que viene después de 'FOLIO_NC' hasta que encontremos el primer salto de línea o hasta el final del campo
WITH CTE_PASO_1 AS (
    SELECT 
        [Número del caso],
        [Descripción],
        -- Extraemos todo lo que viene después de 'FOLIO_NC' hasta el primer salto de línea o hasta el final del campo
        CASE
            WHEN CHARINDEX('FOLIO_NC', [Descripción]) > 0 THEN
                -- Extraemos desde 'FOLIO_NC' hasta el primer salto de línea (si lo hay)
                LTRIM(RTRIM(SUBSTRING(
                    [Descripción], 
                    CHARINDEX('FOLIO_NC', [Descripción]) + LEN('FOLIO_NC'), 
                    CASE 
                        -- Si se encuentra un salto de línea (CHAR(13) o CHAR(10)), extraemos hasta ahí
                        WHEN CHARINDEX(CHAR(13), [Descripción], CHARINDEX('FOLIO_NC', [Descripción])) > 0 THEN 
                            CHARINDEX(CHAR(13), [Descripción], CHARINDEX('FOLIO_NC', [Descripción])) 
                            - (CHARINDEX('FOLIO_NC', [Descripción]) + LEN('FOLIO_NC'))
                        WHEN CHARINDEX(CHAR(10), [Descripción], CHARINDEX('FOLIO_NC', [Descripción])) > 0 THEN 
                            CHARINDEX(CHAR(10), [Descripción], CHARINDEX('FOLIO_NC', [Descripción])) 
                            - (CHARINDEX('FOLIO_NC', [Descripción]) + LEN('FOLIO_NC'))
                        -- Si no se encuentra un salto de línea, extraemos hasta el final
                        ELSE LEN([Descripción]) - CHARINDEX('FOLIO_NC', [Descripción]) - LEN('FOLIO_NC') + 1
                    END
                )))
            ELSE NULL
        END AS FOLIOS
    FROM 
        #TBL_TEMP_00
)

-- Guardamos el resultado en una tabla temporal
SELECT * 
INTO #TBL_TEMP_01
FROM CTE_PASO_1
WHERE FOLIOS IS NOT NULL;

-- PASO 02: Extraemos solo las palabras que contienen "_" o que están dentro de corchetes "[]"
WITH CTE_PASO_3 AS (
    SELECT 
        [Número del caso],
        FOLIOS,
        -- Extraemos solo las palabras que contienen "_" o que están dentro de corchetes
        STRING_AGG(LTRIM(RTRIM(value)), ', ') AS FOLIOS_2
    FROM 
        #TBL_TEMP_01
    CROSS APPLY
        STRING_SPLIT(FOLIOS, ' ') -- Dividimos las palabras por espacio
    WHERE 
        -- Filtramos las palabras que contienen guion bajo "_" o que están dentro de corchetes "[]"
        value LIKE '%[_]%' OR value LIKE '%[%]%' 
    GROUP BY 
        [Número del caso], FOLIOS
)

-- Guardamos el resultado en una tabla temporal
SELECT 

[Número del caso],
REPLACE(REPLACE(REPLACE(FOLIOS_2, ' ',''), '[', ''), ']','') AS FOLIOS

INTO #TBL_TEMP_02
FROM CTE_PASO_3
WHERE FOLIOS_2 IS NOT NULL;

--- PASO 03: -- Dividimos los folios por comas y generamos una fila por cada folio e insertamos en la tabla Final

--SELECT * FROM #TBL_TEMP_02;

WITH CTE_FOLIOS AS (
    SELECT 
        [Número del caso],
        value AS FOLIO 
    FROM 
        #TBL_TEMP_02
    CROSS APPLY 
        STRING_SPLIT(FOLIOS, ',')
)

SELECT 

[Número del caso],
LTRIM(RTRIM(FOLIO)) AS FOLIO,
GETDATE() AS ACTUALIZADO

INTO [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_FOLIOS_NC]
FROM CTE_FOLIOS
WHERE 
    FOLIO IS NOT NULL
	AND FOLIO <> '' AND FOLIO NOT LIKE '%FOLIO%';


-----------------------  [CAUSA RAIZ] y [AREA RESPONSABLE] -----------------------------------
SELECT 
    [Número del caso],
    
    -- Extraemos el primer valor entre '<>' para la columna [CAUSA RAIZ]
    CASE 
        WHEN CHARINDEX('<', [Descripción]) > 0 
            AND CHARINDEX('>', [Descripción]) > CHARINDEX('<', [Descripción]) + 1 -- Aseguramos que '>' está después de '<' y al menos con un carácter entre ellos
            AND (CHARINDEX('>', [Descripción]) - CHARINDEX('<', [Descripción]) - 1) > 0 -- Aseguramos que la longitud es positiva
        THEN
            SUBSTRING([Descripción], 
                CHARINDEX('<', [Descripción]) + 1,
                CHARINDEX('>', [Descripción]) - CHARINDEX('<', [Descripción]) - 1 
            )
        ELSE NULL
    END AS [CAUSA RAIZ],

    -- Extraemos el segundo valor entre '<>' para la columna [MOTIVO CAUSA RAIZ] -- Agregado el 2025-04-03
    CASE
        WHEN CHARINDEX('>', [Descripción]) > 0 -- Aseguramos que existe el primer '>'
            AND CHARINDEX('<3', [Descripción], CHARINDEX('>', [Descripción]) + 1) > 0 
            AND CHARINDEX('>', [Descripción], CHARINDEX('>', [Descripción]) + 1) > CHARINDEX('<3', [Descripción], CHARINDEX('>', [Descripción]) + 1) + 1
            AND (CHARINDEX('>', [Descripción], CHARINDEX('>', [Descripción]) + 1) - CHARINDEX('<3', [Descripción], CHARINDEX('>', [Descripción]) + 1) - 1) > 0
        THEN
            SUBSTRING([Descripción], 
                CHARINDEX('<3', [Descripción], CHARINDEX('>', [Descripción]) + 1) + 1,
                CHARINDEX('>', [Descripción], CHARINDEX('>', [Descripción]) + 1) 
                - CHARINDEX('<3', [Descripción], CHARINDEX('>', [Descripción]) + 1) - 1
            )
        ELSE NULL
    END AS [MOTIVO CAUSA RAIZ],

	 -- Extraemos el segundo valor entre '<>' para la columna [AREA RESPONSABLE] -- Agregado el 2025-04-03
	 CASE
		WHEN 
			 LEN(Descripción) - LEN(REPLACE(Descripción, '>', '')) > 1
			 AND IIF(CHARINDEX('>', Descripción, CHARINDEX('<2', Descripción)) > 0, 'Si', 'No') = 'Si'
		THEN 
			SUBSTRING([Descripción], PATINDEX('%<2%>%', [Descripción])+1, CHARINDEX('>', [Descripción], PATINDEX('%<2%>%', [Descripción])) - PATINDEX('%<2%>%', [Descripción]) - 1) 
		ELSE NULL
	END [AREA RESPONSABLE],

    -- Extraemos el contenido después de "DETALLE DE LA NC" hasta el próximo salto de línea o final del texto
    CASE 
        WHEN CHARINDEX('DETALLE DE LA NC', [Descripción]) > 0 THEN
            LTRIM(
                SUBSTRING(
                    [Descripción], 
                    CHARINDEX('DETALLE DE LA NC', [Descripción]) + LEN('DETALLE DE LA NC'),
                    CASE 
                        -- Busca el próximo salto de línea después de "DETALLE DE LA NC"
                        WHEN CHARINDEX(CHAR(10), [Descripción], CHARINDEX('DETALLE DE LA NC', [Descripción]) + LEN('DETALLE DE LA NC')) > 0 THEN
                            CHARINDEX(CHAR(10), [Descripción], CHARINDEX('DETALLE DE LA NC', [Descripción]) + LEN('DETALLE DE LA NC')) 
                            - (CHARINDEX('DETALLE DE LA NC', [Descripción]) + LEN('DETALLE DE LA NC'))
                        ELSE 
                            LEN([Descripción]) - CHARINDEX('DETALLE DE LA NC', [Descripción]) - LEN('DETALLE DE LA NC') + 1
                    END
                )
            )
        ELSE NULL
    END AS [DETALLE DE LA NC],

    GETDATE() AS ACTUALIZADO
    
INTO CL_SEGUIMIENTO_ACTUAL.dbo.TBL_CAUSA_RESPONSABLE_NC
FROM 
    #TBL_TEMP_00
WHERE 
    -- Condiciones para extraer [CAUSA RAIZ] y [AREA RESPONSABLE] o para incluir registros que contengan "DETALLE DE LA NC"
    (
        CHARINDEX('<', [Descripción]) > 0 
        AND CHARINDEX('>', [Descripción], CHARINDEX('<', [Descripción])) > CHARINDEX('<', [Descripción]) + 1
        AND (CHARINDEX('>', [Descripción], CHARINDEX('<', [Descripción])) - CHARINDEX('<', [Descripción]) - 1) = 4
    )
    OR [Descripción] LIKE '%DETALLE DE LA NC%';
	--AND [Número del caso] = '15514570';

--- Borra tablas temporales al terminar

DROP TABLE IF EXISTS #TBL_TEMP_00;
DROP TABLE IF EXISTS #TBL_TEMP_01;
DROP TABLE IF EXISTS #TBL_TEMP_02;

--TRUNCATE TABLE [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC];

--- LOG FIN ----

UPDATE [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
    SET [Estado] = 'OK',
        [Fecha Fin] = GETDATE()
    WHERE [Fecha Inicio] = (SELECT MAX([Fecha Inicio]) 
                            FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] 
                            WHERE [Nombre] = 'CL_Folios_Causa_Responsable')
    AND [Nombre] = 'CL_Folios_Causa_Responsable';

END TRY
BEGIN CATCH
---
END CATCH;