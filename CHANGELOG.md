# Changelog

Todos los cambios relevantes de TALLY se documentan aquí.

## [0.3.0] — Sin publicar

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
