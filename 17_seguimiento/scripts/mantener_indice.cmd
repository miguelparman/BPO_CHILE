@echo off
setlocal
call "%~dp0..\..\scripts\python_env.cmd"

rem Mantenimiento mensual del indice CIX_HISTORIAL_COMENTARIOS_CASO_FECHA
rem (REORGANIZE / REBUILD ONLINE solo si la fragmentacion lo requiere).
rem Registro: logs\mantenimiento_indice.log
pushd "%~dp0.."
"%ETL_PYTHON%" tools\optimizar_sp_proceso_seguimiento.py mantener-indice
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%
