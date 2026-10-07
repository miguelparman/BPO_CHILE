-- Reemplaza el Execute SQL Task "UPDATE PESO"
UPDATE [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP]
SET [Peso] = CASE
    WHEN [Estado] = 'CAMPAÑA OK' THEN 1
    WHEN [Estado] = 'PARQUE 0' THEN 2
    WHEN [Estado] = 'SIN DATOS' THEN 3
    WHEN [Estado] = 'SIN CONTACTO' THEN 4
    ELSE 5
END
WHERE [Peso] IS NULL
  AND CAST([PERIODO] AS INT) = :periodo;
