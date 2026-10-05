@echo off
REM TALLY - prueba del motor (provisional hasta que exista el portal).
REM Muestra un mes de demostracion con datos ficticios y corre las pruebas.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title TALLY - prueba del motor

where py >nul 2>nul
if errorlevel 1 goto sin_python
py -3.13 -c "import sys" >nul 2>nul
if errorlevel 1 goto sin_python

if exist ".venv\Scripts\python.exe" goto instalar
echo Preparando el entorno de Python, solo la primera vez...
py -3.13 -m venv .venv
if errorlevel 1 goto error

:instalar
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --require-hashes -r requirements-lock.txt
if errorlevel 1 goto error

".venv\Scripts\python.exe" -m motor.demo
echo.
echo Corriendo las pruebas automaticas...
".venv\Scripts\python.exe" -m pytest -q
echo.
pause
exit /b 0

:sin_python
echo.
echo No se encontro Python 3.13.
echo Instalalo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH"
echo y vuelve a abrir este archivo.
echo.
pause
exit /b 1

:error
echo.
echo Algo fallo al preparar el entorno. Revisa tu conexion a Internet y vuelve a intentarlo.
echo.
pause
exit /b 1
