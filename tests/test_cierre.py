"""Cierre de mes: la boleta del mes, recomendaciones, y cerrar sin bloquear (cambios después de cerrar). Solo datos
ficticios."""

from datetime import date, datetime

import pytest

from conftest import D
from motor import categorias, cierre, cuentas, metas, movimientos, perfil, recurrentes, temporales
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Perfil
from motor.serializacion import instantanea, libro_desde_instantanea


class Reloj:
    def __init__(self, momento: datetime) -> None:
        self.momento = momento

    def __call__(self) -> datetime:
        return self.momento


@pytest.fixture
def reloj():
    return Reloj(datetime(2026, 8, 3, 9, 0))


@pytest.fixture
def libro(reloj) -> Libro:
    """Un libro cuyo reloj se puede adelantar (para registrar algo «después de cerrar»)."""
    lib = Libro(reloj=reloj)
    categorias.cargar_catalogo_inicial(lib)
    return lib


@pytest.fixture
def julio(libro, ctas, cat):
    """Abril a junio iguales; julio con más restaurantes, cafés, intereses y una suscripción."""
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 30_000, date(2026, 4, 1))
    for mes in (4, 5, 6, 7):
        movimientos.registrar_ingreso(libro, date(2026, mes, 15), ctas.debito, cat("NOMINA"), 20_000, "Nómina")
        movimientos.registrar_gasto(libro, date(2026, mes, 3), ctas.debito, cat("RENTA"), 8_000, "Renta")
        movimientos.registrar_gasto(libro, date(2026, mes, 10), ctas.debito, cat("RESTAURANTES"),
                                    2_500 if mes == 7 else 1_000, "Restaurante")
    for dia in range(1, 17):
        movimientos.registrar_gasto(libro, date(2026, 7, dia), ctas.debito, cat("CAFETERIAS"), 50, "Café")
    movimientos.registrar_gasto(libro, date(2026, 7, 25), ctas.credito, cat("INTERESES DE TARJETAS"), 120, "Intereses")
    recurrentes.crear(libro, "Streaming Ficticio", "gasto", 199, ctas.credito, "mensual", date(2026, 4, 20),
                      categoria_id=cat("STREAMING DE VIDEO"), suscripcion=True)
    movimientos.registrar_gasto(libro, date(2026, 7, 20), ctas.credito, cat("STREAMING DE VIDEO"), 199, "Streaming")
    recurrentes.crear(libro, "Renta Cobrada Ficticia", "ingreso", 3_000, ctas.debito, "mensual", date(2026, 7, 28),
                      categoria_id=cat("RENTAS COBRADAS"))
    categorias.fijar_presupuesto(libro, categorias.buscar_rubro(libro, "ALIMENTACION").id, 3_000)
    m = metas.crear(libro, "Viaje Ficticio", 10_000)
    metas.aportar(libro, m.id, 1_000, date(2026, 7, 5))
    temporales.registrar(libro, date(2026, 7, 7), ctas.debito, 50, "Verificación ficticia")
    return ctas


def test_la_boleta_del_mes(libro, julio):
    r = cierre.reporte(libro, 2026, 7)
    assert not r.en_curso and not r.cerrado
    assert (r.numeros.ingresos, r.numeros.gastos, r.numeros.ahorro, r.numeros.tasa) == (
        D(20_000), D(11_619), D(8_381), D("41.9"))
    assert (r.anterior.gastos, r.promedio.gastos) == (D(9_000), D(9_000))
    alimentacion = next(x for x in r.rubros if x.nombre == "ALIMENTACION")
    assert (alimentacion.gastado, alimentacion.promedio, alimentacion.diferencia) == (D(3_300), D(1_000), D(2_300))
    assert [x.nombre for x in r.subieron] == ["ALIMENTACION"]
    assert (r.hormiga.veces, r.hormiga.total, r.hormiga.ejemplos[0]) == (16, D(800), ("Café", 16, D(800)))
    assert r.suscripciones == [("Streaming Ficticio", D(199))]
    (presupuesto,) = r.presupuestos
    assert presupuesto.restante == D(-300)
    (renta,) = r.ingresos_fijos
    assert (renta.esperado, renta.recibido, renta.faltan) == (D(3_000), D(0), [date(2026, 7, 28)])
    (tarjeta,) = r.deudas
    assert (tarjeta.al_inicio, tarjeta.al_final, tarjeta.cambio) == (D(0), D(319), D(319))
    assert r.intereses == D(120)
    (viaje,) = r.metas
    assert (viaje.aportado, viaje.ahorrado) == (D(1_000), D(1_000))
    assert (r.patrimonio_inicio, r.patrimonio_fin) == (D(63_000), D(71_381))
    assert [p.clase for p in r.pendientes] == ["temporal", "calendario"]
    assert r.recomendaciones[0].startswith("En ALIMENTACION gastaste $2,300.00 más que tu promedio")
    assert "presupuesto de ALIMENTACION por $300.00" in r.recomendaciones[1]
    assert "$120.00 de intereses" in r.recomendaciones[2]


