# Modelo contable de TALLY

> Documento de referencia del motor financiero. Toda regla aquí descrita vive
> en `motor/` y está cubierta por pruebas en `tests/`. El portal nunca la
> reimplementa.

## 1. Idea central

El usuario registra **operaciones** ("comí en un restaurante", "pagué la
tarjeta", "pasé dinero al ahorro"). Internamente cada operación se guarda como
**2 o más partidas** que **siempre suman cero**.

Cada partida afecta a **una cuenta** (débito, TDC, ahorro…) **o a una
categoría** (Alimentos, Nómina…), nunca a ambas.

De ahí se derivan todas las cifras:

| Cifra | Cálculo |
|---|---|
| Saldo de una cuenta | Suma de sus partidas hasta la fecha |
| Gastos del periodo | Suma de partidas en categorías de **gasto** |
| Ingresos del periodo | −(suma de partidas en categorías de **ingreso**) |

Una transferencia o un pago de tarjeta **solo tiene partidas de cuentas**, así
que es imposible que aparezca como gasto o ingreso.

El campo `tipo` de la operación sirve para la interfaz y para validar; los
reportes **no** dependen de él, solo de las partidas.

## 2. Convención de signos

- **Partida de cuenta:** cambio en el saldo desde el punto de vista del
  usuario (+ entra dinero / baja la deuda, − sale dinero / sube la deuda).
- **Partida de categoría:** el signo opuesto, para que la operación sume cero.
- Una **tarjeta de crédito** con saldo **−800** significa **deuda de $800**.
  Saldo positivo en una TDC = saldo a favor.
- Todo importe se guarda en **centavos enteros** (`int`). Nunca `float`.

## 3. Tabla de reglas

| # | Caso | Partidas | Efecto en reportes |
|---|---|---|---|
| 1 | Ingreso (nómina a débito) | Débito +10,000 · Nómina −10,000 | Ingresos +10,000 |
| 2 | Gasto con débito | Débito −300 · Alimentos +300 | Gastos +300 |
| 3 | Débito → Ahorro | Débito −3,000 · Ahorro +3,000 | Nada (apartado a ahorro +3,000) |
| 4 | Compra con TDC | TDC −500 · Restaurante +500 | Gastos +500, deuda 500 |
| 5 | Pago de TDC | Débito −500 · TDC +500 | **Gastos +0**, deuda 0 |
| 6 | Reembolso / devolución | Cuenta +200 · Categoría de gasto −200 | Gasto neto de la categoría baja 200 |
| 7 | Ajuste de saldo | Cuenta ±X · [Ajuste de saldo] ∓X | Fuera de ingresos y gastos |
| 8 | Saldo inicial | Cuenta ±X · [Saldo inicial] ∓X | Fuera de ingresos y gastos |
| 9 | Intereses / comisiones de TDC | TDC −350 · Gastos financieros +350 | Gasto |
| 10 | Rendimientos (actualizar saldo de ahorro/inversión) | Cuenta ±X · Intereses y rendimientos ∓X | Ingreso (neto, puede ser negativo si hubo pérdida) |
| 11 | Retiro de efectivo | Débito −600 · Retiros de efectivo +600 | Gasto (decisión del usuario: el efectivo no se rastrea) |
| 12 | Prestar / pagar algo de un tercero | Débito −700 · Por cobrar +700 | Nada (es una transferencia) |
| 13 | El tercero me paga | Por cobrar −700 · Débito +700 | Nada |
| 14 | Pago mayor a la deuda de TDC | TDC +600 con deuda 500 | TDC queda en +100 (a favor) |

[Ajuste de saldo] y [Saldo inicial] son categorías **del sistema**: no se
pueden borrar ni renombrar, y nunca entran en ingresos ni gastos.

## 4. Tipos de operación y validaciones

| Tipo | Partidas permitidas |
|---|---|
| `GASTO` | 1 cuenta (−) y 1 o más categorías de gasto (+) |
| `INGRESO` | 1 cuenta (+) y 1 o más categorías de ingreso (−) |
| `REEMBOLSO` | 1 cuenta (+) y 1 o más categorías de gasto (−) |
| `TRANSFERENCIA` | 2 cuentas distintas, sin categorías |
| `PAGO_TARJETA` | Igual que una transferencia; el destino es una cuenta de crédito |
| `RENDIMIENTO` | 1 cuenta y 1 categoría de ingreso, con cualquier signo |
| `AJUSTE` | 1 cuenta y [Ajuste de saldo], con cualquier signo |
| `SALDO_INICIAL` | 1 cuenta y [Saldo inicial]; máximo uno por cuenta |

Validaciones generales:

- Las partidas suman exactamente 0.
- Los importes capturados son > 0 (el signo lo pone el motor). Las excepciones
  son `RENDIMIENTO` y `AJUSTE`, que se generan desde "Actualizar saldo".
- Las cuentas y categorías referidas existen.
- No se registran operaciones nuevas en cuentas o categorías archivadas.

## 5. Cuentas

Tipos: `DEBITO`, `AHORRO`, `CREDITO`, `EFECTIVO`, `INVERSION`, `POR_COBRAR`,
`OTRA`.

Se puede tener **cualquier número** de cuentas de cada tipo; nada en el modelo
asume una sola TDD o una sola TDC.

Campos:

- id
- nombre
- tipo
- institución (opcional)
- moneda (MXN)
- fecha de creación
- activa
- `en_disponible`
- notas
- orden
- Solo para crédito: límite, día de corte y día de pago (opcionales)

- **Archivar** en lugar de borrar cuando la cuenta tiene movimientos. Una
  cuenta archivada con saldo distinto de cero sigue contando en el patrimonio.
- **Tarjeta de débito:** no es una entidad aparte. La cuenta de tipo `DEBITO`
  es la cuenta bancaria.

## 6. Categorías, subcategorías y clasificaciones

| En el portal | En el motor | Qué es |
|---|---|---|
| Categoría | `Rubro` | Caja que agrupa (SALUD, TECNOLOGIA…). De gasto o de ingreso |
| Subcategoría | `Categoria` | Lo que lleva cada partida (DENTISTA, GASOLINA…). Vive en un rubro de su misma clase |
| Clasificación | `Grupo` | Para qué es el gasto (la "Clasif. Metas" del Excel): Necesidad, Compromisos, Estabilidad, Crecimiento, Disfrute, Antojos y Generosidad. Cada subcategoría está en una sola |

- Las partidas solo apuntan a subcategorías. Un rubro nunca tiene movimientos
  propios: sus totales son la suma de sus subcategorías.
- Una subcategoría tiene una clase: `INGRESO`, `GASTO` o `SISTEMA`. Las del
  sistema (AJUSTE DE SALDO, SALDO INICIAL) no están en ningún rubro.
- Nombres de rubros y subcategorías: MAYÚSCULAS y sin acentos (la Ñ se
  conserva). Se comparan sin importar mayúsculas, acentos, signos ni
  espacios: cada subcategoría existe una sola vez en todo el libro, y cada
  rubro también (`motor/textos.py`).
- Una subcategoría de ingreso puede marcarse como **principal** (p. ej.
  NOMINA). Así se detectan las quincenas.
- Borrar una subcategoría con movimientos exige pasarlos a otra (fusión).
  Borrar un rubro con subcategorías exige pasarlas a otro de la misma clase.
- El catálogo inicial está en `motor/catalogo.py`. Los datos de TALLY 0.3 se
  ponen al día una sola vez al abrirlos: nombres estandarizados (si dos
  chocan, la segunda queda como «NOMBRE (2)»), cada subcategoría en su rubro
  del catálogo o en VARIOS / INGRESOS VARIOS, y las del catálogo que falten.

## 6 bis. Carga masiva

`motor/importacion.py` lee la plantilla de texto (un bloque por cuenta) y
aplica las mismas reglas de la tabla 3:

| Columna SUBCATEGORIA | CARGO | ABONO |
|---|---|---|
| Subcategoría de gasto | Gasto | Reembolso |
| Subcategoría de ingreso | Rendimiento negativo | Ingreso |
| AJUSTE DE SALDO | Ajuste (−) | Ajuste (+) |
| Otra cuenta propia | Transferencia hacia ella | Transferencia desde ella |

- Si el destino de la transferencia es una tarjeta de crédito, es un pago de
  tarjeta.
- Una transferencia que viene en los bloques de las dos cuentas se carga una
  vez.
- Lo que ya existe se omite: misma fecha, tipo y partidas, sin importar la
  descripción.
- Es todo o nada: con un solo error no se carga ninguna fila.

## 7. Indicadores

| Indicador | Definición |
|---|---|
| Dinero disponible | Suma de los saldos de las cuentas con `en_disponible` (por defecto: débito y efectivo) |
| Total en cuentas | Suma de las cuentas `DEBITO`, `AHORRO`, `EFECTIVO`, `INVERSION` y `OTRA` |
| Te deben | Suma de las cuentas `POR_COBRAR` |
| Deuda de tarjetas | Suma de los saldos negativos de las cuentas `CREDITO` |
| Patrimonio neto | Suma de todos los saldos |
| Ingresos / Gastos | Partidas de categoría en el periodo |
| Ahorro real | Ingresos − Gastos |
| Apartado a ahorro | Transferencias netas desde otras cuentas hacia `AHORRO` / `INVERSION` |
| Ajustes | Partidas de [Ajuste de saldo] en el periodo; se muestran aparte |

## 8. Periodos

Los reportes aceptan cualquier rango de fechas. El motor ofrece además:

- **Mes calendario.**
- **Quincena:** de una nómina (ingreso principal) a la siguiente. El
  **sobrante de la quincena** es el saldo de la cuenta justo antes de recibir
  la siguiente nómina. Reemplaza las filas "HISTORICO" del Excel.
- **Ciclo de TDC:** según el día de corte. Muestra los cargos y abonos del
  ciclo, el saldo al corte y cuánto falta por liquidar.
- **Fecha límite de pago** (la regla del contrato de cada tarjeta):
  - **N días después del corte**, contados como naturales o como hábiles.
    Ejemplo: «hasta 10 días naturales contados a partir de la fecha de corte».
  - o **un día fijo del mes** (el siguiente después del corte).
  - Si la fecha cae en sábado, domingo o día inhábil bancario, se recorre al
    siguiente día hábil, salvo que la tarjeta indique lo contrario.
  - Los días inhábiles bancarios de México se calculan para cualquier año en
    `motor/calendario.py`, incluidos los jueves y viernes santos.

Dentro de un mismo día, el orden de las operaciones es el de su captura.

## 9. Edición y borrado

- **Editar** reemplaza la operación completa. Una transferencia se edita como
  una sola operación, así que sus dos lados no pueden desincronizarse.
- **Borrar** la elimina con confirmación en el portal. La bitácora (Fase 2)
  conservará una copia completa.

## 10. Decisiones registradas

| Tema | Decisión |
|---|---|
| Moneda | Solo MXN en v1. El campo existe para el futuro |
| Retiros de efectivo | Cuentan como gasto (categoría "Retiros de efectivo"). No hay cuenta de efectivo obligatoria |
| Reembolsos | Restan del gasto de su categoría en la fecha en que llegan |
| Gastos de terceros | Cuenta `POR_COBRAR` (transferencias), no ingreso ni gasto |
| Inversiones | Cuenta `INVERSION`. Su valor se actualiza con "Actualizar saldo" → `RENDIMIENTO` |
| Meses sin intereses | El gasto completo cuenta en la fecha de compra (`Operacion.msi`). La tarjeta solo exige una mensualidad por corte, desde el corte que cierra el ciclo de la compra; la primera mensualidad lleva los centavos que no dividen exacto. «Por liquidar» = deuda al corte − mensualidades futuras − pagos posteriores |
| Cargos temporales | Verificaciones de tarjeta y depósitos que te devuelven: transferencia de tu cuenta a la cuenta `POR RECUPERAR` (tipo `POR_COBRAR`), nunca gasto. La devolución es la transferencia de regreso y guarda en `Operacion.liquida` el cargo que liquida; si no te lo devuelven, un gasto desde `POR RECUPERAR` con `liquida`. Las devoluciones sin liga (carga masiva) se emparejan con el cargo pendiente más antiguo del mismo importe (`motor/temporales.py`) |
| Presupuestos | Tope mensual por categoría de gasto (`Rubro.presupuesto`); se compara con el gasto neto del mes |
| Títulos e inversiones a plazo | `OperacionValor` (compra/venta: símbolo, títulos, precio, moneda, tipo de cambio, comisión) e `InversionPlazo` (monto, tasa anual, plazo). Son un detalle de la cuenta de inversión, no movimientos: no cambian el saldo. Costo promedio en pesos al tipo de cambio de cada compra. Plazos: interés simple, año de 360 días, antes de impuestos (`motor/portafolio.py`) |
| Ganancia de inversiones | Solo entra a la contabilidad con el **valor oficial** que escribe el usuario (`portafolio.ajustar_a_valor_oficial`): un `RENDIMIENTO` (INTERESES Y RENDIMIENTOS) por la diferencia entre ese valor y el saldo de la cuenta en esa fecha. Así coincide al centavo con la app oficial, incluido el efectivo, los dividendos y las comisiones. Registrar el mismo valor otra vez no agrega nada. `Cuenta.plusvalia_registrada` acumula lo registrado, solo como referencia del valor aproximado |
| Precios de mercado | Opcionales y solo de consulta (`motor/cotizaciones.py`): Yahoo Finance, solo se envía el símbolo (y, para el historial, un periodo estándar); sin conexión, precio a mano |
| Estados financieros | `motor/contabilidad.py`, derivados de las partidas (partida positiva = Debe, negativa = Haber). Cuentas de débito, ahorro y efectivo son Activo (efectivo y bancos); inversión, Activo (inversiones); por cobrar, Activo; tarjeta de crédito, Pasivo de corto plazo. Ingresos y gastos son Resultados (subcategoría = subcuenta). SALDO INICIAL es el patrimonio inicial y AJUSTE DE SALDO es resultado. Patrimonio = inicial + resultados acumulados, así que Activo = Pasivo + Patrimonio siempre. Los `RENDIMIENTO` de cuentas de inversión se muestran aparte del día a día. El flujo de efectivo usa el método directo sobre las cuentas de efectivo y clasifica cada movimiento por su contrapartida. En la balanza, las cuentas de resultados empiezan cada periodo en cero y lo anterior queda en «Resultados de periodos anteriores» |
| Bienes | Cuenta `BIEN` + entidad `Bien` (`motor/bienes.py`). Costo = movimientos de la cuenta: la compra y las mejoras son transferencias, no gasto; si ya lo tenías, su valor es el saldo inicial. Depreciación (línea recta con vida y rescate, decreciente con % anual y rescate, o ninguna) y avalúos **calculados**, no guardados. Cada compra o mejora se deprecia desde su fecha. Un avalúo fija el valor y reinicia la depreciación con la vida restante. La venta registra la transferencia del precio y un `AJUSTE` contra «VENTA DE BIENES» (sistema) por la diferencia con el valor del día, y la cuenta queda en ceros. En los estados financieros entran como asientos calculados: depreciación acumulada y plusvalía como contracuentas del activo, y depreciación, plusvalía y venta como «cambios de valor» en Resultados |
| Préstamos | Cuenta `PRESTAMO` (negativo = deuda) + entidad `Prestamo` (`motor/prestamos.py`): monto, tasa anual, plazo, IVA sobre intereses (el del perfil; 0 en hipoteca y familiar), pago pactado y día de pago. Recibirlo es una transferencia del préstamo a la cuenta o bien destino; la comisión por apertura es gasto en el préstamo. Cada pago son dos movimientos: un `GASTO` en el préstamo por intereses + IVA (INTERESES DE PRESTAMOS) y cargos (COMISIONES BANCARIAS u otra), que suben la deuda, y una `TRANSFERENCIA` del pago completo, que la baja. Capital = pago − intereses − IVA − cargos. Tabla y simulaciones con el método francés y la tasa mensual × (1 + IVA). En los estados financieros es pasivo a corto o largo plazo según los meses que faltan con el pago mensual |
| Tarjetas: pago mínimo | Estimado con la regla de Banxico: máx(1.5 % del saldo exigible + intereses + IVA, 1.25 % de la línea), sin pasar de lo exigible. Intereses = lo no pagado del corte anterior × tasa anual / 12 × (1 + IVA, salvo que la tasa lo incluya) |
| Planeación | `motor/planeacion.py`. Ingreso esperado = promedio de los últimos 3 meses completos de las subcategorías de ingreso principal y secundarias (o el que escriba el usuario). Capacidad = (pagos de préstamos + mínimos de tarjetas) / ingreso. Sugeridos = gasto promedio por categoría, ajustado si no cabe en ingreso − préstamos − meta de ahorro. Proyección del mes = máx(lo gastado, lo usual) por categoría |
| Rendimiento en el tiempo | `motor/evolucion.py`. **Por título**: valor diario = títulos × cierre del día (el más reciente conocido: historial, precio de compra o venta, última consulta) × tipo de cambio de ese día. Las compras son entradas y las ventas salidas. Los plazos valen monto + interés hasta vencer; al vencer su dinero sale. **Oficial**: saldo diario de la cuenta; las transferencias son entradas o salidas y los `RENDIMIENTO` son la ganancia. Ganancia = valor final − valor inicial − (entradas − salidas); % por Dietz modificado |
| Fecha | Reloj del sistema; nunca se consulta Internet |
| Perfil | Nombre del usuario (bienvenida "¡Hola!") opcional, guardado localmente |
| Importación | Texto pegado desde Excel (TSV) o CSV, con vista previa y mapeo de categorías (Fase 5) |
| Licencia | MIT |
