CREATE PROCEDURE [dbo].[SP_ASESOR_RESPONSABLE]

AS
BEGIN

SET LANGUAGE SPANISH

--------------------------------------------------------------------------------------------------------------------------------------------------------------

	IF EXISTS 
		(
			SELECT * 
			FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE [CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES
	END	


------------------- CASOS PENDIENTES ----------------------


SELECT 
	X0.[Número del caso],
CASE 
	WHEN X4.Jefatura IS NOT NULL THEN X4.Jefatura 
   --WHEN X5.Jefatura IS NOT NULL THEN X5.Jefatura 
    ELSE X2.Jefatura 
END [Jefatura Responsable],
CASE 
	WHEN X4.[Programa] IS NOT NULL THEN X4.[Programa]
   --WHEN X5.[Programa] IS NOT NULL THEN X5.[Programa]
     ELSE X2.[Programa] 
END [Programa Responsable],
CASE 
	WHEN X4.[DNI] IS NOT NULL THEN X4.[DNI] 
   --WHEN X5.[DNI] IS NOT NULL THEN X5.[DNI] 
    ELSE X2.[DNI] 
END [DNI],
CASE 
	WHEN X4.[DNI Coordinador] IS NOT NULL THEN X4.[DNI Coordinador]
   --WHEN X5.[DNI Coordinador] IS NOT NULL THEN X5.[DNI Coordinador]
	ELSE X2.[DNI Coordinador] 
END [DNI Coordinador],
CASE 
	WHEN X4.[Nombre Coordinador] IS NOT NULL THEN X4.[Nombre Coordinador] 
   --WHEN X5.Coordinador IS NOT NULL THEN X5.Coordinador 
    ELSE X2.[Nombre Coordinador] 
END [Coordinador],
CASE 
	WHEN X4.DNI IS NOT NULL THEN X4.[Nombre Completo]
   --WHEN X5.DNI IS NOT NULL THEN X5.[Nombre Completo]
	ELSE X2.[Nombre Completo] 
END [Asesor Responsable],
GETDATE() [Fecha de Gestión]
INTO 
	[CL_TEMPORALES].DBO.TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES
FROM 
	[CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X0 WITH (NOLOCK)

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] 
		LIKE '%FRACTALIA%'
	) X1--Propietario
ON 
	UPPER(TRIM(REPLACE(X0.[Propietario del caso], CHAR(160), ' '))) =
	UPPER(TRIM(REPLACE(X1.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X2 WITH (NOLOCK)
ON  
	X1.[DNI] = X2.[DNI] 
	AND YEAR(X0.[Fecha/Hora de apertura])*100+MONTH(X0.[Fecha/Hora de apertura]) = X2.Periodo

LEFT JOIN 
	[CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_DNI_DEL_COMENTARIO] X3 --DNI Ultimo Comentario
ON 
	X3.[Número del caso] = X0.[Número del caso]
LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X4
ON 
	X4.DNI = X3.DNI 
	AND YEAR(X3.[Fecha de creación de Comentario del caso])*100+MONTH([Fecha de creación de Comentario del caso]) = X4.Periodo

/*LEFT JOIN [BBDD_TEMP_SEG].[dbo].[TBL_PADRON_NOMBRES_PERSONAL_BPO] X5
ON X5.DNI = X1.DNI*/

WHERE X0.[Estado] NOT IN ('Finalizado','Resuelto','Cerrado','Cancelado','Rechazado')

------------------- CASOS PENDIENTES MAIL TO CASE ----------------------

IF EXISTS 
		(
			SELECT * 
			FROM CL_TEMPORALES.INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES_M2C' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE CL_TEMPORALES.DBO.TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES_M2C
	END

SELECT 
	X0.[Número del caso],
CASE 
	WHEN X4.Jefatura IS NOT NULL THEN X4.Jefatura 
    WHEN X6.Jefatura IS NOT NULL THEN X6.Jefatura 
    ELSE 'No identificados M2C' 
END [Jefatura Responsable],
CASE 
	WHEN X4.Programa IS NOT NULL THEN X4.Programa 
    WHEN X6.Programa IS NOT NULL THEN X6.Programa 
    ELSE 'No identificados M2C' 
END [Programa Responsable],
CASE 
	WHEN X4.DNI IS NOT NULL THEN X4.DNI 
	WHEN X6.DNI IS NOT NULL THEN X6.DNI 
    ELSE 'No identificados M2C' 
END DNI,
CASE 
	WHEN X4.[DNI Coordinador] IS NOT NULL THEN X4.[DNI Coordinador] 
    WHEN X6.[DNI Coordinador] IS NOT NULL THEN X6.[DNI Coordinador] 
    ELSE 'No identificados M2C' 
END [DNI Coordinador],
CASE 
	WHEN X4.[Nombre Coordinador] IS NOT NULL THEN X4.[Nombre Coordinador]
    WHEN X6.[Nombre Coordinador] IS NOT NULL THEN X6.[Nombre Coordinador] 
    ELSE 'No identificados M2C' 
END Coordinador,
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.[Usuario Salesforce]
	WHEN X4.DNI IS NOT NULL THEN X4.[Nombre Completo]
	WHEN X6.DNI IS NOT NULL THEN X6.[Nombre Completo] 
	ELSE 'No identificados M2C' 
END [Asesor Responsable],
GETDATE() [Fecha de Gestión]
INTO 
	CL_TEMPORALES.DBO.TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES_M2C
FROM 
	[CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X0

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES] X1
ON 
	X0.[Número del caso] = X1.[Número del caso]

LEFT JOIN 
	[CL_CARTERA].[dbo].[TBL_CARTERA_ACTUAL] X2 -- POR CARTERA
ON 
	X0.[No. identificación fiscal] = X2.RUT_SIN_DV

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X3
ON 
	LTRIM(RTRIM(X2.[COD_DNI])) = LTRIM(RTRIM(X3.DNI)) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X4 WITH (NOLOCK)
ON  
	X2.[COD_DNI] = X4.[DNI] 
	AND YEAR(X0.[Fecha/Hora de apertura])*100+MONTH(X0.[Fecha/Hora de apertura]) = X4.Periodo

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X5-- POR ULTIMO PROPIETARIO
ON 
	UPPER(TRIM(REPLACE(X0.[Propietario del caso], CHAR(160), ' '))) = 
	UPPER(TRIM(REPLACE((CASE WHEN X5.[Usuario Salesforce] = 'Delmy Graciela Ramirez  Carrillo' THEN 'Delmy Graciela Ramirez  Carrillo ' ELSE X5.[Usuario Salesforce] END), CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN
	(
	SELECT 
		X0.* 
	FROM
		(
		SELECT 
			*
			,ROW_NUMBER() OVER(PARTITION BY DNI ORDER BY PERIODO DESC) Orden 
		FROM 
			[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO]
		)X0 
	WHERE Orden = 1
	)X6
ON X6.DNI = X5.DNI

WHERE 
	X0.[Origen del caso] = 'Email2Case CHI' 
	AND X0.[Creado por] = 'Administrador B2B' 
	AND X1.[Asesor Responsable] IS NULL
	AND [Estado] NOT IN ('Finalizado','Resuelto','Cerrado','Cancelado','Rechazado')


------------------- CASOS FINALIZADOS -------------------

IF EXISTS 
		(
			SELECT * 
			FROM CL_TEMPORALES.INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_FINALIZADOS' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_FINALIZADOS]
	END	


SELECT 
	X0.[Número del caso],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X3.[Jefatura] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X6.[Jefatura] --Cerrados
		WHEN X9.DNI IS NOT NULL THEN X9.[Jefatura] --Finalizados
		WHEN X11.DNI IS NOT NULL THEN X11.[Jefatura] --Propietario
		ELSE NULL 
	END [Jefatura Responsable],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X3.[Programa] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X6.[Programa] --Cerrados
		WHEN X9.DNI IS NOT NULL THEN X9.[Programa] --Finalizados
		WHEN X11.DNI IS NOT NULL THEN X11.[Programa] --Propietario
		ELSE NULL 
	END [Programa Responsable],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X3.[Nombre Coordinador] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X6.[Nombre Coordinador] --Cerrados
		WHEN X9.DNI IS NOT NULL THEN X9.[Nombre Coordinador] --Finalizados
		WHEN X11.DNI IS NOT NULL THEN X11.[Nombre Coordinador] --Propietario
		ELSE NULL 
	END [Coordinador Responsable],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X2.[Usuario Salesforce] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X5.[Usuario Salesforce] --Cerrados
		WHEN X9.[DNI] IS NOT NULL THEN X8.[Usuario Salesforce] --Finalizados
		WHEN X11.DNI IS NOT NULL THEN X10.[Usuario Salesforce] --Propietario
		ELSE NULL 
	END [Asesor Responsable],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X3.DNI --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X6.DNI --Cerrados
		ELSE NULL 
	END [DNI],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X3.[DNI Coordinador] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X6.[DNI Coordinador] --Cerrados
		ELSE NULL 
	END [DNI Coordinador],
	CASE 
		WHEN X3.DNI IS NOT NULL THEN X1.[Fecha de modificación] --Resuelto
		WHEN X6.DNI IS NOT NULL THEN X4.[Fecha de modificación] --Cerrados
		ELSE NULL 
	END [Fecha de Modificación]
INTO 
	CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_FINALIZADOS]
FROM 
	[CL_SALESFORCE_ACTUAL].DBO.[TBL_CASOS] X0

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_RESUELTOS] X1 -- RESUELTOS
ON 
	X0.[Número del caso] = X1.[Número del caso]

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X2
ON 
	UPPER(TRIM(REPLACE(X1.[Modificado por], CHAR(160), ' '))) 
	= UPPER(TRIM(REPLACE(X2.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X3
ON 
	X2.DNI = X3.DNI 
	AND YEAR(X1.[Fecha de modificación])*100+MONTH(X1.[Fecha de modificación]) = X3.Periodo

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_CERRADOS] X4 -- CERRADOS
ON 
	X0.[Número del caso] = X4.[Número del caso]

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE [Nombre Empresa] LIKE '%FRACTALIA%'
	) X5
ON 
	UPPER(TRIM(REPLACE(X4.[Modificado por], CHAR(160), ' '))) 
	= UPPER(TRIM(REPLACE(X5.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X6
ON 
	X5.DNI = X6.DNI 
	AND YEAR(X4.[Fecha de modificación])*100+MONTH(X4.[Fecha de modificación]) = X6.Periodo

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_FINALIZADOS] X7 -- FINALIZADOS
ON 
	X0.[Número del caso] = X7.[Número del caso]

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	)X8
ON 
	UPPER(TRIM(REPLACE(X7.[Modificado por], CHAR(160), ' '))) 
	= UPPER(TRIM(REPLACE(X8.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X9
ON 
	X9.DNI = X8.DNI 
	AND YEAR(X7.[Fecha de modificación])*100+MONTH(X7.[Fecha de modificación]) = X9.Periodo

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X10--Propietario
ON 
	UPPER(TRIM(REPLACE(X0.[Propietario del caso], CHAR(160), ' '))) 
	= UPPER(TRIM(REPLACE(X10.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC 

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X11 WITH (NOLOCK) 
ON  
	X10.[DNI] = X11.[DNI] 
	AND YEAR(X0.[Fecha/Hora de apertura])*100+MONTH(X0.[Fecha/Hora de apertura]) = X11.Periodo

WHERE 
	X0.[Estado] IN ('Resuelto','Cerrado','Finalizado')


------------------- CASOS CANCELADOS -------------------


IF EXISTS 
		(
			SELECT * 
			FROM CL_TEMPORALES.INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_CANCELADOS' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_CANCELADOS]
	END	


SELECT 
	X0.[Número del caso],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.[Jefatura] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X6.[Jefatura] --Rechazados
	ELSE NULL 
END 
	[Jefatura Responsable],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.[Programa] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X6.[Programa] --Rechazados
	ELSE NULL 
END [Programa Responsable],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.[Nombre Coordinador] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X6.[Nombre Coordinador] --Rechazados
	ELSE NULL 
END [Coordinador Responsable],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X2.[Usuario Salesforce] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X5.[Usuario Salesforce] --Rechazados
	ELSE NULL 
END [Asesor Responsable],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.DNI --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X6.DNI --Rechazados
	ELSE NULL 
END [DNI],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X3.[DNI Coordinador] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X6.[DNI Coordinador] --Rechazados
	ELSE NULL 
END [DNI Coordinador],
CASE 
	WHEN X3.DNI IS NOT NULL THEN X1.[Fecha de modificación] --Cancelados
	WHEN X6.DNI IS NOT NULL THEN X4.[Fecha de modificación] --Rechazados
	ELSE NULL 
END [Fecha de Modificación]
INTO 
	CL_TEMPORALES.DBO.[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_CANCELADOS]
FROM 
	[CL_SALESFORCE_ACTUAL].DBO.[TBL_CASOS] X0

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_CANCELADOS] X1 --Cancelados
ON 
	X0.[Número del caso] = X1.[Número del caso]

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X2
ON  
	UPPER(TRIM(REPLACE(X1.[Modificado por], CHAR(160), ' '))) 
	=  UPPER(TRIM(REPLACE(X2.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X3
ON 
	X2.DNI = X3.DNI 
	AND YEAR(X1.[Fecha de modificación])*100+MONTH(X1.[Fecha de modificación]) = X3.Periodo

LEFT JOIN 
	[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_CASOS_RECHAZADOS] X4 --Rechazados
ON 
	X0.[Número del caso] = X4.[Número del caso]

LEFT JOIN 
	(
	SELECT 
		* 
	FROM 
		[BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] 
	WHERE 
		[Nombre Empresa] LIKE '%FRACTALIA%'
	) X5
ON 
	UPPER(TRIM(REPLACE(X4.[Modificado por], CHAR(160), ' '))) 
	= UPPER(TRIM(REPLACE(X5.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC

LEFT JOIN 
	[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X6
ON 
	X5.DNI = X6.DNI 
	AND YEAR(X4.[Fecha de modificación])*100+MONTH(X4.[Fecha de modificación]) = X6.Periodo

WHERE 
	X0.[Estado] IN ('Rechazado','Cancelado')


------------------- ARMANDO TABLA FINAL -------------------

IF EXISTS 
		(
			SELECT * 
			FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_ASESOR_RESPONSABLE' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ASESOR_RESPONSABLE
	END	

SELECT X0.[Número del caso],X0.[Estado],
CASE WHEN X0.[Estado] in ('Cancelado','Rechazado') THEN 'Cancelado'
	 WHEN X0.[Estado] in ('Resuelto','Cerrado') THEN 'Finalizado'
	 ELSE 'En proceso' END [Estado General],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN 'ULTIMO COMENTATRIO'
     WHEN X5.[Número del caso] IS NOT NULL THEN 'ASESOR RESPONSABLE PENDIENTE'
     WHEN X6.[Número del caso] IS NOT NULL THEN 'ASESOR RESPONSABLE M2C'
     WHEN X7.[Fecha de Modificación] IS NOT NULL THEN 'ASESOR RESPONSABLE FINALIZADO'
     WHEN X8.[Fecha de Modificación] IS NOT NULL THEN 'ASESOR RESPONSABLE CANCELADO'
     ELSE NULL END [Cruce],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X3.[Fecha de creación de Comentario del caso] --Ultimo Comentario DNI
	 WHEN X5.[Fecha de Gestión] IS NOT NULL THEN X5.[Fecha de Gestión] --Asesor Pendiente
	 WHEN X6.[Fecha de Gestión] IS NOT NULL THEN X6.[Fecha de Gestión] --Asesor Pendiente M2C
	 WHEN X7.[Fecha de Modificación] IS NOT NULL THEN X7.[Fecha de Modificación] --Asesor Finalizado
	 WHEN X8.[Fecha de Modificación] IS NOT NULL THEN X8.[Fecha de Modificación] --Asesor Cancelado
	 ELSE NULL END [Fecha de Gestión],
--Se ajusta calcule para obtner el nombre del asesor segun el criterio de Asesor Responsable DNI
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.[Nombre Completo] --Ultimo Comentario DNI
	 WHEN X5.[DNI] IS NOT NULL THEN X5.[Asesor Responsable] --Asesor Pendiente
	 WHEN X6.[DNI] IS NOT NULL THEN X6.[Asesor Responsable] --Asesor Pendiente M2C
	 WHEN X7.[DNI] IS NOT NULL THEN X7.[Asesor Responsable] --Asesor Finalizado
	 WHEN X8.[DNI] IS NOT NULL THEN X8.[Asesor Responsable] --Asesor Cancelado
	 ELSE 'Externo' END [Asesor Responsable],

--CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.[Nombre Completo] --Ultimo Comentario DNI
--	 WHEN X5.[Fecha de Gestión] IS NOT NULL THEN X5.[Asesor Responsable] --Asesor Pendiente
--	 WHEN X6.[Fecha de Gestión] IS NOT NULL THEN X6.[Asesor Responsable] --Asesor Pendiente M2C
--	 WHEN X7.[Fecha de Modificación] IS NOT NULL THEN X7.[Asesor Responsable] --Asesor Finalizado
--	 WHEN X8.[Fecha de Modificación] IS NOT NULL THEN X8.[Asesor Responsable] --Asesor Cancelado
--	 ELSE 'Externo' END [Asesor Responsable],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.DNI --Ultimo Comentario DNI
	 WHEN X5.[DNI] IS NOT NULL THEN X5.[DNI] --Asesor Pendiente
	 WHEN X6.[DNI] IS NOT NULL THEN X6.[DNI] --Asesor Pendiente M2C
	 WHEN X7.[DNI] IS NOT NULL THEN X7.[DNI] --Asesor Finalizado
	 WHEN X8.[DNI] IS NOT NULL THEN X8.[DNI] --Asesor Cancelado
	 ELSE 'Externo' END [Asesor Responsable DNI],	
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.[DNI Coordinador] --Ultimo Comentario DNI
	 WHEN X5.[DNI Coordinador] IS NOT NULL THEN X5.[DNI Coordinador] --Asesor Pendiente
	 WHEN X6.[DNI Coordinador] IS NOT NULL THEN X6.[DNI Coordinador] --Asesor Pendiente M2C
	 WHEN X7.[DNI Coordinador] IS NOT NULL THEN X7.[DNI Coordinador] --Asesor Finalizado
	 WHEN X8.[DNI Coordinador] IS NOT NULL THEN X8.[DNI Coordinador] --Asesor Cancelado
	 ELSE 'Externo' END [Coordinador Responsable DNI],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.Jefatura --Ultimo Comentario DNI
	 WHEN X5.[Jefatura Responsable] IS NOT NULL THEN X5.[Jefatura Responsable] --Asesor Pendiente
	 WHEN X6.[Jefatura Responsable] IS NOT NULL THEN X6.[Jefatura Responsable] --Asesor Pendiente M2C
	 WHEN X7.[Jefatura Responsable] IS NOT NULL THEN X7.[Jefatura Responsable] --Asesor Finalizado
	 WHEN X8.[Jefatura Responsable] IS NOT NULL THEN X8.[Jefatura Responsable] --Asesor Cancelado
	 ELSE 'Externo' END [Servicio Responsable],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN X4.Programa --Ultimo Comentario DNI
	WHEN X5.[Programa Responsable] IS NOT NULL THEN X5.[Programa Responsable] --Asesor Pendiente
	WHEN X6.[Programa Responsable] IS NOT NULL THEN X6.[Programa Responsable] --Asesor Pendiente M2C
	WHEN X7.[Programa Responsable] IS NOT NULL THEN X7.[Programa Responsable] --Asesor Finalizado
	WHEN X8.[Programa Responsable] IS NOT NULL THEN X8.[Programa Responsable] --Asesor Cancelado
	ELSE 'Externo' END [Programa Responsable],
CASE WHEN X2.DNI IS NOT NULL THEN X2.DNI
	 WHEN X4.DNI IS NOT NULL THEN X4.DNI 
	 ELSE 'Externo' END [Asesor Creador DNI],
CASE WHEN X2.DNI IS NOT NULL THEN X2.[DNI Coordinador] 
	 WHEN X4.DNI IS NOT NULL THEN X4.[DNI Coordinador] 
	 ELSE 'Externo' END [Coordinador Creador DNI],
CASE WHEN X2.DNI IS NOT NULL THEN X2.[Jefatura]
	 WHEN X2.DNI IS NULL AND X0.[Creado por]= 'Administrador B2B' AND X0.[Origen del caso] = 'Email2Case CHI' THEN 'Cliente'
	 WHEN X4.DNI IS NOT NULL THEN X4.[Jefatura] 
	 ELSE 'Externo' END [Jefatura Creador],
CASE WHEN X2.DNI IS NOT NULL THEN X2.[Programa]
	 WHEN X2.DNI IS NULL AND X0.[Creado por] = 'Administrador B2B' AND X0.[Origen del caso] = 'Email2Case CHI' THEN 'Cliente'
	 WHEN X4.DNI IS NOT NULL THEN X4.[Programa] 
	 ELSE 'Externo' END [Programa Creador],
CASE WHEN X4.DNI IS NOT NULL THEN X4.DNI 
	 ELSE 'Externo' END [Asesor Último DNI],
CASE WHEN X4.DNI IS NOT NULL THEN X4.[DNI Coordinador] 
	 ELSE 'Externo' END [Coordinador Último DNI],
CASE WHEN X4.DNI IS NOT NULL THEN X4.[Jefatura]
	 ELSE 'Externo' END [Jefatura Último DNI],
CASE WHEN X4.DNI IS NOT NULL THEN X4.[Programa]
	 ELSE 'Externo' END [Programa Último DNI],
X3.[Fecha de creación de Comentario del caso] [Fecha Último DNI]

INTO [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ASESOR_RESPONSABLE

FROM [CL_SALESFORCE_ACTUAL].DBO.[TBL_CASOS] X0

LEFT JOIN (SELECT * FROM [BBDD_GENERAL].[dbo].[TBL_SALESFORCE_USUARIOS_UNICOS] WHERE [Nombre Empresa] LIKE '%FRACTALIA%') X1 --Creado por
ON UPPER(TRIM(REPLACE(X0.[Creado por], CHAR(160), ' '))) = UPPER(TRIM(REPLACE(X1.[Usuario Salesforce], CHAR(160), ' '))) Collate Latin1_General_100_CI_AS_SC
LEFT JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X2
ON X1.[DNI] = X2.[DNI] AND YEAR(X0.[Fecha/Hora de apertura])*100+MONTH(X0.[Fecha/Hora de apertura]) = X2.[Periodo]

LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_DNI_DEL_COMENTARIO] X3 --Ultimo Comentario DNI
ON X0.[Número del caso] = X3.[Número del caso] 
LEFT JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X4
ON X3.DNI = X4.DNI AND YEAR(X3.[Fecha de creación de Comentario del caso])*100+MONTH([Fecha de creación de Comentario del caso]) = X4.Periodo

LEFT JOIN CL_TEMPORALES.[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES] X5 --Asesor Pendiente
ON X0.[Número del caso] = X5.[Número del caso]

LEFT JOIN [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_PENDIENTES_M2C] X6 --Asesor Pendiente M2C
ON X0.[Número del caso] = X6.[Número del caso]

LEFT JOIN [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_FINALIZADOS] X7 --Asesor Finalizado
ON X0.[Número del caso] = X7.[Número del caso]

LEFT JOIN [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_ASESOR_RESPONSABLE_CANCELADOS] X8 --Asesor Cancelado
ON X0.[Número del caso] = X8.[Número del caso]


	IF EXISTS 
		(
			SELECT [Número del caso] , COUNT(*)
			FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ASESOR_RESPONSABLE
			GROUP BY [Número del caso] HAVING COUNT(*)> 1
		)
	BEGIN
		RAISERROR ('Números de casos duplicados',16,1); 
	END	

  
  ------------------------------------------------------------------------------- MOTIVO PENDIENTE -------------------------------------------------------------------------------
 
	IF EXISTS 
		(
			SELECT * 
			FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_CASOS_CON_MOTIVOS_PENDIENTES' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO_CASOS_CON_MOTIVOS_PENDIENTES]
	END	


SELECT X0.[Número del caso],X0.[Servicio Responsable],X0.[Programa Responsable]
,CASE WHEN X2.CODIGO IS NOT NULL THEN X2.CODIGO ELSE '-' END [Codigo de pendiente]
,CASE WHEN X2.CODIGO IS NOT NULL THEN X2.ORIGEN  ELSE '-' END [Motivo de pendiente nivel 1]
,CASE WHEN X2.CODIGO IS NOT NULL THEN X2.[ORIGEN SEGMENTADO] ELSE '-' END [Motivo de pendiente nivel 2]
,CASE WHEN X2.CODIGO IS NOT NULL THEN X2.[MOTIVOS A IMPLEMENTAR EN LA LISTA DE SALESFORCE] ELSE '-' END [Motivo de pendiente nivel 3]
INTO [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO_CASOS_CON_MOTIVOS_PENDIENTES]
FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].DBO.TBL_ASESOR_RESPONSABLE X0
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_CODIGO_PENDIENTE_DEL_CASO]X1
ON X0.[Número del caso] = X1.[Número del caso]
LEFT JOIN [CL_DATA].[dbo].[TBL_MOTIVO_PENDIENTE] X2
ON X1.Codigo = X2.Codigo
WHERE X0.[Estado General]='En proceso'


END



