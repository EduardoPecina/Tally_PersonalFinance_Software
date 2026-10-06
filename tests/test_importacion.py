"""Carga masiva desde la plantilla de texto. Todos los datos son ficticios."""

from datetime import date
from decimal import Decimal

import pytest

from conftest import AHORA, D
from motor import categorias, cuentas, importacion, reportes, tarjetas
from motor.errores import ErrorValidacion
from motor.importacion import Destino, leer
from motor.modelo import ClaseCategoria, TipoCuenta, TipoOperacion
from motor.serializacion import instantanea
from motor.sesion import Sesion

JULIO = (date(2026, 7, 1), date(2026, 7, 31))
COLUMNAS = "FECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\tNOTAS\n"


def archivo(*bloques: str) -> str:
    return "\n".join(bloques)


def bloque(cuenta: str, tipo: str | None, filas: list[str], saldo: str = "") -> str:
    texto = f"CUENTA: {cuenta}\n" + (f"TIPO: {tipo}\n" if tipo else "") + (f"SALDO INICIAL: {saldo}\n" if saldo else "")
    return texto + COLUMNAS + "".join(f + "\n" for f in filas)


def saldo(libro, nombre) -> Decimal:
    return cuentas.saldo(libro, cuentas.buscar(libro, nombre).id)


def estados(resultado) -> dict[str, int]:
    return {e: resultado.contar(e) for e in (importacion.NUEVO, importacion.YA_ESTABA, importacion.CONTRAPARTE,
                                             importacion.PENDIENTE, importacion.ERROR) if resultado.contar(e)}


# ------------------------------------------------------------------ plantillas


def test_la_plantilla_completa_se_carga_tal_cual(libro):
    texto = importacion.plantilla()
    previa = importacion.vista_previa(libro, leer(texto))
    assert previa.se_puede_cargar and not previa.pendientes and not previa.errores
    assert estados(previa) == {importacion.NUEVO: 22, importacion.CONTRAPARTE: 3}
    assert libro.cuentas() == []                                          # la vista previa no toca nada

    importacion.cargar(libro, leer(texto))
    assert {c.nombre: c.tipo for c in libro.cuentas()} == {
        "Mi tarjeta de débito": TipoCuenta.DEBITO, "Mi tarjeta de crédito": TipoCuenta.CREDITO,
        "Mi cuenta de ahorro": TipoCuenta.AHORRO, "Mi inversión": TipoCuenta.INVERSION}
    assert saldo(libro, "Mi tarjeta de débito") == D("4199.90")
    assert tarjetas.deuda(libro, cuentas.buscar(libro, "Mi tarjeta de crédito").id) == D("85.30")
    # Las transferencias que vienen en las dos cuentas cuentan una sola vez y no son gasto.
    pagos = [op for op in libro.operaciones() if op.tipo is TipoOperacion.PAGO_TARJETA]
    assert len(pagos) == 1
    resumen = reportes.resumen(libro, *JULIO)
    assert resumen.apartado_a_ahorro == D(3500)

    # Subir el mismo archivo otra vez no duplica nada.
    otra_vez = importacion.vista_previa(libro, leer(texto))
    assert estados(otra_vez) == {importacion.YA_ESTABA: 22, importacion.CONTRAPARTE: 3}
    assert not otra_vez.se_puede_cargar and not otra_vez.cuentas_nuevas


@pytest.mark.parametrize("tipo", importacion.TIPOS_CON_PLANTILLA)
def test_cada_plantilla_por_tipo_se_carga_sin_errores(libro, tipo):
    previa = importacion.vista_previa(libro, leer(importacion.plantilla(tipo)))
    assert previa.se_puede_cargar, (previa.errores, previa.pendientes)
    assert importacion.nombre_de_plantilla(tipo).endswith(".txt")


# ------------------------------------------------------------------ lectura


