-- PUNTUALIDAD, lote 0: calendario laboral en una #temporal (lo usa 30_destino.sql en lugar de
-- recorrer dia por dia dentro de FUNC_CH_FECHA_INICIO / FECHA_FIN / FECHA_VENCIMIENTO /
-- MINUTOS_VALIDOS_ENTRE_FECHAS, que consultaban TBL_CALENDARIO_DIAS_FESTIVOS en cada vuelta).
--
-- Dia NO laboral = sabado, domingo o dia de CL_MOVIL.dbo.TBL_CALENDARIO_DIAS_FESTIVOS (la misma
-- regla de las funciones). 1900-01-01 fue lunes: DATEDIFF % 7 = 5 sabado, 6 domingo (no depende
-- del idioma ni de DATEFIRST de la sesion).
-- idx = dias laborales acumulados hasta ese dia (inclusive); #calw lo invierte: idx -> el dia laboral.
-- Cobertura 2020-01-01 .. 2035-12-31; el codigo Python verifica que las fechas de los datos caigan dentro.
DROP TABLE IF EXISTS #cal
GO
DROP TABLE IF EXISTS #calw
GO

CREATE TABLE #cal (d date NOT NULL PRIMARY KEY, lab tinyint NOT NULL, idx int NOT NULL)
GO

WITH n AS (
	SELECT TOP (5844) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS i
	FROM sys.all_objects a CROSS JOIN sys.all_objects b
),
c AS (
	SELECT d = DATEADD(DAY, i, CAST('20200101' AS date)) FROM n
),
l AS (
	SELECT d,
		lab = CASE
			WHEN DATEDIFF(DAY, '19000101', d) % 7 >= 5 THEN 0
			WHEN EXISTS (SELECT 1 FROM [CL_MOVIL].[dbo].[TBL_CALENDARIO_DIAS_FESTIVOS] f WHERE f.[DIA_FESTIVO] = d) THEN 0
			ELSE 1
		END
	FROM c
)
INSERT INTO #cal (d, lab, idx)
SELECT d, lab, SUM(CAST(lab AS int)) OVER (ORDER BY d ROWS UNBOUNDED PRECEDING)
FROM l
GO

CREATE TABLE #calw (idx int NOT NULL PRIMARY KEY, d date NOT NULL)
GO

INSERT INTO #calw (idx, d)
SELECT idx, d FROM #cal WHERE lab = 1
GO
