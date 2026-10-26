@echo off
setlocal

pushd "%~dp0.."
"C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe" main.py %*
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%
