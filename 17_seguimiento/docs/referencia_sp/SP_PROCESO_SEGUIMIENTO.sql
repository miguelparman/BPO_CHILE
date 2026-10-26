CREATE PROCEDURE [dbo].[SP_PROCESO_SEGUIMIENTO]

AS
BEGIN

SET DATEFORMAT YMD
SET LANGUAGE SPANISH

DECLARE @HOY DATETIME, @periodo_actual  INT
SET @HOY = GETDATE()
SET @periodo_actual = YEAR(@HOY)* 100 + MONTH(@HOY)

--------------------------------------------------------------------------------------------------------------------------------------------------------------

    IF EXISTS 
	(
		SELECT * 
		FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
		WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_1_NUEVO' AND TABLE_SCHEMA='DBO'
	)
	BEGIN
		DROP TABLE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]
	END		


SET DATEFORMAT DMY


-- OPTIMIZACION 2026-10-26 (17_seguimiento) A: FECHAS_VALIDAS se calcula UNA vez por fecha distinta
-- (antes 2 veces por caso, fila por fila y en un solo hilo). Misma funcion => mismo resultado.
DROP TABLE IF EXISTS #FECHAS_QUIEBRE;
SELECT F.[Fecha], [BBDD_GENERAL].[dbo].[FECHAS_VALIDAS](F.[Fecha]) AS [Fecha quiebre]
INTO #FECHAS_QUIEBRE
FROM (SELECT DISTINCT CAST([Fecha de creación de Comentario del caso] AS DATE) AS [Fecha]
      FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO_FRACTALIA]
      WHERE [Fecha de creación de Comentario del caso] IS NOT NULL) F;
CREATE UNIQUE CLUSTERED INDEX IX_FECHAS_QUIEBRE ON #FECHAS_QUIEBRE ([Fecha]);

SELECT 
X0.[Número del caso]
,X0.[Número de caso principal]	
,X0.[Sistema legado]    
,X0.[Identificador FS Local]
,CASE WHEN X0.[cantidad] IS NULL THEN 1 
	  WHEN X0.[cantidad] ='' THEN 1
	  WHEN X0.[cantidad] ='0' THEN 1
	  WHEN X0.[Tipología] ='Averias Móvil' and X0.[cantidad] >10  THEN 10
	  ELSE CAST(X0.[cantidad] AS INT) END [Cantidad]
,X0.[Fecha/Hora de apertura]
,X0.[Fecha de registro en sistema legado] 
,X0. [Fecha Compromiso Cliente]
,X0.[Fecha de envío de cotización]
,X0.[Fecha de confirmación]
,X0.[Fecha de recepción] 
,X0.[Fecha/hora de resolución]
,X0.[Fecha/Hora de cierre] 
,X0.[Abierto] 
,X0.[Estado]
,X0.[Motivos del estado]
,X0.[Propietario del caso] 
,X0.[Asesor] 
,X0.[Asignado a] 
,X0.[No. identificación fiscal] 
,X0.[Id. del cliente legado] 
,X0.[Nombre del cliente] 
,X0.[Cliente principal] 
,X0.[Territorio]
,X0.[Subterritorio] 
,X0.[Sector]
,X0.[Segmento Global] 
,X0.[Subsegmento local] 
,X0.[Categoría del cliente] 
,X0.[Asunto]  
,CASE WHEN X0.[Tipo del caso] ='Caso Interno' THEN 'No'
	  WHEN X0.Confidencialidad = 1 THEN 'Si'
	  ELSE 'No' END [Confidencialidad]
,X0.[Motivo de contacto]  
,CASE WHEN X0.[Tipo del caso] ='Caso Interno' THEN X0.[Tipo Solicitud]
	  ELSE Tipología END [Tipología]
,CASE WHEN X0.[Tipo del caso] ='Caso Interno' THEN X1.[Subtipo de solicitud]							 
	  ELSE Subtipología	END	[Subtipología] 