def test_formatos_de_fecha_e_importe():
    leida = leer(bloque("Débito", "DEBITO", [
        "15/07/2026\tA\tDESPENSA\t$1,234.50\t",
        "5/7/26\tB\tDESPENSA\t1234.5\t",
        "2026-07-15\tC\tDESPENSA\t1 234,50\t",
        "15-jul-2026\tD\tDESPENSA\t(10.00)\t",
        "15.07.2026 00:00\tE\tDESPENSA\t\t-25",
        "15/07/2026\tF\tNOMINA\t\t1,000",
    ]))
    assert leida.errores == []
    (b,) = leida.bloques
    assert [ln.fecha for ln in b.lineas] == [date(2026, 7, 15), date(2026, 7, 5)] + [date(2026, 7, 15)] * 4
    assert [ln.centavos for ln in b.lineas] == [-123450, -123450, -123450, 1000, -2500, 100000]


def test_errores_de_lectura_con_numero_de_linea():
    leida = leer(
        "15/07/2026\tAntes de la cuenta\tDESPENSA\t10\t\n"
        + bloque("Débito", "CHEQUERA", [
            "15/07/2026\tAmbos\tDESPENSA\t10\t10",
            "15/07/2026\tSin importe\tDESPENSA\t\t",
            "31/02/2026\tFecha mala\tDESPENSA\t10\t",
            "15/07/2026\tImporte malo\tDESPENSA\tdiez\t",
        ])
    )
    texto = " | ".join(leida.errores)
    assert "Línea 1: antes de los movimientos" in texto
    assert "Línea 3: tipo de cuenta «CHEQUERA» no reconocido" in texto
    assert "Línea 5: llena CARGO o ABONO, no los dos" in texto
    assert "Línea 6: falta el importe" in texto
    assert "Línea 7: fecha «31/02/2026» no válida" in texto
    assert "Línea 8: importe «diez» no válido" in texto


def test_columnas_en_otro_orden_otros_separadores_y_comentarios():
    texto = ("# comentario\nCUENTA: Débito\nTIPO: tarjeta de débito\n\n"
             "Concepto;Cargo;Abono;Categoría;Fecha\nSúper;100;;despensa;15/07/2026\n")
    (b,) = leer(texto).bloques
    assert b.tipo is TipoCuenta.DEBITO
    (linea,) = b.lineas
    assert (linea.descripcion, linea.destino, linea.centavos, linea.fecha) == ("Súper", "despensa", -10000,
                                                                               date(2026, 7, 15))


def test_archivo_guardado_en_ansi():
    datos = bloque("Débito", "DEBITO", ["15/07/2026\tCafé\tDESPENSA\t10\t"]).encode("cp1252")
    assert leer(importacion.decodificar(datos)).bloques[0].lineas[0].descripcion == "Café"


# ------------------------------------------------------------- interpretación


def test_reglas_contables_por_tipo_de_cuenta(libro):
    texto = archivo(
        bloque("Débito", "DEBITO", [
            "01/07/2026\tQuincena\tNómina\t\t10000",
            "02/07/2026\tSúper\tdespensa\t500\t",
            "03/07/2026\tDevolución\tDESPENSA\t\t100",
            "04/07/2026\tPago TDC\tTarjeta\t300\t",
            "05/07/2026\tCuadre\tAjuste de saldo\t\t5",
        ], saldo="1000"),
        bloque("Tarjeta", "CREDITO", [
            "02/07/2026\tCena\tRESTAURANTES\t300\t",
            "06/07/2026\tIntereses\tINTERESES DE TARJETAS\t20\t",
        ], saldo="200"),
        bloque("Inversión", "INVERSION", [
            "31/07/2026\tMinusvalía\tINTERESES Y RENDIMIENTOS\t40\t",
        ], saldo="5000"),
    )
    importacion.cargar(libro, leer(texto))
    tipos = [op.tipo for op in libro.operaciones() if op.tipo is not TipoOperacion.SALDO_INICIAL]
    assert tipos == [TipoOperacion.INGRESO, TipoOperacion.GASTO, TipoOperacion.GASTO, TipoOperacion.REEMBOLSO,
                     TipoOperacion.PAGO_TARJETA, TipoOperacion.AJUSTE, TipoOperacion.GASTO, TipoOperacion.RENDIMIENTO]
    assert saldo(libro, "Débito") == D(1000 + 10000 - 500 + 100 - 300 + 5)
    assert tarjetas.deuda(libro, cuentas.buscar(libro, "Tarjeta").id) == D(200 + 300 + 20 - 300)
    assert saldo(libro, "Inversión") == D(4960)
    resumen = reportes.resumen(libro, *JULIO)
    # Gastos: súper 500 − devolución 100 + cena 300 + intereses 20. El pago de la tarjeta no es gasto.
    assert resumen.gastos == D(720)
    assert resumen.ingresos == D(10000 - 40)                 # la minusvalía resta del ingreso
    assert resumen.ajustes == D(5)


