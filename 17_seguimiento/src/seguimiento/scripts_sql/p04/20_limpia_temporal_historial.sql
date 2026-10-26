UPDATE [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_HISTORIAL_CASOS]
SET [Número del caso] = RTRIM(LTRIM([Número del caso]))
,[Modificado por] = CASE WHEN [Modificado por] = '' THEN NULL ELSE RTRIM(LTRIM([Modificado por])) END
,[Campo / Evento] = CASE WHEN [Campo / Evento] = '' THEN NULL ELSE RTRIM(LTRIM([Campo / Evento])) END
,[Valor anterior] = CASE WHEN [Valor anterior] = '' THEN NULL ELSE RTRIM(LTRIM([Valor anterior])) END
,[Valor nuevo] = CASE WHEN [Valor nuevo] = '' THEN NULL ELSE RTRIM(LTRIM([Valor nuevo])) END