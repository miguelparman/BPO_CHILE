SET DATEFORMAT DMY
INSERT INTO [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS]
SELECT  
CASE WHEN LEN([Número del caso]) = 7 THEN CONCAT('0',[Número del caso]) ELSE [Número del caso] END
,CASE WHEN LEN([Número de caso principal]) = 9 THEN CONCAT('0',REPLACE([Número de caso principal],'.0','')) ELSE REPLACE([Número de caso principal],'.0','') END
,CASE WHEN [Sistema legado] = '' THEN NULL ELSE [Sistema legado] END --3
,CASE WHEN [Identificador FS Local] = '' THEN NULL ELSE [Identificador FS Local] END --4
,REPLACE(cantidad,'.0','') --5
,CASE WHEN [Fecha/Hora de apertura] LIKE '%m.%' THEN CAST(REPLACE([Fecha/Hora de apertura],'. m.','M') as datetime) ELSE CONVERT(datetime,[Fecha/Hora de apertura],105) END
,CASE WHEN fec_escalado_n2 = '' THEN NULL
      WHEN fec_escalado_n2 LIKE '%m.%' THEN CAST(REPLACE(fec_escalado_n2,'. m.','M') as datetime)
	  ELSE CONVERT(datetime,fec_escalado_n2,105) END
,CASE WHEN [Fecha de registro en sistema legado] IN ('1899-12-30 00:00:00','') THEN NULL
      WHEN ISDATE(LEFT([Fecha de registro en sistema legado],10)) = 0 THEN CAST([Fecha de registro en sistema legado] AS DATETIME2)
      ELSE CONVERT(datetime,[Fecha de registro en sistema legado],105) END
