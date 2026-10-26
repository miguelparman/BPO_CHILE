DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE() 

SET DATEFORMAT DMY

UPDATE [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
SET [Estado] = 'OK',
    [Fecha Fin] = @FECHA_EJECUCION_ETL
WHERE [Fecha Inicio] = (SELECT MAX([Fecha Inicio]) FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] WHERE [Nombre] = 'Update_Historial_Casos_Chile')
AND [Nombre] = 'Update_Historial_Casos_Chile'