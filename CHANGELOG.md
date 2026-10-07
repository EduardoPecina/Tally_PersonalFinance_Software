# Changelog

Todos los cambios relevantes de TALLY se documentan aquí.

## [0.15.0] — Sin publicar

- **Nueva página 🏆 Metas de ahorro** (en Tu dinero):
  - **🛟 Fondo de emergencia:** qué es y cuánto te conviene juntar: de 3 a 6 meses de tus **gastos
    esenciales**. TALLY los calcula con lo que clasificaste como Necesidad y Compromisos (promedio de los
    últimos 3 meses) más los pagos de tus préstamos. Te dice **cuántos meses te cubre** lo que llevas.
  - **Tus metas:** un viaje, una computadora, el enganche… con objetivo, fecha opcional y la cuenta donde
    guardas el dinero. Cada una tiene su barra de avance, lo que falta, **cuánto apartar al mes** para llegar a
    tiempo y, a tu ritmo de los últimos 3 meses, **cuándo la logras**. Si a ese ritmo no llegas, te avisa.
  - **Aportar y retirar:** si eliges otra cuenta, TALLY registra la transferencia a (o desde) la cuenta de la
    meta. Así lo que dice la meta y lo que hay en la cuenta no se separan. Lo que ya tenías al crearla no mueve
    dinero ni cuenta como tu ritmo.
  - **Aviso si no alcanza:** si tus metas dicen que hay más dinero en una cuenta del que realmente tiene, te
    avisa.
  - **Al lograr una meta,** te felicita 🎉. Puedes archivarla, reactivarla o borrarla; borrarla no borra las
    transferencias.

## [0.14.0] — Sin publicar

- **Nueva página 📅 Calendario** (en Tu dinero):
  - **Próximos 30 días:** todo lo que te toca pagar y cobrar, en orden:
    - tus pagos fijos y suscripciones;
    - el pago de cada tarjeta (fecha límite y lo que falta para no generar intereses, más un estimado del ciclo
      en curso);
    - el pago de cada préstamo.

    Cada uno dice si ya está ✅ pagado, ⏳ pendiente o 🔴 vencido.
  - **Flujo de tu dinero:** con tu dinero disponible de hoy, una gráfica de cómo quedaría día con día. Dice
    cuánto entra, cuánto sale y lo más bajo que llegarías; si te quedarías en negativo, te avisa en rojo con la
    fecha. Las compras con tarjeta cuentan en el pago de la tarjeta, no el día que compras.
  - **Registrar con un clic:** eliges el pago del calendario y TALLY lo registra con su importe y su subcategoría
    (cámbialo si ese mes fue distinto).
  - **¿Ya se pagó?:** TALLY lo reconoce solo si registras un movimiento de la misma cuenta y subcategoría, hasta 7
    días antes o después y por un importe parecido (la luz cambia cada mes).
- **Mis pagos fijos y suscripciones:**
  - **Qué puedes agregar:** renta, luz, internet, Netflix, gimnasio, la nómina o pasar dinero al ahorro, con su
    importe aproximado. Se repiten cada semana, 14 días, quincena (el 15 y el último día), mes, 2, 3 o 6 meses,
    o cada año, con fecha de fin opcional.
  - **Cuánto te cuestan:** tus suscripciones al mes y **al año**, tus pagos fijos al mes y tus ingresos fijos.
  - **Editar, pausar o borrar:** con un clic en el renglón.
- **✨ Sugerencias:** TALLY busca en tus últimos 6 meses lo que se repite cada mes (o cada quincena) casi igual,
  por ejemplo Netflix o tu nómina, y te deja agregarlo con un clic.
- **Resumen:** avisa de los pagos fijos vencidos o que tocan en los próximos 3 días.

## [0.13.3] — Sin publicar

- **➕ Agregar a mano lo que falta** al importar del banco: fecha, descripción, importe, si entró o salió y la
  subcategoría o cuenta. Se carga junto con lo demás, y TALLY vuelve a comprobar si ya cuadra (✅) o cuánto falta.
