# Changelog

Todos los cambios relevantes de TALLY se documentan aquí.

## [1.0.0] — Sin publicar

**TALLY 1.0.** La primera versión estable: todo lo que se fue sumando hasta la 0.32 (cuentas, también en otra
moneda; tarjetas, préstamos, presupuestos, metas, calendario de pagos, cierre de mes, inversiones, contabilidad
técnica, impuestos, importar tu banco, contraseña, respaldos y copia en tu NAS, en Windows y en Mac), revisado de
punta a punta. Estos son los arreglos de esa última revisión:

- **Cambiar la cuenta de un movimiento por una de otra moneda conserva lo que vale** (Historial → Editar). Un gasto
  de $180 que pasas a tu cuenta en dólares queda en US$10, no en US$180; igual con un gasto repartido en varias
  subcategorías y con una transferencia. Si además cambias el importe, va en la moneda de la cuenta nueva (lo dice
  la ayuda del campo).
- **Transferencias entre monedas:** cambiar la cuenta de origen o de destino por otra de la misma moneda ya no borra
  «lo que llegó» (antes se volvía a calcular con el tipo de cambio del día).
- **Bienvenida:** elegir otra moneda para una cuenta antes de terminar la bienvenida podía dar un error. Ahí las
  cuentas van en tu moneda; las de dólares u otra moneda se agregan después en Cuentas, y la bienvenida lo dice.
- **Cierre de mes:** si después de cerrar solo cambió un tipo de cambio o un avalúo de ese mes, el aviso dice qué
  cambió («el valor de tus cuentas en otra moneda o de tus bienes») y cuánto se movió tu patrimonio, en lugar de
  «algunos importes».
- **Historial → Repetir** un movimiento de una cuenta eliminada ya no da error: te dice que primero la restaures.
- **Cifras grandes:** en las tarjetas de cifras (Resumen, Calendario…) un importe como $1,234,567.89 ya no se corta
  con «…» en la pantalla de una laptop; el número se achica para caber. En pantallas grandes se ve igual.
- **Nombres con «$»:** tu nombre y los de tus cuentas, tarjetas, categorías y presupuestos se ven tal cual aunque
  lleven «$» (con dos, se dibujaban como fórmula).
- **Peso chileno y peso cubano junto a tu moneda:** «CLP 75.456», con espacio (antes «CLP75.456»).
- **La revisión:** miles de acciones al azar con cuentas en varias monedas (registrar, editar, borrar, repetir,
  transferir, respaldar y restaurar) comprobando después de cada una que todo cuadre; todas las páginas, pestañas y
  desplegables con datos vacíos, normales, grandes y con casos raros (nombres con símbolos y emojis, importes de
  miles de millones, el 29 de febrero, días 31, monedas sin centavos), en las pruebas y en un navegador real.
- El README dice el estado actual (antes seguía en «Fase 3») y la hoja de ruta, completa.
- No cambia el formato de tus datos ni de tus respaldos: la 1.0 abre los de la 0.32 tal cual.

## [0.32.0] — Sin publicar

**Cuentas en otra moneda.** Una cuenta de débito, ahorro, efectivo, inversión u «otra» puede estar en dólares, euros
u otra moneda; TALLY sigue sumando todo en la tuya. Tarjetas, préstamos, bienes y lo que te deben se quedan en tu
moneda.

- **Al crear una cuenta eliges su moneda** (o después, en Administrar cuenta, mientras no tenga movimientos). Su
  saldo se ve en su moneda, como en tu banco, y abajo lo que vale en la tuya: «US$1,200.00 · ≈ $22,200.00 · 1 USD =
  18.50 MXN».
- **Registrar en esa cuenta es igual:** escribes el importe en su moneda y nada más. TALLY guarda también lo que
  valía en tu moneda ese día, así que tus gastos del mes pasado, tus presupuestos y tus cierres no cambian cuando se
  mueve el dólar.
- **Pasar dinero entre monedas:** escribes lo que salió y, si quieres, **lo que llegó**, como lo ves en tu banco
  (así cuenta el tipo de cambio real, con su comisión). Si lo dejas vacío, se calcula con el tipo de cambio del día.
- **Lo que sube o baja el valor de tus dólares** sale aparte, «por tipo de cambio»: debajo de tu patrimonio en el
  Resumen, en la evolución de tu patrimonio y en Contabilidad Técnica (diferencia por tipo de cambio en el activo,
  ganancia o pérdida por tipo de cambio en los cambios de valor y en el flujo de efectivo). Todo sigue cuadrando.
- **Configuración → Tipos de cambio:** el de cada moneda, de qué día es, escribir uno a mano y su historial.
  Opcional: **traerlos de internet cada día**, en segundo plano (no te hace esperar). Solo se envía el par de monedas
  (USDMXN); si internet no trae una moneda, se calcula con el dólar o la escribes tú. Los que escribes tú mandan.
- **Inversiones en dólares:** en una cuenta de inversión en dólares, el costo, el valor, el valor oficial y los
  CETES o plazos van en dólares; una acción en dólares ya no pide tipo de cambio. El rendimiento se pasa a tu
  moneda al registrarlo, y las gráficas de Inversiones suman todo en la tuya.
- **También entienden de monedas:** el Historial (columna «En su moneda»), el estado de cuenta (todo en la moneda de
  la cuenta), los pagos fijos y el Calendario (su importe en la moneda de su cuenta; los totales y tu dinero en 30
  días, en la tuya), las metas, los pagos de préstamos desde una cuenta en dólares, los cargos temporales (vuelve
  lo mismo que te cobraron), cargar el estado de cuenta de tu banco en dólares (sin duplicar al subirlo otra vez)
  y la Salud de tus datos (avisa si falta un tipo de cambio o si es de hace más de un mes).
- **Más monedas:** dólar canadiense, libra esterlina, franco suizo, coronas sueca, noruega, danesa y checa, zloty
  polaco, forinto húngaro y leu rumano. Junto a la tuya, una moneda que usa «$» se escribe US$, CA$, MX$…
- **Cambia el formato de tus datos (esquema 12) y de tus respaldos (formato 12):** TALLY los pone al día solo al
  abrir; tus cuentas de antes quedan en tu moneda. Una versión anterior ya no los abre (sumaría tus dólares como si
  fueran pesos). Los respaldos de antes se siguen restaurando.

## [0.31.0] — Sin publicar

Revisión completa de rapidez y de errores antes de la 1.0. Medido con datos ficticios grandes (5 años, unos 11,600
movimientos y 14 cuentas), abrir las 21 páginas tarda en total **la mitad** que antes (de 13.9 s a unos 7 s); el
Resumen, 75 % menos (de 2.2 s a ~0.55 s) y Contabilidad Técnica, 80 % menos (de 1.7 s a ~0.33 s). Abrir TALLY desde
cero, de unos 2.8 s a 1.8 s.

