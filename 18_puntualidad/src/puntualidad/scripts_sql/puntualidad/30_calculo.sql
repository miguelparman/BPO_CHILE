-- PUNTUALIDAD, lote 2: calculo de las fechas y tiempos, por etapas (#t_fal -> #t_ven -> #t_fin ->
-- #t_min), cada una una tabla temporal con clave rid. En una sola sentencia SQL Server supera el
-- limite de complejidad de expresiones (error 8632).
--
-- Reemplaza a los ALTER TABLE ADD + UPDATE del .dtsx, que llamaban fila por fila a las funciones
-- escalares con WHILE de SERVICIOS_GENERALES. Aqui se resuelven con aritmetica de calendario
-- (#cal / #calw, ver 10_calendario.sql). Equivalencias (las funciones originales siguen en el
-- servidor y son la referencia de la prueba de equivalencia):
--
--   INICIO(x)    x fuera de horario -> 09:00 del dia habil que corresponde; sabado/domingo/festivo ->
--                09:00 del siguiente dia habil (el WHILE avanza de a un dia).
--   FIN(x)       analogo con 18:00 y hacia atras antes de las 08:30 (el lunes retrocede al viernes).
--   VENCIMIENTO  K = minutos / 540 dias habiles de 9 h, saltando no laborales con #calw; la hora
--                se conserva solo si no se cruzo ningun dia no laboral (si se cruza, queda 09:00).
--   MINUTOS      DATEDIFF - 870 * dias habiles - 1440 * dias no habiles (+870), donde los dias
--                se cuentan por diferencia de acumulados de #cal en vez de iterarlos.
DROP TABLE IF EXISTS #t_fal
GO
DROP TABLE IF EXISTS #t_ven
GO
DROP TABLE IF EXISTS #t_fin
GO
DROP TABLE IF EXISTS #t_min
GO

-- FECHA APERTURA LABORAL = FUNC_CH_FECHA_INICIO([Fecha/Hora de apertura])
SELECT b.rid, fal.[FECHA APERTURA LABORAL]
INTO #t_fal
FROM #base b
CROSS APPLY (SELECT ap = b.[Fecha/Hora de apertura]) i
CROSS APPLY (SELECT h = DATEPART(HOUR, i.ap), mi = DATEPART(MINUTE, i.ap), dt = CAST(CAST(i.ap AS date) AS datetime), dw = DATEDIFF(DAY, '19000101', CAST(i.ap AS date)) % 7) a1
CROSS APPLY (SELECT f1 = CASE
		WHEN a1.h >= 18 AND a1.dw <> 4 THEN DATEADD(HOUR, 9, DATEADD(DAY, 1, a1.dt))
		WHEN a1.h <= 7 OR (a1.h = 8 AND a1.mi < 30) THEN DATEADD(HOUR, 9, a1.dt)
		WHEN a1.h >= 18 THEN DATEADD(HOUR, 9, DATEADD(DAY, 3, a1.dt))
		ELSE i.ap END) a2
OUTER APPLY (SELECT lab = c.lab, ix = c.idx FROM #cal c WHERE c.d = CAST(a2.f1 AS date)) a3
OUTER APPLY (SELECT nd = w.d FROM #calw w WHERE w.idx = a3.ix + 1) a4
CROSS APPLY (SELECT [FECHA APERTURA LABORAL] = CASE WHEN a3.lab = 0 THEN DATEADD(HOUR, 9, CAST(a4.nd AS datetime)) ELSE a2.f1 END) fal
GO
CREATE UNIQUE CLUSTERED INDEX ix_t_fal ON #t_fal (rid)
GO

-- FECHA DE VENCIMIENTO
--   'Laboral'    = FUNC_CH_FECHA_VENCIMIENTO([FECHA APERTURA LABORAL], [SLA HORA])
--                  (FUNC_CH_FECHA_INICIO de una fecha ya laboral no la modifica)
--   'Calendario' = FUNC_CH_FECHA_INICIO(DATEADD(HOUR, [SLA HORA], [FECHA APERTURA LABORAL]))
SELECT b.rid, f.[FECHA APERTURA LABORAL], ven.[FECHA DE VENCIMIENTO]
INTO #t_ven
FROM #base b
JOIN #t_fal f ON f.rid = b.rid
CROSS APPLY (SELECT
		 dif = DATEDIFF(MINUTE, CAST(f.[FECHA APERTURA LABORAL] AS time), CAST('18:00:00' AS time))
		,m0 = CAST(CAST(b.[SLA HORA] AS decimal(12,2)) * 60 AS int)
		,dfn = CAST(f.[FECHA APERTURA LABORAL] AS date)) v1
OUTER APPLY (SELECT ixf = c.idx FROM #cal c WHERE c.d = v1.dfn) v2
CROSS APPLY (SELECT u = CASE WHEN v1.m0 > v1.dif THEN 1 ELSE 0 END) v3
CROSS APPLY (SELECT m1 = CASE WHEN v3.u = 1 THEN v1.m0 - v1.dif ELSE v1.m0 END) v4
CROSS APPLY (SELECT k = v4.m1 / 540, r = v4.m1 % 540, ix0 = v2.ixf + v3.u) v5
OUTER APPLY (SELECT d0 = w.d FROM #calw w WHERE w.idx = v5.ix0) v6
OUTER APPLY (SELECT dk = w.d FROM #calw w WHERE w.idx = v5.ix0 + v5.k) v7
CROSS APPLY (SELECT b0 = CASE WHEN v3.u = 1 THEN DATEADD(HOUR, 9, CAST(v6.d0 AS datetime)) ELSE f.[FECHA APERTURA LABORAL] END) v8
CROSS APPLY (SELECT ven = DATEADD(MINUTE, v5.r, CASE
		WHEN v5.k = 0 THEN v8.b0
		WHEN DATEDIFF(DAY, v6.d0, v7.dk) = v5.k THEN DATEADD(DAY, v5.k, v8.b0)
		ELSE DATEADD(HOUR, 9, CAST(v7.dk AS datetime)) END)) v9
CROSS APPLY (SELECT x = DATEADD(HOUR, b.[SLA HORA], f.[FECHA APERTURA LABORAL])) e0
CROSS APPLY (SELECT h = DATEPART(HOUR, e0.x), mi = DATEPART(MINUTE, e0.x), dt = CAST(CAST(e0.x AS date) AS datetime), dw = DATEDIFF(DAY, '19000101', CAST(e0.x AS date)) % 7) e1
CROSS APPLY (SELECT f1 = CASE
		WHEN e1.h >= 18 AND e1.dw <> 4 THEN DATEADD(HOUR, 9, DATEADD(DAY, 1, e1.dt))
		WHEN e1.h <= 7 OR (e1.h = 8 AND e1.mi < 30) THEN DATEADD(HOUR, 9, e1.dt)
		WHEN e1.h >= 18 THEN DATEADD(HOUR, 9, DATEADD(DAY, 3, e1.dt))
		ELSE e0.x END) e2
OUTER APPLY (SELECT lab = c.lab, ix = c.idx FROM #cal c WHERE c.d = CAST(e2.f1 AS date)) e3
OUTER APPLY (SELECT nd = w.d FROM #calw w WHERE w.idx = e3.ix + 1) e4
CROSS APPLY (SELECT ven = CASE WHEN e3.lab = 0 THEN DATEADD(HOUR, 9, CAST(e4.nd AS datetime)) ELSE e2.f1 END) e5
CROSS APPLY (SELECT [FECHA DE VENCIMIENTO] = CASE WHEN b.[Calendario/Laboral (ARBOL)] = 'Laboral' THEN v9.ven ELSE e5.ven END) ven
GO
CREATE UNIQUE CLUSTERED INDEX ix_t_ven ON #t_ven (rid)
GO

-- FUNC_CH_FECHA_FIN([Fecha de cierre general])
SELECT b.rid, g5.fin
INTO #t_fin
FROM #base b
CROSS APPLY (SELECT ce = b.[Fecha de cierre general]) i
CROSS APPLY (SELECT h = DATEPART(HOUR, i.ce), mi = DATEPART(MINUTE, i.ce), dt = CAST(CAST(i.ce AS date) AS datetime), dw = DATEDIFF(DAY, '19000101', CAST(i.ce AS date)) % 7) g1
CROSS APPLY (SELECT f1 = CASE
		WHEN g1.h >= 18 THEN DATEADD(HOUR, 18, g1.dt)
		WHEN (g1.h <= 7 OR (g1.h = 8 AND g1.mi < 30)) AND g1.dw <> 0 THEN DATEADD(HOUR, 18, DATEADD(DAY, -1, g1.dt))
		WHEN g1.h <= 7 OR (g1.h = 8 AND g1.mi < 30) THEN DATEADD(HOUR, 18, DATEADD(DAY, -3, g1.dt))
		ELSE i.ce END) g2
OUTER APPLY (SELECT lab = c.lab, ix = c.idx FROM #cal c WHERE c.d = CAST(g2.f1 AS date)) g3
OUTER APPLY (SELECT nd = w.d FROM #calw w WHERE w.idx = g3.ix + 1) g4
CROSS APPLY (SELECT fin = CASE WHEN g3.lab = 0 THEN DATEADD(HOUR, 18, CAST(g4.nd AS datetime)) ELSE g2.f1 END) g5
GO
CREATE UNIQUE CLUSTERED INDEX ix_t_fin ON #t_fin (rid)
GO

-- FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS
--   atencion  = ([FECHA APERTURA LABORAL], [Fecha de cierre general])
--   pendiente = ([FECHA DE VENCIMIENTO],   [Fecha de cierre general])
-- (el UPDATE posterior del .dtsx deja en 0 los negativos)
SELECT v.rid
	,[TIEMPO DE ATENCION (MINUTOS)] = CASE WHEN ma.minutos < 0 THEN 0 ELSE ma.minutos END
	,[TIEMPO DE PENDIENTE (MINUTOS)] = CASE WHEN mp.minutos < 0 THEN 0 ELSE mp.minutos END
INTO #t_min
FROM #t_ven v
JOIN #t_fin g5 ON g5.rid = v.rid
CROSS APPLY (SELECT s = v.[FECHA APERTURA LABORAL], s0 = CAST(v.[FECHA APERTURA LABORAL] AS date), d = DATEDIFF(MINUTE, v.[FECHA APERTURA LABORAL], g5.fin)) ma1
CROSS APPLY (SELECT n = CASE WHEN ma1.d >= 0 THEN ma1.d / 1440 END) ma2
OUTER APPLY (SELECT lab0 = c.lab, ix0 = c.idx FROM #cal c WHERE c.d = ma1.s0) ma3
OUTER APPLY (SELECT ixn = c.idx FROM #cal c WHERE c.d = DATEADD(DAY, ma2.n, ma1.s0)) ma4
CROSS APPLY (SELECT t = CASE WHEN ma1.d < 0 THEN 0 ELSE ma4.ixn - (ma3.ix0 - ma3.lab0) END) ma5
CROSS APPLY (SELECT nl = CASE WHEN ma1.d < 0 THEN 0 ELSE ma2.n + 1 - ma5.t END) ma6
CROSS APPLY (SELECT minutos = CASE
		WHEN CAST(ma1.s AS time) > CAST(g5.fin AS time) AND ma3.lab0 = 1 THEN ma1.d - 870 * ma5.t - 1440 * ma6.nl
		WHEN CAST(ma1.s AS time) > CAST(g5.fin AS time) THEN ma1.d + 870
		ELSE ma1.d - 870 * ma5.t - 1440 * ma6.nl + 870 END) ma
CROSS APPLY (SELECT s = v.[FECHA DE VENCIMIENTO], s0 = CAST(v.[FECHA DE VENCIMIENTO] AS date), d = DATEDIFF(MINUTE, v.[FECHA DE VENCIMIENTO], g5.fin)) mp1
CROSS APPLY (SELECT n = CASE WHEN mp1.d >= 0 THEN mp1.d / 1440 END) mp2
OUTER APPLY (SELECT lab0 = c.lab, ix0 = c.idx FROM #cal c WHERE c.d = mp1.s0) mp3
OUTER APPLY (SELECT ixn = c.idx FROM #cal c WHERE c.d = DATEADD(DAY, mp2.n, mp1.s0)) mp4
CROSS APPLY (SELECT t = CASE WHEN mp1.d < 0 THEN 0 ELSE mp4.ixn - (mp3.ix0 - mp3.lab0) END) mp5
CROSS APPLY (SELECT nl = CASE WHEN mp1.d < 0 THEN 0 ELSE mp2.n + 1 - mp5.t END) mp6
CROSS APPLY (SELECT minutos = CASE
		WHEN CAST(mp1.s AS time) > CAST(g5.fin AS time) AND mp3.lab0 = 1 THEN mp1.d - 870 * mp5.t - 1440 * mp6.nl
		WHEN CAST(mp1.s AS time) > CAST(g5.fin AS time) THEN mp1.d + 870
		ELSE mp1.d - 870 * mp5.t - 1440 * mp6.nl + 870 END) mp
GO
CREATE UNIQUE CLUSTERED INDEX ix_t_min ON #t_min (rid)
GO
