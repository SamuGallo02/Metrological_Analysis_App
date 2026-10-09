@echo off
rem Builds Installa_AnalisiMetrologica.exe (Windows) from common\ambient\distribution\installer_gui.py.
rem To be run on Windows, with Python 3.10+ installed, from the project folder.
rem Result: dist\Installa_AnalisiMetrologica.exe  (a single file, no console).
cd /d "%~dp0..\..\.."
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller --noconfirm --onefile --windowed --name Installa_AnalisiMetrologica --icon common\assets\app_icon.ico common\ambient\distribution\installer_gui.py || goto :err
echo.
echo Fatto: %CD%\dist\Installa_AnalisiMetrologica.exe
pause
exit /b 0
:err
echo Creazione dell'exe non riuscita.
pause
exit /b 1
