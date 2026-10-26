
-- EXEC BBDD_NUEVO_SEGUIMIENTO.DBO.SP_ASESOR_RESPONSABLE		--00:02:45


CREATE PROCEDURE [dbo].[SP_INSUMOS_SEGUIMIENTO]

AS
BEGIN

SET LANGUAGE SPANISH

DECLARE @HOY DATETIME, @periodo_actual  INT

SET @HOY = GETDATE()
SET @periodo_actual = YEAR(@HOY)* 100 + MONTH(@HOY)

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

IF EXISTS 
(
	SELECT * 
	FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_ULTIMO_COMENTARIO' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO]
END	
	
SELECT 
X0.[Número del caso],
X0.[Comentario del caso creado por],
X0.[Fecha de creación de Comentario del caso],
X0.[Comentarios del caso]
INTO [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO]		
FROM (SELECT X0.*,ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de creación de Comentario del caso] DESC) Orden 
FROM CL_SALESFORCE_ACTUAL.[dbo].[TBL_HISTORIAL_COMENTARIOS] X0
WHERE X0.[Fecha de creación de Comentario del caso] IS NOT NULL)X0  
WHERE Orden = 1 	

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

IF EXISTS 
(
	SELECT * 
	FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_ULTIMO_COMENTARIO_FRACTALIA' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_ULTIMO_COMENTARIO_FRACTALIA
END	
	
SELECT
X0.[Número del caso],
X0.[Comentario del caso creado por],
X0.[Fecha de creación de Comentario del caso],
X0.Jefatura,X0.Programa,
X0.[Comentarios del caso]
INTO CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_ULTIMO_COMENTARIO_FRACTALIA		
FROM (SELECT X0.*,x2.[Jefatura],X2.Programa, 
ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de creación de Comentario del caso] DESC) Orden 
FROM CL_SALESFORCE_ACTUAL.[dbo].[TBL_HISTORIAL_COMENTARIOS] X0
INNER JOIN (SELECT * FROM [BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] WHERE [Nombre Empresa] LIKE '%FRACTALIA%') x1
ON UPPER(REPLACE(X0.[Comentario del caso creado por], CHAR(160), ' ')) = UPPER(REPLACE(X1.[Usuario Salesforce], CHAR(160), ' '))
INNER JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_HISTORICO] X2
ON X1.[DNI]=x2.[DNI] 
--AND CAST(X0.[Fecha de creación de Comentario del caso] AS DATE) BETWEEN X2.[Fecha Ingreso al Àrea] AND X2.[Salida del área]
WHERE X0.[Fecha de creación de Comentario del caso] IS NOT NULL)X0  
WHERE Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

IF EXISTS 
	(
		SELECT * 
		FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.INFORMATION_SCHEMA.TABLES 
		WHERE TABLE_NAME='TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO' AND TABLE_SCHEMA='DBO'
	)
BEGIN
	DELETE FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO
	WHERE DATEDIFF(DAY,[Fecha de creación de Comentario del caso],GETDATE())<=5
END	

INSERT INTO CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO
SELECT X0.[Número del caso],[Fecha de creación de Comentario del caso],[Comentario del caso creado por]
, '[' + SUBSTRING(VALUE,1,CHARINDEX(']',VALUE)) codigo
, [Fecha de Carga al SQL]
FROM CL_SALESFORCE_ACTUAL.[dbo].[TBL_HISTORIAL_COMENTARIOS]  X0
CROSS APPLY STRING_SPLIT ( [Comentarios del caso] , '[' )  
WHERE len(value)>2
AND CHARINDEX(']',VALUE)>=1
AND DATEDIFF(DAY,[Fecha de creación de Comentario del caso],GETDATE())<=5



--- ELIMINANDO DUP

DELETE T
FROM
(
SELECT *
, DupRank = ROW_NUMBER() OVER (
				PARTITION BY  [Número del caso],[Fecha de creación de Comentario del caso],codigo
				ORDER BY [Fecha de Carga al SQL] ASC
			)
FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO
WHERE DATEDIFF(DAY,[Fecha de creación de Comentario del caso],GETDATE())<=5
) AS T
WHERE DupRank > 1 

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

IF EXISTS 
(
	SELECT * 
	FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_ULTIMO_DNI_DEL_COMENTARIO' AND TABLE_SCHEMA='DBO'
)
BEGIN
DROP TABLE CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_ULTIMO_DNI_DEL_COMENTARIO
END	