,CASE WHEN fec_escalado_n3 = '' THEN NULL
      WHEN fec_escalado_n3 LIKE '%m.%' THEN CAST(REPLACE(fec_escalado_n3,'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,fec_escalado_n3,105) END
,CASE WHEN [Fecha Compromiso Cliente] = '' THEN NULL
      WHEN [Fecha Compromiso Cliente] LIKE '%m.%' THEN CAST(REPLACE([Fecha Compromiso Cliente],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Fecha Compromiso Cliente],105) END
,CASE WHEN [Fecha de envío de cotización] = '' THEN NULL
      WHEN [Fecha de envío de cotización] LIKE '%m.%' THEN CAST(REPLACE([Fecha de envío de cotización],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Fecha de envío de cotización],105) END
,CASE WHEN [Fecha de confirmación] = '' THEN NULL
      WHEN [Fecha de confirmación] LIKE '%m.%' THEN CAST(REPLACE([Fecha de confirmación],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Fecha de confirmación],105) END
,CASE WHEN [Fecha de recepción] = '00:00:00' THEN NULL
      ELSE CAST([Fecha de recepción] AS datetime2) END
,CASE WHEN [Fecha/hora de resolución] = '' THEN NULL
      WHEN [Fecha/hora de resolución] LIKE '%m.%' THEN CAST(REPLACE([Fecha/hora de resolución],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Fecha/hora de resolución],105) END
,CASE WHEN [Fecha/Hora de cierre] = '' THEN NULL
      WHEN [Fecha/Hora de cierre] LIKE '%m.%' THEN CAST(REPLACE([Fecha/Hora de cierre],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Fecha/Hora de cierre],105) END
,CASE WHEN [Abierto] = '' THEN NULL ELSE REPLACE([Abierto],'.0','') END
,CASE WHEN [Estado] = '' THEN NULL ELSE [Estado] END
,CASE WHEN [Motivos del estado] = '' THEN NULL ELSE [Motivos del estado] END
,CASE WHEN [Propietario del caso] = '' THEN NULL ELSE [Propietario del caso] END
,CASE WHEN [Asesor] = '' THEN NULL ELSE [Asesor] END
,CASE WHEN [Asignado a] = '' THEN NULL ELSE [Asignado a] END
,CASE WHEN [No. identificación fiscal] = '' THEN NULL ELSE [No. identificación fiscal] END
,CASE WHEN [Nombre del cliente] = '' THEN NULL ELSE [Nombre del cliente] END
,CASE WHEN [Cliente principal] = '' THEN NULL ELSE [Cliente principal] END
,CASE WHEN [Id. del cliente legado] = '' THEN NULL ELSE [Id. del cliente legado] END
,CASE WHEN [Subterritorio] = '' THEN NULL ELSE [Subterritorio] END
,CASE WHEN [Segmento Global] = '' THEN NULL ELSE [Segmento Global] END
,CASE WHEN [Subsegmento local] = '' THEN NULL ELSE [Subsegmento local] END
,CASE WHEN [Territorio] = '' THEN NULL ELSE [Territorio] END
,CASE WHEN [Categoría del cliente] = '' THEN NULL ELSE [Categoría del cliente] END
,CASE WHEN [Asunto] = '' THEN NULL ELSE [Asunto] END
,CASE WHEN [Tipo del caso] = '' THEN NULL ELSE [Tipo del caso] END
,CASE WHEN [Motivo de contacto] = '' THEN NULL ELSE [Motivo de contacto] END
,CASE WHEN [Tipo del caso] = 'Caso Comercial' THEN [Tipología]
      WHEN [Tipo del caso] = 'Caso Comercial II' THEN [Tipología 2]
      ELSE IIF([Tipología] IS NULL OR [Tipología] = '', [Tipología 2], [Tipología])
	  END
,CASE WHEN [Tipo del caso] = 'Caso Comercial' THEN NULL
      WHEN [Tipo del caso] <> 'Caso Comercial' THEN [Subtipología] END
,CASE WHEN [Línea de negocio] = '' THEN NULL ELSE [Línea de negocio] END
,CASE WHEN [Familia de Producto | Servicio] = '' THEN NULL ELSE [Familia de Producto | Servicio] END
,CASE WHEN [Descripción de producto] = '' THEN NULL ELSE [Descripción de producto] END
,CASE WHEN [Territorio del caso] = '' THEN NULL ELSE [Territorio del caso] END
,CASE WHEN [Origen del caso] = '' THEN NULL ELSE [Origen del caso] END
,CASE WHEN [Última fecha/hora de modificación de caso] LIKE '%m.%' THEN CAST(REPLACE([Última fecha/hora de modificación de caso],'. m.','M') as datetime) 
	  ELSE CONVERT(datetime,[Última fecha/hora de modificación de caso],105) END
,CASE WHEN [Última modificación de caso realizada por] = '' THEN NULL ELSE [Última modificación de caso realizada por] END
,CASE WHEN [Motivo de inconformidad] = '' THEN NULL ELSE [Motivo de inconformidad] END
,CASE WHEN [Motivo de incumplimiento del ANS] = '' THEN NULL ELSE [Motivo de incumplimiento del ANS] END
,CASE WHEN [GICS número de circuito/teléfono] = '' THEN NULL ELSE [GICS número de circuito/teléfono] END
,CASE WHEN [Creado por] = '' THEN NULL ELSE [Creado por] END
,CASE WHEN [Nombre de contacto] = '' THEN NULL ELSE [Nombre de contacto] END
,CASE WHEN [Sector] = '' THEN NULL ELSE [Sector] END
,CASE WHEN [Tipo Solicitud] = '' THEN NULL ELSE [Tipo Solicitud] END
,CASE WHEN [Departamento] = '' THEN NULL ELSE [Departamento] END
,CASE WHEN [Confidencialidad] = '' THEN NULL ELSE REPLACE([Confidencialidad],'.0','') END
,CASE WHEN [Subsegmento Global] = '' THEN NULL ELSE [Subsegmento Global] END
,CASE WHEN [To Address] = '' THEN NULL ELSE [To Address] END
,CASE WHEN [Correo Electronico Web] = '' THEN NULL ELSE [Correo Electronico Web] END
,CASE WHEN [Correo Electrónico Contacto] = '' THEN NULL ELSE [Correo Electrónico Contacto] END
,CASE WHEN [Teléfono Contacto] = '' THEN NULL ELSE REPLACE([Teléfono Contacto],'.0','') END
,CASE WHEN [Móvil Contacto] = '' THEN NULL ELSE  REPLACE([Móvil Contacto],'.0','') END
FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_CASOS]
WHERE [Número del caso] IS NOT NULL AND [Número del caso] <> '' AND LEN([Número del caso]) <= 9 AND [Fecha/Hora de apertura] LIKE '%202[3,4,5,6]%'