def test_un_mes_con_deficit_y_otro_sin_problemas(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 6, 1), ctas.debito, cat("NOMINA"), 10_000)
    movimientos.registrar_gasto(libro, date(2026, 6, 2), ctas.debito, cat("RENTA"), 12_000)
    assert cierre.reporte(libro, 2026, 6).recomendaciones[0].startswith("Gastaste $2,000.00 más de lo que entró")
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("NOMINA"), 10_000)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("RENTA"), 5_000)
    assert cierre.reporte(libro, 2026, 7).recomendaciones == [
        "¡Buen mes! Ahorraste el 50.0 % de lo que entró. Si te sobra, súmalo a una meta o a tu fondo de emergencia."]


def test_cerrar_no_bloquea_y_muestra_lo_que_cambio_despues(libro, julio, reloj, cat):
    assert cierre.recordar(libro) == (2026, 7)                     # 3 de agosto: toca cerrar julio
    c = cierre.cerrar(libro, 2026, 7, "  Revisado con el banco  ")
    assert (c.id, c.notas, c.cerrado_en) == ("2026-07", "Revisado con el banco", datetime(2026, 8, 3, 9, 0))
    assert cierre.recordar(libro) is None
    assert not cierre.reporte(libro, 2026, 7).cambios.hay
    assert libro_desde_instantanea(instantanea(libro)).cierres() == [c]
    with pytest.raises(ErrorValidacion, match="aún no termina"):
        cierre.cerrar(libro, 2026, 8)

    reloj.momento = datetime(2026, 8, 4, 10, 0)                     # al día siguiente…
    antes = cierre.huella(libro)
    tarde = movimientos.registrar_gasto(libro, date(2026, 7, 30), julio.debito, cat("RESTAURANTES"), 300, "Olvidado")
    assert cierre.meses_tocados(libro, antes) == ["2026-07"]           # el portal avisa
    renta = next(op for op in libro.operaciones(date(2026, 7, 3), date(2026, 7, 3)))
    movimientos.editar(libro, renta.id, descripcion="Renta de julio")
    cafe = next(op for op in libro.operaciones(date(2026, 7, 16), date(2026, 7, 16)))
    movimientos.eliminar(libro, cafe.id)
    antes = cierre.huella(libro)
    movimientos.registrar_gasto(libro, date(2026, 8, 2), julio.debito, cat("RESTAURANTES"), 100)
    assert cierre.meses_tocados(libro, antes) == []                    # agosto no está cerrado

    cambios = cierre.reporte(libro, 2026, 7).cambios
    assert cambios.hay and (cambios.gastos, cambios.ingresos, cambios.patrimonio) == (D(250), D(0), D(-250))
    assert [op.id for op in cambios.nuevos] == [tarde.id] and [op.id for op in cambios.editados] == [renta.id]
    assert cambios.borrados == 1
    cierre.cerrar(libro, 2026, 7)                                      # volver a cerrar: acepta los cambios
    assert not cierre.reporte(libro, 2026, 7).cambios.hay
    cierre.reabrir(libro, 2026, 7)
    assert libro.cierres() == [] and cierre.recordar(libro) == (2026, 7)


