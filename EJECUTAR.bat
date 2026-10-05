@echo off
REM TALLY - prueba del motor (provisional hasta que exista el portal).
REM Muestra un mes de demostracion con datos ficticios, guarda/respalda/restaura
REM en una carpeta temporal y corre las pruebas.
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
echo [1/4] Creando el entorno de Python, solo la primera vez. Puede tardar unos 30 segundos...
py -3.13 -m venv .venv
if errorlevel 1 goto error

:instalar
echo [2/4] Revisando librerias. La primera vez las descarga de Internet, puede tardar de 1 a 3 minutos...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --require-hashes --timeout 30 --retries 2 -r requirements-lock.txt
if errorlevel 1 goto error

echo.
echo [3/4] Demostracion del motor con datos ficticios:
".venv\Scripts\python.exe" -m motor.demo --persistencia
echo.
echo [4/4] Corriendo las pruebas automaticas...
".venv\Scripts\python.exe" -m pytest -q
echo.
echo Para abrir TALLY en tu navegador: EJECUTAR PORTAL.bat
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
echo Algo fallo al preparar el entorno. Arriba esta el detalle del error.
echo Si estas en una red de trabajo, puede que bloquee las descargas de Python ^(pypi.org^).
echo.
pause
exit /b 1
