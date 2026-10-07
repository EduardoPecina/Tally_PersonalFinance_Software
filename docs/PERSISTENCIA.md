# Persistencia, respaldos y bitácora

Todo vive en `motor/`. El portal solo llama a `Sesion` y a `respaldos`.

## Dónde están los datos

```text
Escritorio\TALLY\                el Escritorio que diga Windows (con o sin OneDrive)
  _Programa\                      el programa (el instalador lo reemplaza al actualizar)
  TALLY.lnk                       abre TALLY (también hay uno en el Escritorio)
  Mis datos de TALLY.lnk          abre la carpeta de tus datos
  LEEME.txt, instalacion.log

C:\Users\<usuario>\TALLY\         tus datos, siempre en esta PC
  Datos\tally.db                  tus finanzas (las actualizaciones nunca lo tocan)
  Respaldos\                      respaldos manuales y automáticos (.zip)
  portal.log                      lo que va pasando mientras TALLY está abierto
```

Los datos van en la carpeta del perfil del usuario porque:

- **OneDrive no la sincroniza.** Solo mueve Escritorio, Documentos e Imágenes.
  Las finanzas no terminan en una nube, aunque sea la de la empresa, y la
  sincronización no bloquea el archivo mientras SQLite escribe.
- **No es `AppData`.** El Python de la Microsoft Store redirige en secreto lo
  que se escribe ahí a una carpeta privada que Windows borra al desinstalarlo.
- Existe en cualquier Windows y el usuario siempre puede escribir en ella.

Si el Escritorio no deja escribir (algunas PC de trabajo), todo se instala en
`C:\Users\<usuario>\TALLY`.

En desarrollo, `Datos/` y `Respaldos/` se crean dentro del repositorio y
`.gitignore` las excluye. Variables de entorno: `TALLY_RAIZ` pone programa y
datos en otra carpeta; `TALLY_DATOS` cambia solo la de los datos.

La regla vive en `motor/rutas.py` y el instalador la usa directamente, así
que los dos siempre buscan los datos en el mismo lugar.

## Cómo se guarda

- **SQLite** en modo WAL con `synchronous=FULL`. Cada guardado es una
  transacción: o se escribe completo o no se escribe. Así se resisten cierres
  inesperados, apagones y errores de Streamlit.
- **Sesión:** el portal hace `with sesion.cambio() as libro: ...`. Al salir
  del bloque se guarda de inmediato. Si algo falla, el libro vuelve al último
  estado guardado; nunca queda a medias.
- Solo se escriben las entidades que cambiaron. Cada una es un documento JSON
  (perfil, clasificación, categoría, subcategoría, cuenta, operación y, desde
  TALLY 0.7, `valor` —compras y ventas de títulos— y `plazo` —CETES, pagarés—),
  en el mismo formato estable que los respaldos. Esquema 3 y respaldos de
  formato 3 desde TALLY 0.7: una versión anterior ya no los abre, para no perder
  los títulos.
- `Datos\precios.json` (TALLY 0.7.1) guarda los últimos precios públicos
  consultados (símbolo, precio, moneda, hora). No es parte de tus datos ni de
  los respaldos: si se borra o se daña, TALLY lo ignora y lo rehace en la
  siguiente consulta.
- Esquema 5 y respaldos de formato 5 desde TALLY 0.11: entidad `prestamo` (cómo se contrató cada préstamo).
- Esquema 4 y respaldos de formato 4 desde TALLY 0.10: entidad `bien` (cómo se deprecia cada cuenta de tipo
  «bien», sus avalúos y su venta). Una versión anterior ya no los abre, para no perder los bienes.
- `Datos\historial_precios.json` (TALLY 0.8) guarda los cierres diarios
  públicos de cada símbolo y tipo de cambio (fecha, precio, moneda), para las
  gráficas de la página Inversiones. Igual que `precios.json`: no es parte de
  tus datos ni de los respaldos, y si se borra se vuelve a pedir.
- Un **contador de revisión** detecta si otra ventana de TALLY modificó los
  datos y pide recargar en lugar de sobrescribir.
- **Al abrir** se ejecuta `PRAGMA quick_check` y se verifica que cada
  movimiento sume cero y que sus cuentas y categorías existan. Si algo está
  mal, TALLY lo dice y sugiere restaurar un respaldo; no trabaja sobre datos
  dañados.
- **Versión de esquema:** un archivo creado por una versión más nueva de TALLY
  no se abre con una más vieja. Esquema 2 (TALLY 0.4): categorías con
  subcategorías. Al abrir datos del esquema 1, `Sesion` los pone al día una
  sola vez (`motor/catalogo.py`) y lo anota en la bitácora.

## Contraseña y cifrado (opcional)

Viene apagado. Al activarlo (`motor/seguridad.py`):

