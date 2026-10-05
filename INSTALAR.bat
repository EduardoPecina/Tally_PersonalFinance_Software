@echo off
REM Instalador de TALLY para Windows.
REM Busca Python 3.13 (o lo instala solo para tu usuario con winget) y llama a instalador\instalar.py.
REM Se puede correr las veces que sea: la primera vez instala y despues actualiza sin tocar tus datos.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Instalador de TALLY
set "TALLY_BITACORA_BAT=%TEMP%\tally_instalar_bat.log"
echo INSTALAR.bat %DATE% %TIME% > "%TALLY_BITACORA_BAT%"
set "PY="

echo Buscando Python 3.13...
call :buscar_python
if defined PY goto encontrado

echo No se encontro Python 3.13. Instalandolo para tu usuario con winget...
echo Python 3.13 no encontrado; se intenta winget >> "%TALLY_BITACORA_BAT%"
where winget >nul 2>nul
if errorlevel 1 goto sin_winget
winget install --id Python.Python.3.13 -e --scope user --silent --accept-package-agreements --accept-source-agreements >> "%TALLY_BITACORA_BAT%" 2>&1
call :buscar_python
if defined PY goto encontrado
goto sin_python

:encontrado
echo Python encontrado: %PY%
echo Python: %PY% >> "%TALLY_BITACORA_BAT%"
"%PY%" instalador\instalar.py
if errorlevel 1 goto fallo
exit /b 0

:buscar_python
for /f "delims=" %%i in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
if defined PY exit /b 0
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
exit /b 0

:sin_winget
echo winget no esta disponible >> "%TALLY_BITACORA_BAT%"
:sin_python
echo.
echo No se pudo instalar Python 3.13 automaticamente.
echo Se abrira la pagina de descarga: instala Python 3.13 y vuelve a correr INSTALAR.bat.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:fallo
echo.
echo La instalacion no se completo. Revisa el archivo instalacion.log en la carpeta TALLY de tu Escritorio.
echo.
pause
exit /b 1
