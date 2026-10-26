-- PUNTUALIDAD, lote 1: la misma consulta del .dtsx, pero a una #temporal y leyendo las
-- vistas VIEW_SLA_4TIP/3TIP/1TIP en linea (su definicion, sobre {{TBL_SLA}}) para poder
-- apuntar a la tabla de prueba. Las columnas, los CASE y los JOIN son los del original.
-- Desempate: las vistas SLA numeran con ROW_NUMBER() ordenando por las mismas columnas de la
-- particion, asi que si un grupo tiene filas con SLA distintos (hoy 4 grupos de VIEW_SLA_3TIP,
-- p.ej. 'Vigente' y 'No vigente') la fila 1 no esta definida y cambia con el plan de ejecucion.
-- Aqui se fija: 'Vigente' primero, que es lo que SSIS dejo en todos los casos observados.
DROP TABLE IF EXISTS #base
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
	,ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) [rid]
INTO 
	#base
FROM 
	{{FUENTE}} x0
LEFT JOIN
	{{SLA_4TIP}} x1
ON
	x1.[Línea de Negocio] = x0.[Linea de negocio general]
	AND x1.[Motivo de contacto] = x0.[Motivo de contacto]
	AND x1.Tipología = x0.Tipología
	AND x1.Subtipología = x0.Subtipología
LEFT JOIN
	{{SLA_3TIP}} x2
ON
	x2.[Motivo de contacto] = x0.[Motivo de contacto]
	AND x2.Tipología = x0.Tipología
	AND x2.Subtipología = x0.Subtipología
LEFT JOIN
	{{SLA_1TIP}} x3
ON
	x3.[Motivo de contacto] = x0.[Motivo de contacto]
WHERE
	CAST([Fecha/Hora de apertura] AS date) >= '2025-08-01'
GO

CREATE UNIQUE CLUSTERED INDEX ix_base_rid ON #base (rid)
GO
