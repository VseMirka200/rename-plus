@echo off & if "%1"=="hidden" goto :hidden
cd /d "%~dp0"
start "" /b wscript.exe //nologo "%~dp0Запуск.vbs"
exit
:hidden
cd /d "%~dp0"
wscript.exe //nologo "%~dp0Запуск.vbs"
exit

