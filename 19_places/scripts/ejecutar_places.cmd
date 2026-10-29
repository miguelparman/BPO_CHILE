@echo off
setlocal
call "%~dp0..\..\scripts\python_env.cmd"

pushd "%~dp0.."
"%ETL_PYTHON%" main.py %*
set "exit_code=%ERRORLEVEL%"
popd

exit /b %exit_code%
