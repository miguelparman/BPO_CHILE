-- Definicion de [CL_LOGUEO].[dbo].[SP_LOGUEO] leida con OBJECT_DEFINITION el 2026-10-01
-- (modify_date 2026-09-23 11:29:11.610000). Solo REFERENCIA: el proceso lo invoca tal cual (tarea 'SP'), no lo reescribe.

CREATE PROCEDURE [dbo].[SP_LOGUEO] 
AS
BEGIN

SET LANGUAGE SPANISH

DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE() 

SET DATEFORMAT DMY

INSERT  INTO [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Proceso,Nombre,Estado,[Fecha Inicio],[Fecha Fin])
(
  SELECT 'SP','CL_LOGUEO','exec...',@FECHA_EJECUCION_ETL,NULL
)


DROP TABLE IF EXISTS [CL_LOGUEO].[DBO].[TBL_LOGUEO_CHILE]
DROP TABLE IF EXISTS [CL_LOGUEO].[DBO].[TBL_LOGUEO_CHILE_TRAMOS]

--::::::::::::::::::::::::::CREACION TABLA TEMPORAL PLACE CARTERIZADOS / TRIADAS::::::::::::::::::::::::

--Se agrega este script para que elimine antes de crear la tabla tem nuevamente

IF OBJECT_ID('[CL_LOGUEO].[DBO].[TEMP_PLACE]', 'U') IS NOT NULL
        DROP TABLE [CL_LOGUEO].[DBO].[TEMP_PLACE];


SELECT distinct pcrc, [ID CONEXION]
---------------------------------------------
INTO [CL_LOGUEO].[DBO].[TEMP_PLACE]
---------------------------------------------
FROM [CL_LOGUEO].[dbo].[TBL_CONEXIONES]
	WHERE [AÑO] = 2024
	AND [MES] = 05
	AND [PCRC] IN ('TRIADA NO CARTERIZADO MICRO','PYMES CARTERIZADOS')
	AND [ID CONEXION] LIKE '5103%'
	AND [DIA] = 06
--::::::::::::::::::::::::::CREACION TABLA TEMPORAL LOGUEO::::::::::::::::::::::::::::::::::::
--Se agrega este script para que elimine antes de crear la tabla tem nuevamente
 IF OBJECT_ID('[CL_LOGUEO].[DBO].[TEMP_LOGUEO_CHILE]', 'U') IS NOT NULL
        DROP TABLE [CL_LOGUEO].[DBO].[TEMP_LOGUEO_CHILE];

SELECT TBL1.* 
,CASE 
			WHEN TBL1.PCRC_TEMP IN ('TRIADAS MICRO', 'TRIADAS NO CARTERIZADOS') THEN 'TRIADA NO CARTERIZADO MICRO'
			WHEN X1.PCRC IS NULL THEN TBL1.PCRC_TEMP	  
	   ELSE X1.PCRC END PCRC
,CASE 
	WHEN TBL1.PCRC_TEMP  =  'PLAT USUARIOS EMPRESA' THEN 'DH' 
	WHEN CAST(LEFT(HORA,2) AS INT) between 9 and 17 THEN 'DH' 
