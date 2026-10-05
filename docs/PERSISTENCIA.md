# Persistencia, respaldos y bitácora

Todo vive en `motor/`. El portal solo llama a `Sesion` y a `respaldos`.

## Dónde están los datos

```text
Escritorio\TALLY\
  _Programa\        el programa (el instalador lo reemplaza al actualizar)
  Datos\tally.db    tus finanzas (las actualizaciones nunca lo tocan)
  Respaldos\        respaldos manuales y automáticos (.zip)
  LEEME.txt
  instalacion.log
```

En desarrollo, `Datos/` y `Respaldos/` se crean dentro del repositorio y
`.gitignore` las excluye. La variable `TALLY_RAIZ` permite usar otra carpeta.

## Cómo se guarda

- **SQLite** en modo WAL con `synchronous=FULL`. Cada guardado es una
  transacción: o se escribe completo o no se escribe. Así se resisten cierres
  inesperados, apagones y errores de Streamlit.
- **Sesión:** el portal hace `with sesion.cambio() as libro: ...`. Al salir
  del bloque se guarda de inmediato. Si algo falla, el libro vuelve al último
  estado guardado; nunca queda a medias.
- Solo se escriben las entidades que cambiaron. Cada una es un documento JSON
  (perfil, grupo, categoría, cuenta u operación), en el mismo formato estable
  que los respaldos.
- Un **contador de revisión** detecta si otra ventana de TALLY modificó los
  datos y pide recargar en lugar de sobrescribir.
- **Al abrir** se ejecuta `PRAGMA quick_check` y se verifica que cada
  movimiento sume cero y que sus cuentas y categorías existan. Si algo está
  mal, TALLY lo dice y sugiere restaurar un respaldo; no trabaja sobre datos
  dañados.
- **Versión de esquema:** un archivo creado por una versión más nueva de TALLY
  no se abre con una más vieja.

## Bitácora

Cada guardado compara el estado anterior con el nuevo y anota en la tabla
`bitacora` qué entidad cambió, la acción (crear, editar, borrar o restaurar),
el valor anterior y el nuevo, con fecha y hora. De un movimiento borrado queda
una copia completa. No se guarda ninguna información sobre el usuario más allá
de sus propios datos.

## Respaldos

Un respaldo es un `.zip` con:

- `manifiesto.json`: formato `tally-respaldo`, versión del formato, versión de
  la app, fecha, resumen y huella SHA-256 de los datos.
- `datos.json`: todas las entidades y la bitácora.

| Función | Qué hace |
|---|---|
| `respaldos.crear(sesion, destino)` | Respaldo en la carpeta o archivo elegido. Se escribe a un `.tmp` y se renombra al terminar |
| `respaldos.inspeccionar(ruta)` | Valida el archivo y resume su contenido (cuentas, movimientos, fechas) para mostrarlo antes de restaurar |
| `respaldos.restaurar(sesion, ruta)` | 1) valida todo, 2) crea `TALLY_antes_de_restaurar_*.zip` con lo actual, 3) reemplaza en una sola transacción y lo anota en la bitácora |
| `respaldos.respaldo_automatico(sesion)` | Respaldo con rotación (conserva los últimos 10) |
| `respaldos.respaldar_archivo_de_datos(ruta, carpeta)` | Respaldo en solo lectura de un `tally.db`. Lo usa el instalador antes de actualizar |

Un respaldo dañado, incompleto, modificado o de una versión más nueva se
rechaza **antes** de tocar nada.

## Instalador

`INSTALAR.bat` busca Python 3.13. Si no lo encuentra, lo instala solo para el
usuario con `winget` y, si eso falla, abre la página de descarga. Después
llama a `instalador/instalar.py`, que:

1. Revisa que TALLY no esté abierto (puerto 8765).
2. Instala las librerías con las versiones exactas de `requirements-lock.txt`.
3. Si ya hay datos, crea `Respaldos\TALLY_antes_de_actualizar_*.zip`. Si no
   puede, **no actualiza**.
4. Reemplaza `_Programa` completo y conserva `_Programa_anterior` para
   regresar a la versión anterior si la copia falla.
5. Crea los accesos directos cuando exista el portal (Fase 3).
6. Escribe todo en `instalacion.log`, sin el nombre de usuario.
