"""Rubros contables (motor/rubros_contables.py): en qué renglón de la Contabilidad técnica cae cada subcategoría.
Solo datos ficticios."""

from datetime import date

import pytest

from conftest import AHORA, D
from motor import auditoria, categorias, cuentas, movimientos, respaldos
from motor import contabilidad as cb
from motor import rubros_contables as rc
from motor.errores import ErrorDatos, ErrorValidacion
from motor.modelo import (RC_FINANCIEROS, RC_IMPUESTOS, RC_INVERSIONES, RC_OTROS_INGRESOS, RC_TRABAJO, RC_VIDA,
                          ClaseCategoria)
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.sesion import Sesion

ANIO = (date(2026, 1, 1), date(2026, 12, 31))


def donde(libro, nombre):
    return rc.de(libro, categorias.buscar(libro, nombre).id).id


def test_el_catalogo_queda_acomodado_por_nombre_y_categoria(libro):
    esperado = {
        "INTERESES DE TARJETAS": RC_FINANCIEROS, "COMISIONES BANCARIAS": RC_FINANCIEROS, "ANUALIDADES": RC_FINANCIEROS,
        "GASTOS FINANCIEROS": RC_FINANCIEROS, "IMPUESTOS": RC_IMPUESTOS, "PREDIAL": RC_IMPUESTOS,
        "TENENCIA Y VERIFICACION": RC_IMPUESTOS, "SEGURO DE VIDA": RC_VIDA, "ALIMENTOS": RC_VIDA, "RENTA": RC_VIDA,
        "RETIROS DE EFECTIVO": RC_VIDA, "NOMINA": RC_TRABAJO, "AGUINALDO": RC_TRABAJO, "HONORARIOS": RC_TRABAJO,
        "VENTAS": RC_TRABAJO, "INTERESES Y RENDIMIENTOS": RC_INVERSIONES, "DIVIDENDOS": RC_INVERSIONES,
        "RENTAS COBRADAS": RC_INVERSIONES, "DEVOLUCION DE IMPUESTOS": RC_OTROS_INGRESOS, "PREMIOS": RC_OTROS_INGRESOS,
    }
    assert {n: donde(libro, n) for n in esperado} == esperado
    todas = rc.asignaciones(libro)
    assert all(r.clase is libro.categoria(i).clase for i, r in todas.items())       # nunca de otro tipo
    assert not any(libro.categoria(i).rubro_contable_id for i in todas)              # nada guardado: automático
    assert rc.motivo(libro, categorias.buscar(libro, "PREDIAL").id) == rc.POR_NOMBRE
    assert rc.motivo(libro, categorias.buscar(libro, "VENTAS").id) == rc.POR_CATEGORIA


def test_mover_una_subcategoria_y_regresarla(libro):
    alimentos = categorias.buscar(libro, "ALIMENTOS").id
    rc.asignar(libro, alimentos, RC_FINANCIEROS)
    assert donde(libro, "ALIMENTOS") == RC_FINANCIEROS and rc.motivo(libro, alimentos) == rc.ELEGIDO
    rc.asignar(libro, alimentos, RC_VIDA)                       # el mismo que elegiría TALLY: vuelve a automático
    assert libro.categoria(alimentos).rubro_contable_id is None
    with pytest.raises(ErrorValidacion, match="solo puede ir en un rubro de gasto"):
        rc.asignar(libro, alimentos, RC_TRABAJO)
    with pytest.raises(ErrorValidacion):
        rc.asignar(libro, "sistema-ajuste", RC_VIDA)


