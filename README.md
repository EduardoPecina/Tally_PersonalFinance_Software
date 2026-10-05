# TALLY

**Mis finanzas, mis números, mi PC, mis datos.**

TALLY es una aplicación de finanzas personales **local-first**, gratuita y de
código abierto. Está pensada para una sola persona y corre únicamente en su
computadora. Es una alternativa más cómoda que llevar las finanzas a mano en
Excel.

> Estado: **Fase 1 — motor financiero**. Todavía no hay interfaz gráfica.

## Privacidad

- Sin cuentas de usuario, sin inicio de sesión, sin correo.
- Sin conexión bancaria, sin nube y sin telemetría.
- Funciona sin Internet. Los datos viven en archivos locales que solo tú controlas.
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

Internamente cada movimiento se guarda en partidas que siempre suman cero. El
detalle está en [`docs/MODELO_CONTABLE.md`](docs/MODELO_CONTABLE.md).

## Funciones del motor (Fase 1)

- Cuentas ilimitadas de cualquier tipo: débito, ahorro, crédito, efectivo,
  inversión, por cobrar y otras.
- Gastos, ingresos, reembolsos y gastos repartidos en varias categorías.
- Transferencias y pagos de tarjeta como **una sola operación**.
- Tarjetas de crédito: deuda, crédito disponible y ciclos de corte (cargos,
  abonos y lo que falta por liquidar).
- «Actualizar saldo» para registrar intereses, rendimientos o ajustes.
- Categorías y grupos de categorías completamente editables.
- Indicadores: dinero disponible, total en cuentas, te deben, deuda de
  tarjetas y patrimonio neto.
- Resumen del periodo: ingresos, gastos, ahorro real y apartado a ahorro.
- Quincenas: lo que sobra en la cuenta antes de cada nómina.

## Estructura

```text
.streamlit/   Configuración del portal local (localhost:8765, sin telemetría)
motor/        Toda la lógica financiera; independiente de Streamlit
portal/       Interfaz con Streamlit (Fase 3)
instalador/   Instalador para Windows (Fase 6)
tests/        Pruebas automatizadas con datos ficticios
docs/         Modelo contable y documentación
_Programa/    Carpeta administrada por el instalador
```

El portal solo muestra información y llama al motor. Ninguna regla financiera
vive fuera de `motor/`.

## Probarlo en Windows (por ahora)

Mientras no exista el portal, `EJECUTAR.bat` muestra un mes de demostración
con datos ficticios y corre las pruebas:

1. Instala [Python 3.13](https://www.python.org/downloads/).
2. Descarga el proyecto (botón **Code → Download ZIP** en GitHub) y descomprímelo.
3. Doble clic en `EJECUTAR.bat`.

## Desarrollo y pruebas

Requiere Python 3.13.

```bash
py -3.13 -m pip install --require-hashes -r requirements-lock.txt
py -3.13 -m pytest
```

Las pruebas no necesitan Streamlit y usan exclusivamente datos ficticios.

## Hoja de ruta

1. **Motor financiero** ✅
2. Persistencia local, respaldo y restauración
3. Portal básico: bienvenida, dashboard, cuentas, captura, historial y categorías
4. Análisis: gráficas, reportes y tablas dinámicas
5. Exportación (Excel, CSV, ODS) e importación (incluido texto pegado desde Excel)
6. Pulido, instalador y documentación

## Licencia

[MIT](LICENSE)
