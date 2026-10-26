UPDATE [CL_ANALISIS].[dbo].[TBL_SLA]
SET [Línea de negocio] = ''
WHERE [Línea de negocio] is null

UPDATE [CL_ANALISIS].[dbo].[TBL_SLA]
SET [Tipología] = ''
WHERE [Tipología] is null

UPDATE [CL_ANALISIS].[dbo].[TBL_SLA]
SET Subtipología = ''
WHERE Subtipología is null

UPDATE [CL_ANALISIS].[dbo].[TBL_SLA]
SET [Línea de negocio] = 'Fija'
WHERE [Línea de negocio] = 'Voz Fija'