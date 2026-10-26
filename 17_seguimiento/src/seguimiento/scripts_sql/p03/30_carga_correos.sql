MERGE [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CORREOS]AS TARGET
USING 
(SELECT X0.* FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_REPORTE_CORREOS]X0
INNER JOIN [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X1
ON X0.[Número del caso]=X1.[Número del caso]) AS SOURCE
ON TARGET.[Número del caso]=SOURCE.[Número del caso] AND 
CONVERT(VARCHAR,TARGET.[Fecha correo],121)=CONVERT(VARCHAR,SOURCE.[Fecha correo],121) 

WHEN NOT MATCHED THEN

INSERT ([De],[Para],[Fecha correo],[Número del caso],[RUC],[Es Entrante],[Asunto del correo electrónico],
[Origen del caso],[Creado por],[Estado del correo electrónico])

VALUES ([De],[Para],[Fecha correo],[Número del caso],[RUC],[Es Entrante],[Asunto del correo electrónico],
[Origen del caso],[Creado por],[Estado del correo electrónico])
;