- **Lo que no entendió, a la vista:** si no cuadra con tu estado de cuenta, TALLY muestra los renglones del PDF que
  tienen fecha o importe pero no leyó como movimiento (por ejemplo, uno que el banco partió en dos renglones),
  para que encuentres el que falta. Los del resumen (saldos, totales, tasas, importes en cero) no se muestran.

## [0.13.2] — Sin publicar

Estados de cuenta de **tarjeta de crédito** en PDF, probados con el formato de una tarjeta mexicana real (sin
guardar sus datos; las pruebas usan una copia inventada del formato):

- **Cuadra con tu deuda:** con el saldo anterior y el del corte del resumen («Saldo revolvente anterior», «al
  corte», «Saldo total»…), TALLY comprueba que deuda anterior + compras − pagos = deuda al corte. Si cuadra, todos
  los movimientos quedan con certeza y lo dice con ✅; si no, ⚠️ con la diferencia y qué revisar.
- **Intereses, comisiones e IVA que solo vienen en el resumen:** si sin ellos no cuadra y son justo lo que falta,
  TALLY los agrega al día del corte, marcados con 📋, para que los veas antes de cargar.
- **Totales de tarjeta:** entiende «Compras/Retiros/…» y «Pagos/Reembolsos/…» además de «Total cargos/abonos».
- **Lo que TALLY no reconoce, agrupado:** arriba de la tabla, una lista de lo que no supo clasificar, con los
  iguales o casi iguales juntos (por ejemplo, todos los «Su pago… Gracias»): eliges una vez por grupo.
- Más comercios conocidos: «REST …» (así abrevian los bancos «restaurante»), alitas, boneless, hamburguesas,
  Anthropic.

## [0.13.1] — Sin publicar

Mejor lectura del PDF del estado de cuenta, probada con el formato de un banco mexicano real (sin guardar sus
datos; las pruebas usan una copia inventada del formato):

- **Entró o salió, con certeza:** el saldo no viene en cada renglón, pero entre dos saldos conocidos solo una
  combinación de entradas y salidas cuadra. También usa el «Saldo anterior» y el «Saldo final» del resumen. Si
  cuadran varias (una nómina que se reparte completa en tres envíos), deciden las palabras del banco (NÓMINA
  entra, ENVIADO sale).
- **Comparación con los totales del banco:** si el estado de cuenta trae «Total cargos» y «Total abonos», TALLY
  dice ✅ si coinciden con lo que leyó, o ⚠️ cuánto falta.
- **El concepto completo:** toma los renglones de abajo de cada movimiento (el comercio, para qué fue, quién te
  pagó), sin referencias, claves ni folios.
- **Sin encabezados:** quita lo que el banco repite en cada hoja (producto, número de cuenta, «Página 2 de 6»).
- Separa palabras pegadas («SPEI RECIBIDOBANCO» → «SPEI RECIBIDO BANCO»).
- Un comercio que empieza con «TOTAL» (Total Play) ya no se confunde con un renglón de totales.
- Lo que eliges para un movimiento se aplica también a los **casi iguales** (el mismo envío en meses distintos).
- Sin avisos técnicos de fuentes al leer algunos PDF.

## [0.13.0] — Sin publicar