- Se crea una **llave maestra** aleatoria de 256 bits que nunca se guarda en
  claro. Se guarda **envuelta dos veces** (AES-256-GCM):
  - una con una llave derivada de la contraseña (scrypt, n=2¹⁵, r=8, p=1);
  - otra con el **Kit de emergencia**: 22 caracteres aleatorios en Crockford
    base32 más 2 de verificación. Tolera minúsculas, espacios, guiones y
    O/0, I/L/1; los errores de tecleo se detectan antes de probar.
- Cada registro (`entidades.datos` y los campos de la bitácora) se cifra
  aparte con AES-256-GCM. El dato adicional autenticado es su lugar
  (`entidad:{tipo}:{id}`, `bitacora:{campo}:…`): un registro movido o
  modificado no se abre en silencio.
- La conversión se hace en **una sola transacción**, con `secure_delete`,
  `wal_checkpoint(TRUNCATE)` y `VACUUM`, para no dejar restos legibles.
  Después se relee y se compara con lo de antes; si no coincide, se deshace.
- `meta.cifrado` guarda la configuración: las dos llaves envueltas, la
  huella de la llave, la pista y las fechas. No guarda contraseñas.
- `VERSION_ESQUEMA` sube a 6: una versión anterior de TALLY pide actualizar
  en vez de leer mal.
- La llave vive solo en la memoria del portal (`portal/componentes/candado.py`).
  Se olvida al bloquear o tras el tiempo de bloqueo automático. Después de 3
  intentos fallidos, la espera crece (2, 4, 8… hasta 60 s).
- **Cambiar la contraseña** solo vuelve a envolver la llave maestra: el Kit
  y los respaldos viejos siguen sirviendo.
- **Quitar la contraseña** descifra todo, incluidos los respaldos de la
  carpeta.

### Respaldos con contraseña

- Se crean sin la llave: son una copia del contenido cifrado.
  `version_formato` 6.
- El manifiesto lleva las llaves envueltas, pero no el resumen (nombre,
  montos).
- Para restaurar:
  - en la misma instalación, con la sesión abierta, se usa la llave actual;
  - si no, la contraseña de ese día o el Kit;
  - una instalación sin contraseña adopta la del respaldo.
- Al activar la contraseña, los respaldos de la carpeta se cifran. Al
  quitarla, se descifran.
- El instalador puede respaldar y mover datos cifrados sin conocer la
  contraseña.

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
| `respaldos.de_seguridad(sesion, prefijo)` | Respaldo antes de algo delicado (cargar datos, restaurar, empezar de cero; el instalador, antes de actualizar). Conserva los últimos 5 de cada tipo |
| `respaldos.respaldar_archivo_de_datos(ruta, carpeta)` | Respaldo en solo lectura de un `tally.db`. Lo usa el instalador antes de actualizar |
| `respaldos.empezar_de_cero(sesion)` | Respalda todo (`TALLY_antes_de_empezar_de_cero_*.zip`) y deja TALLY como recién instalado. Sin respaldo no borra nada |
| `respaldos.copiar_archivo_de_datos(origen, destino)` | Copia un `tally.db` y comprueba con una segunda lectura independiente que sea idéntico (entidades y bitácora). Nunca sobrescribe. Lo usa el instalador para mover los datos |

Un respaldo dañado, incompleto, modificado o de una versión más nueva se
rechaza **antes** de tocar nada. Formato 2 desde TALLY 0.4. Un respaldo de
formato 1 se pone al día al restaurarlo.

## Instalador

`INSTALAR.bat` busca Python 3.13. Si no lo encuentra, lo instala solo para el
usuario con `winget` y, si eso falla, abre la página de descarga. Después
llama a `instalador/instalar.py`, que:

1. Revisa que TALLY no esté abierto (puerto 8765).
2. Instala las librerías con las versiones exactas de `requirements-lock.txt`.
3. Si ya hay datos, crea `Respaldos\TALLY_antes_de_actualizar_*.zip`. Si no
   puede, **no actualiza**.
4. Si encuentra datos de una versión anterior en `Escritorio\TALLY\Datos`,
   los mueve a la carpeta del usuario:
   1. copia y verifica (`copiar_archivo_de_datos`);
   2. aparta la carpeta vieja como `Datos_movido_<fecha>` y la borra. Si
      OneDrive no deja borrarla, el portal la borra al abrir;
   3. mueve los respaldos.

   Si no puede apartar la vieja, borra la copia y **no actualiza**: los datos
   nunca quedan en dos lugares a la vez. Si ya había datos en la carpeta del
   usuario, no mezcla nada: deja los viejos en `Datos_anterior_<fecha>` y lo
   avisa.
5. Reemplaza `_Programa` completo y conserva `_Programa_anterior` para
   regresar a la versión anterior si la copia falla.
6. Crea los accesos directos **TALLY** y **Mis datos de TALLY**.
7. Escribe todo en `instalacion.log`, sin el nombre de usuario.