- **Cálculos mucho más rápidos con años de datos.**
  - El valor de tus bienes (depreciación y avalúos) solo revisa los movimientos de cada bien. Antes recorría todos
    tus movimientos cientos de veces: era lo que hacía lento al Resumen y a Contabilidad.
  - Guardar un cambio con meses ya cerrados ya no compara todos tus movimientos para saber qué meses tocaste.
  - Comparar nombres (reglas automáticas, duplicados, salud de tus datos) es más rápido y se recuerda.
  - Lo que se calcula (Historial, Contabilidad, Gráficas, Tablas dinámicas, Calendario, reglas, salud de tus datos,
    cargos por recuperar…) se recuerda mientras tus datos no cambien: elegir un renglón, abrir una pestaña o volver a
    una página ya no lo recalcula. Cualquier cambio a tus datos lo vuelve a calcular, y al bloquear TALLY con
    contraseña se olvida junto con tus datos.
- **Las páginas solo arman lo que estás viendo.**
  - Pestañas: Contabilidad Técnica, Impuestos, Calendario, Ingresos, Cierre de mes, el préstamo en Deudas y
    Categorías calculan y dibujan solo la pestaña abierta, y recuerdan en cuál estabas aunque cambies de página.
  - Desplegables con formularios, tablas o gráficas (➕ Nueva cuenta, ➕ Agregar un préstamo, la tasa de cada
    tarjeta, aportar a una meta, bienes, inversiones, reglas, categorías, perfiles y conceptos de impuestos, tus meses
    anteriores en el cierre…) se arman al abrirlos; abrirlos solo rehace ese desplegable, no toda la página, y si lo
    dejas abierto sigue abierto al volver. La gráfica por subcategoría del Resumen, igual.
- **Gráficas más ligeras.** Se arman y se mandan al navegador en menos de la mitad del tiempo (se ven igual). Que
  cada gráfica esté bien escrita lo revisan las pruebas, no cada vista.
- **Cada clic, ~0.1 s menos:** Streamlit ya no hace una limpieza de memoria forzada después de cada vista (Python la
  hace por su cuenta cuando hace falta).
- **Abre más rápido.** Mientras tu navegador abre, TALLY ya va cargando lo pesado (las librerías y, si tus datos no
  tienen contraseña, tus datos) con el nuevo `portal/servidor.py`. El respaldo automático del día empieza unos
  segundos después de abrir, para no quitarle velocidad a la primera vista (al cerrar TALLY se espera, como siempre).
- **Arreglo:** el formulario de un perfil de Impuestos aparecía vacío si salías de la página y regresabas (y al
  guardarlo quedaba sin nombre). Ahora se vuelve a llenar con lo guardado.
- **Revisión de errores:** todas las páginas, pestañas y desplegables, con datos vacíos, chicos y grandes y con
  contraseña, en las pruebas y en un navegador real, sin errores; fechas difíciles (29 de febrero, días 29–31) en
  pagos fijos y cortes de tarjeta; y una prueba nueva con cientos de acciones al azar que compara los cálculos
  rápidos contra los lentos.
- No cambia el formato de tus datos ni de tus respaldos.

## [0.30.1] — Sin publicar

- **Mac: TALLY queda en el Dock al instalarlo.** Al terminar `INSTALAR.command`, el ícono de TALLY ya está en el
  Dock, sin arrastrar nada (el Dock se reinicia un instante para mostrarlo). Solo la primera vez: si ya está, no se
  duplica, y si lo quitas, las actualizaciones lo respetan. En Windows no cambia nada (el acceso directo sigue en el
  Escritorio).

## [0.30.0] — Sin publicar

- **TALLY para Mac (con chip de Apple: M1 o más nuevo).** Por dentro es el mismo TALLY; cambia cómo se instala y
  cómo se abre:
  - **`INSTALAR.command`** (clic derecho → Abrir, la primera vez): busca Python 3.13 o descarga el oficial de
    python.org (revisa que esté firmado por la Python Software Foundation) y te pide la contraseña de tu Mac una
    vez. TALLY usa su propio Python en `~/TALLY/_Python`, sin tocar el de tu Mac.
  - Las librerías, con las **mismas versiones** que en Windows y verificadas con su huella
    (`requirements-lock-mac.txt`).
  - Todo vive en **`~/TALLY`** (tus datos, respaldos y el programa), fuera del Escritorio y de iCloud.
  - La app **TALLY** queda en **Aplicaciones** (Launchpad y Spotlight la encuentran; arrástrala al Dock), con el
    color de ícono que elijas en Configuración.
  - En la Mac: «Abrir la carpeta de mis datos» abre Finder; «Elegir carpeta…» de la copia al NAS abre la ventana de
    la Mac; los avisos salen en ventanas de la Mac y los textos hablan de la Mac (rutas como
    `/Volumes/MiNAS/Respaldos`, iCloud en lugar de OneDrive, `INSTALAR.command`).
  - La consulta de precios usa los certificados de seguridad que trae TALLY (el Python de python.org no usa los de
    la Mac).
  - Las Mac con procesador Intel no están incluidas: la librería de cifrado (cryptography 49) ya solo se publica para
    chip de Apple. `INSTALAR.command` lo dice y no cambia nada.
- **Pruebas en una Mac en cada cambio** (GitHub Actions), además de Windows: todas las pruebas, la descarga de Python
  desde python.org y la instalación de punta a punta con `INSTALAR.command` (dos veces, como al actualizar), hasta
  abrir TALLY con la app y comprobar que responde.
- En Windows no cambia nada.

## [0.29.0] — Sin publicar

- **Copia de tus respaldos en tu NAS o disco externo.** En **Configuración › Respaldos › Copia en tu NAS o disco
  externo**:
  - **La carpeta:** con **📁 Elegir carpeta…** se abre la ventana normal de Windows para escogerla (la de «Guardar
    como»), o pegas la ruta (`\\MiNAS\Respaldos`, `E:\Respaldos TALLY`). **Probar la carpeta** revisa que TALLY
    pueda guardar ahí. TALLY la recuerda.
  - **¿Cada cuánto?** Diariamente, Cada semana, Cada mes o Nunca. Se copia al cerrar TALLY (con el botón o cuando se
    apaga solo), o al abrirlo si quedó pendiente (el NAS estaba apagado), y solo si cambiaste algo desde la última
    copia. Con «Nunca», solo cuando le das **Copiar ahora**.
  - **Cuántas copias conservar:** 3 si no eliges otra cosa (de 1 a 30). Las más viejas se borran solas, pero solo
    después de que la nueva quedó completa y revisada: si se cae la red a la mitad, las anteriores siguen ahí.
  - Debajo dice cuándo fue la última copia, o por qué no se pudo («No encuentro la carpeta… ¿está encendido tu
    NAS?»). Si pasa una semana sin poder copiar, el **Resumen** te avisa.
