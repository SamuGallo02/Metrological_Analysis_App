@echo off
rem Removes the firewall rule created by open_firewall.cmd. Run as administrator.
net session >nul 2>&1
if errorlevel 1 (
  echo Run this file as administrator.
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="Analisi server test"
pause