ELSE 'FH' END [HORARIO ATENCIÓN]
----------------------------------------
INTO [CL_LOGUEO].[DBO].[TEMP_LOGUEO_CHILE]
----------------------------------------
FROM
(SELECT 
	ROW_NUMBER() OVER( PARTITION by AÑO,MES,DIA,HORA,[ID CONEXION],[DNI] order by dia)  as ROWNO,
	[FECHA ANSI]
      ,[AÑO]
      ,[MES]
      ,[DIA]
      ,LEFT(CASE WHEN LEFT(HORA,2) IN('0:','1:','2:','3:','4:','5:','6:','7:','8:','9:') THEN CONCAT('0',HORA) ELSE HORA END,5) HORA
      ,[PRIME]
      ,[CANAL]
      ,[PCRC] PCRC_TEMP
      ,[MEDIA]
      ,[FAMILIA]
      ,[CALLCENTER]
      ,[SITE]
      ,[ID CONEXION]
      ,[AGENT_NOMBRE]
      ,[Q_ATE]
      ,[Q_ATE_DIRECT]
      ,[Q_TRANSF]
      ,[Q_ABN_RING]
      ,[Q_OUTBOUND]
      ,[Q_CHAT]
      ,[Q_ANI_TOT]
      ,[T_LOGIN]
      ,[T_WAITING]
      ,[T_TALK]
      ,[T_HOLD]
      ,[T_ACW]
      ,[T_OUTBOUND]
      ,[T_CONSULT]
      ,[TMO]
      ,[TMO_REAL]
      ,[T_RING]
      ,[T_DIALING]
      ,[T_INTERNAL]
      ,[T_NOTR_BACKOFFICE]
      ,[T_NOTR_BAÑO]
      ,[T_NOTR_CAPACITACION]
      ,[T_NOTR_TRABADM]
      ,[T_NOTR_COLACION]
      ,[T_NOTR_BREAK]
      ,[T_NOTR_RETROALIMENTACION]
      ,[T_NOTR_DEDICACION_PERSONAL]
      ,[T_NOTR_PROBLEMA_TEC]
      ,[T_NOTR_CORTE]
      ,[T_NOTR_CONTINGENCIA]
      ,[T_NOTR_480]
      ,[T_NOTR_603]
      ,[DNI]
  FROM [CL_LOGUEO].[dbo].[TBL_CONEXIONES]) TBL1
  LEFT JOIN [CL_LOGUEO].[DBO].[TEMP_PLACE] X1
  ON TBL1.[ID CONEXION] = X1.[ID CONEXION]
  WHERE ROWNO = 1
  --:::::::::::::::::::::TEMPORAL HORARIO POR DIA:::::::::::::::::::::::::::::::::::

  --Se agrega este script para que elimine antes de crear la tabla tem nuevamente
  IF OBJECT_ID('[CL_LOGUEO].[dbo].[TEMP_HORA_PROGRAMADAS_CHILE]', 'U') IS NOT NULL
        DROP TABLE [CL_LOGUEO].[dbo].[TEMP_HORA_PROGRAMADAS_CHILE];

  SELECT SUB1.DNI, SUB1.FechaAnsi, SUB1.[HORARIO ATENCIÓN], 
CASE WHEN SUM(cast(SUB1.MinutosProgramados as decimal))/60 >= 8 THEN (SUM(cast(SUB1.MinutosProgramados as decimal))/60)-1
ELSE SUM(cast(SUB1.MinutosProgramados as decimal))/60 END Hr_Prog

INTO [CL_LOGUEO].[dbo].[TEMP_HORA_PROGRAMADAS_CHILE]