- Todo sigue en tu PC: la copia es un respaldo más (se restaura igual, en **Respaldos y bitácora**). Nada sale a
  internet, TALLY no guarda contraseñas del NAS, y si tus datos tienen contraseña, la copia va cifrada.
- Lo de esta sección es de esta PC (`Datos\copia_externa.json`), no de tus datos: no cambia el formato de tus datos
  ni de tus respaldos.

## [0.28.0] — Sin publicar

- **Gastos hormiga a tu gusto.** En **Cierre de mes › 💸 A dónde se fue**, junto a los gastos hormiga, el botón
  **⚙️ Ajustar** abre una ventana para elegir:
  - **Qué es un gasto chico:** automático (menos del 1 % de lo que gastas en el mes, redondeado, como hasta ahora)
    o **menos de un monto que tú eliges**, que vale igual todos los meses (un mes con una compra grande ya no sube
    el límite).
  - **Subcategorías que nunca cuentan**, como el metro, las casetas o el estacionamiento. Una compra que repartiste
    en varias subcategorías se mide por su total y de ella solo cuenta lo que no excluiste.
  - **Cuándo te lo recomienda el cierre:** si tuviste cierta cantidad o más (antes, siempre 15) o si juntos suman
    cierto % de tus gastos o más (antes, siempre 10 %). Con 0 en los dos ya no te lo recomienda, pero los sigues
    viendo.
  - **Volver a lo de TALLY** regresa a como era.
- Debajo de los gastos hormiga, una línea dice cómo se calcularon: el límite, qué subcategorías no cuentan y cuándo
  te los recomienda.
- Si borras o juntas una subcategoría que no contaba como hormiga, la otra tampoco cuenta.
- Tus ajustes se guardan en tus datos y en tus respaldos (esquema 11, respaldo de formato 11).

## [0.27.2] — Sin publicar

- **Historial: las subcategorías siguen al tipo de movimiento.** Al filtrar por **Ingreso**, la lista de
  Subcategorías ofrecía también las de gasto. Ahora:
  - Gasto o Reembolso: solo subcategorías de gasto; Ingreso o Rendimiento: solo de ingreso; Ajuste y Saldo inicial:
    las suyas; con varios tipos, las de todos; sin tipo elegido, todas.
  - Transferencias y pagos de tarjeta no llevan subcategoría: el filtro dice «No aplica».
  - Si ya habías elegido subcategorías que no son del tipo nuevo, se quitan solas.
  - **Tipos** pasa antes de **Subcategorías** (primero eliges el tipo).
  - Siguen apareciendo las subcategorías archivadas, porque tienen historial.

## [0.27.1] — Sin publicar

- **Categorías: abrir una categoría ya no tarda.** Desde los botones ⚙️ Administrar (0.26.1), abrir o cerrar una
  categoría volvía a armar toda la página, con las cinco pestañas (las cajas de Clasificaciones y Contabilidad tienen
  cientos de etiquetas). Ahora:
  - cada categoría se rehace sola: abrirla o abrir su ⚙️ Administrar no toca lo demás (de ~0.7 a ~0.25 segundos en
    una PC rápida);
  - solo se arma la pestaña que estás viendo, y al volver a Categorías sigue en la última que usaste;
  - guardar desde ⚙️ Administrar también es más rápido (de ~0.85 a ~0.45 segundos).
  - Cambiar de pestaña tarda un poco más que antes (~0.5 segundos), porque ahora se arma al elegirla.
- Cada subcategoría se ve en dos renglones: su nombre y, debajo, su clasificación (en gastos), su rubro contable y
  cuántos movimientos tiene.

## [0.27.0] — Sin publicar

- **Los pagos al fisco salen en tu Calendario.** Si tu perfil de impuestos tiene **🔔 Recordatorio de pago al
  fisco**, lo que te toca pagar aparece en **Calendario › 📅 Próximos 30 días** en su fecha límite (🧾 «Pago al fisco:
  RESICO…», con «ISR e IVA de lo que cobraste en septiembre»), y **cuenta en cómo quedaría tu dinero** día con día, en
  «Sale en 30 días» y en «hasta tu próximo pago» del Resumen.
  - Un periodo que ya terminó: con lo que registraste (o estimado con tu Calendario si no registraste nada).
  - El que va en curso, si su fecha límite cae en los próximos 30 días: **estimado** con lo que llevas cobrado más
    lo que esperas cobrar según tus ingresos fijos (sin contar dos veces lo que ya cobraste).
  - Nueva sección **🧾 Pagos al fisco** abajo de la tabla, con **Ya lo pagué** (como en el Resumen). TALLY sigue sin
    registrar nada: el pago lo registras tú como gasto en IMPUESTOS.
  - Solo los que vencen desde que configuraste el recordatorio, y no los que no tienen nada que pagar.

## [0.26.1] — Sin publicar

- **Categorías: botones ⚙️ Administrar dentro de cada caja.** Ya no hay que bajar hasta «Modificar» y elegir de una
  lista:
  - al abrir una categoría (SALUD, HOGAR…), **⚙️ Administrar categoría** abre una ventana para renombrarla o
    borrarla (pasando sus subcategorías a otra);
  - cada subcategoría tiene su **⚙️ Administrar**: nombre, **mover a otra categoría** («Categoría (para moverla,
    elige otra)», con sus movimientos), clasificación, rubro contable, archivarla o borrarla. Al guardar, la ventana
    se cierra y la caja sigue abierta.
  - Al buscar, cada resultado también trae su ⚙️ Administrar.
- **➕ Nueva subcategoría** y **➕ Nueva categoría** pasan arriba, antes de la lista.
- Las cajas solo se arman al abrirlas: con 20 categorías y más de 100 subcategorías, la página no se hace lenta.

## [0.26.0] — Sin publicar

- **Categorías › Contabilidad: los rubros de TALLY también se editan.** Antes solo los que creabas tú tenían
  **Editar**; los seis de TALLY decían «De TALLY» y no se podían tocar. Ahora todos tienen su botón, como en
  Clasificaciones:
  - **Renombrar** cualquiera («Impuestos» → «Pagos al SAT»). Con su nombre original vuelve a ser como lo trae TALLY.
  - **Borrar** Ingresos por tu trabajo, Ingresos por inversiones y rentas, Gastos financieros o Impuestos. Sus
    subcategorías van a donde las acomodan las demás reglas (por su categoría, o a Gastos de vida / Otros ingresos).
    **Gastos de vida** y **Otros ingresos** no se borran: ahí cae lo que no está en otro rubro.
  - Si te arrepientes, **↩️ Rubros de TALLY que borraste → Recuperar** lo trae de vuelta con su nombre original.
- Arreglado: después de **Acomodar todo de nuevo** (o de borrar o recuperar un rubro), las cajas seguían mostrando
  las subcategorías de antes hasta salir y volver a entrar.
