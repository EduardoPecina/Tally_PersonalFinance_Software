<p align="center"><img src="docs/marca/logotipo.png" alt="TALLY" width="360"></p>

<p align="center"><b>Your money. Your computer. Your data.</b><br>
<i>Tus finanzas, en tu PC, con tus datos.</i></p>

TALLY es una aplicación de finanzas personales **local-first**, gratuita y de
código abierto. Está pensada para una sola persona y corre únicamente en su
computadora. Es una alternativa más cómoda que llevar las finanzas a mano en
Excel.

> Estado: **Fase 3 — portal básico**. Ya se puede usar: bienvenida, resumen,
> registrar movimientos, historial, cuentas, categorías y respaldos.

## Privacidad

- Sin cuentas de usuario y sin correo. La **contraseña es opcional** y vive
  solo en tu PC (ver [Contraseña de TALLY](#contraseña-de-tally-opcional)).
- Sin conexión bancaria, sin nube y sin telemetría.
- Funciona sin Internet. Los datos viven en `C:\Users\<tu usuario>\TALLY`,
  solo en tu PC: fuera de OneDrive y de cualquier nube.
- La única conexión es opcional: **Consultar valor aproximado actual**, en las
  cuentas de inversión. Pide a Yahoo Finance el precio público de cada título y
  envía **solo el símbolo bursátil** (`GET https://…/chart/IVV`), siempre por
  HTTPS:
  - **No envía** cantidades, precios de compra, saldos, movimientos,
    patrimonio, tu nombre ni archivos. Valor actual, ganancia y rentabilidad
    se calculan en tu PC.
  - **No se registra** en bitácoras ni logs. En tu PC solo se guardan los
    últimos precios públicos (`Datos\precios.json`), para seguir funcionando
    sin internet.
  - **Solo consulta** cuando aprietas el botón, o al abrir la cuenta si tú
    activas «Actualizar precios automáticamente» (viene apagado).
  - **Si Yahoo deja de responder**, TALLY avisa y sigue funcionando con los
    últimos precios guardados o con los que escribas a mano. El proveedor está
    concentrado en `motor/cotizaciones.py`, así que cambiarlo por otro es un
    cambio pequeño.
  - El botón **Actualizar historial de precios** (página Inversiones) pide los
    cierres diarios de cada símbolo. Envía el símbolo y un periodo estándar
    (`range=5y`), nunca la fecha exacta de tu primera compra ni cantidades. Se
    guarda en `Datos\historial_precios.json` para ver las gráficas sin
    internet.
  - La ganancia de tus inversiones entra a tu contabilidad **solo con el valor
    oficial** que tú escribes («Cuadrar con tu estado de cuenta»). El precio de
    internet es una referencia.
- Importar movimientos del banco (Excel, CSV o PDF) pasa en tu PC: TALLY no se
  conecta a tu banco ni manda el archivo a ningún lado.
- Los datos financieros nunca forman parte de este repositorio (ver `.gitignore`).

## Qué resuelve

La parte difícil de las finanzas personales no es la interfaz. Es saber **qué
significa cada movimiento** sin contar nada dos veces:

| Movimiento | ¿Gasto? |
|---|---|
| Compra de $500 con tarjeta de crédito | Sí, $500 |
| Pago de esos $500 desde débito | **No** (es un pago de tarjeta) |
| Pasar $3,000 de débito a ahorro | **No** (es una transferencia) |
| Devolución de una compra | Resta del gasto de su categoría |

Detalle en [`docs/MODELO_CONTABLE.md`](docs/MODELO_CONTABLE.md) y
[`docs/PERSISTENCIA.md`](docs/PERSISTENCIA.md).

## Instalar y usar

1. Descarga el proyecto (en GitHub: **Code → Download ZIP**) y descomprímelo
   (clic derecho en el ZIP → **Extraer todo**) en cualquier carpeta que no sea
   el Escritorio (por ejemplo, Descargas). Si corres `INSTALAR.bat` desde
   dentro del ZIP sin extraerlo, el instalador primero copia el programa a una
   carpeta temporal propia, porque Windows puede borrar su copia a media
   instalación.
2. Doble clic en `INSTALAR.bat`. Instala lo necesario y crea
   `Escritorio\TALLY` y el acceso directo **TALLY**. Funciona en cualquier
   PC con Windows, personal o de trabajo, con el Escritorio en OneDrive o no.
3. Doble clic en el acceso directo **TALLY**: se abre en tu navegador, en
   `http://localhost:8765`. Solo tu PC puede verlo.
4. La primera vez te saluda, te pide tu nombre y te deja agregar tus cuentas.
5. Para cerrarlo: botón **Cerrar TALLY** en el menú de la izquierda. Si solo
   cierras la pestaña, TALLY se apaga solo tras 15 minutos sin pestañas
   abiertas. Todo se guarda al momento, así que no se pierde nada.

Para actualizar, corre el `INSTALAR.bat` de la versión nueva. Antes de
actualizar se respaldan tus datos y no se tocan.

Tus datos y respaldos están en `C:\Users\<tu usuario>\TALLY`, fuera del
Escritorio, así que OneDrive no los sube a la nube. Para abrir esa carpeta usa
el acceso directo **Mis datos de TALLY**, dentro de `Escritorio\TALLY`.

| Página | Responde a |
|---|---|
| Resumen | ¿Cuánto dinero tengo? ¿Cuánto gasté y en qué? ¿Tengo pagos de tarjeta por vencer? ¿Cómo voy con mis presupuestos? ¿Qué cargos temporales me deben devolver? |
| Registrar | Anotar un gasto (también a meses sin intereses, repartido o como cargo temporal que te van a devolver), ingreso, transferencia, pago de tarjeta o reembolso |
| Historial | Buscar, filtrar, editar, repetir o eliminar movimientos |
| Cuentas | Saldo de cada cuenta, estado de cuenta con saldo corrido, estado de cada tarjeta (línea, disponible, pago) y, en las de inversión, tus títulos (acciones, ETFs, cripto) y CETES o pagarés con su valor aproximado, y «Cuadrar con tu estado de cuenta» para registrar la ganancia con el valor oficial |
| Deudas | Tarjetas y préstamos: cuánto de tu ingreso se va en deudas, pago mínimo estimado y lo que cuesta pagar solo el mínimo; préstamos con pagos separados en capital, intereses, IVA y cargos, tabla de amortización y simulador para salir antes |
| Presupuestos | Tus ingresos (principal y secundarios), cuánto puedes gastar, presupuestos sugeridos, proyección del mes y el tope mensual por categoría |
| Tablas dinámicas | Pivots por categoría, mes, cuenta… exportables a Excel |
| Gráficas | Dona, barras, tendencias, ingresos vs. gastos y patrimonio; clic en una rebanada o barra para ver de qué movimientos se compone |
| Contabilidad Técnica | Estado de Situación Financiera, Estado de Resultados, Flujo de Efectivo y Balanza de Comprobación, comparativos por periodo, armados solos con tus movimientos y explicados sin tecnicismos; clic en un renglón para ver sus movimientos. **Bienes** (casa, auto, laptop) con depreciación, mejoras, avalúos y venta |
| Inversiones | ¿Cuánto ganaron mis inversiones este mes, este año o en 5 años? Valor en el tiempo, lo que metiste y la ganancia por mes o año, filtrando por cuentas (CETES, GBM…) y por títulos (IVV, VT…); estimado con precios de mercado u oficial con tus valores registrados |
| Categorías | Categorías (SALUD, TECNOLOGIA…) con sus subcategorías y clasificaciones, a tu manera |
| Cargar datos | Importar los movimientos de tu banco (Excel, CSV o PDF) con la subcategoría sugerida, o subir tu historial de Excel con una plantilla `.txt` |
| Respaldos y bitácora | Descargar o restaurar respaldos, ver qué cambió o empezar de cero |
| Configuración ⚙️ | Tu nombre, tema claro u oscuro, color del ícono, respaldo automático diario, periodo del Resumen y datos de la instalación |

### Cambiar de PC sin perder nada

1. En la PC de antes: **Configuración → Respaldos → Descargar respaldo**.
   Guarda el `.zip` en una memoria USB o donde quieras.
2. En la PC nueva: instala TALLY y, en la bienvenida, elige **«Ya usaba
   TALLY»** y sube el `.zip`. También sirve el archivo `tally.db` de la otra
   PC.

### Contraseña de TALLY (opcional)

TALLY abre sin contraseña. Si quieres, en **Configuración → Seguridad →
Establecer una contraseña para TALLY** le pones una en 4 pasos:

1. **Eliges tu contraseña** (mínimo 8 caracteres; mejor una frase) y una pista
   opcional.
2. **Guardas tu Kit de emergencia**: una llave de repuesto como
   `ABCD-EFGH-…`. La descargas, la imprimes, te la mandas por correo o le
   tomas foto. Si olvidas tu contraseña, con esa llave entras y pones otra
   sin perder nada.
3. **Compruebas** que guardaste el Kit y recuerdas la contraseña. Sin esto no
   se activa.
4. **Activas.** Antes, TALLY hace un respaldo; luego cifra tus datos y tus
   respaldos guardados, y comprueba que todo quedó idéntico (si no, lo
   deshace).

Desde entonces:

- TALLY pide la contraseña al abrir, y **se bloquea solo** si no lo usas un
  rato (10 minutos, ajustable). También hay un botón **Bloquear ahora**.
- Tus datos y respaldos se guardan **cifrados** (AES-256): quien copie el
  archivo solo ve letras sin sentido.
- Los respaldos se abren en **cualquier PC** con la contraseña de ese día o
  con tu Kit. En tu PC, con TALLY abierto, se restauran sin pedir nada.
- Puedes cambiar la contraseña (el Kit sigue siendo el mismo), bajar una
  copia **sin contraseña** para una USB o **quitar la contraseña** y volver a
  como estaba.

**La única regla:** si pierdes tu contraseña **y** tu Kit, nadie puede abrir
tus datos, ni TALLY ni un técnico. Por eso no hay recuperación por correo:
sería una puerta trasera.

### Importar los movimientos de tu banco

En **Cargar datos → Desde tu banco**:

1. Elige la cuenta o tarjeta.
2. Sube el archivo que descargas de tu banca en línea (**Excel o CSV**, en
   *Movimientos → Exportar*), el **PDF** de tu estado de cuenta, o pega la
   tabla de movimientos copiada de la página del banco.
3. TALLY encuentra las columnas solo y te muestra cuánto salió y cuánto entró,
   para compararlo con tu estado de cuenta.
4. Revisa la tabla:
   - **Subcategoría sugerida (✨):** lo que elegiste antes para esa
     descripción (TALLY aprende de tu historial) o, si es nuevo, por el
     nombre de comercios conocidos (OXXO, Walmart, Netflix, CFE, Uber…).
   - **Ya está en TALLY (⏭️):** misma cuenta, mismo importe y a pocos días.
     No se carga, salvo que lo marques.
   - Si el dinero fue a otra de tus cuentas, elígela: es una transferencia y
     no cuenta como gasto.
5. **Importar.** Antes se hace un respaldo, y si algo falla no se carga nada.

El archivo se lee en tu PC y no se manda a ningún lado. Si el PDF tiene
contraseña (muchos bancos usan tu RFC), TALLY te la pide y no la guarda.

### Pasar tu historial de Excel a TALLY

1. En **Cargar datos**, descarga la plantilla de tu cuenta (débito, crédito,
   ahorro, inversión) o la de todas.
2. Ábrela con el Bloc de notas. Escribe el nombre de la cuenta y pega tus
   movimientos copiados de Excel en este orden de columnas: FECHA,
   DESCRIPCION, SUBCATEGORIA, CARGO, ABONO y NOTAS.
3. Súbela. Antes de guardar verás una vista previa. Ahí decides qué es cada
   nombre que TALLY no reconozca: una subcategoría nueva, una que ya existe o
   una de tus cuentas.

Si en SUBCATEGORIA escribes el nombre de otra de tus cuentas, el movimiento
es una transferencia y no cuenta como gasto. Si la misma transferencia viene
en las dos cuentas, se carga una sola vez. Subir dos veces el mismo archivo
no duplica nada.

## Desarrollo

### Opción A: doble clic

- `EJECUTAR.bat`: demostración del motor con datos ficticios y todas las pruebas.
- `EJECUTAR PORTAL.bat`: abre el portal (usa `.venv` si existe).

### Opción B: terminal de VS Code

Abre la carpeta del proyecto en VS Code y, en la terminal (PowerShell):

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-lock.txt

python -m pytest                       # todas las pruebas (incluye el portal, sin navegador)
python -m motor.demo --persistencia    # la demostración
python portal\iniciar.py               # abre el portal
```

`requirements-lock.txt` está fijado para Windows con CPython 3.13. En otro
sistema, instala `requirements.txt` sin hashes.

Si PowerShell no deja activar el entorno, ejecuta una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Estructura

```text
.streamlit/   Configuración del portal local (localhost:8765, sin telemetría)
motor/        Toda la lógica financiera y de persistencia; independiente de Streamlit
portal/       Interfaz con Streamlit: páginas, componentes y lanzador (iniciar.py)
instalador/   Instalador para Windows (instalar.py)
tests/        Pruebas automatizadas con datos ficticios
docs/         Modelo contable, persistencia y marca (docs/marca)
_Programa/    Carpeta administrada por el instalador
```

El portal solo muestra información y llama al motor. Ninguna regla financiera
vive fuera de `motor/`.

## Hoja de ruta

1. **Motor financiero** ✅
2. **Persistencia local, bitácora, respaldo, restauración e instalador** ✅
3. **Portal básico: bienvenida, resumen, cuentas, captura, historial, categorías y respaldos** ✅
4. Análisis: gráficas, reportes y tablas dinámicas
5. Exportación (Excel, CSV, ODS) e importación (incluido texto pegado desde Excel)
6. Pulido y documentación

## Licencia

[MIT](LICENSE)