def test_cuenta_existente_nombre_sin_acentos_y_tipo_incorrecto(libro, ctas):
    texto = bloque("banco ficticio debito", None, ["15/07/2026\tSúper\tDESPENSA\t10\t"])
    importacion.cargar(libro, leer(texto))
    assert saldo(libro, "Banco Ficticio Débito") == D(-10) and len(libro.cuentas()) == 4

    previa = importacion.vista_previa(libro, leer(bloque("Ahorro Ficticio", "CREDITO", ["15/07/2026\tX\tDESPENSA\t1\t"])))
    assert any("ya existe en TALLY y no es de ese tipo" in e for e in previa.errores)
    previa = importacion.vista_previa(libro, leer(bloque("Cuenta nueva", None, ["15/07/2026\tX\tDESPENSA\t1\t"])))
    assert any("escribe su TIPO" in e for e in previa.errores) and not previa.se_puede_cargar


def test_nombres_desconocidos_se_mapean(libro, ctas):
    texto = bloque("Banco Ficticio Débito", None, [
        "01/07/2026\tCafé\tCafecitos\t60\t",
        "02/07/2026\tCafé\tcafecitos\t40\t",
        "03/07/2026\tDentista\tDoctor\t900\t",
        "04/07/2026\tAl apartado\tMi apartado\t500\t",
        "05/07/2026\tSin nada\t\t15\t",
        "06/07/2026\tDepósito\t\t\t70",
    ])
    leida = leer(texto)
    previa = importacion.vista_previa(libro, leida)
    pendientes = {d.nombre: (d.filas, d.sugerencia) for d in previa.pendientes}
    assert pendientes == {
        "CAFECITOS": (2, ClaseCategoria.GASTO), "DOCTOR": (1, ClaseCategoria.GASTO),
        "MI APARTADO": (1, ClaseCategoria.GASTO),
        "(SIN SUBCATEGORIA EN CARGOS)": (1, ClaseCategoria.GASTO),
        "(SIN SUBCATEGORIA EN ABONOS)": (1, ClaseCategoria.INGRESO),
    }
    assert not previa.se_puede_cargar and previa.contar(importacion.PENDIENTE) == 6

    clave = {d.nombre: d.clave for d in previa.pendientes}
    mapeo = {
        clave["CAFECITOS"]: Destino.nueva(categorias.buscar_rubro(libro, "Alimentación").id),
        clave["DOCTOR"]: Destino.subcategoria(categorias.buscar(libro, "Consultas médicas").id),
        clave["MI APARTADO"]: Destino.cuenta(ctas.ahorro),
        clave["(SIN SUBCATEGORIA EN CARGOS)"]: Destino.subcategoria(categorias.buscar(libro, "Otros gastos").id),
        clave["(SIN SUBCATEGORIA EN ABONOS)"]: Destino.subcategoria(categorias.buscar(libro, "Otros ingresos").id),
    }
    previa = importacion.vista_previa(libro, leida, mapeo)
    assert previa.se_puede_cargar and previa.subcategorias_nuevas == ["ALIMENTACION › CAFECITOS"]
    assert categorias.buscar(libro, "Cafecitos") is None                 # todavía no se crea

    importacion.cargar(libro, leida, mapeo)
    cafecitos = categorias.buscar(libro, "cafecitos")
    assert cafecitos.nombre == "CAFECITOS" and categorias.nombre_rubro(libro, cafecitos.id) == "ALIMENTACION"
    assert saldo(libro, "Ahorro Ficticio") == D(500)
    assert reportes.resumen(libro, *JULIO).gastos == D(60 + 40 + 900 + 15)


