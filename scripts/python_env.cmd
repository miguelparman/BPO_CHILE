@echo off
rem Define ETL_PYTHON (ruta de python.exe) para los .cmd de los proyectos, de modo que
rem no haya que editarlos en cada equipo. Orden de busqueda:
rem   1) variable de entorno ETL_PYTHON ya definida
rem   2) scripts\python.local.cmd (local a cada equipo, no versionado; lo crea
rem      registrar_tareas_etl.ps1 o se escribe a mano: set "ETL_PYTHON=<ruta>")
rem   3) instalacion historica Python312 de miguel.paredes, si existe
rem   4) python del PATH
rem Se invoca con: call "<carpeta de BPO_CHILE>\scripts\python_env.cmd"
if defined ETL_PYTHON exit /b 0
if exist "%~dp0python.local.cmd" call "%~dp0python.local.cmd"
if defined ETL_PYTHON exit /b 0
if exist "C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe" set "ETL_PYTHON=C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe"
if defined ETL_PYTHON exit /b 0
set "ETL_PYTHON=python"
exit /b 0
