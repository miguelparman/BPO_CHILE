@echo off
rem Cadena programada (tarea \ETL\ETL Cadena trafico), lunes a viernes a las 10:30.
rem Ejecuta en orden, uno detras de otro:
rem   1) 01_servidor_chile
rem   2) 12_trafico
rem   3) 13_fcr        (usa el trafico cargado en el paso 2)
rem   4) 14_EPA_WSP
rem   5) 04_usuarios_y_retenciones   (periodo: PERIODO de su .env)
rem Si un paso falla, la consola pregunta si se reintenta (reintentar.cmd) y
rem espera la respuesta sin limite de tiempo. Si no se reintenta, la cadena
rem sigue con el paso siguiente.
rem Codigo de salida: 0 si todos terminan OK; si alguno falla, 1.
setlocal
call "%~dp0python_env.cmd"

set "PYTHON=%ETL_PYTHON%"
set "RAIZ=%~dp0.."
if not exist "%RAIZ%\logs" mkdir "%RAIZ%\logs"
set "LOG_CADENA=%RAIZ%\logs\cadena_1030.log"
set "COMANDO_REINTENTO="%PYTHON%" main.py"
set "cadena_exit=0"

for %%P in (01_servidor_chile 12_trafico 13_fcr 14_EPA_WSP 04_usuarios_y_retenciones) do (
    call "%~dp0reintentar.cmd" "%%P" "%RAIZ%\%%P" "%RAIZ%\%%P\logs"
    if errorlevel 1 set "cadena_exit=1"
)

>> "%LOG_CADENA%" echo [%DATE% %TIME%] Fin cadena - codigo %cadena_exit%
exit /b %cadena_exit%
