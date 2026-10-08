"""Reglas automáticas de categorías (motor/reglas_categorias.py). Solo comercios y montos ficticios."""

from datetime import date

import pytest

from motor import bancos, categorias, importacion, movimientos, reglas_categorias as reglas
from motor.bancos import Movimiento
from motor.errores import ErrorValidacion
from motor.importacion import leer
from motor.modelo import ClaseCategoria, TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea, verificar_integridad

DIA = date(2026, 7, 15)
GASTO, INGRESO = ClaseCategoria.GASTO, ClaseCategoria.INGRESO


def gasto(libro, cuenta_id, categoria_id, descripcion, monto=100, fecha=DIA):
    return movimientos.registrar_gasto(libro, fecha, cuenta_id, categoria_id, monto, descripcion)


# ------------------------------------------------------------------ alta, cambios y baja


def test_crear_normaliza_el_texto(libro, cat):
    regla = reglas.crear(libro, "  Óxxo  gas. ", cat("GASOLINA"), hoy=DIA)
    assert regla.texto == "OXXO GAS" and regla.creada == DIA and regla.cuenta_id is None
    assert libro.reglas() == [regla]


@pytest.mark.parametrize("texto", ["", " ", "x", "*.-"])
def test_el_texto_debe_tener_al_menos_dos_letras(libro, cat, texto):
    with pytest.raises(ErrorValidacion, match="al menos 2"):
        reglas.crear(libro, texto, cat("GASOLINA"))


def test_solo_subcategorias_de_gasto_o_ingreso_activas(libro, cat):
    rubro = categorias.buscar_rubro(libro, "TRANSPORTE")
    with pytest.raises(Exception):
        reglas.crear(libro, "PEMEX", rubro.id)                       # una categoría, no subcategoría
    with pytest.raises(ErrorValidacion, match="gasto o de ingreso"):
        reglas.crear(libro, "AJUSTE", "sistema-ajuste")
    categorias.archivar(libro, cat("GASOLINA"))
    with pytest.raises(ErrorValidacion, match="archivada"):
        reglas.crear(libro, "PEMEX", cat("GASOLINA"))


def test_no_se_repite_el_mismo_texto_en_la_misma_cuenta(libro, cat, ctas):
    reglas.crear(libro, "Tienda Ficticia", cat("DESPENSA"))
    with pytest.raises(ErrorValidacion, match="Ya tienes una regla"):
        reglas.crear(libro, "TIENDA  FICTICIA", cat("ALIMENTOS"))
    reglas.crear(libro, "Tienda Ficticia", cat("ALIMENTOS"), cuenta_id=ctas.credito)   # en otra cuenta, sí
    assert len(libro.reglas()) == 2


def test_editar_y_eliminar(libro, cat, ctas):
    regla = reglas.crear(libro, "CAFE FICTICIO", cat("RESTAURANTES"))
    editada = reglas.editar(libro, regla.id, texto="cafeteria ficticia", cuenta_id=ctas.debito)
    assert editada.texto == "CAFETERIA FICTICIA" and editada.cuenta_id == ctas.debito
    assert not reglas.editar(libro, regla.id, activa=False).activa
    assert reglas.editar(libro, regla.id, cuenta_id="").cuenta_id is None
    reglas.eliminar(libro, regla.id)
    assert libro.reglas() == []


# ------------------------------------------------------------------ cómo se compara


def test_el_texto_debe_empezar_una_palabra(libro, cat):
    reglas.crear(libro, "UBER", cat("TAXI Y APPS DE VIAJE"))
    indice = reglas.Indice(libro)
    assert indice.buscar("UBER *TRIP 1234", GASTO)
    assert indice.buscar("PAGO UBERTRIP", GASTO)                    # empieza la palabra
    assert indice.buscar("Übér viaje", GASTO)                        # sin acentos ni mayúsculas
    assert indice.buscar("SUBERO FICTICIO", GASTO) is None           # a media palabra, no
    assert indice.buscar("UBER", INGRESO) is None                    # una regla de gasto no aplica a lo que entra


def test_gana_el_texto_mas_largo_y_la_regla_de_la_cuenta(libro, cat, ctas):
    general = reglas.crear(libro, "AMAZON", cat("DESPENSA"))
    prime = reglas.crear(libro, "AMAZON PRIME", cat("STREAMING DE VIDEO"))
    de_la_tarjeta = reglas.crear(libro, "AMAZON", cat("ALIMENTOS"), cuenta_id=ctas.credito)
    indice = reglas.Indice(libro)
    assert indice.buscar("AMAZON MX MARKETPLACE", GASTO) == general
    assert indice.buscar("AMAZON PRIME MEMBERSHIP", GASTO) == prime
    assert indice.buscar("AMAZON PRIME MEMBERSHIP", GASTO, ctas.credito) == prime     # el más largo gana
    assert indice.buscar("AMAZON MX MARKETPLACE", GASTO, ctas.credito) == de_la_tarjeta
    assert indice.buscar("AMAZON MX MARKETPLACE", GASTO, ctas.debito) == general


