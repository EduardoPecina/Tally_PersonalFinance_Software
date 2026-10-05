"""Pruebas del portal con el banco de pruebas de Streamlit (sin navegador).

Recorren cada página con datos ficticios y verifican que no haya errores y que
las acciones lleguen al motor. Se omiten si Streamlit no está instalado.
"""

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from motor import cuentas, movimientos, perfil, respaldos  # noqa: E402
from motor.sesion import Sesion  # noqa: E402
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "portal" / "app.py")


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("TALLY_RAIZ", str(tmp_path))
    return tmp_path


def sesion_en(raiz) -> Sesion:
    return Sesion(raiz / "Datos" / "tally.db")


@pytest.fixture
def con_datos(raiz):
    """Un libro ficticio con perfil, cuentas y movimientos."""
    s = sesion_en(raiz)
    hoy = s.libro.hoy()
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        debito = cuentas.crear(lib, "Débito Ficticio", "debito", saldo_inicial=5000, fecha_creacion=date(hoy.year, 1, 1)).id
        ahorro = cuentas.crear(lib, "Ahorro Ficticio", "ahorro", fecha_creacion=date(hoy.year, 1, 1)).id
        tdc = cuentas.crear(lib, "TDC Ficticia", "credito", limite_credito=2000, dia_corte=3, dia_pago=23,
                            fecha_creacion=date(hoy.year, 1, 1)).id
        cat = {c.nombre: c.id for c in lib.categorias()}
        movimientos.registrar_ingreso(lib, hoy, debito, cat["Nómina"], 4000, "Nómina")
        movimientos.registrar_gasto(lib, hoy, tdc, cat["Alimentos"], 300, "Pizza")
        movimientos.registrar_gasto(lib, hoy, debito, cat["Transporte"], 80, "Taxi")
        registrar_transferencia(lib, hoy, debito, ahorro, 1000, "Al ahorro")
        registrar_pago_tarjeta(lib, hoy, debito, tdc, 300, "Pago TDC")
    return {"debito": debito, "ahorro": ahorro, "tdc": tdc, "cat": cat}