,X0.[Línea de negocio] 
,X0.[Familia de Producto | Servicio] 
,X0.[Descripción de producto] 
,X0.[Territorio del caso] 
,CASE WHEN X7.[Origen del caso] IS NOT NULL THEN X7.[Origen del caso] 
	  ELSE  X0.[Origen del caso] END [Origen del caso] 
,X0.[Última fecha/hora de modificación de caso]
,X0.[Última modificación de caso realizada por] 
,X0.[Motivo de inconformidad] 
,X0.[Motivo de incumplimiento del ANS] 
,X0.[GICS número de circuito/teléfono] 
,X0.[Creado por] 
,X0.[Nombre de contacto] 
,X0.[Departamento]
,X0.[Subsegmento Global]
,CASE WHEN [Línea de negocio] IN ('Móviles','Móvil','CHI_Móviles') THEN 'Móviles'
	  WHEN [Línea de negocio] IN ('Fija','Voz Fija','Servicios Multimedia (TV)','CHI_Servicios fijos') THEN 'Fija'
	  WHEN [Línea de negocio] <> '' THEN 'Otros'
	  END [Linea de negocio general]
,CASE WHEN X0.[Estado] IN ('Cancelado','Canceled') THEN 'Cancelado'
	  WHEN X0.[Estado] IN ('Rechazado') THEN 'Rechazado'
	  WHEN X0.[Estado] in ('Rechazado','Cerrado','Resuelto','Finalizado') THEN 'Finalizado'
	  ELSE 'En proceso' END [Estado general]
, X1.[Fecha de Solicitud Cliente]
,CASE WHEN X3.[Número del caso] IS NULL AND X4.[Número del caso] IS NULL THEN 'Caso sin comentario'
	  WHEN X4.[Número del caso] IS NOT NULL AND X3.[Número del caso] IS NULL THEN 'Si'
	  WHEN X4.[Número del caso] IS NOT NULL AND X3.[Número del caso] IS NOT NULL AND X4.[Fecha de creación de Comentario del caso]>=X3.[Fecha de creación de Comentario del caso] THEN 'Si' 
	  ELSE 'No'	END [Ultimo comentario pertenece Fractalia?]
,X4.[Comentarios del caso][Ultimo Comentario Fractalia]
,X4.[Fecha de creación de Comentario del caso][Ultima fecha de comentario Fractalia]
,X4.[Comentario del caso creado por][Creador último comentario Fractalia]
,DATEDIFF(DAY,CAST(X4.[Fecha de creación de Comentario del caso] AS DATE),CAST(@HOY AS DATE)) AS [Días al ultimo comentario Fractalia]
,FQ.[Fecha quiebre] AS [Fecha de quiebre comentario Fractalia]
,DATEDIFF(DD,FQ.[Fecha quiebre],CAST(@HOY AS DATE)) AS [Dias de quiebre comentario Fractalia]
,CASE WHEN [Fecha/hora de resolución] IS NOT NULL THEN DATEDIFF(DD,[Fecha/Hora de apertura],[Fecha/hora de resolución])
	  WHEN [Fecha/Hora de cierre] IS NOT NULL THEN DATEDIFF(DD,[Fecha/Hora de apertura],[Fecha/Hora de cierre])
	  ELSE DATEDIFF(DD,[Fecha/Hora de apertura],@HOY) END [Tiempo de atención]
,CASE WHEN [Fecha/hora de resolución] IS NOT NULL THEN [Fecha/hora de resolución]
	  WHEN [Fecha/Hora de cierre] IS NOT NULL THEN [Fecha/Hora de cierre]
	  WHEN [Estado] IN ('Cancelado', 'Cerrado', 'Resuelto') AND [Fecha/hora de resolución] IS NULL AND [Fecha/Hora de cierre] IS NULL THEN [Última fecha/hora de modificación de caso] 
	  ELSE  @HOY END [Fecha de cierre general]