- **Importar los movimientos de tu banco** (Cargar datos → *Desde tu banco*):
  - **Qué sube:** el **Excel o CSV** de tu banca en línea, el **PDF** de tu estado de cuenta o la tabla
    copiada de la página del banco.
  - **Columnas:** TALLY las encuentra solo, aunque el banco ponga antes su nombre, la cuenta o el periodo.
    Entiende fechas (15/07/2026, 15-jul-26, 2026-07-15, mes/día…) e importes de varios países (1,234.56,
    1.234,56, −850.00, (850.00), 850.00 CR). Si se equivoca, se corrigen a mano.
  - **Signo:** con un solo importe con signo, lo deduce del saldo (o te deja cambiarlo). En un PDF, del
    saldo, de las marcas (−, CR) o de palabras como ABONO o SU PAGO; lo que no sabe seguro lo marca con 🔍.
  - **Totales para comparar:** muestra cuánto salió y cuánto entró, para cotejarlo con tu estado de cuenta.
  - **Subcategoría sugerida:** primero lo que elegiste antes para una descripción igual o casi igual (TALLY
    aprende de tu historial, también las transferencias a tus cuentas). Luego comercios conocidos de México y
    Latinoamérica (OXXO, Walmart, Netflix, CFE, Uber, Pemex…). Al final, lo que se parece.
  - **Duplicados:** lo que ya está en TALLY (misma cuenta, mismo importe, hasta 4 días de diferencia) se
    aparta y no se carga, salvo que lo marques. Subir el mismo archivo dos veces no duplica nada.
  - **Revisión:** una tabla editable para marcar o desmarcar, corregir la descripción, cambiar si el dinero
    entra o sale y elegir la subcategoría o la cuenta. Lo que elijas para un movimiento se usa también para
    los que se llaman igual, y lo que falte puede ir a OTROS GASTOS u OTROS INGRESOS.
  - **Carga:** se hace un respaldo antes. Se aplican las reglas de siempre: todo o nada, transferencias y
    pagos de tarjeta sin contar como gasto, devoluciones como reembolso.
  - **PDF con contraseña:** TALLY la pide y no la guarda. Un PDF escaneado o un Excel antiguo (.xls) se
    explican con un mensaje claro.
  - **Privacidad:** todo pasa en tu PC; el archivo no se manda a ningún lado.
- Nueva dependencia: `pypdf` (solo lee el PDF, en tu PC). `INSTALAR.bat` la instala.
- Los textos de Seguridad usan un español neutro («Si un día no te apetece»).

## [0.12.0] — Sin publicar

- **Contraseña opcional para TALLY** (Configuración → Seguridad → *Establecer una contraseña para TALLY*). Viene
  apagada. Un asistente de 4 pasos, explicado sin tecnicismos:
  1. Tu contraseña (mínimo 8 caracteres) y una pista opcional.
  2. Tu **Kit de emergencia**: una llave de repuesto para entrar si olvidas la contraseña. La descargas (.txt),
     la imprimes (.html), te la mandas por correo o le tomas foto.
  3. Comprobar el Kit y la contraseña. Sin esto no se activa nada.
  4. Activar. Antes hace un respaldo y, si la verificación no coincide, lo deshace solo.
- Con contraseña:
  - **Tus datos y respaldos se guardan cifrados** (AES-256-GCM, un registro a la vez) y no quedan restos
    legibles en el disco.
  - **Pantalla de entrada** con la pista. Tras 3 intentos fallidos, la espera crece.
  - **«¿Olvidaste tu contraseña?»**: entras con tu Kit y pones una nueva, sin perder nada.
  - **Bloqueo automático** si no usas TALLY un rato (10 minutos, ajustable) y botón **Bloquear ahora**.
  - **Respaldos cifrados en cualquier PC**: se abren con la contraseña de ese día o con el Kit, y la PC nueva
    se queda con la misma contraseña y el mismo Kit. En tu PC se restauran sin pedir nada.
  - **Cambiar la contraseña** (el Kit no cambia), **comprobar el Kit** (te lo recuerda cada 90 días),
    **copia sin contraseña** para una USB y **quitar la contraseña** (todo vuelve a estar sin cifrar).
  - Si pierdes tu contraseña **y** tu Kit, TALLY no borra nada: aparta tus datos cifrados y te deja empezar de
    nuevo o restaurar una copia sin contraseña.
- El esquema de datos y el formato de respaldo pasan a la versión 6: una versión anterior de TALLY pide
  actualizar en vez de leer mal.
- Nueva dependencia: `cryptography`. `INSTALAR.bat` la instala.

## [0.11.0] — Sin publicar

