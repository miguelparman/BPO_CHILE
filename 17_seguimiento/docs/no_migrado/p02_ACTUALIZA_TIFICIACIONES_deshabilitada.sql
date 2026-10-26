-- Tarea 'Package\CARGA BASE CASOS SALESFORCE\ACTUALIZA TIFICIACIONES' de CL_Seguimiento_02_Proc_Carga_Casos.dtsx: NO MIGRADA (ver docs/EQUIVALENCIA.md)
UPDATE X0
SET 
Tipología = CASE 
				WHEN x0.[Tipo del caso] = 'Caso Comercial' THEN X1.[Tipología]
				WHEN x0.[Tipo del caso] = 'Caso Comercial II' THEN X1.[Tipología 2]
				ELSE IIF(X1.[Tipología] IS NULL OR X1.[Tipología] = '', X1.[Tipología 2], X1.[Tipología])
			END,
Subtipología = X1.Subtipología,
[Motivo de contacto] = x1.[Motivo de contacto],
[Línea de negocio] = x1.[Línea de negocio]
FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X0
inner join [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_CASOS]  X1
ON X0.[Número del caso] = X1.[Número del caso]