,CASE WHEN X0.[Asunto] like '%PER-%' or X0.[Identificador FS Local] like '%PER-%' 
	  THEN 'SI' ELSE 'NO' END [# Oportunidad?]
,X0.[Tipo del caso] 
,CASE WHEN X2.[Número de caso principal] IS NOT NULL THEN X0.[Tipo del caso]+' padre'
	  WHEN X0.[Tipo del caso] IS NOT NULL or X0.[Tipo del caso] <>'' THEN X0.[Tipo del caso]
	  ELSE '-' END [Tipo del Caso Final]
,X0.[Tipo Solicitud]
,'Salesforce' AS [Fuente]
,@HOY  [Fecha de corte]
--, '' AS [Programa Responsable 2]
--, '' AS [Servicio Responsable 2]
,CASE WHEN X0.[Tipo del caso] ='Caso Interno' AND (X7.[Tipo del caso] in ('Caso Agrupador','Caso Comercial II') AND X7.Indicador='Todos hijos internos')
	  THEN 1 ELSE 0 END [Casos Excluidos]
,CASE WHEN X0.[Línea de negocio] IS NULL THEN NULL
	  WHEN X0.[Línea de negocio]='Datos' THEN 'DATOS'
	  WHEN X0.[Línea de negocio]='Servicios Multimedia (TV)' THEN 'MOVISTAR TV' 
	  ELSE 'VOZ' END [Tipo de Producto]
,CASE WHEN X0.[Descripción de producto] IS NULL THEN [Familia de Producto | Servicio]
	  WHEN X0.[Descripción de producto] IN ('Otros','No aplica') THEN X0.[Familia de Producto | Servicio]
	  WHEN X0.[Descripción de producto] IS NOT NULL  THEN X0.[Descripción de producto]
	  WHEN X0.[Familia de Producto | Servicio] IS NOT NULL THEN X0.[Familia de Producto | Servicio]
	  WHEN X0.[Línea de negocio]='Datos' THEN 'Conectividad de Datos (ADSL, MPLS, IP)'
	  WHEN X0.[Línea de negocio]='Voz Fija' THEN 'Servicios de Voz Fija'
	  ELSE X0.[Línea de negocio] END [Tipo de Subproducto]
,X0.[To Address][To Addres] -- agregado 24/08/23
,X0.[Correo Electronico Web]
,X0.[Correo Electrónico Contacto]
,X0.[Teléfono Contacto]
,X0.[Móvil Contacto]
INTO [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]		
FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] X0
LEFT JOIN [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS_B] X1
ON X0.[Número del caso] = X1.[Número del caso]
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_CASOS_PADRES] X2
ON X0.[Número del caso]=X2.[Número de caso principal]
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_CASOS_PADRES] X7
ON X0.[Número de caso principal]=X7.[Número de caso principal]
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO]  X3
ON  X0.[Número del caso]  = X3.[Número del caso]
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO_FRACTALIA] X4
ON  X0.[Número del caso]  = X4.[Número del caso]
LEFT JOIN #FECHAS_QUIEBRE FQ  -- OPTIMIZACION 2026-10-26 A
ON FQ.[Fecha] = CAST(X4.[Fecha de creación de Comentario del caso] AS DATE)
WHERE (X0.[Nombre del cliente] NOT LIKE '%FAROLITO%' OR X0.[Nombre del cliente] IS NULL)
AND X0.[Número del caso] NOT IN (SELECT [Número del caso] FROM [CL_TEMPORALES].[dbo].[TBL_CASOS_NO_CONSIDERAR])--AGREGADO 05/12/2024, PEDIDO DE ANDREA ERROR CLIENTE TRANSVE S A
		
UPDATE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]
SET [Linea de negocio general] = 
CASE WHEN [Tipo Solicitud] IN ('FACTURACIÓN MECANIZADA DATOS/TIC', 'FACTURACIÓN MECANIZADA VOZ', 'FACTURACIÓN MECANIZADA CABLE') THEN 'Fija'
     WHEN [Tipo Solicitud] = 'FACTURACIÓN MECANIZADA MOVIL' THEN 'Móviles' 
	 ELSE NULL END
WHERE [Linea de negocio general] IS NULL