def test_al_crear_una_subcategoria_va_con_las_hermanas_que_moviste(libro):
    negocio = categorias.crear_rubro(libro, "Mi negocio", ClaseCategoria.GASTO).id
    isr = categorias.crear(libro, "ISR anual", negocio)                      # por su nombre
    iva = categorias.crear(libro, "IVA", negocio)
    assert (rc.de(libro, isr.id).id, rc.de(libro, iva.id).id) == (RC_IMPUESTOS, RC_IMPUESTOS)
    assert isr.rubro_contable_id is None                                     # automático
    papeleria = categorias.crear(libro, "Papelería del negocio", negocio)    # ISR e IVA no la arrastran
    assert papeleria.rubro_contable_id is None and rc.de(libro, papeleria.id).id == RC_VIDA

    vivienda = rc.crear(libro, "Vivienda", "gasto").id                       # muevo casi todo HOGAR
    hogar = categorias.subcategorias(libro, categorias.buscar_rubro(libro, "HOGAR").id)
    for c in hogar[:8]:
        rc.asignar(libro, c.id, vivienda)
    nueva = categorias.crear(libro, "Jardinería", categorias.buscar_rubro(libro, "HOGAR").id)
    assert libro.categoria(nueva.id).rubro_contable_id == vivienda           # va con ellas, y se guarda
    con_nombre = categorias.crear(libro, "Impuesto sobre la renta de la casa", categorias.buscar_rubro(libro, "HOGAR").id)
    assert rc.de(libro, con_nombre.id).id == RC_IMPUESTOS                     # su nombre manda
    taqueria = categorias.crear(libro, "Taquería", categorias.buscar_rubro(libro, "ALIMENTACION").id)
    assert taqueria.rubro_contable_id is None and rc.de(libro, taqueria.id).id == RC_VIDA
    nuevo = categorias.crear(libro, "Seguro de tarjeta", categorias.buscar_rubro(libro, "FINANZAS").id)
    assert rc.de(libro, nuevo.id).id == RC_VIDA                              # «SEGURO» manda sobre su categoría


def test_rubros_propios(libro):
    negocio = rc.crear(libro, "  Gastos del negocio ", "gasto")
    assert negocio.nombre == "Gastos del negocio" and [r.id for r in rc.todos(libro, ClaseCategoria.GASTO)][-1] == negocio.id
    with pytest.raises(ErrorValidacion, match="Ya hay"):
        rc.crear(libro, "gastos DEL negocio", "gasto")
    with pytest.raises(ErrorValidacion, match="Ya hay"):
        rc.crear(libro, "Impuestos", "gasto")
    with pytest.raises(ErrorValidacion):
        rc.crear(libro, "Raro", "sistema")
    papeleria = categorias.buscar(libro, "PAPELERIA").id
    rc.asignar(libro, papeleria, negocio.id)
    assert rc.renombrar(libro, negocio.id, "Mi negocio").nombre == "Mi negocio"
    for prohibido in (lambda: rc.renombrar(libro, RC_VIDA, "Otra"), lambda: rc.eliminar(libro, RC_VIDA)):
        with pytest.raises(ErrorValidacion, match="TALLY"):
            prohibido()
    assert rc.eliminar(libro, negocio.id) == 1
    assert libro.categoria(papeleria).rubro_contable_id is None and donde(libro, "PAPELERIA") == RC_VIDA


def test_restablecer(libro):
    rc.asignar(libro, categorias.buscar(libro, "ALIMENTOS").id, RC_IMPUESTOS)
    rc.asignar(libro, categorias.buscar(libro, "NOMINA").id, RC_OTROS_INGRESOS)
    assert rc.restablecer(libro, ClaseCategoria.INGRESO) == 1
    assert donde(libro, "NOMINA") == RC_TRABAJO and donde(libro, "ALIMENTOS") == RC_IMPUESTOS
    assert rc.restablecer(libro) == 1 and donde(libro, "ALIMENTOS") == RC_VIDA


