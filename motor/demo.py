"""Demostración del motor con un mes ficticio (no usa ni toca datos reales).

Uso:  python -m motor.demo                 un mes calculado por el motor
      python -m motor.demo --persistencia  además: guardar, reabrir, respaldar y restaurar
                                           (en una carpeta temporal que se muestra al final)
Provisional hasta que exista el portal (Fase 3).
"""

import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

from motor import categorias, cuentas, movimientos, perfil, reportes, tarjetas
from motor.dinero import formatear
from motor.libro import Libro
from motor.modelo import TipoCuenta
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia


def armar_libro() -> Libro:
    libro = Libro(reloj=lambda: datetime(2026, 8, 10, 9, 0))
    categorias.cargar_catalogo_inicial(libro)
    perfil.configurar(libro, "Usuario de prueba")

    def cat(nombre: str) -> str:
        return categorias.buscar(libro, nombre).id

    debito = cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, saldo_inicial=120, fecha_creacion=date(2026, 7, 1)).id
    tdc = cuentas.crear(
        libro, "Tarjeta de crédito", TipoCuenta.CREDITO, limite_credito=1000, dia_corte=3, dia_pago=23,
        fecha_creacion=date(2026, 7, 1),
    ).id
    ahorro = cuentas.crear(libro, "Ahorro", TipoCuenta.AHORRO, saldo_inicial=8000, fecha_creacion=date(2026, 7, 1)).id
    por_cobrar = cuentas.crear(libro, "Por cobrar", TipoCuenta.POR_COBRAR, fecha_creacion=date(2026, 7, 1)).id

    movimientos.registrar_ingreso(libro, date(2026, 7, 15), debito, cat("Nómina"), 4000)
    registrar_transferencia(libro, date(2026, 7, 15), debito, ahorro, 3000, "Al ahorro")
    movimientos.registrar_gasto(libro, date(2026, 7, 5), tdc, cat("Alimentos"), 500, "Restaurante")
    movimientos.registrar_gasto(libro, date(2026, 7, 9), tdc, cat("Snacks y antojos"), 60, "Antojo")
    registrar_pago_tarjeta(libro, date(2026, 7, 15), debito, tdc, 500, "Pago parcial")
    movimientos.registrar_gasto(libro, date(2026, 7, 20), debito, cat("Transporte"), 75, "Taxi")
    movimientos.registrar_gasto(libro, date(2026, 7, 22), debito, cat("Retiros de efectivo"), 200)
    registrar_transferencia(libro, date(2026, 7, 24), ahorro, por_cobrar, 300, "Le presté a un amigo")
    movimientos.registrar_gasto(libro, date(2026, 7, 26), ahorro, cat("Hogar y mantenimiento"), 250, "Insecticida")
    movimientos.registrar_reembolso(libro, date(2026, 7, 28), ahorro, cat("Hogar y mantenimiento"), 250, "Devolución")
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), debito, cat("Nómina"), 4000)
    movimientos.actualizar_saldo(
        libro, ahorro, cuentas.saldo(libro, ahorro, date(2026, 7, 31)) + 42, date(2026, 7, 31),
        categoria_id=cat("Intereses y rendimientos"), descripcion="Intereses de julio",
    )
    return libro


def _fila(etiqueta: str, importe) -> str:
    return f"  {etiqueta:<34}{formatear(importe):>14}"