--------------------------------------------------------------------------------------------------------------------------------------------------


	IF EXISTS 
		(
			SELECT * 
			FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_2_NUEVO' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_2_NUEVO]
	END	

SELECT 
X0.[Número del caso],
X0.[Número de caso principal],
X0.[Sistema legado],
X0.[Identificador FS Local],
CASE WHEN X6.[Asesor Responsable] IS NOT NULL THEN X6.[Asesor Responsable] ELSE 'Externo' END [Asesor Responsable],
CASE WHEN X6.[Asesor Responsable DNI] IS NOT NULL THEN X6.[Asesor Responsable DNI] ELSE 'Externo' END [Asesor Responsable DNI],
CASE WHEN X6.[Coordinador Responsable DNI] IS NOT NULL THEN X6.[Coordinador Responsable DNI] ELSE 'Externo' END [Coordinador Responsable DNI],
CASE WHEN X6.[Programa Responsable] IS NOT NULL THEN X6.[Programa Responsable] ELSE 'Externo' END [Programa Responsable],
CASE WHEN X6.[Servicio Responsable] IS NOT NULL THEN X6.[Servicio Responsable] ELSE 'Externo' END [Servicio Responsable],
CASE WHEN X6.Cruce IS NOT NULL THEN X6.Cruce ELSE NULL END Cruce,
X1.Etiqueta [Triada Actual],
X0.[Cantidad],
X0.[Fecha/Hora de apertura],
X0.[Fecha de registro en sistema legado] ,
X0.[Fecha Compromiso Cliente],
X0.[Fecha de envío de cotización],
X0.[Fecha de confirmación],
X0.[Fecha de recepción],
X0.[Fecha/hora de resolución],
X0.[Fecha/Hora de cierre],
X0.[Fecha de Solicitud Cliente],
X0.[Abierto],
X0.[Estado],
X0.[Motivos del estado],
X0.[Propietario del caso],
X0.[Asesor],
X0.[Asignado a] [Caso asignado a],
X0.[No. identificación fiscal],
X0.[Nombre del cliente],
X0.[Cliente principal],
X0.[Categoría del cliente],
X0.[Asunto],
X0.[Motivo de contacto],
X0.[Tipología],
X0.[Subtipología],
X0.[Línea de negocio],
X0.[Familia de Producto | Servicio],
X0.[Descripción de producto],
X0.[Territorio del caso],
X0.[Origen del caso],
X0.[Última fecha/hora de modificación de caso],
X0.[Última modificación de caso realizada por],
X0.[GICS número de circuito/teléfono],
X0.[Creado por],
CASE WHEN X6.[Asesor Creador DNI] IS NOT NULL THEN X6.[Asesor Creador DNI] ELSE 'Externo' END [Asesor Creador DNI],
CASE WHEN X6.[Coordinador Creador DNI] IS NOT NULL THEN X6.[Coordinador Creador DNI] ELSE 'Externo' END [Coordinador Creador DNI],
CASE WHEN X6.[Programa Creador] IS NOT NULL THEN X6.[Programa Creador] ELSE 'Externo' END [Programa del creador],
CASE WHEN X6.[Jefatura Creador] IS NOT NULL THEN X6.[Jefatura Creador] ELSE 'Externo' END [Jefatura Creador],
X0.[Nombre de contacto],
X0.[Departamento],
X0.Confidencialidad,
X0.[Linea de negocio general],
X0.[Estado general],
CASE WHEN X6.[Asesor Último DNI] IS NOT NULL THEN X6.[Asesor Último DNI] ELSE 'Externo'	END [Asesor Último DNI],
CASE WHEN X6.[Coordinador Último DNI] IS NOT NULL THEN X6.[Coordinador Último DNI] ELSE 'Externo' END [Coordinador Último DNI],
CASE WHEN X6.[Programa Último DNI] IS NOT NULL THEN X6.[Programa Último DNI] ELSE 'Externo' END [Programa Último DNI],
CASE WHEN X6.[Jefatura Último DNI] IS NOT NULL THEN X6.[Jefatura Último DNI] ELSE 'Externo' END [Jefatura Último DNI],
X0.[Ultimo Comentario Fractalia],
X0.[Ultima fecha de comentario Fractalia],
X0.[Fecha de quiebre comentario Fractalia],
X0.[Dias de quiebre comentario Fractalia],
X0.[Fecha de corte],
X0.[Días al ultimo comentario Fractalia],
X0.[Creador último comentario Fractalia],
X0.[Ultimo comentario Pertenece fractalia?],
X0.[Tiempo de atención],
CASE WHEN X0.[Estado general]<>'En proceso' THEN X0.[Fecha de cierre general] ELSE @HOY END [Fecha de cierre general],
X0.[# Oportunidad?],
CASE WHEN ( x6.[Servicio Responsable] = 'Móvil' and X0.Cantidad <= 6) OR (X6.[Servicio Responsable] in ('Fija','Altas') and X0.Cantidad <= 30 ) THEN 'Front'
	 WHEN ( X6.[Servicio Responsable] = 'Móvil' and X0.Cantidad > 6) OR (X6.[Servicio Responsable] in ('Fija','Altas') and X0.Cantidad > 30 ) THEN 'Back'
     ELSE '' END [Servicio por línea],
X0.[Tipo del Caso Final],
X0.[Tipo del caso],
CASE WHEN X1.RUT_SIN_DV IS NOT NULL THEN 'SI' ELSE 'NO' END [Con cartera], 
X0.[Casos Excluidos] ,
X0.[Segmento Global],
X0.[Subsegmento Global],
X0.[Subsegmento local],
X0.[Territorio],
X0.[Subterritorio],
X0.[Sector],
X0.[Tipo de Producto],
X0.[Tipo de Subproducto],
CASE WHEN X1.RUT_SIN_DV IS NOT NULL THEN X1.SEGMENTO ELSE NULL END [Tipo de cartera],
CASE WHEN X1.NOM_SM_TITULAR IS NOT NULL THEN X1.NOM_SM_TITULAR
     ELSE 'Externo' END [Asesor Cartera],
CASE WHEN X1.NOM_SUPERVISOR IS NOT NULL THEN X1.NOM_SUPERVISOR
     ELSE 'Externo' END [Coordinador Cartera],
CASE WHEN X1.SUB_SEGMENTO LIKE '%Triada%' THEN 'Triadas'
     WHEN X1.SUB_SEGMENTO NOT LIKE '%Triada%' AND X1.RUT IS NOT NULL THEN 'Carterizados'
     ELSE 'Externo' END [Jefatura Carterizado],
CASE WHEN X1.SUB_SEGMENTO LIKE '%Triada%' THEN 'Triadas Chile'
     WHEN X1.SUB_SEGMENTO NOT LIKE '%Triada%' AND X1.RUT IS NOT NULL THEN 'Carterizados Chile'
     ELSE 'Externo' END [Programa Carterizado],
CASE WHEN X0.Fuente IS NOT NULL THEN X0.Fuente END Fuente,
X0.[Tipo Solicitud],
CASE WHEN X7.[Codigo de pendiente] IS NOT NULL THEN X7.[Codigo de pendiente] ELSE '-' END [Codigo de pendiente],
CASE WHEN X7.[Codigo de pendiente] IS NOT NULL THEN X7.[Motivo de pendiente nivel 1] ELSE '-' END [Motivo de pendiente nivel 1],
CASE WHEN X7.[Codigo de pendiente] IS NOT NULL THEN X7.[Motivo de pendiente nivel 2] ELSE '-' END [Motivo de pendiente nivel 2],
CASE WHEN X7.[Codigo de pendiente] IS NOT NULL THEN X7.[Motivo de pendiente nivel 3] ELSE '-' END [Motivo de pendiente nivel 3],
X0.[To Addres],
X0.[Correo Electronico Web],
X0.[Correo Electrónico Contacto],
X0.[Teléfono Contacto],
X0.[Móvil Contacto]
INTO [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_2_NUEVO]		
FROM [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO] X0

--- CRUCE CON CARTERAS
LEFT JOIN CL_CARTERA.DBO.TBL_CARTERA_ACTUAL X1
on X0.[No. identificación fiscal] = REPLACE(X1.RUT,'-','')
LEFT JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X1A
ON X1.COD_DNI = X1A.DNI AND @periodo_actual=X1A.periodo

-- CRUCE CON ASESOR RESPONSABLE	
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ASESOR_RESPONSABLE] X6
ON X0.[Número del caso]=X6.[Número del caso]
LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO_CASOS_CON_MOTIVOS_PENDIENTES] X7
ON X0.[Número del caso]=X7.[Número del caso]


