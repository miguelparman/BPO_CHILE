UPDATE [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_REPORTE_CORREOS]
SET [Fecha correo] = CASE WHEN [Fecha correo] = '' THEN NULL 
                          WHEN ISDATE(REPLACE([Fecha correo],'. m.','M'))=0 THEN NULL 
	                      ELSE cast(REPLACE([Fecha correo],'. m.','M') as datetime) END
,[Número del caso] = CASE WHEN LEN([Número del caso]) = 9 THEN CONCAT('0',REPLACE([Número del caso],'.0','')) 
                          ELSE REPLACE([Número del caso],'.0','') END
,[RUC] = CASE WHEN [RUC] = '' THEN NULL ELSE [RUC] END
