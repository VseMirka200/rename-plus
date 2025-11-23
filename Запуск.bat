@echo off
cd /d "%~dp0"
python file_renamer.py
if errorlevel 1 (
    echo.
    echo Ошибка запуска! Проверьте, что Python установлен.
    echo.
    pause
)

