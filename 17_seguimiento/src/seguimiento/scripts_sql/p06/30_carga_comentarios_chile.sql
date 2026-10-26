MERGE [CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS] AS TARGET
USING 
(SELECT X0.* FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_HISTORIAL_COMENTARIOS] X0
INNER JOIN [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X1
ON X0.[Número del caso]=X1.[Número del caso]) AS SOURCE
ON TARGET.[Número del caso]=SOURCE.[Número del caso] AND 
CONVERT(VARCHAR,TARGET.[Fecha de creación de Comentario del caso],121)=CONVERT(VARCHAR,SOURCE.[Fecha de creación de Comentario del caso],121) AND
TARGET.[Comentarios del caso]=SOURCE.[Comentarios del caso]

WHEN NOT MATCHED THEN

INSERT ([Número del caso],[Comentario del caso creado por],[Fecha de creación de Comentario del caso]
,[Comentarios del caso],[Fecha de Carga al SQL])
VALUES([Número del caso],[Comentario del caso creado por],[Fecha de creación de Comentario del caso]
,[Comentarios del caso],GETDATE())
;