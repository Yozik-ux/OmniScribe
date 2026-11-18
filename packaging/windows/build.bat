@echo off
REM Збирає OmniScribe.exe і Setup-інсталятор на Windows.
REM Запуск (у PowerShell/cmd, з кореня репозиторію): packaging\windows\build.bat [версія]
REM Потребує: Python 3.11+, pip, і встановлений NSIS (makensis у PATH).

setlocal
cd %~dp0..\..

if "%~1"=="" (set VERSION=0.1.0) else (set VERSION=%~1)

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

pip install --quiet -r requirements.txt pyinstaller

echo ==^> PyInstaller
rmdir /S /Q dist\OmniScribe 2>nul
rmdir /S /Q build 2>nul
pyinstaller --noconfirm --clean --onedir --name OmniScribe --paths . --add-data "assets;assets" app.py

echo ==^> NSIS
makensis /DVERSION=%VERSION% packaging\windows\installer.nsi

echo Готово: dist\OmniScribe-Setup-%VERSION%.exe
endlocal
