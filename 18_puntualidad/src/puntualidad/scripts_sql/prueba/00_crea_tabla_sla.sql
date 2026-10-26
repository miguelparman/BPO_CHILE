-- Modo prueba: TBL_SLA de prueba = clon exacto (columnas, tipos, nulabilidad) de la tabla real,
-- sin filas. Si ya existe no se toca.
IF OBJECT_ID(N'{{TBL_SLA}}', N'U') IS NULL
	SELECT TOP 0 * INTO {{TBL_SLA}} FROM {{TBL_SLA_REAL}}