- **Nueva página 💳 Deudas** (en Tu dinero): tus tarjetas y préstamos, cuánto pagar y cómo salir sin ahogarte.
  - **¿Cuánto de tu ingreso se va en deudas?**: pagos de préstamos más pagos mínimos de tarjetas contra tu ingreso
    esperado. Lo sano es menos del 30 %; arriba del 40 %, te avisa. También muestra cuánto te queda para vivir.
  - **Tarjetas**:
    - **Pago mínimo estimado**, con la regla del Banco de México: el mayor entre 1.5 % del saldo más intereses
      e IVA, y 1.25 % de tu línea. Cada banco lo calcula a su manera.
    - Cuánto pagar para no generar intereses.
    - **Cuánto tardarías y cuántos intereses pagarías si pagas solo el mínimo.**
    - Nuevos datos de la tarjeta: tasa anual, **CAT** (o TAE, CAE, CFT, TEA en otros países, informativo) y si la
      tasa ya incluye IVA.
  - **Préstamos** (personal, de auto, hipoteca, de nómina, de un familiar u otro):
    - **Contratarlo**: monto que solicitaste, tasa anual, plazo, día de pago, pago pactado, CAT y comisión por
      apertura. El dinero llega a una de tus cuentas, o directo a un bien (tu auto). Si ya lo tenías, escribes
      cuánto debes hoy.
    - **Registrar pago**: separa intereses, IVA y cargos (mora, retraso, comisión, seguro), que son **gasto**,
      del capital, que baja tu deuda. Trae una estimación de los intereses que puedes corregir con tu estado de
      cuenta. Con intereses en 0 es un abono extra a capital.
    - **Cargo o mora** sin pago: sube tu deuda y es gasto.
    - **¿Cuánto pagar para salir antes?**: con tu pago actual, +10 %, +25 % o para terminar en el plazo del
      contrato, cuándo terminas y cuánto te ahorras de intereses.
    - **Simulador**: pago mensual, extra cada mes y abono único (aguinaldo, bono…), con gráfica de lo que debes
      en el tiempo. Avisa si el pago no cubre ni los intereses o si te pasarías del 40 % de tu ingreso.
    - **Tabla de amortización** del contrato (método francés) y **datos del contrato** editables.
    - En Contabilidad Técnica aparecen como pasivo a corto o largo plazo (según si los terminas en un año), y en
      el flujo de efectivo como «Préstamos».
- **Presupuestos**:
  - **Tus ingresos**: elige tu ingreso **principal** (la nómina) y tus ingresos **secundarios fijos**. Su promedio
    de los últimos 3 meses completos es tu **ingreso esperado**, o lo puedes escribir a mano. Incluye una **meta de
    ahorro**.
  - **¿Cuánto puedes gastar?**: ingreso − pagos de préstamos − ahorro, y **presupuestos sugeridos** por categoría
    (lo que sueles gastar, ajustado si no te alcanza), con un botón para usarlos.
  - **Proyección del mes**: cuánto vas a gastar al cierre, en qué categorías te vas a pasar y cuánto te quedaría.
- **Configuración → IVA de tu país** (México 16 %, España 21 %, Colombia y Chile 19 %…): se usa en los intereses de
  tarjetas y préstamos.
- Cuentas muestra también bienes y préstamos (con «Debes» en los préstamos).
- Datos versión 5 y respaldos formato 5: una versión anterior de TALLY ya no los abre, para no perder los préstamos.

## [0.10.0]

- **Contabilidad Técnica: clic en un renglón para ver su detalle.**
  - En los 4 reportes, al dar clic en una cuenta, categoría, sección o total, debajo aparecen los movimientos que
    forman esa cifra: fecha, descripción, tipo, contrapartida e importe. En la Balanza, separados en Debe y Haber.
  - Los estados se ven como tablas con títulos y totales resaltados. El Estado de Resultados se puede ver por
    subcategoría.
