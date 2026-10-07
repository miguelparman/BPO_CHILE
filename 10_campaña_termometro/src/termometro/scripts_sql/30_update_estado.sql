-- Reemplaza el Execute SQL Task "UPDATE ESTADO"
UPDATE [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP]
SET [Estado] = CASE
    WHEN [Promedio del termómetro] = 0 AND ([Comentarios] IS NULL OR [Comentarios] = '') THEN 'NO RECORRIDO'
    WHEN [Promedio del termómetro] = 0 AND [Comentarios] LIKE '%CONTACTO NO EVALUADO%' THEN 'CONTACTO NO EVALUADO'
    WHEN [Promedio del termómetro] = 0 AND [Comentarios] LIKE '%SIN DATOS%' THEN 'SIN DATOS'
    WHEN [Promedio del termómetro] = 0 AND [Comentarios] LIKE '%PARQUE CERO%' THEN 'PARQUE CERO'
    WHEN [Promedio del termómetro] = 0 AND [Comentarios] LIKE '%PARQUE 0%' THEN 'PARQUE CERO'
    WHEN [Promedio del termómetro] = 0 AND [Comentarios] LIKE '%SIN CONTACTO%' THEN 'SIN CONTACTO'
    WHEN [Promedio del termómetro] = 0 THEN 'SIN CONTACTO'
    ELSE 'CAMPAÑA OK'
END
WHERE [Estado] IS NULL
  AND CAST([PERIODO] AS INT) = :periodo;