FROM
  (SELECT X0.*, X1.Jefatura,X1.Programa
  ,CASE 
		WHEN X1.Programa = 'Usuarios Front Chile' THEN 'DH'
		WHEN X0.Hora BETWEEN 9 AND 17 THEN 'DH'
		ELSE 'FH' END 'HORARIO ATENCIÓN'
   FROM [BBDD_NUEVA_ASISTENCIA].[dbo].[TBL_HORARIOS_FRACTALIA_TRAMO_30_MIN] X0
   LEFT JOIN [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] X1
   ON RTRIM(X0.DNI) = X1.DNI
   AND LEFT(X0.[FechaAnsi],6) = X1.[Periodo]
   WHERE X0.[FechaAnsi] >= 20240101
   AND X1.Jefatura IN ('Carterizados','Triadas','Usuarios')

   )SUB1
   group by SUB1.DNI, SUB1.FechaAnsi, SUB1.[HORARIO ATENCIÓN]
  --:::::::::::::::::::::CREACION TABLA FINAL LOGUEO POR DIA:::::::::::::::::::::::::::
  SELECT SUB1.*, X1.[Hr_Prog]
  INTO [CL_LOGUEO].[DBO].[TBL_LOGUEO_CHILE]
  FROM
 ( SELECT 
  PCRC, AÑO, MES, DIA, [ID CONEXION], DNI, 
    (SUM(CAST(T_TALK AS decimal))+SUM(CAST(T_hold AS decimal))+SUM(CAST(T_Acw AS decimal))+SUM(CAST(T_WAITING AS decimal))+SUM(CAST(T_outbound AS decimal))+SUM(CAST(T_CONSULT AS decimal))+SUM(CAST([T_NOTR_CAPACITACION] AS decimal))+SUM(CAST([T_NOTR_TRABADM] AS decimal))+SUM(CAST([T_NOTR_RETROALIMENTACION] AS decimal)))/3600 [Logueo_Productivo]
,CASE WHEN                                         
  (SUM(CAST(T_TALK AS decimal))+SUM(CAST(T_hold AS decimal))+SUM(CAST(T_Acw AS decimal))+SUM(CAST(T_WAITING AS decimal))+SUM(CAST(T_outbound AS decimal))+SUM(CAST(T_CONSULT AS decimal))+SUM(CAST([T_NOTR_CAPACITACION] AS decimal))+SUM(CAST([T_NOTR_TRABADM] AS decimal))+SUM(CAST([T_NOTR_RETROALIMENTACION] AS decimal)))/3600 > 8.6 THEN 8.6 
ELSE                                               
  (SUM(CAST(T_TALK AS decimal))+SUM(CAST(T_hold AS decimal))+SUM(CAST(T_Acw AS decimal))+SUM(CAST(T_WAITING AS decimal))+SUM(CAST(T_outbound AS decimal))+SUM(CAST(T_CONSULT AS decimal))+SUM(CAST([T_NOTR_CAPACITACION] AS decimal))+SUM(CAST([T_NOTR_TRABADM] AS decimal))+SUM(CAST([T_NOTR_RETROALIMENTACION] AS decimal)))/3600 END [Logueo_Limite]
,(SUM(CAST(T_TALK AS decimal))+SUM(CAST(T_hold AS decimal))+SUM(CAST(T_Acw AS decimal))+SUM(CAST(T_WAITING AS decimal))+SUM(CAST(T_outbound AS decimal))+SUM(CAST(T_CONSULT AS decimal)))/3600 [Horas_Productivas]
,SUM(CAST([T_NOTR_CAPACITACION] AS decimal))/3600 Capacitación
,(SUM(CAST([T_NOTR_TRABADM] AS decimal))+ 
SUM(CAST([T_NOTR_RETROALIMENTACION] AS decimal)))/3600 [Aux_Productivo]
-- Tiempos
,SUM(CAST([T_Login] AS decimal))/3600 H_T_Login
,SUM(CAST([T_NOTR_TRABADM] AS decimal))/3600 H_T_trab_adm
,SUM(CAST([T_NOTR_RETROALIMENTACION] AS decimal))/3600 H_T_retroalimentacion
,SUM(CAST([T_NOTR_BAÑO] AS decimal))/3600 H_T_Baño
,SUM(CAST([T_NOTR_COLACION] AS decimal))/3600 H_T_Colacion
,SUM(CAST([T_NOTR_BREAK] AS decimal))/3600 H_T_break
,SUM(CAST([T_NOTR_DEDICACION_PERSONAL] AS decimal))/3600 H_T_Dedicacion_de_personal
,SUM(CAST([T_NOTR_PROBLEMA_TEC] AS decimal))/3600 H_T_Problemas_tecnicos
,SUM(CAST([T_NOTR_CORTE] AS decimal))/3600 H_T_Corte
--,SUM(CAST([T_discando] AS decimal))/3600 H_T_Discado
,SUM(CAST([T_NOTR_BACKOFFICE] AS decimal))/3600 H_T_Backoffice
,SUM(CAST([T_NOTR_CONTINGENCIA] AS decimal))/3600 H_T_Contingencia
,SUM(CAST([T_NOTR_480] AS decimal))/3600 H_T_Not_ready_480
,SUM(CAST([T_NOTR_603] AS decimal))/3600 H_T_Not_ready_603
,SUM(CAST([T_dialing] AS decimal))/3600 H_T_Dialing
,SUM(CAST([T_WAITING] AS decimal))/3600 H_T_disponible
,CONCAT(DNI,AÑO,MES) Llave_DNI_Periodo
,CONCAT(AÑO,MES,DIA) FechaAnsi
,CASE 
	WHEN [PCRC] = 'PLAT USUARIOS EMPRESA' THEN 'USUARIOS'
	WHEN [PCRC] = 'TRIADA NO CARTERIZADO MICRO' THEN 'TRIADAS'
	WHEN [PCRC] = 'PYMES CARTERIZADOS' THEN 'CARTERIZADOS'
	WHEN [PCRC] = 'RETENCION PYME INTEGRAL' THEN 'RETENCIONES'
ELSE 'OTROS' END SERVICIO
,CONCAT(DIA,'/',MES,'/',AÑO) FECHA
-----TIEMPO HABLADO y Aux----------------
,(SUM(CAST(T_TALK AS decimal))+SUM(CAST(T_hold AS decimal))+SUM(CAST(T_Acw AS decimal))+SUM(CAST(T_Ring AS decimal))+SUM(CAST(T_outbound AS decimal))+SUM(CAST(T_CONSULT AS decimal))+SUM(CAST([T_INTERNAL] AS decimal))+SUM(CAST([T_dialing] AS decimal)))/3600 [H_T_Hablado]
,(SUM(CAST(T_NOTR_BAÑO AS decimal))+SUM(CAST(T_NOTR_CAPACITACION AS decimal))+SUM(CAST(T_NOTR_RETROALIMENTACION AS decimal))+SUM(CAST(T_NOTR_COLACION AS decimal))+SUM(CAST(T_NOTR_BREAK AS decimal))+SUM(CAST(T_NOTR_DEDICACION_PERSONAL AS decimal))+SUM(CAST([T_NOTR_PROBLEMA_TEC] AS decimal))+SUM(CAST([T_NOTR_CORTE] AS decimal))+SUM(CAST([T_NOTR_BACKOFFICE] AS decimal))+SUM(CAST([T_NOTR_TRABADM] AS decimal))++SUM(CAST([T_NOTR_CONTINGENCIA] AS decimal))+SUM(CAST([T_NOTR_480] AS decimal))+SUM(CAST([T_NOTR_603] AS decimal)))/3600 [Auxiliar]
----------------------------------------
,[HORARIO ATENCIÓN]
----------------------------------

-----------------------------------
FROM [CL_LOGUEO].[dbo].[TEMP_LOGUEO_CHILE]
WHERE [PCRC] IN ('PLAT USUARIOS EMPRESA','TRIADA NO CARTERIZADO MICRO','PYMES CARTERIZADOS','RETENCION PYME INTEGRAL')
	  AND [ID CONEXION] LIKE '5103%'
  
GROUP BY
[HORARIO ATENCIÓN],PCRC, AÑO, MES, DIA, [ID CONEXION], DNI)SUB1
LEFT JOIN [CL_LOGUEO].[dbo].[TEMP_HORA_PROGRAMADAS_CHILE] X1
ON SUB1.DNI = RTRIM(X1.DNI)
AND SUB1.[FechaAnsi] = X1.[FechaAnsi]
AND SUB1.[HORARIO ATENCIÓN] = X1.[HORARIO ATENCIÓN]
--:::::::::::::::::::::::::::CREACION TABLA FINAL LOGUEO POR TRAMOS::::::::::::::::::::::::::::::::::::
SELECT *
, CONCAT(DNI, LEFT([FECHA ANSI],6)) Llave_DNI_Periodo
, CONCAT(format(cast(DIA as int),'0'),'/',MES,'/',AÑO,HORA) ID_Tramo
, CONCAT(format(cast(DIA as int),'0'),'/',MES,'/',AÑO) Id_Fecha
,(CAST(T_TALK AS decimal)+CAST(T_hold AS decimal)+CAST(T_Acw AS decimal)+CAST(T_WAITING AS decimal)+CAST(T_outbound AS decimal)+CAST(T_CONSULT AS decimal))/3600 [H_T_Productivo]
,(CAST([T_NOTR_TRABADM] AS decimal)+ CAST([T_NOTR_RETROALIMENTACION] AS decimal)+CAST([T_NOTR_CAPACITACION] AS decimal))/3600 [Aux_Productivo]