- **Bienes** (Fase 2), en la nueva pestaña **Bienes** de Contabilidad Técnica: tu casa, auto, laptop o muebles.
  - **Agregar un bien**: «Ya lo tenía» (su valor de hoy entra a tu patrimonio) o «Lo compré» (con qué cuenta lo
    pagaste). Comprarlo es una transferencia, **no un gasto**: cambias dinero por una cosa.
  - **Depreciación** con métodos para personas, no tasas fiscales:
    - **Línea recta**, con vida útil y valor de rescate (laptop 4 años, celular 3, muebles 10…).
    - **Decreciente**: un % al año sobre lo que vale, más al principio (auto: 15 %).
    - **No se deprecia**: casa y terreno.
    - Los valores sugeridos se pueden cambiar y todo se recalcula.
  - **Mejoras** (remodelación, ampliación) que suben el valor del bien, también sin ser gasto.
  - **Avalúos**: el bien vale lo que diga el avalúo y la diferencia es **plusvalía** (o minusvalía). Desde ahí
    se deprecia lo que le queda de vida.
  - **Venta**: con el precio y la cuenta a la que llegó el dinero. La diferencia contra su valor es ganancia o
    pérdida, y la cuenta del bien queda en ceros. Se puede deshacer.
  - Gráfica del valor del bien en el tiempo.
  - La depreciación y los avalúos **se calculan**: no llenan tu Historial ni cuentan como gasto en tu Resumen.
  - En Contabilidad Técnica:
    - Situación Financiera: el costo, la depreciación acumulada y la plusvalía de cada bien.
    - Resultados: un bloque **Cambios de valor** con depreciación, plusvalía, ganancia o pérdida al vender y
      rendimientos de inversiones.
    - Balanza: asientos calculados.
    - Todo sigue cuadrando.
  - El patrimonio del Resumen también considera la depreciación y la plusvalía.
- **Convertir un gasto en un bien** (Historial → elige el gasto → «Convertir en un bien»): un gasto que en realidad
  fue la compra de algo con valor, o una mejora a un bien que ya tienes, se vuelve transferencia al bien.
- Datos versión 4 y respaldos formato 4: una versión anterior de TALLY ya no los abre, para no perder los bienes.

## [0.9.0]

- **Nueva página 📒 Contabilidad Técnica** (en Análisis): tus estados financieros, armados solos con lo que ya
  registras. No se captura ni se guarda nada nuevo: son vistas de los mismos movimientos (que ya estaban en
  partida doble), así que si corriges uno, todos los reportes cambian y siempre cuadran.
  - **Estado de Situación Financiera**: lo que tienes (Activo), lo que debes (Pasivo) y lo que vales
    (Patrimonio). Incluye el aviso «Cuadra: Activo = Pasivo + Patrimonio».
    - El Activo se divide en efectivo y bancos, inversiones, por cobrar y otros. El Pasivo son las tarjetas
      de crédito, a corto plazo.
    - El Patrimonio es el patrimonio inicial (los saldos con los que empezaste) más los resultados de años
      anteriores y el resultado del año.
  - **Estado de Resultados**: ingresos y gastos por categoría (y por subcategoría), con el **resultado de tu día
    a día**. Los rendimientos de tus inversiones van aparte, para no mezclarlos con tu sueldo.
  - **Estado de Flujo de Efectivo**, por el método directo: efectivo al inicio, por dónde entró y salió (tu día
    a día, tarjetas, inversiones, préstamos y cobros, cuentas nuevas) y efectivo al final. Explica por qué una
    compra con tarjeta es gasto pero todavía no es salida de efectivo.
  - **Balanza de Comprobación**:
    - Saldos inicial y final (deudor y acreedor), movimientos (Debe y Haber), variación, **Origen /
      Aplicación** con explicación, y una lectura en palabras («Tienes más», «Debes menos ✓»).
    - Por categoría o por subcategoría (subcuentas), con la comprobación «sumas iguales».
    - Una cuenta por cobrar que ya te pagaron queda **en ceros: compensada ✓**.
  - **Comparativos**: este año, año pasado, este mes, mes pasado, últimos 12 meses o las fechas que elijas,
    contra el mismo periodo del año anterior o el inmediato anterior.
  - Explicación «¿Cómo se lee? (sin ser contador)» y descarga de los 4 reportes en Excel.
- **Entrada y Salida** en lugar de «Abono» y «Cargo» en el estado de cuenta y en su descarga a Excel.
- El menú de la izquierda muestra siempre todas las páginas (ya no se esconden en «View more»).

## [0.8.0]