def test_las_coincidencias_que_se_enciman_tambien_cuentan(libro, cat):
    reglas.crear(libro, "AB CD", cat("DESPENSA"))
    larga = reglas.crear(libro, "CD EF GH", cat("ALIMENTOS"))
    assert reglas.buscar(libro, "AB CD EF GH", GASTO) == larga


def test_una_regla_inactiva_o_de_subcategoria_archivada_no_aplica(libro, cat):
    regla = reglas.crear(libro, "GIMNASIO FICTICIO", cat("RESTAURANTES"))
    reglas.editar(libro, regla.id, activa=False)
    assert reglas.buscar(libro, "GIMNASIO FICTICIO", GASTO) is None
    reglas.editar(libro, regla.id, activa=True)
    categorias.archivar(libro, cat("RESTAURANTES"))
    assert reglas.buscar(libro, "GIMNASIO FICTICIO", GASTO) is None


def test_devoluciones_y_categoria_para_un_movimiento_nuevo(libro, cat):
    reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"))
    reglas.crear(libro, "EMPRESA FICTICIA", cat("NOMINA"))
    indice = reglas.Indice(libro)
    assert indice.para_importe("TIENDA FICTICIA 001", -5_000).categoria_id == cat("DESPENSA")
    assert indice.para_importe("DEVOLUCION TIENDA FICTICIA", 5_000).categoria_id == cat("DESPENSA")
    assert indice.para_importe("TIENDA FICTICIA", 5_000) is None
    assert indice.para_importe("DEPOSITO EMPRESA FICTICIA", 900_000).categoria_id == cat("NOMINA")
    assert reglas.categoria_para(libro, "Tienda ficticia centro", TipoOperacion.GASTO) == cat("DESPENSA")
    assert reglas.categoria_para(libro, "Tienda ficticia centro", "reembolso") == cat("DESPENSA")
    assert reglas.categoria_para(libro, "Tienda ficticia centro", "ingreso") is None
    assert reglas.categoria_para(libro, "Tienda ficticia", "transferencia") is None
    probado = reglas.probar(libro, "EMPRESA FICTICIA PAGO")
    assert probado[GASTO] is None and probado[INGRESO].texto == "EMPRESA FICTICIA"


# ------------------------------------------------------------------ tu historial


def test_pendientes_y_aplicar_al_historial(libro, cat, ctas):
    viejo = gasto(libro, ctas.debito, cat("ALIMENTOS"), "TIENDA FICTICIA 01", fecha=date(2026, 7, 1))
    nuevo = gasto(libro, ctas.debito, cat("ALIMENTOS"), "TIENDA FICTICIA 02", fecha=date(2026, 7, 2))
    gasto(libro, ctas.debito, cat("DESPENSA"), "TIENDA FICTICIA 03")             # ya está bien
    gasto(libro, ctas.debito, cat("ALIMENTOS"), "OTRA COSA")                     # no coincide
    repartido = movimientos.construir(TipoOperacion.GASTO, DIA, ctas.debito, descripcion="TIENDA FICTICIA mixto",
                                      reparto=((cat("ALIMENTOS"), 50), (cat("RESTAURANTES"), 30)))
    libro.agregar_operacion(repartido)                                             # repartido: no se toca
    regla = reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"))

    cambios = reglas.pendientes(libro)
    assert [c.operacion.id for c in cambios] == [nuevo.id, viejo.id]               # del más reciente
    assert all(c.regla == regla and c.categoria_actual == cat("ALIMENTOS") for c in cambios)
    assert reglas.pendientes(libro, regla_id="otra") == []
    assert reglas.contar(libro) == {regla.id: 3}                                  # el repartido no cuenta

    assert reglas.aplicar(libro, cambios) == 2
    assert movimientos.detalle(libro, viejo.id).categoria_id == cat("DESPENSA")
    assert libro.operacion(viejo.id).creado_en == viejo.creado_en                 # el mismo movimiento, editado
    assert reglas.pendientes(libro) == []
    assert reglas.aplicar(libro, cambios) == 0                                     # ya no hay nada que cambiar


def test_aplicar_ignora_lo_borrado_o_cambiado_mientras_tanto(libro, cat, ctas):
    a = gasto(libro, ctas.debito, cat("ALIMENTOS"), "TIENDA FICTICIA 01")
    b = gasto(libro, ctas.debito, cat("ALIMENTOS"), "TIENDA FICTICIA 02")
    reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"))
    cambios = reglas.pendientes(libro)
    movimientos.eliminar(libro, a.id)
    movimientos.editar(libro, b.id, categoria_id=cat("RESTAURANTES"))
    assert reglas.aplicar(libro, cambios) == 0
    assert movimientos.detalle(libro, b.id).categoria_id == cat("RESTAURANTES")