IF EXISTS 
		(
		SELECT * 
		FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
		WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_1_NUEVO' AND TABLE_SCHEMA='DBO'
	)
	BEGIN
		DROP TABLE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]
	END	
--------------------------------------------------------------------------------------------------------------------------------------------------

   IF EXISTS 
		(
			SELECT * 
			FROM [CL_SEGUIMIENTO_ACTUAL].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO' AND TABLE_SCHEMA='DBO'
		)
	BEGIN
		DROP TABLE [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]
	END	


-- OPTIMIZACION 2026-10-26 (17_seguimiento) B: los casos con estos [Valor nuevo] en el historial se leen UNA vez
-- (antes, dos EXISTS sobre TBL_HISTORIAL_CASOS por cada caso). Mismas condiciones => mismo resultado.
DROP TABLE IF EXISTS #HIST_VALOR_NUEVO;
SELECT DISTINCT [Número del caso], [Valor nuevo]
INTO #HIST_VALOR_NUEVO
FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_CASOS]
WHERE [Valor nuevo] IN ('CHI - Especialista SSPP PYME', 'CHI-Isla de Retención');
CREATE CLUSTERED INDEX IX_HIST_VALOR_NUEVO ON #HIST_VALOR_NUEVO ([Número del caso]);

SELECT X0.*
	,CASE
		-- Agregado el 05/03/26
		WHEN Asunto LIKE '% HITO %' AND Asunto LIKE 'Salesforce%' THEN 'Externo'

		WHEN Asunto LIKE '%![TERM%' escape '!' 	THEN 'Seguimiento termómetro'   -- [010]
		--WHEN Asunto LIKE '%promojun%' THEN 'Abordaje carterizado' 03/07/25
		WHEN Asunto LIKE '%![promo%' escape '!' THEN 'Abordaje carterizado'
		--agregado el 20 de mayo 
		WHEN Asunto LIKE '%![TENTADO%' escape '!' 	THEN 'Seguimiento tentados' -- [014]
		WHEN Asunto LIKE '%![BAJA POR MORA%' escape '!' 	THEN 'Seguimiento baja por mora' -- [015]
		
		--Retirado 20250926
		--WHEN [Creado por] = 'Johnny Lesster Cossio Perez' THEN 'Usuarios'
		--Agregado 20250926
		WHEN [Programa del creador] = 'Crosselling Chile' THEN 'Usuarios'
		--
		WHEN [Servicio Responsable] = 'Usuarios' THEN 'Usuarios'
		WHEN EXISTS (SELECT 1
					FROM #HIST_VALOR_NUEVO X1
					WHERE 1=1
					AND X0.[Número del caso] = X1.[Número del caso]
					AND X1.[Valor nuevo] = 'CHI - Especialista SSPP PYME'
					--Agregado 2025-09-26
					AND x0.[Propietario del caso] IN (
					'CHI - Especialista SSPP PYME'
					,'Eva Luz Cortez Rios'
					,'Luis Angel Martin Flores Lopez'
					,'Medaly Mirella Avila Alvarez'
					,'Magaly Del Pilar Balvin Gutierrez'
					--Agregado 2025-12-26
					,'Elena Cristina Chamorro Nuñez'
					--Agregado 20206-09-14
					,'Yadira Yahaira Guevara Cubillas'
					)
					--
				) THEN 'Especialista SSPP'

		--ADD 2025-09-26
		WHEN x0.[Programa Responsable] LIKE '% SSPP%' THEN 'Especialista SSPP'
		--

		WHEN [Jefatura Carterizado] IN ('Carterizados','Triadas') 
			AND [Servicio responsable] not in ('Externo','No identificados M2C') 
			AND (Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%' or Asunto LIKE '%011]%' or Asunto LIKE '%012]%' or Asunto LIKE '%013]%') 
				THEN CONCAT('Seguimiento de encuestas ',[Jefatura Carterizado])
		WHEN [Jefatura Carterizado] IN ('Carterizados','Triadas') 
			AND [Programa del creador] <> 'Externo' 
			AND (Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%'or Asunto LIKE '%011]%' or Asunto LIKE '%012]%' or Asunto LIKE '%013]%') 
				THEN CONCAT('Seguimiento de encuestas ',[Jefatura Carterizado])
		WHEN [Jefatura creador] = 'Externo' 
			AND [Servicio Responsable] <> 'Externo' 
			AND (Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%'or Asunto LIKE '%011]%' or Asunto LIKE '%012]%' or Asunto LIKE '%013]%')
				THEN CONCAT('Seguimiento de encuestas ',[Servicio Responsable])
		WHEN [Jefatura Carterizado] = 'Externo' 
			AND [Servicio Responsable] <> 'Externo' 
			AND (Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%'or Asunto LIKE '%011]%' or Asunto LIKE '%012]%' or Asunto LIKE '%013]%') 
				THEN CONCAT('Seguimiento de encuestas ',[Servicio Responsable])
		WHEN [Jefatura Carterizado] = 'Externo'  
			AND [Jefatura creador] <> 'Externo' 
			AND (Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%'or Asunto LIKE '%011]%' or Asunto LIKE '%012]%' or Asunto LIKE '%013]%') 
				THEN CONCAT('Seguimiento de encuestas ',[Jefatura creador])
		WHEN Asunto LIKE '%007]%' or Asunto LIKE '%008]%' or Asunto LIKE '%009]%' or Asunto LIKE '%011]%'  or Asunto LIKE '%012]%' or Asunto LIKE '%013]%'
				THEN 'Seguimiento de encuestas Otros'

		WHEN [Jefatura Carterizado] IN ('Carterizados','Triadas') 
			AND [Servicio responsable] not in ('Externo','No identificados M2C') 
				THEN [Jefatura Carterizado]
		WHEN [Jefatura Carterizado] IN ('Carterizados','Triadas') 
			AND [Programa del creador] <> 'Externo' THEN [Jefatura Carterizado]

		WHEN [Jefatura creador] = 'Externo' 
			AND [Servicio Responsable] <> 'Externo' THEN [Servicio Responsable]

		WHEN [Jefatura Carterizado] = 'Externo' 
			AND [Servicio Responsable] <>'Externo' THEN [Servicio Responsable]

		WHEN EXISTS (SELECT 1
					FROM #HIST_VALOR_NUEVO X1
					WHERE 1=1
					AND X0.[Número del caso] = X1.[Número del caso]
					AND X1.[Valor nuevo] = 'CHI-Isla de Retención'
				) THEN 'Isla de Retención'

		WHEN [Jefatura Carterizado] = 'Externo' 
			AND [Jefatura creador] <> 'Externo' THEN [Jefatura creador]
		ELSE 'Externo' 
	END [Vista final]

