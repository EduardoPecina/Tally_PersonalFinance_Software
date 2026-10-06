# Changelog

Todos los cambios relevantes de TALLY se documentan aquí.

## [0.7.1] — Sin publicar

- **Precios de títulos, más transparentes y a prueba de fallas**:
  - Nota visible: «⚡ Precios obtenidos desde Yahoo Finance. La consulta solo envía los símbolos bursátiles…».
  - Los últimos precios consultados se **guardan en tu PC** (`Datos\precios.json`). Si no hay internet, o la
    red lo bloquea, se muestran los últimos guardados, con la hora de la **última actualización**.
  - Interruptor **«Actualizar precios automáticamente»**, apagado por omisión. Al abrir una cuenta de
    inversión, consulta solo si los precios tienen más de una hora, una vez por visita, y envía solo los
    símbolos.
  - Si el proveedor deja de responder como antes (cambió o desapareció), TALLY lo **avisa** y sigue
    funcionando con los precios guardados o a mano. El proveedor quedó en un solo lugar para poder cambiarlo.
  - La consulta solo se hace por HTTPS y no se registra en bitácoras ni logs.

## [0.7.0]

- **Títulos e inversiones a plazo** en las cuentas de inversión (Cuentas → Ver movimientos):
  - Registra **compras y ventas** de acciones, ETFs y cripto: símbolo (como en Yahoo Finance: IVVPESO.MX, AAPL,
    BTC-USD), títulos (con decimales), precio, moneda, tipo de cambio y comisión. TALLY lleva el **costo
    promedio** y la **ganancia de lo vendido**, y no deja vender títulos que no tenías.
  - Registra **CETES, pagarés y certificados de depósito** (monto, tasa anual, plazo). Su valor e interés se
    calculan en tu PC, sin internet.
  - Botón **«Consultar valor aproximado actual»**: trae el precio de hoy de cada título y, si cotiza en dólares,
    el tipo de cambio. Muestra el valor actual y la ganancia en $ y %. **Solo envía el símbolo**, nunca tus
    títulos, montos ni archivos, y solo cuando lo aprietas. Sin conexión (o si la red lo bloquea) lo dice y
    puedes escribir los precios a mano.
  - **«Registrar como rendimiento»** (opcional): pasa a tu saldo la ganancia (o pérdida) que aún no estaba
    registrada. TALLY recuerda lo ya registrado para no contar nada dos veces.
  - Registrar títulos no cambia el saldo de la cuenta: el dinero ya estaba ahí.
- Los datos y los respaldos de esta versión ya no los abre una versión anterior de TALLY, para que no se pierdan
  tus títulos. Los respaldos anteriores se siguen restaurando sin problema.

## [0.6.0]

- **Clasificaciones nuevas**:
  - Antes eran 5 (Necesidad, Disfrute, Estabilidad, Inversión, Dádivas) y ahora son 7, cada una con una
    pregunta clara:
    - **Necesidad**: lo indispensable para vivir.
    - **Compromisos**: intereses, comisiones, impuestos, multas y pagos de deudas; lo que pagas por obligación.
    - **Estabilidad**: seguros, herramientas de trabajo e imprevistos.
    - **Crecimiento** (antes «Inversión»): estudios, cursos, libros, ejercicio.
    - **Disfrute**: salidas, viajes, entretenimiento, compras.
    - **Antojos**: los gastos hormiga, como botanas, café y comida a domicilio.
    - **Generosidad** (antes «Dádivas»): regalos, celebraciones, donativos, apoyo a la familia.
  - Tus datos se ponen al día solos al abrir TALLY, una sola vez. Solo se mueven las subcategorías del catálogo
    que seguían en su clasificación original; las que tú ya habías movido se quedan donde las pusiste.
- **Categorías → Clasificaciones**, rediseñada:
  - Cada clasificación es una caja con su descripción y **todas sus subcategorías adentro**, agrupadas por
    categoría.
  - Agregas o quitas subcategorías ahí mismo. Cada subcategoría está en **una sola** clasificación: si intentas
    ponerla en otra, TALLY no lo deja y te dice dónde está.
  - Arriba, una tabla con cuánto pesa cada clasificación en tu gasto del año.
  - Renombrar y borrar quedan en el botón «Editar» de cada caja.

## [0.5.5]

