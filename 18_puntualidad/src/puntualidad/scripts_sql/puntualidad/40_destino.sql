-- PUNTUALIDAD, lote 3: arma la tabla final con UN solo SELECT ... INTO: mismas columnas, mismo orden
-- y mismos tipos que el original (DROP + SELECT INTO + 11 x ALTER TABLE ADD / UPDATE).
-- Los UPDATE del .dtsx pasan a ser las expresiones de abajo, con la misma logica CASE.
-- Todo va en la transaccion del loader: si algo falla, la tabla anterior queda intacta.
DROP TABLE IF EXISTS {{TBL_PUNTUALIDAD}}
GO

SELECT
	  b.[Número del caso]
	 ,b.[Estado general]
	 ,b.[Fecha/Hora de apertura]
	 ,b.[Fecha de cierre general]
	 ,b.[Línea de negocio]
	 ,b.[Motivo de contacto]
	 ,b.[Tipología]
	 ,b.[Subtipología]
	 ,b.[Coordinador Cartera]
	 ,b.[Asesor Cartera]
	 ,b.[Origen]
	 ,b.[GRUPO DOMINIO]
	 ,b.[Motivos del estado]
	 ,b.[Vista final]
	 ,b.[Tipo del caso]
	 ,b.[No. identificación fiscal]
	 ,b.[Nombre del cliente]
	 ,b.[Linea de negocio general]
	 ,b.[Asesor Responsable]
	 ,b.[Asesor Responsable DNI]
	 ,b.[Coordinador Responsable DNI]
	 ,b.[Estado]
	 ,b.[ESTADO PRESENTACION]
	 ,b.[ESTADO CASO PADRE]
	 ,b.[ESTADO (ARBOL)]
	 ,b.[SLA (ARBOL)]
	 ,b.[Día/Hora (ARBOL)]
	 ,b.[Calendario/Laboral (ARBOL)]
	 ,b.[ESTADO ARBOL SLA]
	 ,b.[SLA HORA]
	 ,b.[INDICADOR GENERAL]
	 ,b.[ESTADO FINAL]
	,v.[FECHA APERTURA LABORAL]
	,v.[FECHA DE VENCIMIENTO]
	,CAST(CASE
		WHEN b.[Estado general] = 'En proceso' and b.[Fecha de cierre general] <= v.[FECHA DE VENCIMIENTO] THEN 'DENTRO DE PLAZO'
		WHEN b.[Fecha de cierre general] > v.[FECHA DE VENCIMIENTO] THEN 'NO CUMPLE'
		ELSE 'CUMPLE'
	 END AS NVARCHAR(20)) [ESTADO CUMPLIMIENTO]
	,CAST(CASE
		WHEN b.[Estado general] = 'En proceso' and b.[Fecha de cierre general] <= v.[FECHA DE VENCIMIENTO] THEN 'DENTRO DE PLAZO'
		WHEN b.[Estado general] = 'En proceso' and b.[Fecha de cierre general] > v.[FECHA DE VENCIMIENTO] THEN 'VENCIDO'
		WHEN b.[Fecha de cierre general] > v.[FECHA DE VENCIMIENTO] THEN 'ATENDIDO FUERA DE PLAZO'
		ELSE 'ATENDIDO DENTRO DE PLAZO' + CHAR(9)  -- el literal del original termina en un tabulador
	 END AS NVARCHAR(25)) [INDICADOR PLAZO DE ATENCION]
	,m.[TIEMPO DE ATENCION (MINUTOS)]
	,CAST(TRY_CAST(m.[TIEMPO DE ATENCION (MINUTOS)] AS decimal(10,2))/60 AS DECIMAL(10,2)) [TIEMPO DE ATENCION (HORAS)]
	,m.[TIEMPO DE PENDIENTE (MINUTOS)]
	,CAST((m.[TIEMPO DE PENDIENTE (MINUTOS)]*1.00)/60 AS DECIMAL(10,2)) [TIEMPO DE PENDIENTE (HORAS)]
	,CAST(CASE
		WHEN b.[Estado general] = 'En proceso' THEN 'No atendido'
		WHEN v.[FECHA APERTURA LABORAL] = b.[Fecha de cierre general] THEN 'Atendido mismo dia'
		ELSE 'Atendido diferente dia'
	 END AS NVARCHAR(25)) [DIA DE ATENCION]
	,CAST(CASE
		WHEN DAY(v.[FECHA DE VENCIMIENTO]) <= 7 THEN 'SEMANA 01'
		WHEN DAY(v.[FECHA DE VENCIMIENTO]) <= 14 THEN 'SEMANA 02'
		WHEN DAY(v.[FECHA DE VENCIMIENTO]) <= 21 THEN 'SEMANA 03'
		ELSE 'SEMANA 04'
	 END AS NVARCHAR(25)) [FECHA DE VENCIMIENTO SEMANA]
	,CAST(CASE
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 1 THEN '1.- Mismo dia'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 2 THEN '2.- 1 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 3 THEN '3.- 2 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 4 THEN '4.- 3 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 5 THEN '5.- 4 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 6 THEN '6.- 5 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 7 THEN '7.- 6 Día'
		WHEN DATEDIFF(D, b.[Fecha/Hora de apertura], b.[Fecha de cierre general]) < 8 THEN '8.- 1 Semana'
		ELSE '9.- + Semana'
	 END AS NVARCHAR(25)) [Rango]
INTO
	{{TBL_PUNTUALIDAD}}
FROM
	#base b
JOIN #t_ven v ON v.rid = b.rid
JOIN #t_min m ON m.rid = b.rid
GO

-- Las columnas que el original agregaba con ALTER TABLE ... ADD quedan NULL; SELECT INTO deduce
-- NOT NULL de un CASE con solo literales. Se restablece para que el esquema sea el mismo.
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [FECHA APERTURA LABORAL] DATETIME NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [FECHA DE VENCIMIENTO] DATETIME NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [ESTADO CUMPLIMIENTO] NVARCHAR(20) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [INDICADOR PLAZO DE ATENCION] NVARCHAR(25) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [TIEMPO DE ATENCION (MINUTOS)] INT NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [TIEMPO DE ATENCION (HORAS)] DECIMAL(10,2) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [TIEMPO DE PENDIENTE (MINUTOS)] INT NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [TIEMPO DE PENDIENTE (HORAS)] DECIMAL(10,2) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [DIA DE ATENCION] NVARCHAR(25) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [FECHA DE VENCIMIENTO SEMANA] NVARCHAR(25) NULL
GO
ALTER TABLE {{TBL_PUNTUALIDAD}} ALTER COLUMN [Rango] NVARCHAR(25) NULL
GO