- **Cuadrar con tu estado de cuenta** (antes «Registrar como rendimiento»):
  - Para pasar la ganancia o pérdida de una inversión a tu contabilidad, ahora es **obligatorio** escribir el valor
    oficial de la cuenta según tu app (GBM, Cetesdirecto, tu banco…), con su fecha.
  - TALLY te muestra la diferencia contra su saldo de ese día y, al confirmar, la registra como rendimiento
    (INTERESES Y RENDIMIENTOS). Así la cuenta coincide **al centavo** con la oficial: el precio de internet
    queda solo como referencia.
  - Incluye lo que el precio de internet no ve: efectivo dentro de la cuenta, dividendos y comisiones.
  - Funciona sin internet y también en cuentas de inversión sin títulos registrados. Registrar el mismo valor
    dos veces no agrega nada.
- **Nueva página 📈 Inversiones** (en Análisis): el rendimiento de tus inversiones a lo largo del tiempo.
  - **Periodo**: este mes, mes pasado, 3 o 6 meses, este año, 1, 2, 5 o 10 años, desde el inicio, o las fechas
    que elijas.
  - **Filtros**: las cuentas que quieras (CETES + GBM, solo una…) y, dentro de ellas, los títulos o inversiones a
    plazo que quieras (solo IVV, IVV + VT, solo CETES…).
  - **Cifras del periodo**: valor al inicio, lo que metiste, lo que sacaste, valor al final y ganancia, con su %.
    El % considera cuándo metiste o sacaste el dinero (método de Dietz modificado).
  - **Gráficas**:
    - Valor en el tiempo contra lo que metiste; la distancia entre ambas líneas es la ganancia.
    - Una línea por título o por cuenta.
    - Ganancia o pérdida de cada mes o año.
  - **Detalle** por título, inversión a plazo o cuenta.
  - **Dos vistas**:
    - **Por título**: un estimado con precios de cierre diarios.
    - **Oficial**: exacta. Usa el saldo de la cuenta con tus ajustes al valor oficial; la ganancia son los
      rendimientos registrados y las transferencias son aportaciones o retiros.
  - Los CETES crecen con interés simple. Al vencer, su dinero sale del CETE; si lo reinviertes, no se cuenta dos
    veces.
- **Historial de precios**:
  - Botón «Actualizar historial de precios» que trae los cierres diarios de Yahoo Finance.
  - Envía **solo** los símbolos y un periodo estándar (por ejemplo «5 años»), nunca la fecha de tu primera compra
    ni cantidades. Siempre por HTTPS y sin registros.
  - Se guarda en tu PC (`Datos\historial_precios.json`) para ver las gráficas sin internet. La siguiente vez solo
    pide los días que faltan.
  - Con «Actualizar precios automáticamente» activado, se actualiza solo al abrir la página, una vez por visita.
  - Si no hay historial, la página usa tus precios de compra o el último precio consultado, y lo dice.
  - Las cuentas de inversión usan el cierre más reciente del historial si es más nuevo que la última consulta.

## [0.7.3]

- **Instalador a prueba de «lo corrí desde dentro del ZIP»**:
  - Antes, si se corría `INSTALAR.bat` sin extraer el ZIP, Windows podía borrar su copia temporal mientras se
    instalaban las librerías, y el respaldo previo fallaba con «No module named 'motor.respaldos'». No se
    cambiaba nada, pero no se podía actualizar.
  - Ahora `INSTALAR.bat` detecta que está dentro de un ZIP, copia el programa a `%TEMP%\TALLY_instalador` y se
    vuelve a lanzar desde ahí.
  - El instalador revisa que el programa esté completo antes de empezar. Si falta algo, explica que hay que
    usar «Extraer todo» y no toca nada.
  - El motor que hace el respaldo previo se carga desde el principio, antes de la instalación de librerías
    (que tarda).

## [0.7.2]

- **Gráficas: ¿qué hay en «OTROS»?**
  - La dona y las barras muestran los 7 grupos más grandes y juntan el resto en OTROS. Debajo de la gráfica,
    «Todos los importes» lista **cada** grupo con su importe y su %, y marca cuáles van dentro de OTROS.
  - **Clic en una rebanada o barra** (o elígela en «Ver el detalle de») para **desglosarla**: en qué se reparte
    (una categoría en sus subcategorías, una cuenta en categorías; OTROS en lo que junta) y la lista de los
    movimientos que la forman.
  - Funciona en dona, barras y barras por mes. En líneas, se elige en la lista.

## [0.7.1]

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