,CASE WHEN X1.[Número del caso] IS NOT NULL THEN 'Si'
     WHEN CAST(X0.[Fecha/Hora de apertura] AS DATE) >= '2023-01-01' AND X0.[Asesor Responsable DNI] = '74356174' THEN 'Si'
     ELSE 'No' END [GERENCIA],
CASE WHEN X3.[Número del caso] IS NOT NULL THEN 'Si'
     ELSE 'No' END [CLOSE THE LOOP],
CASE WHEN X4.[Número del caso] IS NOT NULL THEN 'Si'
     ELSE 'No' END [T-ATIENDO],
CASE WHEN x5.[Número del caso] IS NOT NULL THEN 'Si'
     ELSE 'No' END [CITA DE NEGOCIOS],
CASE WHEN X0.Asunto LIKE '%007]%' OR X0.Asunto LIKE '%008]%' OR X0.Asunto LIKE '%009]%' or Asunto LIKE '%011]%'  or Asunto LIKE '%012]%' or Asunto LIKE '%013]%' THEN 'Si' 
     ELSE 'No' END [DETRACTORES],
CASE WHEN X2.[Número del caso] IS NOT NULL THEN 'Si' 
     ELSE 'No' END [ESCALAMIENTO],
CASE WHEN [Creado por] = 'Administrador b2b' THEN 'Email2case'
     WHEN X0.[Origen del caso] IN ('Llamada','Call center','Llamada entrante','Llamada saliente') THEN 'Llamada'
     WHEN X0.[Origen del caso] IN ('Chat','WhatsApp') THEN 'Chat/WhatsApp'
     ELSE 'Correo' END [Origen],
