@echo off
setlocal
call "%~dp0..\..\scripts\python_env.cmd"

pushd "%~dp0.."
"%ETL_PYTHON%" ETL_Polars_Historial_contactos.py %*
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%
