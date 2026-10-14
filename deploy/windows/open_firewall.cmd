@echo off
rem Allows incoming connections to the test server (TCP 8765) on PRIVATE networks only.
rem Run as administrator (right click -> Run as administrator).
net session >nul 2>&1
if errorlevel 1 (
  echo Run this file as administrator.
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="Analisi server test" >nul 2>&1
netsh advfirewall firewall add rule name="Analisi server test" dir=in action=allow protocol=TCP localport=8765 profile=private
echo.
echo Rule added (private networks only). Remove it with close_firewall.cmd when the test is over.
pause
