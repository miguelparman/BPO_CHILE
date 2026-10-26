-- Las fechas de los casos deben caer dentro del calendario de #cal (2020-01-01 .. 2035-12-31),
-- con un anio de margen al final para los vencimientos. Si no, el calculo daria NULL en silencio:
-- se aborta y la transaccion deshace todo.
IF EXISTS (
	SELECT 1 FROM #base
	WHERE [Fecha/Hora de apertura] < '20200102' OR [Fecha/Hora de apertura] >= '20341231'
	   OR [Fecha de cierre general] < '20200102' OR [Fecha de cierre general] >= '20341231'
)
	THROW 50001, 'Hay fechas de apertura o cierre fuera del calendario laboral (2020-01-02 .. 2034-12-30). Ampliar 10_calendario.sql.', 1
GO
