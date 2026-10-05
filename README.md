<p align="center"><img src="docs/marca/logotipo.png" alt="TALLY" width="360"></p>

<p align="center"><b>Mis finanzas, mis números, mi PC, mis datos.</b><br>
<i>Your money. Your computer. Your data.</i></p>

TALLY es una aplicación de finanzas personales **local-first**, gratuita y de
código abierto. Está pensada para una sola persona y corre únicamente en su
computadora. Es una alternativa más cómoda que llevar las finanzas a mano en
Excel.

> Estado: **Fase 3 — portal básico**. Ya se puede usar: bienvenida, resumen,
> registrar movimientos, historial, cuentas, categorías y respaldos.

## Privacidad

- Sin cuentas de usuario, sin inicio de sesión, sin correo.
- Sin conexión bancaria, sin nube y sin telemetría.
- Funciona sin Internet. Los datos viven en `Datos\tally.db`, en tu PC.
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
   en cualquier carpeta que no sea el Escritorio (por ejemplo, Descargas).
2. Doble clic en `INSTALAR.bat`. Instala lo necesario y crea
   `Escritorio\TALLY` y el acceso directo **TALLY**.
3. Doble clic en el acceso directo **TALLY**: se abre en tu navegador, en
   `http://localhost:8765`. Solo tu PC puede verlo.
4. La primera vez te saluda, te pide tu nombre y te deja agregar tus cuentas.
5. Para cerrarlo: botón **Cerrar TALLY** en el menú de la izquierda. Si solo
   cierras la pestaña, TALLY se apaga solo tras 15 minutos sin pestañas
   abiertas. Todo se guarda al momento, así que no se pierde nada.

Para actualizar, corre el `INSTALAR.bat` de la versión nueva. Antes de
actualizar se respaldan tus datos y no se tocan.

| Página | Responde a |
|---|---|
| Resumen | ¿Cuánto dinero tengo? ¿Cuánto gasté este periodo y en qué? ¿Cuánto debo en mis tarjetas? |
| Registrar | Anotar un gasto, ingreso, transferencia, pago de tarjeta o reembolso, rápido |
| Historial | Buscar, filtrar, ordenar, ver, editar o eliminar movimientos |
| Cuentas | ¿Cuánto tengo en cada cuenta? Crear, editar, actualizar saldo, archivar |
| Categorías | Organizar categorías y grupos a tu manera |
| Respaldos y bitácora | Crear o restaurar respaldos y ver qué cambió |

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
