-- Reemplaza el Execute SQL Task "DELETE FUERA DE RANGO"
DELETE [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP]
WHERE [Fecha de la encuesta] NOT BETWEEN :fecha_inicio AND :fecha_fin;