- Arreglado: al borrar un rubro o una clasificación, el **Editar** de la siguiente caja se quedaba abierto solo (con
  su botón de borrar a la mano).
- Tus datos pasan al esquema 10 y los respaldos al formato 10. Una versión anterior de TALLY ya no los abre.

## [0.25.1] — Sin publicar

- **Cuentas: botón ⚙️ Administrar cuenta en cada cuenta.** Ya no hay que bajar hasta «Administrar una cuenta» y
  elegirla de una lista: junto a **Ver movimientos** y **Eliminar**, el botón abre una ventana con **Editar**,
  **Actualizar saldo** y **Saldo inicial** de esa cuenta. Al guardar, la ventana se cierra; con la X o Esc, también.
  **Eliminar** abre su propia ventana, como antes.
- Los botones de cada cuenta miden lo que su texto: en pantallas angostas bajan de renglón en vez de cortarse.
- Las ayudas que decían «Cuentas → Editar» ahora dicen «Cuentas → Administrar cuenta → Editar».

## [0.25.0] — Sin publicar

- **Recordatorio de pago al fisco.** En cada perfil de impuestos (Impuestos › ⚙️ Configurar) hay una sección
  **🔔 Recordatorio de pago al fisco** (opcional):
  - **cada cuándo** pagas esos impuestos (cada mes, 2, 3 o 6 meses, o cada año);
  - **sobre qué ingresos** (las subcategorías donde los registras: HONORARIOS, VENTAS…);
  - **cómo los registras**: lo que te llega a la cuenta (TALLY saca de ahí el monto antes de impuestos) o el
    subtotal;
  - la **fecha límite**: el día del mes y cuántos meses después del periodo (en México, el 17 del mes siguiente).

  Al terminar cada periodo, **el Resumen te dice cuánto pagar y hasta cuándo**, con el desglose («Paga a más tardar
  el 17 de noviembre: $2,070 al fisco · ISR $150 · IVA $1,920, por lo que cobraste en octubre»). Si pasa la fecha
  límite, el aviso se pone en rojo. **TALLY no registra nada**: cuando pagues, lo registras como gasto en IMPUESTOS
  y das clic en **Ya lo pagué**. Si en un periodo no registraste esos ingresos, usa lo que esperas según tu
  Calendario (y lo dice). Solo te recuerda los pagos que vencen desde que lo configuraste.
- **Nueva pestaña Impuestos › 📅 Pagos al fisco**: por cada perfil con recordatorio, los últimos 12 periodos con lo
  cobrado, lo que es antes de impuestos, cada impuesto, lo que toca pagar, la fecha límite y si ya lo pagaste; ahí
  también se marca (o desmarca) un periodo como pagado.
- **Nuevo efecto «Lo pagas tú aparte»** para los impuestos que pagas directo al fisco, como el ISR del RESICO
  cuando le cobras a una persona. No cambia lo que recibes en un recibo; en el cálculo del recibo aparece aparte y
  no se pide al revisar uno.
- En **📅 Pagos al fisco**, un periodo sin ingresos dice **Nada que pagar** (no «Venció»).
- **Lo que toca pagar** es lo que trasladas (el IVA que cobraste) y lo que es a tu cargo, menos lo que ya te
  retuvieron *de ese mismo impuesto* (la retención de 2/3 del IVA se resta del IVA; «Retención ISR», del ISR). Es
  una estimación: no resta el IVA de tus gastos ni otras deducciones.
- Ejemplos nuevos: RESICO a una persona y RESICO a una empresa con su ISR a tu cargo.
- Tus datos pasan al esquema 9 y los respaldos al formato 9. Una versión anterior de TALLY ya no los abre.

## [0.24.1] — Sin publicar

- **Perfiles de impuestos: ya se puede escribir sin batallar.** Los impuestos de un perfil se capturaban en una
  tabla en la que había que dar clic en la celda para escribir; la casilla de la izquierda seleccionaba el renglón
  (para borrarlo) y escondía el ➕, así que parecía que no dejaba escribir. Ahora cada impuesto es un renglón con
  campos normales: nombre, tasa, «Sobre» (una lista con el subtotal y los impuestos de arriba: ya no hay que
  escribirlo) y efecto; **Agregar otro impuesto** y el bote para quitar uno. Con explicación en cada campo («?»).

## [0.24.0] — Sin publicar

- **Rubros contables: ves y decides de dónde sale cada número de tu Contabilidad técnica.** Nueva pestaña
  **Categorías › Contabilidad**, con la misma idea que Clasificaciones: una caja por rubro con sus subcategorías.
  - Rubros de TALLY: **Ingresos por tu trabajo**, **Ingresos por inversiones y rentas**, **Otros ingresos**, **Gastos
    de vida**, **Gastos financieros** (intereses, comisiones, anualidades: cuánto le pagas al banco) e **Impuestos**.
    Puedes crear los tuyos, de ingreso o de gasto («Gastos del negocio», «Vivienda»…), renombrarlos y borrarlos.
  - **TALLY acomoda cada subcategoría solo**: por su nombre (INTERESES… → Gastos financieros, PREDIAL → Impuestos,
    NOMINA → trabajo), por el de su categoría (FINANZAS, INGRESOS INDEPENDIENTES…) o, si nada lo dice, en Gastos de
    vida u Otros ingresos. Si moviste a la mayoría de las subcategorías de una categoría a un mismo rubro, las que
    agregues ahí van con ellas. Al crear una subcategoría o una categoría, TALLY te dice dónde quedó.
  - Para moverla, la agregas en otra caja (sale de donde estaba); con la ✕ regresa a donde la acomoda TALLY. Las que
    moviste tú llevan ✋. También se cambia al editar la subcategoría, y «Que TALLY vuelva a acomodar todo» deshace
    lo que moviste.
  - Un mapa de **qué forma cada reporte y dónde se cambia**: la Situación financiera sale de tus cuentas (según su
    tipo), los Resultados de tus subcategorías, el Flujo de ambos. Y cuánto llevas en el año en cada rubro.
  - Explicaciones en cada parte (los «?»), pensadas para quien no es contador.
- **Contabilidad técnica por rubro contable.** El **Estado de Resultados** muestra cada rubro con su subtotal y, dentro,
  sus categorías (y subcategorías con «Ver cada subcategoría»). En el **Flujo de efectivo**, tu día a día va por rubro
  («Pagaste: Impuestos»), como en el método directo de un contador. La **Balanza** tiene la columna **Rubro**: dónde
  cae cada renglón (el grupo del balance de cada cuenta o el rubro de cada subcategoría). También en el Excel.
  Mover una subcategoría de rubro no cambia ningún total: todo sigue cuadrando.
- En las tablas de Gastos e Ingresos de Categorías, la columna **Rubro contable**.
- Tus datos pasan al esquema 8 y los respaldos al formato 8 (los rubros que creas y lo que mueves). Una versión
  anterior de TALLY ya no abre los datos: así no se pierde nada. Los respaldos anteriores se restauran igual.