,(CAST([T_Login] AS decimal))/3600 H_T_Login
,(CAST([T_NOTR_TRABADM] AS decimal))/3600 H_T_trab_adm
,(CAST([T_NOTR_RETROALIMENTACION] AS decimal))/3600 H_T_retroalimentacion
,(CAST([T_NOTR_BAÑO] AS decimal))/3600 H_T_Baño
,(CAST([T_NOTR_COLACION] AS decimal))/3600 H_T_Colacion
,(CAST([T_NOTR_BREAK] AS decimal))/3600 H_T_break
,(CAST([T_NOTR_DEDICACION_PERSONAL] AS decimal))/3600 H_T_Dedicacion_de_personal
,(CAST([T_NOTR_PROBLEMA_TEC] AS decimal))/3600 H_T_Problemas_tecnicos
,(CAST([T_NOTR_CORTE] AS decimal))/3600 H_T_Corte
,(CAST([T_NOTR_BACKOFFICE] AS decimal))/3600 H_T_Backoffice
,(CAST([T_NOTR_CONTINGENCIA] AS decimal))/3600 H_T_Contingencia
,(CAST([T_NOTR_480] AS decimal))/3600 H_T_Not_ready_480
,(CAST([T_NOTR_603] AS decimal))/3600 H_T_Not_ready_603
,(CAST([T_DIALING] AS decimal))/3600 H_T_Dialing
,(CAST([T_WAITING] AS decimal))/3600 H_T_disponible
,(CAST([T_NOTR_CAPACITACION] AS decimal))/3600 H_T_Capacitación
,(CAST(T_NOTR_BAÑO AS decimal)+CAST(T_NOTR_CAPACITACION AS decimal)+CAST(T_NOTR_RETROALIMENTACION AS decimal)+CAST(T_NOTR_COLACION AS decimal)+CAST(T_NOTR_BREAK AS decimal)+CAST(T_NOTR_DEDICACION_PERSONAL AS decimal)+CAST([T_NOTR_PROBLEMA_TEC] AS decimal)+CAST([T_NOTR_CORTE] AS decimal)+CAST([T_NOTR_BACKOFFICE] AS decimal)+CAST([T_NOTR_TRABADM] AS decimal)+CAST([T_NOTR_CONTINGENCIA] AS decimal)+CAST([T_NOTR_480] AS decimal)+CAST([T_NOTR_603] AS decimal))/3600 [Auxiliar]
--------------------------------------------
INTO [CL_LOGUEO].[dbo].[TBL_LOGUEO_CHILE_TRAMOS]
--------------------------------------------
  FROM [CL_LOGUEO].[dbo].[TEMP_LOGUEO_CHILE]
  WHERE CONCAT(AÑO,MES) >= 202401
--::::::::::::::::::::::::::ELIMINAR TABLAS TEMPORALES:::::::::::::::::::::::::
DROP TABLE IF EXISTS [CL_LOGUEO].[DBO].[TEMP_PLACE]
DROP TABLE IF EXISTS [CL_LOGUEO].[DBO].[TEMP_LOGUEO_CHILE]
DROP TABLE IF EXISTS [CL_LOGUEO].[dbo].[TEMP_HORA_PROGRAMADAS_CHILE]

DECLARE @FECHA_FIN_ETL DATETIME
SET @FECHA_FIN_ETL = GETDATE() 

UPDATE [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
SET [Estado] = 'OK',
    [Fecha Fin] = @FECHA_FIN_ETL
WHERE [Fecha Inicio] = (SELECT MAX([Fecha Inicio]) FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] WHERE [Nombre] = 'CL_LOGUEO')
AND [Nombre] = 'CL_LOGUEO'

END

