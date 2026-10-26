-- Decision del usuario (2026-10-26): se conserva el valor REAL del SLA. El Excel trae 13,5 horas en 6 filas y
-- el .dtsx las dejaba en 14 al insertar numeric(10,2) en una columna int. TBL_SLA.SLA pasa a decimal(10,2).
-- Es idempotente: si ya es decimal no hace nada. Va dentro de la transaccion de la carga (si algo falla se
-- deshace). No hay indices ni restricciones sobre la columna, y las vistas VIEW_SLA_* no tienen SCHEMABINDING.
IF EXISTS (
	SELECT 1 FROM [CL_ANALISIS].sys.columns c
	WHERE c.object_id = OBJECT_ID(N'{{TBL_SLA}}') AND c.name = N'SLA' AND TYPE_NAME(c.system_type_id) = N'int'
)
	ALTER TABLE {{TBL_SLA}} ALTER COLUMN [SLA] DECIMAL(10,2) NULL