def test_sugerencias_desde_tu_historial(libro, cat, ctas):
    for i in range(4):
        gasto(libro, ctas.debito, cat("RESTAURANTES"), f"COMPRA CAFE FICTICIO {i:04d} SUC CENTRO")
    for i in range(3):                                                             # dividido: no se sugiere
        gasto(libro, ctas.debito, cat("DESPENSA") if i else cat("ALIMENTOS"), f"MERCADO FICTICIO {i}")
    for i in range(2):                                                             # muy pocas veces
        gasto(libro, ctas.debito, cat("GASOLINA"), f"GASOLINERA FICTICIA {i}")
    for i in range(5):                                                             # palabra genérica
        gasto(libro, ctas.debito, cat("ALIMENTOS"), f"TRANSFERENCIA {i}")
    (sugerencia,) = reglas.sugerencias(libro)
    assert (sugerencia.texto, sugerencia.categoria_id, sugerencia.veces) == ("CAFE", cat("RESTAURANTES"), 4)
    reglas.crear(libro, sugerencia.texto, sugerencia.categoria_id)
    assert reglas.sugerencias(libro) == []                                         # ya la cubre una regla


# ------------------------------------------------------------------ integración con el resto de TALLY


def test_al_importar_del_banco_tu_regla_va_primero(libro, cat, ctas):
    # El historial y el catálogo de comercios dirían otra cosa; tu regla manda.
    gasto(libro, ctas.debito, cat("ALIMENTOS"), "OXXO 1234")
    reglas.crear(libro, "OXXO", cat("DESPENSA"))
    reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"), cuenta_id=ctas.credito)
    lista = [Movimiento(1, DIA, "COMPRA OXXO 9999", -5_000), Movimiento(2, DIA, "TIENDA FICTICIA", -1_000),
             Movimiento(3, DIA, "DEVOLUCION OXXO 9999", 5_000)]
    compra, tienda, devolucion = bancos.revisar(libro, ctas.debito, lista)
    assert compra.destino == bancos.destino_subcategoria(cat("DESPENSA"))
    assert compra.motivo == "Por tu regla «OXXO»"
    assert "regla" not in tienda.motivo                                            # esa regla es de la tarjeta
    assert devolucion.destino == bancos.destino_subcategoria(cat("DESPENSA"))


def test_la_plantilla_sin_subcategoria_usa_tus_reglas(libro, cat, ctas):
    reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"))
    texto = ("CUENTA: Banco Ficticio Débito\nFECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\tNOTAS\n"
             "15/07/2026\tTIENDA FICTICIA 01\t\t120.00\t\t\n"
             "16/07/2026\tCOSA SIN REGLA\t\t80.00\t\t\n")
    previa = importacion.vista_previa(libro, leer(texto))
    assert [d.filas for d in previa.pendientes] == [1]                             # solo la que no tiene regla
    (con_regla,) = [f for f in previa.filas if f.estado == importacion.NUEVO]
    assert "DESPENSA" in con_regla.destino and con_regla.detalle == "Por tu regla «TIENDA FICTICIA»"


def test_borrar_la_subcategoria_mueve_o_quita_sus_reglas(libro, cat, ctas):
    uno = reglas.crear(libro, "TIENDA UNO", cat("ALIMENTOS"))
    dos = reglas.crear(libro, "TIENDA DOS", cat("RESTAURANTES"))
    gasto(libro, ctas.debito, cat("ALIMENTOS"), "TIENDA UNO")
    categorias.eliminar(libro, cat("ALIMENTOS"), reasignar_a=cat("DESPENSA"))
    assert libro.regla(uno.id).categoria_id == cat("DESPENSA")
    categorias.eliminar(libro, cat("RESTAURANTES"))
    assert dos.id not in {r.id for r in libro.reglas()}
    assert verificar_integridad(libro) == []


def test_borrar_la_cuenta_borra_sus_reglas(libro, cat, ctas):
    general = reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"))
    reglas.crear(libro, "TIENDA FICTICIA", cat("ALIMENTOS"), cuenta_id=ctas.ahorro)
    libro.quitar_cuenta(ctas.ahorro)
    assert libro.reglas() == [general]


def test_se_guardan_y_se_restauran(libro, cat, ctas):
    regla = reglas.crear(libro, "TIENDA FICTICIA", cat("DESPENSA"), cuenta_id=ctas.debito, hoy=DIA)
    otra = libro_desde_instantanea(instantanea(libro), libro.secuencia)
    assert otra.reglas() == [regla]


@pytest.mark.parametrize("descripciones, esperado", [
    (["COMPRA OXXO 1234 SUC CENTRO", "OXXO 9876 NORTE"], "OXXO"),
    (["PAGO NOMINA EMPRESA FICTICIA"], "EMPRESA"),          # «NOMINA» dice qué es, no de quién
    (["SPEI 123", "SPEI 456"], None),
    ([], None),
])
def test_texto_para_una_regla_nueva(descripciones, esperado):
    assert reglas.texto_para(descripciones) == esperado
