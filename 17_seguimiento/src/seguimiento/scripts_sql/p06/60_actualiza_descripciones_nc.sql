-- ACTUALIZA DESCRIPCIONES NC: casos que YA estan en la tabla y cuya descripcion cambio en el CSV.
-- #TBL_DESCRIPCIONES_NC es la #temporal con el contenido del CSV (molde: la propia tabla permanente).
-- La comparacion es binaria (BIN2): detecta tambien cambios de mayusculas o tildes; NULL cuenta como un valor.
-- Un caso repetido en el archivo se toma una sola vez. La clave [Número del caso] no se modifica.
;WITH S AS (
	SELECT [Número del caso],
		[Descripción],
		ROW_NUMBER() OVER (PARTITION BY [Número del caso] ORDER BY (SELECT NULL)) AS RN
	FROM #TBL_DESCRIPCIONES_NC
	WHERE ISNULL([Número del caso],'') <> ''
)
UPDATE T
SET T.[Descripción] = S.[Descripción]
FROM [CL_TEMPORALES].[dbo].[TBL_DESCRIPCIONES_NC] T
INNER JOIN S ON T.[Número del caso] = S.[Número del caso]
WHERE S.RN = 1
AND (
	T.[Descripción] COLLATE Latin1_General_100_BIN2 <> S.[Descripción] COLLATE Latin1_General_100_BIN2
	OR (T.[Descripción] IS NULL AND S.[Descripción] IS NOT NULL)
	OR (T.[Descripción] IS NOT NULL AND S.[Descripción] IS NULL)
)