## [0.23.6] — Sin publicar

Listo para muchos años de datos. Medido con libros ficticios de unos 6 movimientos al día:

| | 10 años (~22,700 movimientos) | 30 años (~68,000) |
|---|---|---|
| Primera vez que abres TALLY en el día | 4.7 s → **2.1 s** | 16.2 s → **4.9 s** |
| Respaldo (manual o del día) | 1.7 s → **0.8 s** | 6.3 s → **3.6 s** |
| Salud de tus datos | 0.3 s → **0.2 s** | 1.2 s → **0.6 s** |

- **El respaldo automático del día se hace en segundo plano.** TALLY abre de inmediato y el respaldo termina mientras
  ya lo usas; lo que guardes mientras tanto entra en el de mañana. El `.zip` solo aparece completo. Si falla, te avisa
  al siguiente clic. Si cierras TALLY antes de que termine, espera unos segundos a que acabe; si se interrumpe de todos
  modos, se vuelve a hacer la próxima vez que abras. Si pones o quitas tu contraseña mientras se hace, también se
  convierte.
- **Respaldos más rápidos y con menos memoria.** Sin contraseña, el respaldo se arma con lo guardado tal cual, como
  ya se hacía con contraseña: antes se leía todo y se volvía a escribir.
- **Abrir TALLY, casi el doble de rápido con años de datos.** Mientras se cargan tus movimientos, Python ya no se
  detiene una y otra vez a revisar la memoria. Además, los datos y su número de versión se leen del mismo momento,
  aunque otra ventana esté guardando.
- **Arreglado: con más de 15 años de datos, «Salud de tus datos» marcaba como «Fechas muy antiguas» todo lo de antes.**
  Con 30 años eran unos 34,000 avisos, también en el Resumen. Ahora solo marca los movimientos que quedan sueltos, a más
  de un año de todo lo demás (casi siempre el año mal escrito): no importa cuántos años lleves en TALLY.
- **Los filtros de fechas llegan a toda tu historia.** El calendario solo dejaba ir 10 años atrás: en el Historial,
  en el periodo personalizado del Resumen y en Contabilidad técnica ahora puedes elegir cualquier fecha.

## [0.23.5] — Sin publicar

- **«Comparar con» ya aplica a la Balanza de comprobación.** Antes solo cambiaba Situación financiera, Resultados y
  Flujo de efectivo; en la Balanza no pasaba nada. Ahora, al comparar, la Balanza muestra el **saldo final de cada
  cuenta en el otro periodo** y la **diferencia**, también de las cuentas que solo tuvieron movimientos allá (en ceros
  en este periodo). Con «No comparar» esas columnas desaparecen. También van en el Excel.
- La columna «Variación» de la Balanza se llama ahora **«Cambio en el periodo»** (saldo final − saldo inicial del
  mismo periodo), para no confundirla con la comparación.

## [0.23.4] — Sin publicar

- **«✓ Todo guardado» en el menú de la izquierda**, con la hora del último cambio («hoy 6:42 p. m.»). TALLY guarda cada
  cambio en cuanto lo haces: no hay que darle «Guardar» a nada más. El «?» lo explica.

## [0.23.3] — Sin publicar

- **«Lo que te sobró antes de cada pago» usa el nombre de tu ingreso principal.** La gráfica del Resumen ya se
  calculaba con tu ingreso principal (el que marcaste como principal, sea nómina, honorarios o ventas), pero el título
  siempre decía «nómina». Ahora dice, por ejemplo, «antes de cada pago de Honorarios»: el nombre que le pusiste en
  Ingresos o, si aún no lo configuras, el de su subcategoría.
- **Kit de emergencia: un mensaje más claro.** Los 2 caracteres de verificación de la llave atrapan los errores de
  tecleo salvo 1 de cada 1,024. Ese error que se cuela nunca abría nada, pero TALLY decía que la llave «no es la de
  estos datos». Ahora, si termina igual que la de tu Kit, te dice que seguramente hay una letra o número cambiado.
  Las llaves que ya tienes siguen sirviendo igual.
- Pruebas: la del Kit usaba una llave al azar y fallaba cerca de 1 de cada 40 corridas (la falla suelta que veíamos).
  Ahora usa una llave fija y revisa los 744 cambios de una letra posibles.

## [0.23.2] — Sin publicar

- **«Transferencia entre mis cuentas».** Así se llama ahora la opción de Registrar para mover dinero de una de tus
  cuentas a otra (de tu nómina al ahorro, sacar efectivo…): no es gasto ni ingreso.
- **Pasar a transferencia lo que guardaste como gasto o ingreso.** En el Historial, al elegir un gasto o un ingreso,
  la pestaña **↔ Entre mis cuentas**: eliges a qué cuenta fue el dinero (o de cuál vino) y se convierte en
  transferencia —o en pago de tarjeta si fue a una de crédito—, con la misma fecha, importe, descripción, notas y
  comprobantes. Deja de contar como gasto o ingreso y el dinero aparece en la otra cuenta. Las compras a meses sin
  intereses y los cargos temporales no se pueden pasar.

## [0.23.1] — Sin publicar

- **Sacar efectivo ya llega a tu cuenta de Efectivo.** Un retiro de efectivo registrado como gasto en «EFECTIVO ›
  RETIROS DE EFECTIVO» se contaba como gasto y el dinero no llegaba a tu cuenta de efectivo. Si tienes una cuenta de
  efectivo activa, sacar dinero del cajero (o disponer con tu tarjeta) ya no es un gasto, sino un paso de dinero a tu
  cartera; el gasto es lo que pagas después con ese efectivo.
  - **Al registrar:** un gasto en RETIROS DE EFECTIVO se guarda como transferencia a tu cuenta de efectivo y te lo
    dice al guardar.
  - **Al importar del banco:** los retiros en cajero se sugieren como paso a tu cuenta de efectivo.
  - **Lo que ya guardaste así**, desde que llevas tu efectivo en TALLY (la fecha de su saldo inicial), se pasa con un
    clic: en el Historial (al elegir el movimiento) o en Salud de tus datos («Pasarlos a mi efectivo»). Conserva la
    fecha, el importe, la descripción y sus comprobantes. Los de antes no se tocan: ya están dentro del saldo inicial.
  - Sin cuenta de efectivo, RETIROS DE EFECTIVO sigue contando como gasto.
  - Guía y ayuda: «Sacar efectivo del cajero».

## [0.23.0] — Sin publicar

Cinco mejoras, integradas con lo que ya había:

- **⚡ Reglas automáticas de categorías** (Categorías › ⚡ Reglas automáticas). «Si la descripción dice OXXO, va a
  SNACKS Y ANTOJOS», en todas tus cuentas o solo en una.
  - Se usan al **importar del banco** (antes que lo aprendido de tu historial y que los comercios conocidos), al
    **registrar** sin elegir subcategoría y en la **plantilla de Excel** con la subcategoría vacía.
  - Da igual mayúsculas, acentos y signos; el texto debe empezar una palabra («UBER» encuentra «UBER EATS», no
    «SUBERO»). Si varias coinciden, gana la más precisa (el texto más largo) y la de esa cuenta.
  - **Probar** una descripción, **sugerencias** con lo que más se repite en tu historial (se crean con un clic) y
    **corregir tu historial**: los movimientos que ya tienes y que tus reglas mandarían a otra subcategoría, con vista
    previa antes de cambiarlos.
  - Al importar del banco, el botón **⚡** junto a cada grupo que TALLY no reconoce crea la regla al momento.
  - Borrar una subcategoría pasa sus reglas a la otra (o las borra); borrar una cuenta borra las suyas.
- **🎯 Plan para salir de deudas** (Deudas). Pones cuánto puedes pagar al mes entre todas tus tarjetas y préstamos:
  - cada mes se paga el mínimo de cada una (las mensualidades a meses sin intereses aparte, sin intereses) y lo que
    sobra va a una sola; al terminarla, lo que le pagabas pasa a la siguiente;
  - **avalancha** (la tasa más alta primero) o **bola de nieve** (la que debes menos primero), con cuál te conviene,
    cuándo terminas, cuánto pagas de intereses y cuánto te ahorras contra pagar solo los mínimos, y la gráfica;
  - el orden de ataque y **cuánto pagar a cada una este mes**. Guárdalo y el Resumen te lo recuerda.
- **📎 Comprobantes adjuntos.** La foto del ticket, el PDF o el XML de la factura en cada movimiento (Historial →
  📎 Comprobantes, o al registrar).
  - Se guardan **dentro de tu archivo de datos**, en la misma transacción que el movimiento, cifrados si tienes
    contraseña (también al ponerla o quitarla), y **van en tus respaldos** con su huella para comprobarlos al
    restaurar. Borrar el movimiento borra sus comprobantes.
  - Se revisa que el archivo sea de verdad lo que dice (JPG, PNG, WEBP, HEIC, PDF, XML), hasta 10 MB; avisa si el
    mismo archivo está en otro movimiento (¿un gasto registrado dos veces?).
  - En **Impuestos**: cuáles de tus deducibles no tienen comprobante y **todos los del año en un `.zip`** (una carpeta
    por concepto e `indice.csv` para Excel), para tu contador o tu declaración.
- **🩺 Salud de tus datos** (Ajustes). Revisa lo que suele ser un error o algo incompleto: movimientos que parecen
  **duplicados** (se borra el que sobra desde ahí), cuentas de débito o ahorro **en negativo**, tarjetas **pasadas de
  su límite**, **fechas** de otro año, cargos temporales sin devolver, movimientos en OTROS GASTOS o sin descripción,
  tarjetas y préstamos **sin sus datos**, cuentas sin movimientos, lo que tus reglas acomodarían distinto y deducibles
  sin comprobante. Cada cosa dice dónde se arregla; «Está bien así» la oculta. El Resumen avisa solo lo importante.
- **❓ Guía y ayuda.** Tus **primeros pasos** (cuentas, movimientos, ingreso, pagos fijos, tarjetas, presupuestos,
  metas… y opcionales) se marcan **solos** con tus datos; el Resumen muestra el siguiente mientras falte algo (se
  puede ocultar). «¿Cómo hago…?» con buscador y las palabras que usa TALLY.
- Datos: esquema 7 y respaldos de formato 7 (reglas, comprobantes y la tabla de archivos). Los respaldos anteriores
  se siguen restaurando.

## [0.22.0] — Sin publicar

- **Lo que sale, en rojo.** Los importes negativos (gastos, salidas, ahorro en contra, saldos y diferencias que
  bajan, pérdidas) se ven en rojo en toda la app; los ingresos y lo positivo, en el color normal del texto.
  - En las métricas grandes (por ejemplo «Ahorro real» cuando gastaste más de lo que entró), en los textos y avisos,
    y en las tablas: Historial, estado de cuenta (la columna «Salida» completa), Cierre de mes, Contabilidad,
    Tablas dinámicas, Inversiones, Deudas…
  - Funciona con cualquier moneda (`-$300.00`, `-1.234,56 €`, `-S/ 99.90`) y con el tema oscuro.
- **Tablas muy largas:** el Historial y el estado de cuenta muestran los primeros 2,000 movimientos (con colores) y
  un interruptor «Ver los …» para verlos todos. Pintar decenas de miles de celdas tardaría segundos.

## [0.21.1] — Sin publicar

Correcciones de los avisos y del bloqueo automático, probadas en un navegador real:

- **Los avisos ven lo que ya registraste a futuro.** Si la renta de la otra semana ya está registrada, un gasto de hoy
  que no deja para pagarla avisa, con el día en que la cuenta quedaría en negativo (o la tarjeta pasaría su límite).
- **Solo avisa cuando ese movimiento cruza la línea.** Si la cuenta ya estaba en negativo (o la tarjeta ya pasaba su
  límite), no pide confirmar cada gasto. Se revisa día por día: si solo un día de más adelante ya queda en negativo,
  un cero de más en el gasto de hoy sigue avisando.
- **Más claro qué hacer:** el aviso dice «**Todavía no se guardó**» y que hay que marcar «Sí, está bien así» y dar
  Guardar otra vez; si das Guardar sin marcarla, te lo recuerda. Pregunta si están bien la cuenta (o la tarjeta) **y
  el importe**, y el de la tarjeta dice «tu deuda quedaría en…».
- **Lo que falta se pide primero:** sin subcategoría ya no sale el aviso antes del error, y si faltan la subcategoría
  y el importe los pide juntos.
- **Repartir:** un renglón con subcategoría y sin importe (o al revés) ya no tumba la página: pide completarlo o
  borrarlo.
- **La ventanita de Cuentas → Agregar movimiento** se abre limpia cada vez (en Gasto y con los interruptores
  apagados), aunque antes la hayas cerrado con la X.
- «Transferencia de $100.00 guarda**da**».
- **Bloqueo automático:**
  - lo que haces dentro de una ventanita (Agregar movimiento, Ya me lo devolvieron, Eliminar cuenta…) cuenta como
    usar TALLY: ya no se bloquea a media captura;
  - todas las pestañas abiertas vuelven a la contraseña al bloquearse, también las que se abrieron antes de poner la
    contraseña o de prender el bloqueo;
  - la pantalla de entrada explica cuando TALLY se bloqueó solo;
  - en Configuración, el ajuste se guarda solo cuando tú lo cambias (otra pestaña abierta ya no lo regresa a su valor
    viejo), abajo dice cuál quedó (antes, un mensaje podía quedarse con el valor anterior) y al volver de otra página
    el interruptor muestra cómo está de verdad;
  - textos más claros: qué cuenta como usarlo, que lo escrito sin guardar se pierde y que al poner contraseña queda
    prendido en 10 minutos.

