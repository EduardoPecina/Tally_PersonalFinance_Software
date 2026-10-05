@echo off
REM Abre TALLY en tu navegador (servidor local en localhost:8765).
REM Usa el entorno .venv si existe (desarrollo); si no, Python 3.13 (instalado con INSTALAR.bat).
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title TALLY
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" portal\iniciar.py
) else (
    py -3.13 portal\iniciar.py
)
if errorlevel 1 pause