def test_meses_y_cuando_recordar(libro, julio, reloj):
    assert cierre.meses(libro) == [(2026, 8), (2026, 7), (2026, 6), (2026, 5), (2026, 4)]
    reloj.momento = datetime(2026, 8, 15, 9, 0)
    assert cierre.recordar(libro) is None                              # ya pasaron los primeros días
    assert cierre.reporte(libro, 2026, 8).en_curso


def test_sin_movimientos(libro):
    assert cierre.meses(libro) == [] and cierre.recordar(libro) is None
    r = cierre.reporte(libro, 2026, 7)
    assert r.numeros.tasa is None and r.recomendaciones == [] and r.rubros == []


# ------------------------------------------------------------------ gastos hormiga a tu gusto


def _hormiga(libro):
    return cierre.reporte(libro, 2026, 7).hormiga


def test_gastos_hormiga_automaticos_por_omision(libro, julio):
    perfil.configurar(libro, "Usuaria Ficticia")
    a = cierre.ajustes_hormiga(libro)
    assert a == cierre.AjustesHormiga() and a.automatico and (a.veces, a.porcentaje) == (15, 10)
    p = Perfil("x", datetime(2026, 1, 1))                         # el perfil y el cierre dicen lo mismo
    assert (p.hormiga_tope, p.hormiga_fuera, p.hormiga_veces, p.hormiga_porcentaje) == (
        None, (), cierre.HORMIGA_VECES, cierre.HORMIGA_PORCENTAJE)
    h = _hormiga(libro)
    assert (h.umbral, h.veces, h.total) == (D(100), 16, D(800))  # 1 % de $11,619, redondeado: menos de $100


def test_un_monto_fijo_para_gasto_hormiga(libro, julio):
    perfil.configurar(libro, "Usuaria Ficticia")
    cierre.ajustar_hormiga(libro, tope=200)
    h = _hormiga(libro)                                          # ahora también los intereses y el streaming
    assert (h.umbral, h.veces, h.total) == (D(200), 18, D(1_119)) and not h.ajustes.automatico
    assert [e[0] for e in h.ejemplos] == ["Café", "Streaming", "Intereses"]
    cierre.ajustar_hormiga(libro, tope=None)                     # de vuelta a automático
    assert _hormiga(libro).umbral == D(100)


