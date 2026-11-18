@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\5.2\python\bin\python.exe" (
  "runtime\5.2\python\bin\python.exe" launch.py %*
) else (
  py -3 launch.py %*
)
set "ruster_exit=%errorlevel%"
if "%ruster_exit%"=="0" exit /b 0
:check_headless
if "%~1"=="" goto show_error
if /I "%~1"=="--headless" exit /b %ruster_exit%
shift
goto check_headless
:show_error
pause
exit /b %ruster_exit%
