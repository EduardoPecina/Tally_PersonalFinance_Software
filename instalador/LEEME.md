# instalador/

Instalador para usuarios no técnicos (Fase 6): detecta Python 3.13, instala
dependencias, crea la carpeta en el Escritorio y los accesos directos,
actualiza `_Programa/` sin tocar `Datos/`, hace rollback si algo falla y
escribe `instalacion.log`.

- **Windows:** `INSTALAR.bat` busca Python 3.13 (o lo instala con winget) y
  llama a `instalar.py` con `requirements-lock.txt`.
- **Mac (chip de Apple):** `INSTALAR.command` busca Python 3.13 (o descarga el
  de python.org, comprueba su firma y lo instala con la contraseña de la Mac),
  crea el Python de TALLY en `~/TALLY/_Python` y llama a `instalar.py` con
  `requirements-lock-mac.txt`. Todo vive en `~/TALLY` y la app
  `~/Applications/TALLY.app` abre el portal. `INSTALAR.command --probar-descarga`
  solo descarga y verifica Python (lo usan las pruebas en GitHub).