- **Respaldos sin acumularse**:
  - «Descargar respaldo» ya no deja una copia en la carpeta Respaldos: el archivo solo va a tus Descargas.
  - Los respaldos de seguridad (antes de actualizar, de cargar datos, de restaurar y de empezar de cero) se
    rotan solos: se conservan los últimos 5 de cada tipo.
  - Los automáticos diarios siguen como antes (los últimos 10, o los que elijas en Configuración) y los que
    guardas a mano con «Guardar respaldo en la carpeta» nunca se borran.

## [0.5.4]

- **Cargar datos**: dentro de un mismo día se carga primero lo que entra (nómina, rendimientos, devoluciones),
  luego lo que se mueve entre cuentas y al final los gastos. Así ningún saldo pasa por un negativo que nunca
  existió (por ejemplo, un retiro total y su ganancia del mismo día).
- **Estado de cuenta**: nuevo selector «Más recientes primero» / «Más antiguos primero». Ordena bien los
  movimientos del mismo día, para leer el saldo de arriba abajo; al ordenar con clic en una columna el saldo no
  se recalcula, y así lo dice la nota de la tabla.

## [0.5.3]

- **Cargos temporales**: lo que te cobran para verificar tu tarjeta y te
  devuelven después (Amazon, Uber, un hotel…). **No cuentan como gasto.**
  - En Registrar → Gasto, activa «Cargo temporal: me lo van a devolver».
    Se guarda como transferencia a la cuenta **POR RECUPERAR** (tipo Por
    cobrar, suma en «Te deben»), que se crea sola.
  - El Resumen muestra la lista «Por recuperar» con dos botones:
    «Ya me lo devolvieron» (regresa el dinero a la cuenta que elijas) y
    «No me lo devolvieron» (lo pasa a gasto en la fecha que elijas).
  - Si pasan más de 45 días sin devolución, el Resumen te avisa para que
    lo reclames. Los días se cambian en Configuración → Resumen.
  - En la plantilla de carga, escribe POR RECUPERAR en SUBCATEGORIA, en el
    cargo y en su devolución.

## [0.5.2]

- **Eliminar cuenta o tarjeta**: botón «Eliminar» en cada cuenta.
  - Si tiene movimientos, desaparece de tus cuentas y de los formularios,
    pero **su historial se guarda** en Historial, Tablas dinámicas y
    Gráficas.
  - Puedes ver su estado de cuenta y restaurarla con «Mostrar eliminadas».
  - Si todavía tiene saldo o deuda, te avisa y te deja ponerla en $0 con un
    ajuste (si ya la pagaste o cancelaste).
  - Antes de eliminarla puedes descargar su historial a Excel.
  - Si no tiene movimientos, se borra por completo.

## [0.5.1]

- Configuración → Apariencia: el ícono «Acento» ahora se llama **«Violeta»**.

## [0.5.0]

**Fase 4: análisis.**

- **Tablas dinámicas** (pivots), como en Excel:
  - filas por categoría, subcategoría, clasificación, cuenta o ingreso/gasto;
  - columnas por mes, trimestre, año u otra dimensión;
  - suma de gastos, ingresos, los dos o el balance;
  - todo el historial o un rango de meses, de todas o algunas cuentas;
  - fila opcional con lo apartado a ahorro, como la fila AHORRO de tu Excel;
  - atajos rápidos y exportación a Excel (con la hoja de movimientos) o CSV.
- **Gráficas** a elegir, con el botón «Visualizar gráfica»: dona, barras de
  mayor a menor, barras por mes, líneas de tendencia, ingresos vs. gastos y
  evolución del patrimonio. Tienen tooltips y colores fijos por grupo,
  legibles con daltonismo.
- **Estado de cuenta** en Cuentas → «Ver movimientos»:
  - los movimientos de la cuenta con el saldo después de cada uno, como el
    Excel;
  - botón «Agregar movimiento» y filtro por periodo;
  - editar, repetir o eliminar cada movimiento;
  - exportar a Excel.
- **Meses sin intereses:** la compra cuenta completa como gasto el día que la
  haces, pero el «pagar para no generar intereses» de la tarjeta solo suma la
  mensualidad de cada corte. Lista de compras a MSI con lo que falta y la
  última mensualidad.
- **Presupuestos** mensuales por categoría, con barras de avance en su página
  y en el Resumen.
- **Avisos** en el Resumen si un pago de tarjeta está vencido o vence en los
  próximos días.