def main() -> None:
    libro = armar_libro()
    julio = reportes.rango_mes(2026, 7)
    print(f"\n¡Hola, {libro.perfil.nombre}!  (datos ficticios de demostración)\n")

    print("SALDOS")
    for cuenta in cuentas.listar(libro):
        print(_fila(cuenta.nombre, cuentas.saldo(libro, cuenta.id)))

    i = reportes.indicadores(libro)
    print("\nSITUACIÓN")
    print(_fila("Dinero disponible", i.dinero_disponible))
    print(_fila("Total en cuentas", i.total_en_cuentas))
    print(_fila("Te deben", i.te_deben))
    print(_fila("Deuda de tarjetas", i.deuda_tarjetas))
    print(_fila("Patrimonio neto", i.patrimonio_neto))

    r = reportes.resumen(libro, *julio)
    print("\nJULIO 2026")
    print(_fila("Ingresos", r.ingresos))
    print(_fila("Gastos", r.gastos))
    print(_fila("Ahorro real (ingresos - gastos)", r.ahorro_real))
    print(_fila("Apartado a ahorro", r.apartado_a_ahorro))

    print("\nGASTOS POR CATEGORÍA")
    for t in reportes.gastos_por_categoria(libro, *julio):
        print(_fila(f"{t.nombre} ({t.grupo})", t.total))

    tdc = cuentas.buscar(libro, "Tarjeta de crédito").id
    c = tarjetas.resumen_ciclo(libro, tdc, date(2026, 7, 10), hasta=date(2026, 8, 10))
    print(f"\nTARJETA: CICLO {c.inicio:%d/%m} - {c.fin:%d/%m}  (pagar antes del {c.fecha_limite_pago:%d/%m})")
    print(_fila("Cargos del ciclo", c.cargos))
    print(_fila("Abonos del ciclo", c.abonos))
    print(_fila("Por liquidar", c.por_liquidar))

    debito = cuentas.buscar(libro, "Débito").id
    print("\nSOBRANTE ANTES DE CADA NÓMINA (lo que era 'HISTORICO')")
    for s in reportes.sobrantes_de_quincena(libro, debito):
        print(_fila(f"{s.fecha:%d/%m/%Y}", s.sobrante))

    print(
        "\nComprueba: la compra de $500 con tarjeta cuenta como gasto UNA vez, aunque después se pagó;"
        "\nel traspaso al ahorro, el préstamo y la devolución no son gasto.\n"
    )


def demo_persistencia() -> None:
    from motor import respaldos
    from motor.serializacion import instantanea
    from motor.sesion import Sesion

    carpeta = Path(tempfile.mkdtemp(prefix="tally_demo_"))
    ruta = carpeta / "Datos" / "tally.db"
    print("PERSISTENCIA")

    sesion = Sesion(ruta)
    with sesion.cambio() as libro:
        perfil.configurar(libro, "Usuario de prueba")
        debito = cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, saldo_inicial=1000).id
        movimientos.registrar_gasto(libro, libro.hoy(), debito, categorias.buscar(libro, "Alimentos").id, 250, "Pizza")
    print(f"  1. Guardado en {ruta}")

    reabierta = Sesion(ruta)
    print(f"  2. Al reabrir, saldo de Débito: {formatear(cuentas.saldo(reabierta.libro, debito))}")

    respaldo = respaldos.crear(reabierta, carpeta / "Respaldos")
    print(f"  3. Respaldo creado: {respaldo.name}")

    with reabierta.cambio() as libro:
        movimientos.registrar_gasto(libro, libro.hoy(), debito, categorias.buscar(libro, "Regalos").id, 700, "Error")
    print(f"  4. Se registró un gasto por error. Saldo: {formatear(cuentas.saldo(reabierta.libro, debito))}")

    info = respaldos.inspeccionar(respaldo)
    print(f"  5. El respaldo contiene {info.cuentas} cuenta(s) y {info.movimientos} movimiento(s) de {info.perfil}")
    resultado = respaldos.restaurar(reabierta, respaldo, carpeta_seguridad=carpeta / "Respaldos")
    print(f"  6. Restaurado. Saldo: {formatear(cuentas.saldo(reabierta.libro, debito))}"
          f"  (antes se guardó {resultado.respaldo_de_seguridad.name})")

    assert instantanea(Sesion(ruta).libro) == instantanea(reabierta.libro)
    print("\nBITÁCORA (últimos cambios)")
    for registro in reabierta.almacen.bitacora(limite=4):
        datos = registro.despues or registro.antes or {}
        nombre = datos.get("descripcion") or datos.get("nombre") or datos.get("archivo", "")
        print(f"  {registro.fecha_hora}  {registro.accion:<10} {registro.entidad:<10} {nombre}")
    print(f"\nPuedes revisar los archivos en: {carpeta}\n")


if __name__ == "__main__":
    main()
    if "--persistencia" in sys.argv:
        demo_persistencia()
