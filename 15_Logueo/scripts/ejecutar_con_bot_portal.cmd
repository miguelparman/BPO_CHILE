@echo off
rem Cadena programada (tarea \ETL\ETL Logueo Chile):
rem   1) 203_bot_portal_comercial: descarga REPORTE_AGENTES_FRACTALIA_SEM.csv del
rem      Portal Comercial y lo sube a SharePoint (15 PORTAL COMERCIAL).
rem   2) 15_Logueo: carga el CSV en TBL_CONEXIONES, AGREGA DNI y SP_LOGUEO.
rem Si un paso falla, la consola pregunta si se reintenta (reintentar.cmd) y
rem espera la respuesta sin limite de tiempo.
rem El paso 2 se ejecuta aunque el bot falle y no se reintente: el bot
rem devuelve 1 si falla cualquiera de sus 2 flujos (p.ej. solo
rem 'Dimensionamiento', con el CSV de agentes ya subido), y si el CSV no se
rem actualizo el Lookup no inserta nada.
rem Codigo de salida: 0 solo si ambos terminan OK.
setlocal
call "%~dp0..\..\scripts\python_env.cmd"

set "PYTHON=%ETL_PYTHON%"
set "BOT_DIR=%~dp0..\..\203_bot_portal_comercial"
set "ETL_DIR=%~dp0.."
if not exist "%ETL_DIR%\logs" mkdir "%ETL_DIR%\logs"
set "LOG_CADENA=%ETL_DIR%\logs\cadena_programada.log"

set "COMANDO_REINTENTO="%PYTHON%" main.py"
call "%~dp0reintentar.cmd" "203_bot_portal_comercial" "%BOT_DIR%" "%BOT_DIR%\logs"
set "bot_exit=%ERRORLEVEL%"

set COMANDO_REINTENTO=call "%~dp0ejecutar_logueo.cmd" %*
call "%~dp0reintentar.cmd" "15_Logueo" "%ETL_DIR%" "%ETL_DIR%\logs"
set "etl_exit=%ERRORLEVEL%"

if not "%etl_exit%"=="0" exit /b %etl_exit%
exit /b %bot_exit%
