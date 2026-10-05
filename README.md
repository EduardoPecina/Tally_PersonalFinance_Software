# TALLY

**Mis finanzas, mis números, mi PC, mis datos.**

TALLY es una aplicación de finanzas personales **local-first**, gratuita y de
código abierto. Está pensada para una sola persona y corre únicamente en su
computadora. Es una alternativa más cómoda que llevar las finanzas a mano en
Excel.

> Estado: **Fase 2 — persistencia, respaldos e instalador**. Todavía no hay
> interfaz gráfica (llega en la Fase 3).

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

## Probarlo en tu PC

### Opción A: doble clic

1. Descarga el proyecto (en GitHub: **Code → Download ZIP**) y descomprímelo.
2. Doble clic en `EJECUTAR.bat`. Muestra un mes de demostración, guarda,
   respalda y restaura en una carpeta temporal, y corre las pruebas. Todo con
   datos ficticios.

### Opción B: terminal de VS Code

Abre la carpeta del proyecto en VS Code y, en la terminal (PowerShell):

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-lock.txt

python -m pytest                       # todas las pruebas
python -m motor.demo --persistencia    # la demostración
```

Si PowerShell no deja activar el entorno, ejecuta una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Opción C: instalarlo como lo haría un usuario

Doble clic en `INSTALAR.bat`. Crea `Escritorio\TALLY` con `Datos`,
`Respaldos`, `_Programa`, `LEEME.txt` e `instalacion.log`. Correrlo otra vez
actualiza el programa y antes respalda tus datos.

## Estructura

```text
.streamlit/   Configuración del portal local (localhost:8765, sin telemetría)
motor/        Toda la lógica financiera y de persistencia; independiente de Streamlit
portal/       Interfaz con Streamlit (Fase 3)
instalador/   Instalador para Windows (instalar.py)
tests/        Pruebas automatizadas con datos ficticios
docs/         Modelo contable y persistencia
_Programa/    Carpeta administrada por el instalador
```

El portal solo muestra información y llama al motor. Ninguna regla financiera
vive fuera de `motor/`.

## Hoja de ruta

1. **Motor financiero** ✅
2. **Persistencia local, bitácora, respaldo, restauración e instalador** ✅
3. Portal básico: bienvenida, dashboard, cuentas, captura, historial y categorías
4. Análisis: gráficas, reportes y tablas dinámicas
5. Exportación (Excel, CSV, ODS) e importación (incluido texto pegado desde Excel)
6. Pulido y documentación

## Licencia

[MIT](LICENSE)
