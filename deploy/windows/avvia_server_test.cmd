@echo off
rem Starts the test server, reachable from other devices on the same network.
rem Double-click, or run from the project folder. Stop with Ctrl+C.
cd /d "%~dp0\..\.."
set "PY=librery\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo === Server di test ===
"%PY%" -m server doctor
echo.
"%PY%" -m server serve --lan
pause
