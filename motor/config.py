"""Constantes generales de la aplicación."""

import sys

APP_NOMBRE = "TALLY"
VERSION = "1.0.0"
MONEDA = "MXN"
LEMA = "Your money. Your computer. Your data."
PUERTO_PORTAL = 8765
MAC = sys.platform == "darwin"
INSTALADOR = "INSTALAR.command" if MAC else "INSTALAR.bat"      # el que se vuelve a correr para reparar o actualizar