- Registrar: **repartir un gasto** entre varias subcategorías; también se abre
  desde cada cuenta.
- Historial: **repetir** un movimiento en otra fecha.
- Configuración → Apariencia:
  - **tema oscuro**;
  - **color del ícono** del acceso directo y de la pestaña (claro, oscuro,
    acento o gris). Se conserva al actualizar.
- Lema en inglés: *Your money. Your computer. Your data.*
- Menú agrupado en Tu dinero, Análisis y Ajustes.
- Pruebas automáticas en **Windows** (GitHub Actions) en cada pull request.
- Nueva dependencia: `openpyxl` (exportar a Excel), fijada con su hash en el
  lock.

## [0.4.2]

- **Descargar respaldo** en un clic, en Respaldos y en Configuración. Es un
  `.zip` con todo: cuentas, movimientos, categorías, configuración y
  bitácora. También queda una copia en la carpeta Respaldos.
- **«Ya usaba TALLY»** en la bienvenida: subes tu respaldo y TALLY queda como
  lo tenías, sin capturar nada.
- Restaurar acepta un respaldo `.zip` o el archivo de datos `tally.db` de
  otra PC. Se lee en solo lectura y se valida antes de reemplazar nada.
- **⚙️ Configuración**:
  - tu nombre o apodo;
  - descargar respaldo;
  - respaldo automático diario (activarlo o no y cuántos conservar);
  - periodo que muestra el Resumen al abrir;
  - datos de la instalación y botón para abrir la carpeta de tus datos.
- Respaldo automático: uno por día al abrir TALLY. Conserva los últimos 10
  (configurable).

## [0.4.1]

- **Estado de cada tarjeta de crédito** en Resumen y en Cuentas:
  - cuánto debes, tu disponible y tu línea de crédito;
  - qué porcentaje de la línea usas (con aviso si pasa del 70 %);
  - si estás al corriente o cuánto pagar del último corte y antes de qué
    fecha (con los días que faltan), o si el pago ya venció;
  - el ciclo actual y el próximo corte.
- Nuevo `tarjetas.estado()` en el motor.

## [0.4.0]

- **Categorías y subcategorías.** Las categorías son cajas (SALUD, TECNOLOGIA,
  MASCOTAS…) que agrupan subcategorías (DENTISTA, CELULARES Y TABLETS…). A
  cada movimiento se le pone una subcategoría y los reportes suman por las
  dos. Los grupos de antes (Necesidad, Disfrute…) ahora se llaman
  **clasificaciones**.
- **Catálogo amplio**: 25 categorías y más de 130 subcategorías comunes
  (despensa, gimnasio, gasolina, streaming, mascotas, hijos, viajes…),
  además de las originales. Todo es editable.
- Nombres de categorías y subcategorías siempre en **MAYÚSCULAS y sin
  acentos** (la Ñ se conserva). No se puede agregar dos veces lo mismo,
  aunque cambien mayúsculas, acentos, signos o espacios.
- Tus datos se ponen al día solos al abrir TALLY: nombres estandarizados,
  cada subcategoría en su categoría (las tuyas, en VARIOS) y las nuevas
  agregadas. No se pierde ni se junta nada; queda en la bitácora. Los
  respaldos de la 0.3 también se ponen al día al restaurarlos.
- **Cargar datos**: plantillas `.txt` (débito, crédito, ahorro, inversión o
  todas) para subir muchos movimientos a la vez desde Excel. Vista previa,
  crea las cuentas que falten, pregunta qué es cada nombre desconocido, no
  duplica transferencias que vienen en las dos cuentas ni lo que ya estaba,
  respaldo automático antes de cargar y todo o nada.
- **Empezar de cero** (Respaldos y bitácora): borra todo y deja TALLY como
  recién instalado, con un respaldo previo para recuperarlo.
- Resumen: gasto por categoría, por clasificación y por subcategoría.
- Los datos y respaldos de esta versión ya no se abren con una versión
  anterior de TALLY (que no conoce las subcategorías).

## [0.3.6]

- `portal.log` pasa del Escritorio a `C:\Users\<tu usuario>\TALLY`, junto a
  tus datos. TALLY escribe en él mientras está abierto y OneDrive lo
  resincronizaba sin parar. Al actualizar se borra el del Escritorio.

## [0.3.5]

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