def test_subcategorias_que_no_cuentan_como_hormiga(libro, julio, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    cierre.ajustar_hormiga(libro, tope=200, fuera=[cat("CAFETERIAS"), cat("CAFETERIAS")])
    assert cierre.ajustes_hormiga(libro).fuera == (cat("CAFETERIAS"),)
    h = _hormiga(libro)
    assert (h.veces, h.total) == (2, D(319)) and [e[0] for e in h.ejemplos] == ["Streaming", "Intereses"]


def test_una_compra_repartida_cuenta_por_su_total(libro, julio, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    cierre.ajustar_hormiga(libro, fuera=[cat("CAFETERIAS")])
    movimientos.registrar_gasto(libro, date(2026, 7, 30), julio.debito, descripcion="Tienda",
                                reparto=[(cat("CAFETERIAS"), 30), (cat("RESTAURANTES"), 60)])     # $90: chica
    movimientos.registrar_gasto(libro, date(2026, 7, 31), julio.debito, descripcion="Súper",
                                reparto=[(cat("CAFETERIAS"), 400), (cat("RESTAURANTES"), 60)])    # $460: no
    h = _hormiga(libro)
    assert (h.veces, h.total, h.ejemplos) == (1, D(60), [("Tienda", 1, D(60))])


def test_cuando_te_lo_recomienda(libro, julio):
    perfil.configurar(libro, "Usuaria Ficticia")
    gastos = D(11_619)
    assert _hormiga(libro).merece_aviso(gastos)                  # 16 gastos chicos: 15 o más
    cierre.ajustar_hormiga(libro, veces=20, porcentaje=0)
    assert not _hormiga(libro).merece_aviso(gastos)
    cierre.ajustar_hormiga(libro, veces=0, porcentaje=5)          # $800 son el 6.9 % de $11,619
    assert _hormiga(libro).merece_aviso(gastos)
    cierre.ajustar_hormiga(libro, veces=0, porcentaje=7)
    assert not _hormiga(libro).merece_aviso(gastos)
    assert not _hormiga(libro).merece_aviso(D(0))
    assert not cierre.Hormiga(D(100), 0, D(0), []).merece_aviso(D(1_000))


def test_la_recomendacion_de_gastos_hormiga(libro, ctas, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("NOMINA"), 10_000)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("RENTA"), 5_000)
    for dia in range(1, 21):
        movimientos.registrar_gasto(libro, date(2026, 7, dia), ctas.debito, cat("CAFETERIAS"), 40, "Café")

    def menciona() -> bool:
        return any("gastos chicos" in t for t in cierre.reporte(libro, 2026, 7).recomendaciones)
    assert menciona()                                             # 20 gastos de menos de $50
    cierre.ajustar_hormiga(libro, veces=0, porcentaje=0)          # ya no te lo recomienda
    assert not menciona() and cierre.reporte(libro, 2026, 7).hormiga.veces == 20


def test_los_ajustes_de_hormiga_se_guardan(libro, julio, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    cierre.ajustar_hormiga(libro, tope="150.50", fuera=[cat("TRANSPORTE PUBLICO")], veces=8, porcentaje=12)
    copia = libro_desde_instantanea(instantanea(libro))
    assert cierre.ajustes_hormiga(copia) == cierre.AjustesHormiga(D("150.50"), (cat("TRANSPORTE PUBLICO"),), 8, 12)
    assert _hormiga(copia).umbral == D("150.50")


@pytest.mark.parametrize("cambios, motivo", [
    (dict(tope=0), "mayor que cero"),
    (dict(tope=-50), "mayor que cero"),
    (dict(veces=-1), "de 0 a 1000"),
    (dict(veces=1_001), "de 0 a 1000"),
    (dict(veces=True), "de 0 a 1000"),
    (dict(porcentaje=101), "de 0 a 100"),
])
def test_ajustes_de_hormiga_no_validos(libro, cambios, motivo):
    perfil.configurar(libro, "Usuaria Ficticia")
    with pytest.raises(ErrorValidacion, match=motivo):
        cierre.ajustar_hormiga(libro, **cambios)
    assert cierre.ajustes_hormiga(libro) == cierre.AjustesHormiga()


def test_solo_subcategorias_de_gasto_quedan_fuera(libro, cat):
    with pytest.raises(ErrorValidacion, match="bienvenida"):
        cierre.ajustar_hormiga(libro, tope=100)
    perfil.configurar(libro, "Usuaria Ficticia")
    with pytest.raises(ErrorValidacion, match="Solo las subcategorías de gasto"):
        cierre.ajustar_hormiga(libro, fuera=[cat("NOMINA")])


def test_al_borrar_o_juntar_una_subcategoria_excluida(libro, ctas, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    transporte = categorias.buscar_rubro(libro, "MOVILIDAD").id
    propia = categorias.crear(libro, "PASAJES FICTICIOS", transporte).id
    usada = categorias.crear(libro, "CASETAS FICTICIAS", transporte).id
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, usada, 40, "Caseta")
    cierre.ajustar_hormiga(libro, fuera=[propia, usada])
    categorias.eliminar(libro, propia)                                 # sin movimientos: sale de la lista
    assert libro.perfil.hormiga_fuera == (usada,)
    categorias.eliminar(libro, usada, reasignar_a=cat("TRANSPORTE PUBLICO"))        # se junta con otra: esa tampoco cuenta
    assert cierre.ajustes_hormiga(libro).fuera == (cat("TRANSPORTE PUBLICO"),)


def test_una_excluida_que_ya_no_existe_se_ignora(libro, cat):
    perfil.configurar(libro, "Usuaria Ficticia")
    from dataclasses import replace
    libro.perfil = replace(libro.perfil, hormiga_fuera=("no-existe", cat("NOMINA"), cat("TRANSPORTE PUBLICO")))
    assert cierre.ajustes_hormiga(libro).fuera == (cat("TRANSPORTE PUBLICO"),)
