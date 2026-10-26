SET DATEFORMAT DMY
INSERT INTO [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS_B]
SELECT 
RTRIM(LTRIM(X0.[Número del caso]))
,CASE WHEN [Dirección de instalación | entrega] = '' THEN NULL ELSE RTRIM(LTRIM([Dirección de instalación | entrega])) END
,CASE WHEN [Nombre del Contacto Final] = '' THEN NULL ELSE RTRIM(LTRIM([Nombre del Contacto Final])) END
,CASE WHEN [Apellido del Contacto Final] = '' THEN NULL ELSE RTRIM(LTRIM([Apellido del Contacto Final])) END
,CASE WHEN [Teléfono del contacto final] = '' THEN NULL ELSE RTRIM(LTRIM([Teléfono del contacto final])) END
,CASE WHEN [Fecha de Solicitud Cliente] = ''  THEN  NULL 
     ELSE cast(REPLACE([Fecha de Solicitud Cliente],'. m.','M') as datetime) END AS [Fecha de Solicitud Cliente]
,CASE WHEN [Fecha de solicitud padre]=''  then NULL 
      ELSE cast(REPLACE([Fecha de solicitud padre],'. m.','M') as datetime) END AS [Fecha de solicitud padre]
,CASE WHEN [Motivo cambio de fecha de compromiso] = '' THEN NULL ELSE RTRIM(LTRIM([Motivo cambio de fecha de compromiso])) END
,CASE WHEN [Ámbito] = '' THEN NULL ELSE RTRIM(LTRIM([Ámbito])) END
,CASE WHEN [Subtipo de solicitud] = '' THEN NULL ELSE RTRIM(LTRIM([Subtipo de solicitud])) END
,CASE WHEN [Tipo] = '' THEN NULL ELSE RTRIM(LTRIM([Tipo])) END
,CASE WHEN [Prioridad] = '' THEN NULL ELSE RTRIM(LTRIM([Prioridad])) END
,CASE WHEN [Tipo de solicitud] = '' THEN NULL ELSE RTRIM(LTRIM([Tipo de solicitud])) END
,CASE WHEN [Activo] = '' THEN NULL ELSE RTRIM(LTRIM([Activo])) END
,CASE WHEN [Tipo de registro del cliente] = '' THEN NULL ELSE RTRIM(LTRIM([Tipo de registro del cliente])) END
,CASE WHEN [Solución del caso] = '' THEN NULL ELSE RTRIM(LTRIM([Solución del caso])) END
,CASE WHEN [Id de la oportunidad] = '' THEN NULL ELSE RTRIM(LTRIM([Id de la oportunidad])) END
,CASE WHEN [Distribuidor Asociado] = '' THEN NULL ELSE RTRIM(LTRIM([Distribuidor Asociado])) END
,CASE WHEN Complejidad = '' THEN NULL ELSE RTRIM(LTRIM(Complejidad)) END
,CASE WHEN [Función del propietario del caso] = '' THEN NULL ELSE RTRIM(LTRIM([Función del propietario del caso])) END
,CASE WHEN [Etapa de la oportunidad] = '' THEN NULL ELSE RTRIM(LTRIM([Etapa de la oportunidad])) END
FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_CASOS_B] X0
INNER JOIN [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X1
ON X0.[Número del caso]=X1.[Número del caso]
WHERE LEN(X0.[Número del caso]) <= 9