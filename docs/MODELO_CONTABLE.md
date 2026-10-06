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

## 6. Categorías y grupos

- Una categoría tiene una clase: `INGRESO`, `GASTO` o `SISTEMA`.
- Opcionalmente pertenece a un **grupo**, equivalente a la columna
  "Clasif. Metas" del Excel. Los grupos por defecto son Necesidad, Disfrute,
  Estabilidad, Inversión y Dádivas. **Todos son editables.**
- Una categoría de ingreso puede marcarse como **principal** (p. ej. Nómina).
  Así se detectan las quincenas.
- Borrar una categoría con movimientos exige reasignarlos a otra, lo que
  equivale a fusionarlas.

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
| Meses sin intereses | El gasto completo cuenta en la fecha de compra. El seguimiento de mensualidades queda para después |
| Fecha | Reloj del sistema; nunca se consulta Internet |
| Perfil | Nombre del usuario (bienvenida "¡Hola!") opcional, guardado localmente |
| Importación | Texto pegado desde Excel (TSV) o CSV, con vista previa y mapeo de categorías (Fase 5) |
| Licencia | MIT |