## [0.21.0] — Sin publicar

- **Avisos antes de guardar** (Registrar, y Cuentas → Agregar movimiento). Si algo parece un error de dedo, TALLY lo
  dice dentro del formulario y no guarda hasta que lo corrijas o marques «Sí, está bien: guárdalo así»:
  - una cuenta de débito, ahorro, efectivo o inversión **quedaría en negativo** (¿la cuenta equivocada?, ¿un cero de
    más?);
  - una tarjeta de crédito **pasaría su límite**;
  - la **fecha** es de más de un mes adelante o de hace un año o más (¿el año mal escrito?).

  Lo que escribiste ya no se borra si algo falta o hay que corregir: el formulario se limpia solo al guardar.
- **Bloqueo automático a tu manera** (Configuración → Seguridad, solo con contraseña):
  - un interruptor para prenderlo o apagarlo;
  - tras cuánto tiempo sin usar TALLY: 5, 10, 15, 25, 30 o 45 minutos, o 1 hora (viene en 10 minutos);
  - al pasar ese tiempo, **la pantalla vuelve sola a pedir tu contraseña**, aunque no toques nada. Antes se bloqueaba
    hasta tu siguiente clic, y mientras tanto tus datos seguían a la vista.
  - Sin contraseña aparece apagado y explica que se activa cuando le pones una: sin contraseña no hay pantalla a
    dónde volver a entrar.

## [0.20.0] — Sin publicar

**Rápido aunque tengas muchos años de datos.** Medido con un libro ficticio de 10 años (unos 22,700 movimientos):

| Qué | Antes | Ahora |
|---|---|---|
| Primera vez que abres TALLY en el día (con su respaldo automático) | 6.5 s | 2.4 s |
| Respaldo automático del día | 8.5 s | 1 s |
| Guardar cada cambio (registrar, editar, borrar…) | 0.17–0.3 s | 0.03 s |
| Deshacer tras un error (un dato mal escrito) | 0.35 s | 0.04 s |
| Tablas dinámicas | 3.1 s | 0.13 s |
| Cuentas | 0.8 s | 0.03 s |
| Resumen | 0.5 s | 0.16 s |
| Registrar | 0.2 s | 0.01 s |
| Calendario, Deudas, Ingresos, Cierre de mes, Presupuestos | 0.1–0.2 s | 0.02–0.06 s |

- **Movimientos y saldos con índice:** TALLY guarda tus movimientos en orden y el saldo acumulado de cada cuenta, y
  los rehace solo cuando algo cambia. Pedir los de un mes o el saldo a una fecha ya no recorre todo tu historial.
- **Guardar solo lo que cambió:** al guardar ya no se vuelven a convertir los miles de movimientos que no cambiaron.
- **Respaldos compactos:** el archivo de respaldo se escribe sin espacios de sobra (más rápido y más chico). Los
  respaldos de antes se siguen restaurando igual.
- **Excel y CSV solo cuando los descargas:** las páginas ya no arman el archivo en cada clic; se genera al presionar
  «Descargar».

## [0.19.0] — Sin publicar

- **Tu moneda, la de tu país.** En la bienvenida y en Configuración → Tu perfil eliges tu moneda: peso mexicano,
  dólar, euro, pesos argentino, colombiano, chileno, uruguayo, dominicano y cubano, sol, guaraní, boliviano, bolívar,
  quetzal, lempira, córdoba o colón.
  - Todo TALLY la usa con su símbolo y su formato: `$1,234.56`, `1.234,56 €`, `$ 1.234,56`, `$1.235` (sin centavos
    en Chile, Colombia y Paraguay), `S/ 1,234.56`…
  - La usan las métricas, las tablas, los ejes de las gráficas, los mensajes, las recomendaciones y el Excel que
    descargas (el formato de dinero de Excel lleva tu símbolo).
  - Cambiarla **no convierte** importes (no es un tipo de cambio): solo cambia cómo se ven. Conviene elegirla al
    empezar.
- **Inversiones contra tu moneda.** El tipo de cambio ya no es siempre contra el peso mexicano: un título en dólares
  se valúa en tu moneda (USDEUR=X en España, USDARS=X en Argentina…). Los textos dicen «cuántos ARS por 1 USD»,
  ya no «pesos por 1 USD».
- **Umbrales que valen en cualquier moneda.** Gasto hormiga, «esta categoría subió» y el redondeo de los presupuestos
  sugeridos se calculan en proporción a tus propios gastos, no con montos fijos en pesos mexicanos.
- **Cargar datos lee importes de cualquier país:** `1.234,56 €`, `S/ 99.90`, `1 234,50`…
- **Las fechas de las gráficas, en español** («12 jul», no «12 Jul»).
- El IVA de Configuración explica que en muchos países los intereses no llevan IVA.

## [0.18.0] — Sin publicar

- **Nueva página 📆 Cierre de mes** (en Análisis): la boleta de cada mes.
  - **El resultado:** cuánto entró, cuánto salió y cuánto ahorraste, contra tu meta de ahorro, el mes anterior y tu
    promedio de los meses previos.
  - **A dónde se fue:** cada categoría contra tu promedio (marca las que subieron), los **gastos hormiga** (muchos
    gastos de menos de $100) y las suscripciones que te cobraron.
  - **Presupuestos** cumplidos o no, **ingresos fijos** que llegaron o faltan, **deudas** al empezar y al terminar con
    los intereses y comisiones que pagaste, **metas** y **patrimonio**.
  - **Para cerrar bien:** lo que falta registrar (pagos del calendario, cargos temporales, el pago de una tarjeta),
    con casillas para ir marcando.
  - **3 recomendaciones** para el mes siguiente, calculadas con tus números (nada sale de tu computadora).
  - **Descarga en Excel** (resumen, recomendaciones, categorías, presupuestos, deudas, pendientes y movimientos) e
    historial de tus meses anteriores.
- **Cerrar un mes no lo bloquea.** Guarda cómo estaban sus números. Si después registras, corriges o borras algo de
  ese mes, TALLY te avisa al momento y el cierre lo muestra como **cambios después de cerrar**. Puedes volver a
  cerrarlo para aceptarlos, o quitar el cierre.
- **Resumen:** los primeros 10 días del mes te recuerda revisar el cierre del mes anterior.

## [0.17.2] — Sin publicar

- **Deudas sabe lo que ya pagaste de tu tarjeta.** Antes seguía pidiendo «para no generar intereses» y avisaba del
  mínimo aunque ya hubieras pagado el corte (Cuentas sí lo mostraba al corriente). Ahora:
  - lo que abonas después del corte baja lo que falta y el pago mínimo;
  - si ya lo pagaste completo, dice «Ya pagaste el corte» y no avisa nada;
  - la capacidad de pago tampoco lo cuenta.
