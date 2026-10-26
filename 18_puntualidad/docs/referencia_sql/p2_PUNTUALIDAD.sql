DROP TABLE IF EXISTS [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
GO

SELECT 
	 x0.[Número del caso]
	,x0.[Estado general]
	,x0.[Fecha/Hora de apertura]
	,x0.[Fecha de cierre general]
	,x0.[Línea de negocio]
	,x0.[Motivo de contacto]
	,x0.Tipología
	,x0.Subtipología
	,x0.[Coordinador Cartera]
	,x0.[Asesor Cartera]
	,x0.Origen
	,x0.[GRUPO DOMINIO]
	,x0.[Motivos del estado]
	,x0.[Vista final]
	,x0.[Tipo del caso]
	,x0.[No. identificación fiscal]
	,x0.[Nombre del cliente]
	,x0.[Linea de negocio general]
	,x0.[Asesor Responsable]
	--
	,x0.[Asesor Responsable DNI]
	,x0.[Coordinador Responsable DNI]
	--
	,x0.Estado
	,x0.[ESTADO PRESENTACION]
	,x0.[ESTADO CASO PADRE]
	,CASE
		WHEN x1.Estado IS NOT NULL THEN x1.Estado
		WHEN x2.Estado IS NOT NULL THEN x2.Estado
		WHEN x3.Estado IS NOT NULL THEN x3.Estado
		ELSE NULL
	END [ESTADO (ARBOL)]
	,CASE
		WHEN x1.SLA IS NOT NULL THEN x1.SLA
		WHEN x2.SLA IS NOT NULL THEN x2.SLA
		WHEN x3.SLA IS NOT NULL THEN x3.SLA
		ELSE 1
	END [SLA (ARBOL)]
	,CASE
		WHEN x1.[Día/Hora] IS NOT NULL THEN x1.[Día/Hora]
		WHEN x2.[Día/Hora] IS NOT NULL THEN x2.[Día/Hora]
		WHEN x3.[Día/Hora] IS NOT NULL THEN x3.[Día/Hora]
		ELSE 'Dias'
	END [Día/Hora (ARBOL)]
	,CASE
		WHEN x1.[Calendario/Laboral] IS NOT NULL THEN x1.[Calendario/Laboral]
		WHEN x2.[Calendario/Laboral] IS NOT NULL THEN x2.[Calendario/Laboral]
		WHEN x3.[Calendario/Laboral] IS NOT NULL THEN x3.[Calendario/Laboral]
		ELSE 'Calendario'
	END [Calendario/Laboral (ARBOL)]
	,CASE
		WHEN x1.Estado IS NOT NULL THEN 'CON SLA'
		WHEN x2.Estado IS NOT NULL THEN 'CON SLA'
		WHEN x3.Estado IS NOT NULL THEN 'CON SLA'
		ELSE 'NO APLICA'
	END [ESTADO ARBOL SLA]
	,CASE
		WHEN x1.[Calendario/Laboral] = 'Calendario' THEN x1.SLA*24
		WHEN x1.[Calendario/Laboral] = 'Laboral' AND x1.[Día/Hora] = 'Horas' THEN x1.SLA
		WHEN x1.[Calendario/Laboral] = 'Laboral' THEN x1.SLA*9
		WHEN x2.[Calendario/Laboral] = 'Calendario' THEN x2.SLA*24
		WHEN x2.[Calendario/Laboral] = 'Laboral' AND x2.[Día/Hora] = 'Horas' THEN x2.SLA
		WHEN x2.[Calendario/Laboral] = 'Laboral' THEN x2.SLA*9
		WHEN x3.[Calendario/Laboral] = 'Calendario' THEN x3.SLA*24
		WHEN x3.[Calendario/Laboral] = 'Laboral' AND x3.[Día/Hora] = 'Horas' THEN x3.SLA
		WHEN x3.[Calendario/Laboral] = 'Laboral' THEN x3.SLA*9
		ELSE 24
	END [SLA HORA]
	,CASE
		WHEN [Estado general] = 'En proceso' THEN 'NO ATENDIDO'
		ELSE 'ATENDIDO' 
	END [INDICADOR GENERAL]
	,CASE
		WHEN [Estado general] = 'En proceso' THEN 'PENDIENTE'
		ELSE 'ATENDIDO' 
	END [ESTADO FINAL]
INTO 
	[CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
FROM 
	CL_VISTAS.dbo.VIEW_FACT_SEGUIMIENTO_VOL_GENERAL x0
LEFT JOIN
	[CL_ANALISIS].[dbo].[VIEW_SLA_4TIP] x1
ON
	x1.[Línea de Negocio] = x0.[Linea de negocio general]
	AND x1.[Motivo de contacto] = x0.[Motivo de contacto]
	AND x1.Tipología = x0.Tipología
	AND x1.Subtipología = x0.Subtipología
LEFT JOIN
	[CL_ANALISIS].[dbo].[VIEW_SLA_3TIP] x2
ON
	x2.[Motivo de contacto] = x0.[Motivo de contacto]
	AND x2.Tipología = x0.Tipología
	AND x2.Subtipología = x0.Subtipología
LEFT JOIN
	[CL_ANALISIS].[dbo].[VIEW_SLA_1TIP] x3
ON
	x3.[Motivo de contacto] = x0.[Motivo de contacto]
WHERE
	CAST([Fecha/Hora de apertura] AS date) >= '2025-08-01'
GO
	--AND [Número del caso] = '13494768'

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [FECHA APERTURA LABORAL] DATETIME
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [FECHA APERTURA LABORAL] = [SERVICIOS_GENERALES].[dbo].[FUNC_CH_FECHA_INICIO]([Fecha/Hora de apertura])
WHERE [FECHA APERTURA LABORAL] IS NULL
GO

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [FECHA DE VENCIMIENTO] DATETIME
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [FECHA DE VENCIMIENTO] = 
								CASE
									WHEN [Calendario/Laboral (ARBOL)]  = 'Laboral' THEN [SERVICIOS_GENERALES].[dbo].[FUNC_CH_FECHA_VENCIMIENTO]([FECHA APERTURA LABORAL],[SLA HORA])
									ELSE [SERVICIOS_GENERALES].[dbo].[FUNC_CH_FECHA_INICIO] (DATEADD(HOUR,[SLA HORA],[FECHA APERTURA LABORAL]))
								END					
WHERE [FECHA DE VENCIMIENTO] IS NULL
GO

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [ESTADO CUMPLIMIENTO] NVARCHAR(20)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [ESTADO CUMPLIMIENTO] = 
							CASE
								WHEN [Estado general] = 'En proceso' and [Fecha de cierre general] <= [FECHA DE VENCIMIENTO] THEN 'DENTRO DE PLAZO'
								WHEN [Fecha de cierre general] > [FECHA DE VENCIMIENTO] THEN 'NO CUMPLE'
								ELSE 'CUMPLE'
							END 
WHERE [ESTADO CUMPLIMIENTO] IS NULL
GO
--
ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [INDICADOR PLAZO DE ATENCION] NVARCHAR(25)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [INDICADOR PLAZO DE ATENCION] = 
							CASE
								WHEN [Estado general] = 'En proceso' and [Fecha de cierre general] <= [FECHA DE VENCIMIENTO] THEN 'DENTRO DE PLAZO'
								WHEN [Estado general] = 'En proceso' and [Fecha de cierre general] > [FECHA DE VENCIMIENTO] THEN 'VENCIDO'
								WHEN [Fecha de cierre general] > [FECHA DE VENCIMIENTO] THEN 'ATENDIDO FUERA DE PLAZO'
								ELSE 'ATENDIDO DENTRO DE PLAZO	'
							END 
WHERE [INDICADOR PLAZO DE ATENCION] IS NULL
GO
--

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [TIEMPO DE ATENCION (MINUTOS)] INT
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [TIEMPO DE ATENCION (MINUTOS)] = [SERVICIOS_GENERALES].[dbo].[FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS]([FECHA APERTURA LABORAL],[Fecha de cierre general])
WHERE [TIEMPO DE ATENCION (MINUTOS)] IS NULL
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] 
SET [TIEMPO DE ATENCION (MINUTOS)] = 0
WHERE [TIEMPO DE ATENCION (MINUTOS)] <0
GO


ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [TIEMPO DE ATENCION (HORAS)] DECIMAL (10,2)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [TIEMPO DE ATENCION (HORAS)]  = TRY_CAST([TIEMPO DE ATENCION (MINUTOS)] AS decimal(10,2))/60
WHERE [TIEMPO DE ATENCION (HORAS)] IS NULL
GO

-- TIEMPO DE PENDIENTE
ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [TIEMPO DE PENDIENTE (MINUTOS)] INT
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [TIEMPO DE PENDIENTE (MINUTOS)] = [SERVICIOS_GENERALES].[dbo].[FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS]([FECHA DE VENCIMIENTO],[Fecha de cierre general])
WHERE [TIEMPO DE PENDIENTE (MINUTOS)] IS NULL
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] 
SET [TIEMPO DE PENDIENTE (MINUTOS)] = 0
WHERE [TIEMPO DE PENDIENTE (MINUTOS)] <0
GO

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [TIEMPO DE PENDIENTE (HORAS)] DECIMAL (10,2)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [TIEMPO DE PENDIENTE (HORAS)]  = ([TIEMPO DE PENDIENTE (MINUTOS)]*1.00)/60
WHERE [TIEMPO DE PENDIENTE (HORAS)] IS NULL
GO

ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [DIA DE ATENCION] NVARCHAR(25)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [DIA DE ATENCION] = CASE
							WHEN [Estado general] = 'En proceso' THEN 'No atendido'
							WHEN [FECHA APERTURA LABORAL] = [Fecha de cierre general] THEN 'Atendido mismo dia'
							ELSE 'Atendido diferente dia'
						END