CASE WHEN X0.[Tipo del Caso Final] NOT LIKE '%padre%' AND X0.[Casos Excluidos] = 0 THEN 'Si'
     WHEN X6.[Número de caso principal] IS NOT NULL AND X0.[Casos Excluidos] = 0 THEN 'Si' ELSE 'No' END [Final?]
INTO [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]				
FROM [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_2_NUEVO] X0
LEFT JOIN (SELECT DISTINCT [Número del caso] FROM [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_GERENCIA]) X1
ON X0.[Número del caso] = X1.[Número del caso]
LEFT JOIN (SELECT DISTINCT [Número del caso] FROM [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_ESCALAMIENTO]) X2
ON X0.[Número del caso] = X2.[Número del caso]
LEFT JOIN (SELECT [Número del caso] FROM [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_CLOSE_THE_LOOP] GROUP BY [Número del caso]) X3
ON X3.[Número del caso] = X0.[Número del caso]
LEFT JOIN (SELECT [Número del caso] FROM [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_T_ATIENDO] GROUP BY [Número del caso]) X4
ON X4.[Número del caso] = X0.[Número del caso]
LEFT JOIN (SELECT [Número del caso] FROM [CL_MOVIL].[dbo].[TBL_VOLUMETRIA_CITA_DE_NEGOCIOS] GROUP BY [Número del caso]) X5
ON X5.[Número del caso] = X0.[Número del caso]

