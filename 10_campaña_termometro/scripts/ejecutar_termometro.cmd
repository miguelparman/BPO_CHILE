@echo off
setlocal

REM Al reanudar desde suspension la red (Wi-Fi/VPN) tarda en levantar. Se
REM espera hasta 15 min (90 intentos x 10 s) a que respondan el SQL Server y
REM SharePoint; si no responden se ejecuta igual y el error queda en el log.
set "intentos=0"
:esperar_red
powershell -NoProfile -Command "foreach($h in @(@('172.17.0.162',1433),@('fractaliagroup.sharepoint.com',443))){ $c=New-Object Net.Sockets.TcpClient; try{ if(-not $c.ConnectAsync($h[0],$h[1]).Wait(3000)){exit 1} }catch{exit 1}finally{$c.Dispose()} }; exit 0"
if not errorlevel 1 goto red_ok
set /a intentos+=1
if %intentos% geq 90 (
    echo [%date% %time%] Sin red tras 15 min, se ejecuta igual.
    goto red_ok
)
echo [%date% %time%] Esperando red... intento %intentos%
timeout /t 10 /nobreak >nul
goto esperar_red
:red_ok

pushd "%~dp0.."
"C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe" main.py %*
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%