WHERE [DIA DE ATENCION] IS NULL
GO


-- SEMANA FECHA DE VENCIMIENTO
ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [FECHA DE VENCIMIENTO SEMANA] NVARCHAR(25)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [FECHA DE VENCIMIENTO SEMANA] = CASE
										WHEN DAY([FECHA DE VENCIMIENTO]) <= 7 THEN 'SEMANA 01'
										WHEN DAY([FECHA DE VENCIMIENTO]) <= 14 THEN 'SEMANA 02'
										WHEN DAY([FECHA DE VENCIMIENTO]) <= 21 THEN 'SEMANA 03'
										ELSE 'SEMANA 04'
									END
WHERE [FECHA DE VENCIMIENTO SEMANA] IS NULL
GO

--RANGO
ALTER TABLE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD] ADD [Rango] NVARCHAR(25)
GO

UPDATE [CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]
SET [Rango] = CASE
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 1 THEN '1.- Mismo dia'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 2 THEN '2.- 1 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 3 THEN '3.- 2 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 4 THEN '4.- 3 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 5 THEN '5.- 4 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 6 THEN '6.- 5 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 7 THEN '7.- 6 Día'
		WHEN DATEDIFF(D, [Fecha/Hora de apertura], [Fecha de cierre general]) < 8 THEN '8.- 1 Semana'
		ELSE '9.- + Semana'
		END
WHERE [Rango] IS NULL
GO
