MERGE [CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_CASOS] AS TARGET
USING 
(SELECT X0.* FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_HISTORIAL_CASOS] X0
INNER JOIN [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X1
ON X0.[Número del caso]=X1.[Número del caso]) AS SOURCE
ON CAST(TARGET.[Número del caso] AS VARCHAR(15))=CAST(SOURCE.[Número del caso] AS VARCHAR(15)) AND 
CAST(TARGET.[Fecha de modificación] AS DATETIME)=CAST(SOURCE.[Fecha de modificación] AS DATETIME) AND
CAST(TARGET.[Campo / Evento] AS VARCHAR(50))=CAST(SOURCE.[Campo / Evento] AS VARCHAR(50)) AND
COALESCE(CAST(TARGET.[Valor anterior] AS VARCHAR(300)),'ZZZ')=COALESCE(CAST(SOURCE.[Valor anterior] AS VARCHAR(300)),'ZZZ') AND
COALESCE(CAST(TARGET.[Valor nuevo] AS VARCHAR(300)),'ZZZ')=COALESCE(CAST(SOURCE.[Valor nuevo] AS VARCHAR(300)),'ZZZ')



WHEN NOT MATCHED THEN

INSERT ([Número del caso],[Modificado por],[Fecha de modificación],[Campo / Evento],[Valor anterior],[Valor nuevo])
VALUES([Número del caso],[Modificado por],[Fecha de modificación],[Campo / Evento],[Valor anterior],[Valor nuevo])

;
