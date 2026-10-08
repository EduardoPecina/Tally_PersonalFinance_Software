"""Guía de primeros pasos (motor/guia.py). Solo datos ficticios."""

from datetime import date

import pytest

from motor import categorias, cuentas, guia, metas, movimientos, perfil, plan_deudas, recurrentes, reglas_categorias
from motor.errores import ErrorValidacion
from motor.serializacion import instantanea, libro_desde_instantanea


def hechos(libro, **opciones) -> dict[str, bool]:
    return {p.clave: p.hecho for p in guia.avance(libro, **opciones).pasos}


def test_cada_paso_se_marca_solo(libro):
    perfil.configurar(libro, "Usuario Ficticio")
    av = guia.avance(libro)
    assert av.hechos == 1 and av.siguiente.clave == "cuentas"          # sin tarjetas, ese paso no falta
    assert not av.completo and guia.se_muestra_en_el_resumen(libro, av)

    debito = cuentas.crear(libro, "Débito Ficticio", "debito", saldo_inicial=5_000,
                           fecha_creacion=date(2026, 1, 1)).id
    for i in range(guia.MOVIMIENTOS_PARA_EMPEZAR):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), debito, categorias.buscar(libro, "ALIMENTOS").id,
                                    10 + i, f"Gasto ficticio {i}")
    nomina = categorias.buscar(libro, "NOMINA").id
    recurrentes.crear(libro, "Nómina ficticia", "ingreso", 10_000, debito, "quincenal", date(2026, 7, 15),
                      categoria_id=nomina)
    recurrentes.crear(libro, "Renta ficticia", "gasto", 4_000, debito, "mensual", date(2026, 7, 1),
                      categoria_id=categorias.buscar(libro, "RENTA").id)
    categorias.fijar_presupuesto(libro, categorias.buscar_rubro(libro, "ALIMENTACION").id, 3_000)
    metas.crear(libro, "Fondo ficticio", 20_000)
    assert all(hechos(libro)[c] for c in ("cuentas", "movimientos", "ingreso", "fijos", "presupuestos", "metas"))
    assert guia.avance(libro).completo and not guia.se_muestra_en_el_resumen(libro, guia.avance(libro))


def test_tarjetas_incompletas_y_deudas(libro, cat):
    perfil.configurar(libro, "Usuario Ficticio")
    tdc = cuentas.crear(libro, "TDC Ficticia", "credito", deuda_inicial=1_000, dia_corte=3, dia_pago=23,
                        fecha_creacion=date(2026, 1, 1))
    av = {p.clave: p for p in guia.avance(libro).pasos}
    assert not av["tarjetas"].hecho and not av["deudas"].opcional       # con tarjetas, el plan cuenta
    cuentas.editar(libro, tdc.id, tasa_anual=40)
    plan_deudas.guardar(libro, 500, plan_deudas.AVALANCHA)
    assert hechos(libro)["tarjetas"] and hechos(libro)["deudas"]


def test_opcionales(libro, cat):
    perfil.configurar(libro, "Usuario Ficticio")
    reglas_categorias.crear(libro, "OXXO", cat("SNACKS Y ANTOJOS"))
    av = {p.clave: p for p in guia.avance(libro, con_contrasena=True).pasos}
    assert av["reglas"].hecho and av["contrasena"].hecho and av["reglas"].opcional
    assert av["deudas"].opcional                                         # sin tarjetas ni préstamos


def test_ocultar_la_guia(libro):
    with pytest.raises(ErrorValidacion):
        guia.ocultar(libro)
    perfil.configurar(libro, "Usuario Ficticio")
    guia.ocultar(libro)
    assert not guia.se_muestra_en_el_resumen(libro, guia.avance(libro))
    assert libro_desde_instantanea(instantanea(libro), libro.secuencia).perfil.guia_oculta
    guia.ocultar(libro, False)
    assert guia.se_muestra_en_el_resumen(libro, guia.avance(libro))