- **Préstamos:** si adelantas el pago del mes (hasta 7 días antes), el próximo pago pasa al mes siguiente en Deudas y
  en el Calendario. El día que te toca pagar se muestra como hoy, no el mes siguiente.
- **Impuestos, 100 % tuyo:** se quitaron las plantillas. En su lugar, ejemplos por país (México, España, Argentina,
  Colombia, Perú, Chile) que explican cómo armar tus deducibles y tus perfiles, y una calculadora de tu tasa
  aproximada de ISR o IRPF (lo que pagaste ÷ tus ingresos). Nada se agrega solo.
  - Cada concepto deducible y cada perfil tiene su botón **Borrar** a la vista.
  - **Borrar todos mis deducibles** (con confirmación) y notas editables.
  - La tabla de un perfil nuevo empieza con un renglón vacío y claro.
- **Todo lo que agregas se puede quitar:**
  - **Quitar mi ingreso principal** (en Ingresos);
  - **Quitar todos mis presupuestos** (en Presupuestos);
  - en un préstamo, cómo borrarlo desde Cuentas.

## [0.17.1] — Sin publicar

Correcciones antes de la 1.0:

- **Impuestos e Ingresos ya no se caen al borrar una subcategoría.** Antes, borrar (o juntar con otra) una
  subcategoría que estaba en un gasto deducible dejaba la página Impuestos sin abrir, y borrar la de un ingreso fijo
  hacía lo mismo con Ingresos.
  - Al juntar, tus gastos deducibles pasan a la otra subcategoría; al borrarla sin más, se quita del concepto.
  - Un ingreso fijo que se queda sin subcategoría dice «❓ Elige la subcategoría», como ya hacía el Calendario.
  - Si tus datos ya habían quedado así, las páginas abren y solo dejan de ofrecer la subcategoría que ya no existe.
- **«vs. periodo anterior» compara contra el periodo correcto:**
  - un año contra el año anterior completo, aunque uno sea bisiesto (antes, 2025 contra 2024 se saltaba el
    1 de enero);
  - una quincena contra la quincena anterior (antes, la del 16 al 31 se comparaba con «30 de junio al 15 de julio»);
  - los últimos 12 meses, un trimestre o un año exacto, contra los mismos meses de antes.
  - También en los comparativos de Contabilidad Técnica.
- **Resumen a mitad de mes:** lo que llevas del mes se compara con **los mismos días del mes pasado** (el 7 de
  octubre, del 1 al 7 de septiembre), y lo dice abajo de las cifras. Antes se comparaba con el mes pasado completo, así
  que a principio de mes siempre parecía que gastabas mucho menos.
- **Metas: el aporte sigue a su transferencia.** Si en el Historial borras la transferencia de un aporte (o de un
  retiro), también se quita de la meta; si la corriges, la meta toma su nueva fecha e importe. Antes la meta seguía
  contando un dinero que ya no estaba en la cuenta. Al borrar, el Historial avisa de qué meta es.

## [0.17.0] — Sin publicar

- **Nueva página 💰 Ingresos** (en Tu dinero). Sale de Presupuestos y tiene su lugar propio:
  - **Tu ingreso principal:** cada cuánto te pagan (quincena, catorcena, semana o mes), a qué cuenta y cuánto. En
    quincena, la **1.ª (la del 15) y la 2.ª (la de fin de mes)** pueden ser distintas por centavos (retenciones,
    redondeos).
  - **Si el día de pago cae en sábado o domingo:** se adelanta al viernes, se pasa al lunes o se queda igual. Vale
    también para cualquier pago fijo del Calendario.
  - **¿Cuánto te tiene que durar?** Cada pago y los días que tiene que durarte. No todas las quincenas duran lo
    mismo: si el 15 cae en domingo te pagan el viernes 13 y ese dinero tiene que durar hasta fin de mes. TALLY
    avisa de los periodos más largos de lo normal y cuánto tocas al día.
  - **Hasta tu próximo pago:** con tu dinero disponible y lo que te toca pagar y cobrar antes, cuánto puedes gastar
    al día.
  - **Otros ingresos fijos** (una renta, honorarios…) y **tu ingreso al mes** (principal, secundarios, el que
    escribes a mano y tu meta de ahorro).
- **Registrar tu nómina sin teclear:** en Registrar → Ingreso, elige uno de tus ingresos fijos y la fecha; TALLY
  llena el importe de esa quincena, la subcategoría, la cuenta y la descripción. Lo puedes corregir antes de guardar.
- **Ingreso esperado:** mientras no tengas meses completos registrados, es lo que configuraste en tus ingresos
  fijos. El primer mes a medias y los saldos iniciales ya no bajan el promedio (tampoco el de tus gastos).
- **Enlaces con su cajita:** los enlaces a otras páginas (por ejemplo «Cargar datos desde Excel» en Configuración)
  se ven como botones.

## [0.16.0] — Sin publicar

- **Nueva página 🧾 Impuestos** (en Análisis), **para cualquier país**. TALLY no supone las leyes de ningún lugar:
  tú pones las reglas, y hay **plantillas** para empezar que puedes cambiar. Todo es una referencia; lo oficial lo
  dice tu autoridad fiscal o tu contador.
  - **Gastos deducibles del año.** Defines *conceptos* (gastos médicos, colegiaturas, alquiler…) con:
    - las subcategorías que cuentan;
    - qué parte se deduce (100 %, 40 %…);
    - un tope al año;
    - si deja fuera lo pagado en efectivo;
    - si entra o no en el **tope total** (un monto, un % de tus ingresos, o el menor de los dos).

    El reporte muestra lo pagado, lo que no cuenta por efectivo, lo deducible y lo topado, cada pago, y se
    descarga en Excel.
  - **Calcular un recibo o factura** con un *perfil de impuestos*. Cada impuesto tiene su tasa, se calcula sobre
    el subtotal u otro impuesto (por ejemplo «2/3 del IVA»; la tasa acepta fracciones) y se suma o se retiene. Se
    calcula desde el subtotal o **desde lo que recibes**, al centavo.
  - **Revisar un recibo que te dieron:** compara cada impuesto con lo que corresponde (tolerancia de $1 por
    redondeos), dice qué no cuadra y por qué, y detecta un impuesto capturado en el lugar de otro.
  - **Plantillas de deducibles:** México (persona física: médicos, lentes, seguro de gastos médicos, colegiaturas
    y donativos, tope del 15 %) y Argentina (Ganancias).
  - **Plantillas de perfiles:** México (honorarios en régimen general y en RESICO, venta con IVA), España
    (autónomo, IVA e IRPF), Argentina (IVA 21 %) y Colombia (IVA 19 %).

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
