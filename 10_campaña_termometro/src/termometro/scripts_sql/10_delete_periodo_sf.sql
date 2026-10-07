-- Reemplaza el Execute SQL Task "DELETE PERIODO" (rama Salesforce)
DELETE [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP]
WHERE CAST(PERIODO AS INT) = :periodo;
