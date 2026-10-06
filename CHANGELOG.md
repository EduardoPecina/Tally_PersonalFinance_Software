# Changelog

Todos los cambios relevantes de TALLY se documentan aquí.

## [0.3.5] — Sin publicar

- **Tus datos ya no viven en el Escritorio:** ahora están en
  `C:\Users\<tu usuario>\TALLY` (`Datos\tally.db` y `Respaldos\`). Así
  OneDrive (personal o de la empresa) no los sube a la nube ni pelea con
  SQLite mientras TALLY guarda. El programa y el acceso directo siguen en el
  Escritorio que diga Windows, esté o no dentro de OneDrive.
- Al actualizar, el instalador **mueve solo** los datos de una versión
  anterior: respalda, copia, comprueba que la copia sea idéntica (cuentas,
  movimientos y bitácora) y hasta entonces quita la del Escritorio. Si algo
  falla, no cambia nada. Si encuentra datos en los dos lugares, no mezcla
  ni borra: aparta los viejos en `Datos_anterior_<fecha>` y lo avisa.
- Acceso directo **Mis datos de TALLY** dentro de la carpeta TALLY del
  Escritorio, para encontrar tus datos y respaldos. La página Respaldos
  muestra dónde están.
- Si Windows no deja escribir en el Escritorio (PC de trabajo con
  restricciones), TALLY se instala completo en `C:\Users\<tu usuario>\TALLY`.

## [0.3.4]

- **Fecha límite de pago de tarjetas según su contrato:** un día fijo del mes
  o N días después del corte, naturales o hábiles. Si cae en día inhábil, se
  recorre al siguiente día hábil (opcional por tarjeta). El portal deja elegir
  la regla y la muestra en palabras en Cuentas.
- Nuevo `motor/calendario.py`: días inhábiles bancarios de México para
  cualquier año (Pascua calculada, lunes festivos y cambio de Poder
  Ejecutivo cada seis años).

## [0.3.3]

- Instalador: si pip pasa 30 s sin escribir nada (instalando Streamlit mientras
  el antivirus revisa sus archivos), muestra «...sigue trabajando (N min). No
  cierres esta ventana.» Antes la ventana parecía congelada y, al cerrarla,
  la instalación quedaba a medias.
- Instalador: antes de instalar, borra los restos `~paquete` que deja una
  instalación interrumpida («Ignoring invalid distribution ~treamlit»).
- Aviso previo de que la primera instalación puede tardar hasta 10 minutos.

## [0.3.2]

- Acceso directo **TALLY** más confiable: el instalador lo crea con pywin32,
  como el Portal de Honorarios, y si falla usa PowerShell (restringido en
  algunas PC de trabajo). Al final comprueba que los dos `.lnk` existan (en
  el Escritorio y dentro de la carpeta TALLY) y anota en `instalacion.log`
  cualquiera que falte.
- Nueva dependencia solo para Windows: `pywin32` (lock: 44 paquetes con hash).

## [0.3.1]

### Marca y robustez del portal

- Identidad visual de TALLY: símbolo de marcas de conteo, logotipo con
  wordmark, acento violeta `#6B53F1`, favicon e ícono del acceso directo.
  Recursos y su generador en `docs/marca/`.
- «Cerrar TALLY» detiene todo lo del portal (incluidos portales viejos y el
  lanzador) y muestra «TALLY se cerró» en lugar del error de conexión.
- TALLY se apaga solo tras 15 minutos sin pestañas abiertas
  (`TALLY_INACTIVIDAD_MIN`).
- Lanzador más robusto: un solo lanzador a la vez (clics de más), reinicio
  de un portal trabado, vida máxima y mensaje de error con las últimas
  líneas de `portal.log`.
- Al abrir se borran las copias `_Programa_anterior` que OneDrive no dejó
  borrar al actualizar, solo si de verdad son copias del programa.
- Corregido: al intentar abrir un archivo de datos dañado quedaba una
  conexión abierta; en Windows eso bloqueaba el archivo e impedía apartarlo
  para restaurar un respaldo.
- Nueva dependencia: `psutil` (lock regenerado: 43 paquetes con hash).

Basado en la lógica de apagado, lanzador y limpieza del Portal de Honorarios.

## [0.3.0]

### Fase 3: portal básico (Streamlit)

- **Bienvenida** («¡Hola!»): tu nombre y tus cuentas, todas las que quieras.
- **Resumen**: dinero disponible, total en cuentas, deuda de tarjetas,
  patrimonio y lo que te deben. Ingresos, gastos, ahorro real y apartado a
  ahorro del periodo, comparados con el periodo anterior. Gasto por categoría
  y por grupo, evolución del patrimonio, tarjetas (por liquidar y fecha
  límite) y sobrante antes de cada nómina. Periodos: este mes, mes pasado,
  esta quincena, este año, últimos 12 meses o fechas a elegir.
- **Registrar**: gasto, ingreso, transferencia, pago de tarjeta y reembolso,
  en un solo formulario que recuerda la última cuenta usada.
- **Historial**: búsqueda sin importar acentos; filtros por cuenta,
  categoría, tipo y fechas que se conservan al cambiar de página; botón
  «Quitar todos los filtros»; orden; detalle, edición y eliminación con
  confirmación.
- **Cuentas**: crear, editar, actualizar saldo (intereses o ajuste), saldo
  inicial, archivar y borrar.
- **Categorías y grupos**: crear, renombrar, cambiar de grupo, archivar y
  borrar (con reasignación de movimientos).
- **Respaldos y bitácora**: crear y descargar respaldos, restaurar con vista
  previa y confirmación, y consultar los cambios recientes.
- **Recuperación**: si el archivo de datos está dañado, se restaura un
  respaldo o se empieza de cero sin borrar el archivo original.
- Lanzador `portal/iniciar.py` y `EJECUTAR PORTAL.bat`. El instalador crea el
  acceso directo **TALLY** con su ícono.
- El motor suma: consultas del historial, periodos con nombre, comparación
  con el periodo anterior, evolución del patrimonio, ciclo de tarjeta por
  pagar y resumen legible de la bitácora.
- `requirements-lock.txt` regenerado para Windows y CPython 3.13 con
  Streamlit 1.65 (42 paquetes, todos precompilados y con hash).

## [0.2.0]

### Fase 2: persistencia, respaldos e instalador

- Guardado automático en SQLite (`Datos/tally.db`): transacciones completas,
  modo WAL, verificación de integridad al abrir y detección de cambios hechos
  desde otra ventana.
- `Sesion`: cada cambio se guarda al momento y, si algo falla, se deshace por
  completo.
- Bitácora local de cambios con valor anterior, valor nuevo, fecha y hora.
- Respaldos `.zip` versionados con huella SHA-256: crear, inspeccionar antes
  de restaurar, restaurar (con respaldo de seguridad previo) y respaldos
  automáticos con rotación.
- Instalador para Windows (`INSTALAR.bat` + `instalador/instalar.py`), basado
  en el del Portal de Honorarios: carpeta en el Escritorio real, `_Programa`
  reemplazable con rollback, respaldo de los datos antes de actualizar,
  `instalacion.log` y accesos directos (cuando exista el portal).
- La demostración incluye el ciclo guardar → reabrir → respaldar → restaurar
  (`python -m motor.demo --persistencia`).

## [0.1.0]

### Fase 1: motor financiero

- Modelo contable con partidas que siempre suman cero
  (`docs/MODELO_CONTABLE.md`).
- Cuentas ilimitadas de los tipos débito, ahorro, crédito, efectivo, inversión,
  por cobrar y otra, con saldo o deuda inicial, archivado y borrado seguro.
- Gastos, ingresos y reembolsos, incluidos los repartidos en varias categorías.
- Transferencias y pagos de tarjeta como una sola operación, sin doble conteo.
- Tarjetas de crédito: deuda, crédito disponible, ciclos de corte y fecha
  límite de pago.
- «Actualizar saldo» para ajustes y rendimientos (intereses, inversiones).
- Categorías y grupos editables, con catálogo inicial; fusión de categorías.
- Reportes: resumen del periodo, gastos e ingresos por categoría, grupo y
  cuenta, indicadores, tabla de hechos para pivots y sobrantes por quincena.
- Perfil local para la bienvenida.
- Pruebas automatizadas con datos ficticios.
- `EJECUTAR.bat` provisional: demostración del motor con datos ficticios
  (`python -m motor.demo`) y pruebas automáticas.
- Estructura del proyecto, licencia MIT y configuración de Streamlit.