@pytest.fixture
def con_movimientos(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    movimientos.registrar_ingreso(libro, date(2026, 3, 1), ctas.debito, cat("NOMINA"), 20_000, "Nómina ficticia")
    movimientos.registrar_gasto(libro, date(2026, 3, 2), ctas.debito, cat("ALIMENTOS"), 1_500, "Súper ficticio")
    movimientos.registrar_gasto(libro, date(2026, 3, 3), ctas.credito, cat("INTERESES DE TARJETAS"), 300, "Intereses")
    movimientos.registrar_gasto(libro, date(2026, 3, 4), ctas.debito, cat("IMPUESTOS"), 800, "ISR ficticio")
    movimientos.registrar_gasto(libro, date(2026, 3, 5), ctas.debito, cat("SEGURO DE VIDA"), 200, "Seguro ficticio")
    return libro


def test_los_estados_se_agrupan_por_rubro_y_siguen_cuadrando(con_movimientos, cat):
    libro = con_movimientos
    r = cb.resultados(libro, [ANIO])
    assert [(x.seccion, x.grupo, x.nombre) for x in r.gastos] == [
        ("Gastos de vida", "ALIMENTACION", "ALIMENTOS"), ("Gastos de vida", "FINANZAS", "SEGURO DE VIDA"),
        ("Gastos financieros", "FINANZAS", "INTERESES DE TARJETAS"), ("Impuestos", "FINANZAS", "IMPUESTOS")]
    f = cb.flujo(libro, [ANIO])
    dia = {x.nombre: x.importes[0] for x in f.renglones if x.naturaleza == cb.DIA_A_DIA}
    assert dia == {"Cobraste: Ingresos por tu trabajo": D(20_000), "Pagaste: Gastos de vida": D(-1_700),
                   "Pagaste: Impuestos": D(-800)}                    # los intereses se cargaron a la tarjeta
    assert f.cuadra
    b = cb.balanza(libro, *ANIO)
    rubros = {c.nombre: c.rubro for c in b.cuentas}
    assert rubros["FINANZAS › IMPUESTOS"] == "Impuestos" and rubros["Banco Ficticio Débito"] == cb.EFECTIVO_Y_BANCOS
    assert rubros["Tarjeta Ficticia"] == cb.TARJETAS
    juntas = [(c.rubro, c.nombre) for c in b.por_categoria().cuentas if c.nombre == "FINANZAS"]
    assert juntas == [("Gastos de vida", "FINANZAS"), ("Gastos financieros", "FINANZAS"), ("Impuestos", "FINANZAS")]

    antes = (r.total_gastos(), r.resultado(), cb.situacion(libro, [ANIO[1]]).total(cb.PATRIMONIO))
    rc.asignar(libro, cat("ALIMENTOS"), RC_IMPUESTOS)                 # mover no cambia ningún total
    despues = cb.resultados(libro, [ANIO])
    assert (despues.total_gastos(), despues.resultado(),
            cb.situacion(libro, [ANIO[1]]).total(cb.PATRIMONIO)) == antes
    assert cb.balanza(libro, *ANIO).cuadra and cb.flujo(libro, [ANIO]).cuadra
    assert [x.seccion for x in despues.gastos][0] == "Gastos de vida"           # en el orden de los rubros
    flujo = {x.nombre: x for x in cb.flujo(libro, [ANIO]).renglones}
    assert [m.descripcion for m in cb.movimientos(libro, flujo["Pagaste: Impuestos"].origen)] == [
        "ISR ficticio", "Súper ficticio"]                               # el detalle sigue al rubro


def test_comparar_balanzas_con_una_categoria_en_dos_rubros(con_movimientos):
    actual = cb.balanza(con_movimientos, *ANIO).por_categoria()
    anterior = cb.balanza(con_movimientos, date(2025, 1, 1), date(2025, 12, 31)).por_categoria()
    filas = cb.comparar_balanzas(actual, anterior)
    assert sum(x.cuenta.nombre == "FINANZAS" for x in filas) == 3


def test_se_guarda_se_respalda_y_se_restaura(tmp_path):
    s = Sesion(tmp_path / "Datos" / "tally.db", reloj=lambda: AHORA)
    with s.cambio() as lib:
        from motor import perfil

        perfil.configurar(lib, "Usuario Ficticio")
        negocio = rc.crear(lib, "Mi negocio", "gasto")
        rc.asignar(lib, categorias.buscar(lib, "PAPELERIA").id, negocio.id)
    otra = Sesion(tmp_path / "Datos" / "tally.db", reloj=lambda: AHORA)
    assert [r.nombre for r in otra.libro.rubros_contables_propios()] == ["Mi negocio"]
    assert rc.de(otra.libro, categorias.buscar(otra.libro, "PAPELERIA").id).nombre == "Mi negocio"
    resumen = [auditoria.resumen(r) for r in otra.almacen.bitacora(limite=3)]
    assert any("Rubro contable «Mi negocio»" in t for t in resumen)
    assert any("Subcategoría «PAPELERIA» (rubro contable)" in t for t in resumen)

    respaldo = respaldos.crear(otra, tmp_path / "Respaldos")
    with otra.cambio() as lib:
        rc.eliminar(lib, negocio.id)
    respaldos.restaurar(otra, respaldo, carpeta_seguridad=tmp_path / "Respaldos")
    assert rc.de(otra.libro, categorias.buscar(otra.libro, "PAPELERIA").id).nombre == "Mi negocio"


def test_un_rubro_contable_roto_se_detecta(libro):
    datos = instantanea(libro)
    papeleria = categorias.buscar(libro, "PAPELERIA").id
    datos["categoria"][papeleria]["rubro_contable_id"] = "no-existe"
    with pytest.raises(ErrorDatos, match="rubro contable inexistente"):
        libro_desde_instantanea(datos)
    datos["categoria"][papeleria]["rubro_contable_id"] = RC_TRABAJO           # de ingreso, y PAPELERIA es gasto
    with pytest.raises(ErrorDatos, match="mismo tipo que su rubro contable"):
        libro_desde_instantanea(datos)