LEFT JOIN (SELECT * FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_CASOS_PADRES]
WHERE [Tipo del caso] <> 'Caso Interno' AND Indicador='Todos hijos internos') X6
ON X0.[Número del caso]=x6.[Número de caso principal];


UPDATE [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]
SET [Vista final] = 'Carterizados'
WHERE [Vista final] = 'Cliente' AND
[Propietario del caso] IN 
('Bryan Echevarria Oropeza'
,'Cristhaly Maciel Rinojo De Los Rios'
,'Jerry Anthony Leonardo Mendoza'
,'Jose Yohel Carloman Loayza Portal'
,'Lens Cliver Ocaña Trujillo'
,'Mariela Gonzales Berrospi'
,'Wilmer Jose Izarra Pernia')


	IF EXISTS 
		(
			SELECT [Número del caso] , COUNT(*)
			FROM [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]
			GROUP BY [Número del caso] HAVING COUNT(*)> 1
		)
	BEGIN
		RAISERROR ('Números de casos duplicados',16,1); 
	END	

	
	IF EXISTS 
			(
			SELECT * 
			FROM [CL_TEMPORALES].INFORMATION_SCHEMA.TABLES 
			WHERE TABLE_NAME='TBL_SEGUIMIENTO_TOTAL_2_NUEVO' AND TABLE_SCHEMA='DBO'
		)
		BEGIN
			DROP TABLE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_2_NUEVO]
		END	

--------------------------------------------------------------------------------------------------------------------------------------------------------------


END



