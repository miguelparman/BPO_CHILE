-- CARGA DESCRIPCIONES NC: casos nuevos (no estan en la tabla). Acumulativo: no se trunca ni se borra nada.
-- Corre DESPUES de ACTUALIZA DESCRIPCIONES NC, en la misma transaccion.
;WITH S AS (
	SELECT [Número del caso],
		[Descripción],
		ROW_NUMBER() OVER (PARTITION BY [Número del caso] ORDER BY (SELECT NULL)) AS RN
	FROM #TBL_DESCRIPCIONES_NC
	WHERE ISNULL([Número del caso],'') <> ''
)
INSERT INTO [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC] ([Número del caso],[Descripción])
SELECT S.[Número del caso],S.[Descripción]
FROM S
WHERE S.RN = 1
AND NOT EXISTS (
	SELECT 1 FROM [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC] T
	WHERE T.[Número del caso] = S.[Número del caso]
)