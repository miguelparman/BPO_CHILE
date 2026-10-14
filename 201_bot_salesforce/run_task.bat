@echo off
REM Wrapper pensado para ser llamado desde el Programador de tareas de
REM Windows. Usa python.exe (no pythonw.exe) para que el logger escriba
REM tambien en esta consola -- asi se puede ver el progreso en vivo (y el
REM aviso de MFA si la sesion de Salesforce necesita renovarse), igual que
REM al ejecutar main.py desde VSCode.
REM
REM %~dp0 se expande a la carpeta donde vive este .bat (con barra final),
REM asi que el "cd /d" garantiza que .env, config/reports.py y
REM playwright/.auth/ se resuelvan sin importar el directorio de trabajo
REM que use la tarea programada.
cd /d "%~dp0"

REM Al reanudar desde suspension la red (Wi-Fi/VPN) tarda en levantar. Se
REM espera hasta 15 min (90 intentos x 10 s) a que SharePoint responda por
REM 443; si no responde se ejecuta igual y el error queda en el log.
set "intentos=0"
:esperar_red
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try{ if($c.ConnectAsync('fractaliagroup.sharepoint.com',443).Wait(3000)){exit 0}else{exit 1} }catch{exit 1}finally{$c.Dispose()}"
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

python.exe main.py
