-- ACTUALIZA COLA RECLAMO: casos que YA estan en la tabla y cambiaron propietario, email o subtipo.
-- #TBL_COLA_CHI_RECLAMO_PROPIETARIO es la #temporal del Data Flow (molde: la propia tabla destino).
-- Una celda vacia del CSV equivale a NULL (asi esta el historico de la tabla: 0 textos vacios).
-- La comparacion es binaria (BIN2): detecta tambien cambios de mayusculas o tildes; NULL cuenta como un valor.
-- Un caso repetido en el archivo se toma una sola vez. La clave [Número del caso] no se modifica.
;WITH S AS (
	SELECT [Número del caso],
		NULLIF([Propietario del caso],'') AS [Propietario del caso],
		NULLIF([Email del propietario del caso],'') AS [Email del propietario del caso],
		NULLIF([Subtipo de solicitud],'') AS [Subtipo de solicitud],
		ROW_NUMBER() OVER (PARTITION BY [Número del caso] ORDER BY (SELECT NULL)) AS RN
	FROM #TBL_COLA_CHI_RECLAMO_PROPIETARIO
	WHERE ISNULL([Número del caso],'') <> ''
)
UPDATE T
SET T.[Propietario del caso] = S.[Propietario del caso],
	T.[Email del propietario del caso] = S.[Email del propietario del caso],
	T.[Subtipo de solicitud] = S.[Subtipo de solicitud]
FROM [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO] T
INNER JOIN S ON T.[Número del caso] = S.[Número del caso]
WHERE S.RN = 1
AND (
	(T.[Propietario del caso] COLLATE Latin1_General_100_BIN2 <> S.[Propietario del caso] COLLATE Latin1_General_100_BIN2
		OR (T.[Propietario del caso] IS NULL AND S.[Propietario del caso] IS NOT NULL)
		OR (T.[Propietario del caso] IS NOT NULL AND S.[Propietario del caso] IS NULL))
	OR (T.[Email del propietario del caso] COLLATE Latin1_General_100_BIN2 <> S.[Email del propietario del caso] COLLATE Latin1_General_100_BIN2
		OR (T.[Email del propietario del caso] IS NULL AND S.[Email del propietario del caso] IS NOT NULL)
		OR (T.[Email del propietario del caso] IS NOT NULL AND S.[Email del propietario del caso] IS NULL))
	OR (T.[Subtipo de solicitud] COLLATE Latin1_General_100_BIN2 <> S.[Subtipo de solicitud] COLLATE Latin1_General_100_BIN2
		OR (T.[Subtipo de solicitud] IS NULL AND S.[Subtipo de solicitud] IS NOT NULL)
		OR (T.[Subtipo de solicitud] IS NOT NULL AND S.[Subtipo de solicitud] IS NULL))
)