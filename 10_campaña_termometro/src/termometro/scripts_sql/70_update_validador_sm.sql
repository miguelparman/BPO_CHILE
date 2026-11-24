-- (Agregado, no existe en el .dtsx) Corrige NOM_SM y cod_dni con la hoja VALIDADOR_SM.
-- Llave: PERIODO = PERIODO y ID_GENESYS_SM_TITULAR = PLACE. Solo el periodo procesado.
-- Si el validador trae el dato vacío se conserva el actual.
-- Parámetros: periodo

UPDATE T
SET
     T.[NOM_SM]  = COALESCE(NULLIF(LTRIM(RTRIM(V.[NOM_SM])), ''), T.[NOM_SM])
    ,T.[cod_dni] = COALESCE(NULLIF(LTRIM(RTRIM(V.[DNI])), ''), T.[cod_dni])
FROM [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO] T
INNER JOIN [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_VALIDADOR_SM] V
    ON TRY_CAST(V.[PERIODO] AS INT) = CAST(T.[PERIODO] AS INT)
   AND TRY_CAST(V.[PLACE] AS FLOAT) = T.[ID_GENESYS_SM_TITULAR]  -- en la tabla final es float
WHERE CAST(T.[PERIODO] AS INT) = :periodo;