def abrir(pagina: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    if pagina:
        at.switch_page(pagina).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def boton(at: AppTest, texto: str):
    return next(b for b in at.button if b.label == texto)


def sin_errores(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_bienvenida_crea_cuenta_y_perfil(raiz):
    at = abrir()
    assert at.title[0].value.startswith("¡Hola!")
    at.text_input(key="bienvenida_nombre").input("Usuario Ficticio").run()
    next(t for t in at.text_input if t.label == "Nombre").input("Débito Ficticio")
    next(n for n in at.number_input if n.label.startswith("¿Cuánto tienes")).set_value(1500.0)
    boton(at, "Agregar cuenta").click().run()
    sin_errores(at)
    boton(at, "Empezar a usar TALLY").click().run()
    sin_errores(at)
    assert at.title[0].value == "¡Hola, Usuario Ficticio!"

    lib = sesion_en(raiz).libro
    assert lib.perfil.nombre == "Usuario Ficticio"
    (cuenta,) = cuentas.listar(lib)
    assert cuentas.saldo(lib, cuenta.id) == 1500


def test_resumen_muestra_indicadores(con_datos):
    at = abrir()
    sin_errores(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Gastos"] == "$380.00"  # la compra con TDC y su pago cuentan una sola vez
    assert metricas["Ingresos"] == "$4,000.00"
    assert metricas["Apartado a ahorro"] == "$1,000.00"
    assert metricas["Deuda de tarjetas"] == "$0.00"
    for clave in ("mes_anterior", "quincena", "anio", "12_meses", "personalizado"):
        at.segmented_control(key="_w_inicio_periodo").set_value(clave).run()
        sin_errores(at)


def test_registrar_gasto_y_pago_de_tarjeta(raiz, con_datos):
    at = abrir()
    at.switch_page(_pagina("registrar")).run()
    sin_errores(at)
    next(s for s in at.selectbox if s.label == "Categoría").set_value(con_datos["cat"]["Alimentos"])
    next(s for s in at.selectbox if s.label == "Pagado con").set_value(con_datos["tdc"])
    next(n for n in at.number_input if n.label == "Importe").set_value(125.5)
    next(t for t in at.text_input if t.label == "Descripción").input("Tacos")
    boton(at, "Guardar").click().run()
    sin_errores(at)

    at.segmented_control(key="registrar_tipo").set_value("pago_tarjeta").run()
    next(n for n in at.number_input if n.label == "Importe").set_value(125.5)
    boton(at, "Guardar").click().run()
    sin_errores(at)

    lib = sesion_en(raiz).libro
    assert cuentas.saldo(lib, con_datos["tdc"]) == 0
    from motor import reportes

    assert reportes.resumen(lib, *reportes.rango_periodo(lib, "mes_actual")).gastos == 380 + 125.5


def test_registrar_sin_importe_avisa(con_datos):
    at = abrir()
    at.switch_page(_pagina("registrar")).run()
    boton(at, "Guardar").click().run()
    assert any("importe" in e.value for e in at.error)


def test_historial_filtra_y_conserva_filtros(con_datos):
    at = abrir()
    at.switch_page(_pagina("historial")).run()
    sin_errores(at)
    assert at.dataframe[0].value.shape[0] == 6  # 5 movimientos + saldo inicial
    at.text_input(key="_w_historial_texto").input("pizza").run()
    assert at.dataframe[0].value.shape[0] == 1
    # Ir a otra página y volver: el filtro sigue.
    at.switch_page(_pagina("cuentas")).run()
    at.switch_page(_pagina("historial")).run()
    assert at.text_input(key="_w_historial_texto").value == "pizza"
    assert at.dataframe[0].value.shape[0] == 1
    boton(at, "Quitar todos los filtros (1)").click().run()
    sin_errores(at)
    assert at.dataframe[0].value.shape[0] == 6


def test_cuentas_y_categorias_y_respaldos_cargan(con_datos):
    at = abrir()
    for pagina in ("cuentas", "categorias", "respaldos"):
        at.switch_page(_pagina(pagina)).run()
        sin_errores(at)


def test_crear_cuenta_desde_cuentas(raiz, con_datos):
    at = abrir()
    at.switch_page(_pagina("cuentas")).run()
    at.selectbox(key="cuentas_tipo_nueva").set_value("credito").run()
    next(t for t in at.text_input if t.label == "Nombre" and not t.value).input("TDC Nueva")
    next(n for n in at.number_input if n.label == "¿Cuánto debes hoy?").set_value(450.0)
    boton(at, "Agregar cuenta").click().run()
    sin_errores(at)
    nueva = cuentas.buscar(sesion_en(raiz).libro, "TDC Nueva")
    assert cuentas.saldo(sesion_en(raiz).libro, nueva.id) == -450


def test_crear_respaldo_desde_el_portal(raiz, con_datos):
    at = abrir()
    at.switch_page(_pagina("respaldos")).run()
    boton(at, "Crear respaldo ahora").click().run()
    sin_errores(at)
    (respaldo,) = (raiz / "Respaldos").glob("TALLY_respaldo_*.zip")
    assert respaldos.inspeccionar(respaldo).movimientos == 6


def test_archivo_danado_ofrece_recuperacion(raiz):
    (raiz / "Datos").mkdir()
    (raiz / "Datos" / "tally.db").write_bytes(b"no es una base de datos" * 50)
    at = abrir()
    assert at.title[0].value == "No se pudieron abrir tus datos"
    at.checkbox[0].check().run()
    boton(at, "Empezar de cero").click().run()
    assert not at.exception
    assert list((raiz / "Datos").glob("tally_danado_*.db"))  # el archivo original se conserva
    assert at.title[0].value.startswith("¡Hola!")


def _pagina(nombre: str) -> str:
    return f"vistas/{nombre}.py"