SELECT [Número del caso],[Fecha de creación de Comentario del caso],[DNI]
INTO CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_ULTIMO_DNI_DEL_COMENTARIO
FROM (
SELECT [Número del caso],[Fecha de creación de Comentario del caso],X1.[DNI]
,ROW_NUMBER() OVER(PARTITION BY [Número del caso] ORDER BY [Fecha de creación de Comentario del caso] DESC) Orden
FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO X0
INNER JOIN  [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X1
ON REPLACE(REPLACE(X0.codigo,'[',''),']','')=X1.[DNI] AND 
YEAR(X0.[Fecha de creación de Comentario del caso])*100+MONTH(X0.[Fecha de creación de Comentario del caso])=X1.periodo
WHERE X0.[Comentario del caso creado por] NOT IN ('VENTANILLA UNICA')) A
WHERE A.Orden=1  ---26904

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

----- NUEVO CODIGO PENDIENTE

IF EXISTS 
(
	SELECT * 
	FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_ULTIMO_CODIGO_PENDIENTE_DEL_CASO' AND TABLE_SCHEMA='DBO'
)
BEGIN
DROP TABLE [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ULTIMO_CODIGO_PENDIENTE_DEL_CASO
END	

SELECT X0.[Número del caso],
X0.Codigo
INTO [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ULTIMO_CODIGO_PENDIENTE_DEL_CASO	--(8744 rows affected)
FROM (
SELECT X0.[Número del caso], X0.Codigo
,ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de creación de Comentario del caso] DESC) Orden 
FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CODIGO_INCUMPLIMIENTO_COMENTARIO X0
INNER JOIN (SELECT * FROM [BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] WHERE [Nombre Empresa] LIKE '%FRACTALIA%') x1
ON UPPER(REPLACE(X0.[Comentario del caso creado por], CHAR(160), ' ')) = UPPER(REPLACE(X1.[Usuario Salesforce], CHAR(160), ' '))
INNER JOIN [BBDD_GENERAL].DBO.TBL_PERSONAL_HISTORICO X2
ON X1.[DNI]=x2.[DNI]
--AND CAST(X0.[Fecha de creación de comentario del caso] as date) between x2.[Fecha Ingreso al Àrea] AND x2.[Salida del área] -- Se quita restricción de fecha si agente esta activo.
WHERE CODIGO IN (SELECT CODIGO FROM [CL_DATA].DBO.TBL_MOTIVO_PENDIENTE
				WHERE CODIGO NOT LIKE '%RTX%' AND CODIGO NOT LIKE '%EX%')) X0 
WHERE Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

-- CASOS RESUELTOS

IF EXISTS 
(
	SELECT * 
	FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_CASOS_RESUELTOS' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_RESUELTOS
END		


SELECT X0.[Número del caso],
	X0.[Fecha de modificación],
	X0.[Modificado por]
INTO [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_RESUELTOS	
FROM (SELECT X0.[Número del caso] ,X0.[Fecha de modificación],
	REPLACE(REPLACE(REPLACE(X0.[Modificado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' ') [Modificado por],
	ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de modificación] desc  ) Orden 
	FROM CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_CASOS X0
	WHERE [Campo / Evento] ='Estado' AND [Valor nuevo]='Resuelto')X0  
WHERE Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

-- CASOS FINALIZADOS 

IF EXISTS 
(
	SELECT * 
	FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_CASOS_FINALIZADOS' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_FINALIZADOS
END		


SELECT X0.[Número del caso],
X0.[Fecha de modificación]
,REPLACE(REPLACE(REPLACE(REPLACE(X0.[Modificado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '), CHAR(160), ' ') [Modificado por]
INTO [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_FINALIZADOS
FROM 
(	SELECT X0.[Número del caso] ,
	X0.[Fecha de modificación],
	X0.[Modificado por],
ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de modificación] DESC) Orden 
FROM CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_CASOS X0
WHERE [Campo / Evento] ='Estado' AND [Valor nuevo] = 'Finalizado')X0  
WHERE Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

-- CASOS CERRADOS 

IF EXISTS 
(
	SELECT * 
	FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_CASOS_CERRADOS' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_CERRADOS
END		


SELECT 
	X0.[Número del caso]
	,X0.[Fecha de modificación]
	,REPLACE(REPLACE(REPLACE(REPLACE(X0.[Modificado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '), CHAR(160), ' ') [Modificado por]
INTO 
	[CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_CERRADOS
FROM 
	(	
	SELECT 
		X0.[Número del caso]
		,X0.[Fecha de modificación]
		,X0.[Modificado por]
		,ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de modificación] DESC) Orden 
	FROM 
		CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_CASOS X0
	WHERE 
		[Campo / Evento] ='Estado' 
		AND [Valor nuevo] = 'Cerrado'
		--and [Número del caso] = '11188653'
	)X0  
WHERE 
	Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

-- CASOS CANCELADOS 

IF EXISTS 
(
	SELECT * 
	FROM CL_TEMPORALES.INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_CASOS_CANCELADOS' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_CANCELADOS]
END		


SELECT 
	X0.[Número del caso],
	X0.[Fecha de modificación]
	,REPLACE(REPLACE(REPLACE(REPLACE(X0.[Modificado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '), CHAR(160), ' ') [Modificado por]
INTO 
	CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_CANCELADOS]
FROM 
	(	
	SELECT 
		X0.[Número del caso] ,
		X0.[Fecha de modificación],
		X0.[Modificado por],
		ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de modificación] desc, X0.[Modificado por] desc  ) Orden 
	FROM 
		CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_CASOS X0
	WHERE 
		[Campo / Evento] ='Estado' 
		AND (
			[Valor nuevo] ='Cancelado' 
			OR [Valor nuevo] ='Canceled'
			)
		--AND [Número del caso] = '15339534'
	)X0  
WHERE 
	Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

-- CASOS RECHAZADOS

IF EXISTS 
(
	SELECT * 
	FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_CASOS_RECHAZADOS' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_RECHAZADOS
END		


SELECT X0.[Número del caso],
	X0.[Fecha de modificación]
	,REPLACE(REPLACE(REPLACE(REPLACE(X0.[Modificado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '), CHAR(160), ' ') [Modificado por]
INTO [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_TOTAL_CASOS_RECHAZADOS
FROM 
(	SELECT X0.[Número del caso] ,
		X0.[Fecha de modificación],
		X0.[Modificado por],
	ROW_NUMBER() OVER(PARTITION BY X0.[Número del caso] ORDER BY X0.[Fecha de modificación] desc  ) Orden 
	FROM CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_CASOS X0
	WHERE [Campo / Evento] ='Estado' AND [Valor nuevo]='Rechazado')X0  
WHERE Orden = 1

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------	

--- TOTAL CASOS PADRES

IF EXISTS 
(
	SELECT * 
	FROM CL_INSUMOS_SEGUIMIENTO_ACTUAL.INFORMATION_SCHEMA.TABLES 
	WHERE TABLE_NAME='TBL_CASOS_PADRES' AND TABLE_SCHEMA='DBO'
)
BEGIN
	DROP TABLE CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CASOS_PADRES
END	

SELECT p.[Número de caso principal],X1.[Origen del caso],x1.[Tipo del caso]
,SUM([Caso Agrupador])[Caso Agrupador]
,SUM([Caso Comercial II])[Caso Comercial II]
,SUM([Caso Interno])[Caso Interno]
,SUM([Caso Comercial])[Caso Comercial]
,CASE WHEN SUM([Caso Agrupador])+SUM([Caso Comercial II])+SUM([Caso Comercial])=0 AND SUM([Caso Interno])<>0 THEN 'Todos hijos internos'
WHEN SUM([Caso Agrupador])+SUM([Caso Interno])+SUM([Caso Comercial])=0 AND SUM([Caso Comercial II])<>0 THEN 'Todos hijos comerciales II'
WHEN SUM([Caso Comercial II])+SUM([Caso Interno])+SUM([Caso Comercial])=0 AND SUM([Caso Agrupador])<>0 THEN 'Todos hijos agrupadores'
WHEN SUM([Caso Comercial II])+SUM([Caso Interno])+SUM([Caso Agrupador])=0 AND SUM([Caso Comercial])<>0 THEN 'Todos hijos comerciales'
ELSE '-' END [Indicador]
INTO CL_INSUMOS_SEGUIMIENTO_ACTUAL.DBO.TBL_CASOS_PADRES
FROM CL_SALESFORCE_ACTUAL.[dbo].[TBL_CASOS]
PIVOT
(COUNT([Número del caso])
FOR [Tipo del caso] IN ([Caso Agrupador],[Caso Comercial II],[Caso Interno],[Caso Comercial])
) AS P
LEFT JOIN CL_SALESFORCE_ACTUAL.[dbo].[TBL_CASOS] X1
ON p.[Número de caso principal]=x1.[Número del caso]
WHERE p.[Número de caso principal]<>'0'
GROUP BY p.[Número de caso principal],x1.[Origen del caso],x1.[Tipo del caso]

END



