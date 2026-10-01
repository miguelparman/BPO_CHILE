@echo off
rem Ejecuta un proceso y, si termina con error, pregunta en consola si se
rem reintenta. La consola espera la respuesta SIN limite de tiempo. Sin limite
rem de reintentos: se pregunta de nuevo despues de cada fallo.
rem
rem Uso:
rem   set "COMANDO_REINTENTO=<comando a ejecutar>"
rem   set "LOG_CADENA=<archivo donde anotar intentos y respuestas>"   (opcional)
rem   call reintentar.cmd "<nombre>" "<carpeta de trabajo>" "<carpeta de logs del proceso>"
rem
rem Devuelve 0 si algun intento termino OK; si no, el codigo del ultimo intento.
setlocal

set "NOMBRE=%~1"
set "CARPETA=%~2"
set "LOGS_PROCESO=%~3"
set /a INTENTO=0

:intentar
set /a INTENTO+=1
call :registrar "Inicio %NOMBRE% - intento %INTENTO%"
pushd "%CARPETA%"
%COMANDO_REINTENTO%
set "CODIGO=%ERRORLEVEL%"
popd
call :registrar "Fin %NOMBRE% - intento %INTENTO% - codigo %CODIGO%"
if "%CODIGO%"=="0" exit /b 0

echo.
echo ============================================================
echo  [ERROR] %NOMBRE% termino con codigo %CODIGO% - intento %INTENTO%
echo  Logs: %LOGS_PROCESO%
echo ============================================================
choice /c SN /n /m "Reintentar %NOMBRE%? [S]i / [N]o: "
rem S = 1, N = 2. Si la consola no admite respuesta (codigo 255) se toma como N.
if errorlevel 2 goto no_reintentar
call :registrar "Respuesta S: se reintenta %NOMBRE%"
echo.
goto intentar

:no_reintentar
call :registrar "Respuesta N: no se reintenta %NOMBRE% - codigo final %CODIGO%"
exit /b %CODIGO%

:registrar
rem La redireccion va primero: un mensaje que termina en digito ("intento 1")
rem seguido de '>>' se interpretaria como redireccion del flujo 1.
if defined LOG_CADENA >> "%LOG_CADENA%" echo [%DATE% %TIME%] %~1
exit /b 0
