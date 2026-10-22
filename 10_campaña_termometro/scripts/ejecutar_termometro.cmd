@echo off
setlocal

REM Al reanudar desde suspension la red (Wi-Fi/VPN) tarda en levantar. Se
REM espera hasta 15 min (reloj, no numero de intentos) a que respondan el SQL
REM Server y SharePoint; si no responden se ejecuta igual y el error queda en
REM el log. Todo el bucle va en un solo PowerShell con Start-Sleep porque
REM "timeout /t" falla al instante cuando lo lanza el Programador de tareas
REM (sin consola) y la espera dejaba de durar lo previsto.
powershell -NoProfile -Command "$limite=(Get-Date).AddMinutes(15); $n=0; while($true){ $ok=$true; foreach($h in @(@('172.17.0.162',1433),@('fractaliagroup.sharepoint.com',443))){ $c=New-Object Net.Sockets.TcpClient; try{ if(-not $c.ConnectAsync($h[0],$h[1]).Wait(3000)){$ok=$false} }catch{$ok=$false}finally{$c.Dispose()}; if(-not $ok){break} }; if($ok){exit 0}; $n++; if((Get-Date) -ge $limite){ Write-Host ('[{0}] Sin red tras 15 min ({1} intentos), se ejecuta igual.' -f (Get-Date),$n); exit 1 }; Write-Host ('[{0}] Esperando red... intento {1}' -f (Get-Date),$n); Start-Sleep -Seconds 10 }"

pushd "%~dp0.."
"C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe" main.py %*
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%