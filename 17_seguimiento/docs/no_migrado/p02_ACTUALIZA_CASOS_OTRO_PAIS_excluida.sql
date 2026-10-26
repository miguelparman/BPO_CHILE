-- Tarea 'Package\ACTUALIZA CASOS OTRO PAIS' de CL_Seguimiento_02_Proc_Carga_Casos.dtsx: NO MIGRADA (ver docs/EQUIVALENCIA.md)
--- Borra casos tabla CASOS_A

DELETE FROM [PE_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS]
WHERE [Número del caso] IN (SELECT [Número del caso] FROM [CL_TEMPORALES].dbo.TBL_SALESFORCE_CASOS)

--- Borra casos tabla CASOS_B

DELETE FROM [PE_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS_B]
WHERE [Número del caso] IN (SELECT [Número del caso] FROM [CL_TEMPORALES].dbo.TBL_SALESFORCE_CASOS)