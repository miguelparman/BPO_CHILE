-- CARGA COLA RECLAMO: casos nuevos (no estan en la tabla). Acumulativo: no se trunca ni se borra nada.
-- Corre DESPUES de ACTUALIZA COLA RECLAMO, en la misma transaccion.
;WITH S AS (
	SELECT [Número del caso],
		NULLIF([Propietario del caso],'') AS [Propietario del caso],
		NULLIF([Email del propietario del caso],'') AS [Email del propietario del caso],
		NULLIF([Subtipo de solicitud],'') AS [Subtipo de solicitud],
		ROW_NUMBER() OVER (PARTITION BY [Número del caso] ORDER BY (SELECT NULL)) AS RN
	FROM #TBL_COLA_CHI_RECLAMO_PROPIETARIO
	WHERE ISNULL([Número del caso],'') <> ''
)
INSERT INTO [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO]
	([Número del caso],[Propietario del caso],[Email del propietario del caso],[Subtipo de solicitud])
SELECT S.[Número del caso],S.[Propietario del caso],S.[Email del propietario del caso],S.[Subtipo de solicitud]
FROM S
WHERE S.RN = 1
AND NOT EXISTS (
	SELECT 1 FROM [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO] T
	WHERE T.[Número del caso] = S.[Número del caso]
)