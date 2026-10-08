@echo off
rem Crea Installa_AnalisiMetrologica.exe (Windows) dal file distribution\installer_gui.py.
rem Da eseguire su Windows, con Python 3.10+ installato, dalla cartella del progetto.
rem Risultato: dist\Installa_AnalisiMetrologica.exe  (un solo file, nessuna console).
cd /d "%~dp0.."
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller --noconfirm --onefile --windowed --name Installa_AnalisiMetrologica --icon assets\app_icon.ico distribution\installer_gui.py || goto :err
echo.
echo Fatto: %CD%\dist\Installa_AnalisiMetrologica.exe
pause
exit /b 0
:err
echo Creazione dell'exe non riuscita.
pause
exit /b 1