def test_no_se_crea_una_subcategoria_para_filas_vacias(libro, ctas):
    leida = leer(bloque("Banco Ficticio Débito", None, ["05/07/2026\tSin nada\t\t15\t"]))
    (pendiente,) = importacion.vista_previa(libro, leida).pendientes
    previa = importacion.vista_previa(libro, leida, {pendiente.clave: Destino.nueva(libro.rubros()[0].id)})
    assert any("subcategoría existente" in e for e in previa.errores) and not previa.se_puede_cargar


def test_duplicados(libro, ctas):
    filas = ["15/07/2026\tCafé\tCAFETERIAS\t50\t", "15/07/2026\tCafé\tCAFETERIAS\t50\t"]
    texto = bloque("Banco Ficticio Débito", None, filas)
    assert importacion.vista_previa(libro, leer(texto)).nuevos == 2       # dos cafés iguales en el mismo día
    importacion.cargar(libro, leer(bloque("Banco Ficticio Débito", None, filas[:1])))
    previa = importacion.vista_previa(libro, leer(texto))
    assert estados(previa) == {importacion.NUEVO: 1, importacion.YA_ESTABA: 1}


def test_transferencia_en_un_solo_lado_tambien_se_carga(libro):
    texto = archivo(
        bloque("Débito", "DEBITO", ["10/07/2026\tAl ahorro\tAhorro\t100\t", "11/07/2026\tAl ahorro\tAhorro\t100\t"]),
        bloque("Ahorro", "AHORRO", ["10/07/2026\tDel débito\tDébito\t\t100"]),
    )
    previa = importacion.vista_previa(libro, leer(texto))
    assert estados(previa) == {importacion.NUEVO: 2, importacion.CONTRAPARTE: 1}
    importacion.cargar(libro, leer(texto))
    assert saldo(libro, "Ahorro") == D(200) and saldo(libro, "Débito") == D(-200)


def test_errores_de_reglas_por_fila(libro, ctas):
    categorias.archivar(libro, categorias.buscar(libro, "Bonos").id)
    texto = bloque("Banco Ficticio Débito", None, [
        "01/07/2026\tBono\tBONOS\t\t100",
        "02/07/2026\tA mí mismo\tBanco Ficticio Débito\t5\t",
        "03/07/2026\tInicio\tSaldo inicial\t\t5",
    ])
    previa = importacion.vista_previa(libro, leer(texto))
    detalles = {f.numero: f.detalle for f in previa.filas if f.estado == importacion.ERROR}
    assert "archivada" in detalles[3]
    assert "misma cuenta" in detalles[4]
    assert "SALDO INICIAL" in detalles[5]
    with pytest.raises(ErrorValidacion, match="No se cargó nada"):
        importacion.cargar(libro, leer(texto))


def test_en_la_sesion_es_todo_o_nada(tmp_path):
    sesion = Sesion(tmp_path / "tally.db", reloj=lambda: AHORA)
    antes = instantanea(sesion.libro)
    texto = bloque("Débito", "DEBITO", ["01/07/2026\tBien\tDESPENSA\t10\t", "02/07/2026\tMal\tAjena\t5\t"])
    with pytest.raises(ErrorValidacion):
        with sesion.cambio() as libro:
            importacion.cargar(libro, leer(texto))
    assert instantanea(sesion.libro) == antes
    assert instantanea(Sesion(tmp_path / "tally.db", reloj=lambda: AHORA).libro) == antes
