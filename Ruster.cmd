@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\4.5\python\bin\python.exe" (
  "runtime\4.5\python\bin\python.exe" launch.py %*
) else (
  py -3 launch.py %*
)
if errorlevel 1 pause
