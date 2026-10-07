"""Pruebas del portal con el banco de pruebas de Streamlit (sin navegador).

Recorren cada página con datos ficticios y verifican que no haya errores y que
las acciones lleguen al motor. Se omiten si Streamlit no está instalado.
"""

from datetime import date
from decimal import Decimal
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
        movimientos.registrar_ingreso(lib, hoy, debito, cat["NOMINA"], 4000, "Nómina")
        movimientos.registrar_gasto(lib, hoy, tdc, cat["ALIMENTOS"], 300, "Pizza")
        movimientos.registrar_gasto(lib, hoy, debito, cat["TRANSPORTE"], 80, "Taxi")
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
    next(s for s in at.selectbox if s.label == "Subcategoría").set_value(con_datos["cat"]["ALIMENTOS"])
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
    for pagina in ("cuentas", "categorias", "respaldos", "cargar"):
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
    boton(at, "Guardar respaldo en la carpeta").click().run()
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


def test_tarjeta_con_10_dias_naturales_despues_del_corte(raiz, con_datos):
    at = abrir()
    at.switch_page(_pagina("cuentas")).run()
    at.selectbox(key="cuentas_tipo_nueva").set_value("credito").run()
    assert at.radio(key="cuentas_modo_pago").value == "dias"
    next(t for t in at.text_input if t.label == "Nombre" and not t.value).input("TDC con plazo")
    next(n for n in at.number_input if n.label == "Día de corte (opcional)").set_value(3)
    assert next(n for n in at.number_input if n.label == "Días para pagar después del corte").value == 10
    boton(at, "Agregar cuenta").click().run()
    sin_errores(at)
    tdc = cuentas.buscar(sesion_en(raiz).libro, "TDC con plazo")
    assert (tdc.dia_corte, tdc.dias_para_pagar, tdc.dias_habiles, tdc.recorrer_inhabil, tdc.dia_pago) == (
        3, 10, False, True, None)


def nueva_subcategoria(at: AppTest, rubro_id: str, nombre: str) -> None:
    """Llena el formulario «Nueva subcategoría» de la pestaña Gastos (la primera)."""
    next(s for s in at.selectbox if s.label == "Dentro de la categoría").set_value(rubro_id)
    next(t for t in at.text_input if t.label == "Nombre de la subcategoría").input(nombre)
    boton(at, "Agregar subcategoría").click().run()


def test_categorias_y_subcategorias_desde_el_portal(raiz, con_datos):
    from motor import categorias

    at = abrir(_pagina("categorias"))
    sin_errores(at)
    assert any(e.label.startswith("**SALUD**") for e in at.expander)
    at.text_input(key="buscar_gasto").input("dentísta").run()
    assert at.dataframe[0].value["Subcategoría"].tolist() == ["DENTISTA"]
    at.text_input(key="buscar_gasto").input("").run()

    salud = categorias.buscar_rubro(sesion_en(raiz).libro, "Salud").id
    nueva_subcategoria(at, salud, "Ortodóncia")
    sin_errores(at)
    nueva = categorias.buscar(sesion_en(raiz).libro, "ortodoncia")
    assert nueva.nombre == "ORTODONCIA" and nueva.rubro_id == salud

    # La misma, escrita distinto: no se puede agregar dos veces.
    nueva_subcategoria(at, salud, "ORTODONCIA ")
    assert any("dos veces" in e.value for e in at.error)


TEXTO_CON_DESCONOCIDA = (
    "CUENTA: Débito Ficticio\nFECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\n"
    "01/07/2026\tCafé\tCafecitos\t60\t\n02/07/2026\tSúper\tDespensa\t500\t\n"
)


def test_cargar_datos_con_la_plantilla(raiz, con_datos):
    from motor import categorias, importacion

    at = abrir(_pagina("cargar"))
    sin_errores(at)
    at.text_area(key="cargar_texto_0").input(importacion.plantilla()).run()
    sin_errores(at)
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Se cargan"] == "22" and metricas["En las dos cuentas"] == "3"
    boton(at, "Cargar 22 movimiento(s)").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    assert cuentas.buscar(lib, "Mi tarjeta de crédito") is not None
    assert list((raiz / "Respaldos").glob("TALLY_antes_de_cargar_datos_*.zip"))
    assert at.text_area(key="cargar_texto_1").value == ""                 # listo para otro archivo

    # Un nombre que TALLY no conoce: por omisión se crea como subcategoría nueva en VARIOS.
    at.text_area(key="cargar_texto_1").input(TEXTO_CON_DESCONOCIDA).run()
    sin_errores(at)
    assert any(m.value.startswith("**CAFECITOS**") for m in at.markdown)
    boton(at, "Cargar 2 movimiento(s)").click().run()
    sin_errores(at)
    cafecitos = categorias.buscar(sesion_en(raiz).libro, "cafecitos")
    assert categorias.etiqueta(sesion_en(raiz).libro, cafecitos.id) == "VARIOS › CAFECITOS"


def test_cargar_datos_con_errores_no_carga_nada(raiz, con_datos):
    at = abrir(_pagina("cargar"))
    at.text_area(key="cargar_texto_0").input(
        "CUENTA: Débito Ficticio\nFECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\n31/02/2026\tMal\tDespensa\t5\t\n"
        "01/07/2026\tBien\tDespensa\t5\t\n").run()
    assert any("Línea 3" in e.value for e in at.error)
    assert boton(at, "Cargar 1 movimiento(s)").disabled


def test_empezar_de_cero_desde_respaldos(raiz, con_datos):
    at = abrir(_pagina("respaldos"))
    assert boton(at, "Borrar todo y empezar de cero").disabled
    at.text_input(key="confirmar_empezar_de_cero").input("borrar").run()
    boton(at, "Borrar todo y empezar de cero").click().run()
    assert not at.exception
    assert at.title[0].value.startswith("¡Hola!")                         # como recién instalado
    lib = sesion_en(raiz).libro
    assert lib.perfil is None and lib.cuentas() == []
    (respaldo,) = (raiz / "Respaldos").glob("TALLY_antes_de_empezar_de_cero_*.zip")
    assert respaldos.inspeccionar(respaldo).movimientos == 6


def test_estado_de_tarjeta_en_resumen_y_cuentas(raiz, con_datos):
    s = sesion_en(raiz)
    with s.cambio() as lib:
        movimientos.registrar_gasto(lib, lib.hoy(), con_datos["tdc"], con_datos["cat"]["DESPENSA"], 500, "Súper")
    for pagina in (None, _pagina("cuentas")):
        at = abrir(pagina)
        sin_errores(at)
        metricas = {m.label: m.value for m in at.metric}
        assert metricas["Línea de crédito"] == "$2,000.00"
        assert metricas["Disponible"] == "$1,500.00"
        assert any("Usas el 25% de tu línea" in str(p.proto) for p in at.get("progress"))


def test_descargar_respaldo_en_un_clic(raiz, con_datos):
    at = abrir(_pagina("respaldos"))
    sin_errores(at)
    (descarga,) = [b for b in at.get("download_button") if "Descargar respaldo" in str(b.proto)]
    assert ".zip" in str(descarga.proto)
    from portal.componentes import respaldo as componente
    from portal.componentes.sesion import sesion as sesion_actual

    capturado = {}
    real = componente.st.download_button
    componente.st.download_button = lambda etiqueta, datos, **_: capturado.setdefault("datos", datos)
    try:
        import streamlit as st
        st.session_state.clear()
        componente.sesion = lambda: sesion_en(raiz)
        componente.boton_descargar("prueba")
    finally:
        componente.st.download_button = real
        componente.sesion = sesion_actual
    contenido = capturado["datos"]()
    assert contenido[:2] == b"PK"                                         # un .zip de verdad
    assert not list((raiz / "Respaldos").glob("TALLY_descargado_*.zip"))   # sin copia en la carpeta


def test_el_respaldo_automatico_del_dia(raiz, con_datos):
    abrir()
    (automatico,) = (raiz / "Respaldos").glob("TALLY_automatico_*.zip")
    assert respaldos.inspeccionar(automatico).movimientos == 6
    abrir()
    assert len(list((raiz / "Respaldos").glob("TALLY_automatico_*.zip"))) == 1   # uno por día


@pytest.mark.parametrize("formato", ["zip", "db"])
def test_instalacion_nueva_recupera_un_respaldo_o_un_tally_db(raiz, tmp_path, formato):
    """Lo que hace la bienvenida con «Ya usaba TALLY»: sirve el .zip descargado o el tally.db de la otra PC."""
    from motor.respaldos import copiar_archivo_de_datos
    from portal.componentes import respaldo

    otra = Sesion(tmp_path / "otra_pc" / "tally.db")
    with otra.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        cuentas.crear(lib, "Débito de la otra PC", "debito", saldo_inicial=777)
    archivo = (respaldos.crear(otra, tmp_path / "usb") if formato == "zip"
               else copiar_archivo_de_datos(otra.almacen.ruta, tmp_path / "usb" / "tally.db"))
    assert formato in respaldo.TIPOS

    nueva = sesion_en(raiz)
    assert perfil.necesita_bienvenida(nueva.libro)
    assert respaldos.inspeccionar(archivo).perfil == "Usuario Ficticio"
    respaldos.restaurar(nueva, archivo)
    lib = sesion_en(raiz).libro
    assert not perfil.necesita_bienvenida(lib)
    assert cuentas.saldo(lib, cuentas.buscar(lib, "Débito de la otra PC").id) == 777


def test_bienvenida_ofrece_ya_usaba_tally(raiz):
    at = abrir()
    at.segmented_control(key="bienvenida_eleccion").set_value("Ya usaba TALLY: tengo un respaldo").run()
    sin_errores(at)
    assert at.subheader[0].value == "Recupera tus datos"
    assert not [t for t in at.text_input if t.key == "bienvenida_nombre"]


def test_configuracion(raiz, con_datos):
    at = abrir(_pagina("configuracion"))
    sin_errores(at)
    next(t for t in at.text_input if t.label == "Nombre").input("Apodo Ficticio")
    next(b for b in at.button if b.label == "Guardar").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    assert lib.perfil.nombre == "Apodo Ficticio"

    at.selectbox[0].set_value("anio")
    [b for b in at.button if b.label == "Guardar"][-1].click().run()
    sin_errores(at)
    assert sesion_en(raiz).libro.perfil.periodo_inicial == "anio"
    at.switch_page(_pagina("inicio")).run()
    assert at.title[0].value == "¡Hola, Apodo Ficticio!"
    assert at.segmented_control(key="_w_inicio_periodo").value == "anio"


# ------------------------------------------------------------------ fase 4


def test_tablas_dinamicas(raiz, con_datos):
    at = abrir(_pagina("pivots"))
    sin_errores(at)
    tabla = at.dataframe[0].value
    assert list(tabla.columns)[0] == "Categoría" and tabla.iloc[-1, 0] == "Suma total"
    assert tabla.iloc[-1]["Total"] == "$380.00"                # 300 de comida + 80 de taxi; el pago de TDC no
    for rapida in ("Total por categoría", "Ingresos y gastos por mes", "Gasto por cuenta", "Por clasificación"):
        boton(at, rapida).click().run()
        sin_errores(at)
    assert at.dataframe[0].value.shape[0] >= 1


def test_graficas_de_todos_los_tipos(raiz, con_datos):
    from portal.paginas import graficas

    at = abrir(_pagina("graficas"))
    sin_errores(at)
    for tipo in graficas.TIPOS:
        at.selectbox[0].set_value(tipo)
        boton(at, "Visualizar gráfica").click().run()
        sin_errores(at)
        assert at.subheader[0].value


def test_presupuestos_y_aviso_en_el_resumen(raiz, con_datos):
    from motor import categorias as cats

    s = sesion_en(raiz)
    with s.cambio() as lib:
        cats.fijar_presupuesto(lib, cats.buscar_rubro(lib, "Alimentación").id, 250)
    at = abrir(_pagina("presupuestos"))
    sin_errores(at)
    assert any("te pasaste por" in m.value and "ALIMENTACION" in m.value for m in at.markdown)
    at = abrir()
    assert any(s.value == "Presupuestos del mes" for s in at.subheader)


def test_estado_de_cuenta_desde_cuentas(raiz, con_datos):
    at = abrir(_pagina("cuentas"))
    next(b for b in at.button if b.key == f"ver_{con_datos['debito']}").click().run()
    sin_errores(at)
    assert at.title[0].value == "Débito Ficticio"
    tabla = at.dataframe[0].value
    assert list(tabla.columns) == ["Fecha", "Descripción", "Subcategoría o cuenta", "Entrada", "Salida", "Saldo"]
    assert tabla.iloc[0]["Saldo"] == "$7,620.00"                  # 5000 + 4000 − 80 − 1000 − 300, saldo corrido
    assert boton(at, "Agregar movimiento")
    at.selectbox(key="cuenta_orden").set_value("antiguos").run()
    sin_errores(at)
    tabla = at.dataframe[0].value
    assert tabla.iloc[0]["Saldo"] == "$5,000.00" and tabla.iloc[-1]["Saldo"] == "$7,620.00"   # de arriba abajo
    boton(at, "← Todas mis cuentas").click().run()
    assert at.title[0].value == "Cuentas"


def test_registrar_a_meses_sin_intereses(raiz, con_datos):
    from motor import tarjetas as tdc

    at = abrir(_pagina("registrar"))
    next(s for s in at.selectbox if s.label == "Subcategoría").set_value(con_datos["cat"]["CELULARES Y TABLETS"])
    next(s for s in at.selectbox if s.label == "Pagado con").set_value(con_datos["tdc"])
    next(n for n in at.number_input if n.label == "Importe").set_value(1200.0)
    next(n for n in at.number_input if n.label == "Meses sin intereses").set_value(6)
    boton(at, "Guardar").click().run()
    sin_errores(at)
    (compra,) = tdc.compras_a_msi(sesion_en(raiz).libro, con_datos["tdc"])
    assert (compra.meses, compra.mensualidad) == (6, 200)


def test_historial_ofrece_repetir_el_movimiento(raiz, con_datos):
    """Al elegir un movimiento aparece la pestaña Repetir (la acción se prueba en tests/test_analisis.py)."""
    at = abrir(_pagina("historial"))
    at.session_state["historial_tabla"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    sin_errores(at)
    assert boton(at, "Repetir este movimiento")
    assert any(d.label == "Fecha del nuevo" for d in at.date_input)


def test_apariencia_tema_oscuro_e_icono(raiz, con_datos):
    at = abrir(_pagina("configuracion"))
    at.radio(key="configuracion_tema").set_value("oscuro").run()
    sin_errores(at)
    assert sesion_en(raiz).libro.perfil.tema == "oscuro"
    assert any("invert" in str(h.proto) for h in at.get("html"))
    next(b for b in at.button if b.key == "configuracion_icono_acento").click().run()
    sin_errores(at)
    assert sesion_en(raiz).libro.perfil.icono == "acento"


def test_el_icono_violeta_se_llama_asi(raiz, con_datos):
    at = abrir(_pagina("configuracion"))
    etiquetas = [b.label for b in at.button if b.key and b.key.startswith("configuracion_icono_")]
    assert "Usar violeta" in etiquetas and not any("acento" in e.lower() for e in etiquetas)


def test_eliminar_tarjeta_guarda_su_historial(raiz, con_datos):
    at = abrir(_pagina("cuentas"))
    sin_errores(at)
    # Desde la pestaña Eliminar de «Administrar una cuenta» (el mismo contenido que la ventana del botón).
    at.selectbox(key="cuentas_elegida").set_value(con_datos["tdc"]).run()
    clave = f"pestana_eliminar_{con_datos['tdc']}"
    at.checkbox(key=f"{clave}_confirmar").check().run()
    next(b for b in at.button if b.key == f"{clave}_eliminar").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    assert not lib.cuenta(con_datos["tdc"]).activa
    assert any(op for op in lib.operaciones() if any(p.cuenta_id == con_datos["tdc"] for p in op.partidas))
    assert not any(b.key == f"ver_{con_datos['tdc']}" for b in at.button)       # ya no sale en la lista

    at.toggle(key="cuentas_mostrar_archivadas").set_value(True).run()
    next(b for b in at.button if b.key == f"restaurar_{con_datos['tdc']}").click().run()
    sin_errores(at)
    assert sesion_en(raiz).libro.cuenta(con_datos["tdc"]).activa


def test_cuenta_eliminada_se_ve_sin_agregar_movimientos(raiz, con_datos):
    s = sesion_en(raiz)
    with s.cambio() as lib:
        cuentas.eliminar_cuenta(lib, con_datos["ahorro"])
    at = abrir(_pagina("cuentas"))
    at.toggle(key="cuentas_mostrar_archivadas").set_value(True).run()
    next(b for b in at.button if b.key == f"ver_{con_datos['ahorro']}").click().run()
    sin_errores(at)
    assert at.title[0].value == "Ahorro Ficticio"
    assert not any(b.label == "Agregar movimiento" for b in at.button)


def test_cargo_temporal_se_registra_y_se_devuelve(raiz, con_datos):
    from motor import reportes, temporales

    at = abrir(_pagina("registrar"))
    at.toggle(key="registrar_temporal").set_value(True).run()
    sin_errores(at)
    assert not any(s.label == "Subcategoría" for s in at.selectbox)
    next(s for s in at.selectbox if s.label == "¿Dónde te lo cobraron?").set_value(con_datos["tdc"])
    next(n for n in at.number_input if n.label == "Importe").set_value(1.0)
    next(t for t in at.text_input if t.label == "Descripción").input("Verificación ficticia")
    boton(at, "Guardar").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    (cargo,) = temporales.pendientes(lib)
    assert reportes.resumen(lib, *reportes.rango_periodo(lib, "mes_actual")).gastos == 380

    at.switch_page(_pagina("inicio")).run()
    sin_errores(at)
    assert any(s.value == "Por recuperar" for s in at.subheader)
    next(b for b in at.button if b.key == f"devuelto_{cargo.operacion_id}").click().run()
    sin_errores(at)
    boton(at, "Guardar").click().run()
    sin_errores(at)
    assert temporales.pendientes(sesion_en(raiz).libro) == []


def test_cargo_temporal_vencido_avisa_y_se_pasa_a_gasto(raiz, con_datos):
    from datetime import timedelta

    from motor import temporales

    s = sesion_en(raiz)
    with s.cambio() as lib:
        cargo = temporales.registrar(lib, lib.hoy() - timedelta(days=60), con_datos["debito"], 50, "Depósito ficticio")
    at = abrir(_pagina("inicio"))
    assert any("Conviene reclamarlo" in w.value for w in at.warning)
    next(b for b in at.button if b.key == f"no_devuelto_{cargo.id}").click().run()
    boton(at, "Pasar a gasto").click().run()
    sin_errores(at)
    assert temporales.pendientes(sesion_en(raiz).libro) == []


def test_clasificaciones_como_cajas_con_sus_subcategorias(raiz, con_datos):
    s = sesion_en(raiz)
    grupo = {g.nombre: g.id for g in s.libro.grupos()}
    snacks = next(c.id for c in s.libro.categorias() if c.nombre == "SNACKS Y ANTOJOS")
    at = abrir(_pagina("categorias"))
    sin_errores(at)

    def caja(nombre):                       # la clave lleva una versión que cambia tras cada ajuste
        return next(m for m in at.multiselect if m.key.startswith(f"clasif_{grupo[nombre]}_"))

    assert snacks in caja("Antojos").value

    # Ponerla en Disfrute sin quitarla de Antojos: no se deja y se explica.
    caja("Disfrute").select(snacks).run()
    assert any("ya está en «Antojos»" in e.value for e in at.error)
    assert sesion_en(raiz).libro.categoria(snacks).grupo_id == grupo["Antojos"]

    # Quitarla de Antojos y luego agregarla en Disfrute sí.
    caja("Antojos").unselect(snacks).run()
    assert sesion_en(raiz).libro.categoria(snacks).grupo_id is None
    caja("Disfrute").select(snacks).run()
    sin_errores(at)
    assert sesion_en(raiz).libro.categoria(snacks).grupo_id == grupo["Disfrute"]


def test_titulos_en_una_cuenta_de_inversion(raiz, monkeypatch):
    import json

    from motor import cotizaciones, portafolio

    s = sesion_en(raiz)
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        inv = cuentas.crear(lib, "Inversión Ficticia", "inversion", saldo_inicial=1000, fecha_creacion=date(2026, 1, 1)).id
        portafolio.registrar_compra(lib, inv, date(2026, 7, 2), "FICT.MX", 10, 100)
        portafolio.registrar_plazo(lib, inv, "Cetes ficticios", date(2026, 7, 1), 500, 10, 28)
    enviados = []

    def falso(simbolo):
        enviados.append(simbolo)
        return json.dumps({"chart": {"result": [{"meta": {"currency": "MXN", "regularMarketPrice": 112.5}}]}})

    monkeypatch.setattr(cotizaciones, "enviar", falso)
    at = abrir(_pagina("cuentas"))
    next(b for b in at.button if b.key == f"ver_{inv}").click().run()
    sin_errores(at)
    assert any(h.value == "Tus títulos e inversiones a plazo" for h in at.subheader)
    next(b for b in at.button if b.key == f"consultar_{inv}").click().run()
    sin_errores(at)
    assert enviados == ["FICT.MX"]                                       # solo el símbolo
    assert not any(b.key == f"registrar_rendimiento_{inv}" for b in at.button)   # primero, el valor oficial
    at.number_input(key=f"oficial_valor_{inv}").set_value(1123.45)
    next(b for b in at.button if b.label == "Revisar diferencia").click().run()
    sin_errores(at)
    assert any("se registra un rendimiento de **+" in i.value for i in at.info)
    next(b for b in at.button if b.key == f"registrar_rendimiento_{inv}").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    assert cuentas.saldo(lib, inv) == Decimal("1123.45")                # igual que la app oficial, al centavo
    assert lib.cuenta(inv).plusvalia_registrada == 12345


def test_precios_automaticos_solo_si_el_usuario_los_activa(raiz, monkeypatch):
    import json

    from motor import cotizaciones, portafolio

    s = sesion_en(raiz)
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        inv = cuentas.crear(lib, "Inversión Ficticia", "inversion", saldo_inicial=1000, fecha_creacion=date(2026, 1, 1)).id
        portafolio.registrar_compra(lib, inv, date(2026, 7, 2), "FICT.MX", 10, 100)
    enviados = []

    def falso(simbolo):
        enviados.append(simbolo)
        return json.dumps({"chart": {"result": [{"meta": {"currency": "MXN", "regularMarketPrice": 101}}]}})

    monkeypatch.setattr(cotizaciones, "enviar", falso)
    at = abrir(_pagina("cuentas"))
    next(b for b in at.button if b.key == f"ver_{inv}").click().run()
    sin_errores(at)
    assert enviados == []                                    # apagado por omisión: no sale nada al abrir

    at.toggle(key=f"auto_precios_{inv}").set_value(True).run()
    sin_errores(at)
    assert sesion_en(raiz).libro.perfil.actualizar_precios
    assert enviados == ["FICT.MX"]                           # una consulta, solo el símbolo
    at.run()
    assert enviados == ["FICT.MX"]                           # no vuelve a consultar en la misma visita
    assert any("Última actualización" in c.value for c in at.caption)
    assert cotizaciones.ultimos()[0]["FICT.MX"].valor == 101   # guardado en la PC para usarlo sin internet


def test_graficas_dicen_que_hay_dentro_de_otros(raiz, con_datos):
    s = sesion_en(raiz)
    hoy = s.libro.hoy()
    nombres = ["RENTA", "LUZ", "GASOLINA", "DENTISTA", "CINE", "ROPA", "IMPUESTOS", "VUELOS", "VETERINARIO", "REGALOS"]
    with s.cambio() as lib:
        cat = {c.nombre: c.id for c in lib.categorias()}
        for i, nombre in enumerate(nombres):
            movimientos.registrar_gasto(lib, hoy, con_datos["debito"], cat[nombre], 10 + i, f"Ficticio {nombre}")
    at = abrir(_pagina("graficas"))
    sin_errores(at)
    importes = at.dataframe[0].value
    assert "dentro de OTROS" in set(importes["En la gráfica"])
    at.selectbox(key="grafica_detalle").set_value("OTROS").run()
    sin_errores(at)
    assert any(m.value.startswith("#### Detalle de OTROS") for m in at.markdown)
    por_categoria, movimientos_tabla = at.dataframe[1].value, at.dataframe[2].value
    assert set(por_categoria["Categoría"]) == {n for n in importes["Categoría"]
                                                if importes.set_index("Categoría").loc[n, "En la gráfica"] ==
                                                "dentro de OTROS"}
    assert len(movimientos_tabla) >= len(por_categoria)
    at.selectbox(key="grafica_detalle").set_value("HOGAR").run()
    assert "Subcategoría" in at.dataframe[1].value.columns                      # una categoría se abre en subcategorías


def test_inversiones_rendimiento_en_el_tiempo(raiz, monkeypatch):
    import json
    from datetime import datetime, timezone

    from motor import cotizaciones, portafolio

    s = sesion_en(raiz)
    hoy = s.libro.hoy()
    inicio = date(hoy.year - 1, hoy.month, 1)
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        gbm = cuentas.crear(lib, "Casa de Bolsa Ficticia", "inversion", saldo_inicial=5000, fecha_creacion=inicio).id
        cetes = cuentas.crear(lib, "Cetes Ficticios", "inversion", saldo_inicial=2000, fecha_creacion=inicio).id
        portafolio.registrar_compra(lib, gbm, inicio, "FICTA", 10, 100)
        portafolio.registrar_compra(lib, gbm, inicio, "FICTB", 5, 10, moneda="USD", tipo_cambio=20)
        portafolio.registrar_plazo(lib, cetes, "Cetes 28 días", inicio, 1000, 10, 28)
        portafolio.ajustar_a_valor_oficial(lib, gbm, 5100, hoy)
    enviados = []

    def falso(simbolo, rango):
        enviados.append((simbolo, rango))
        tiempo = int(datetime(hoy.year, hoy.month, hoy.day, 15, tzinfo=timezone.utc).timestamp())
        precio, moneda = {"FICTA": (120, "MXN"), "FICTB": (11, "USD"), "USDMXN=X": (19, "MXN")}[simbolo]
        return json.dumps({"chart": {"result": [{"meta": {"currency": moneda, "gmtoffset": 0}, "timestamp": [tiempo],
                                                 "indicators": {"quote": [{"close": [precio]}]}}]}})

    monkeypatch.setattr(cotizaciones, "enviar_historial", falso)
    at = abrir(_pagina("inversiones"))
    sin_errores(at)
    assert enviados == []                                    # nada sale a internet sin pedirlo
    assert any(m.label == "Ganancia del periodo" for m in at.metric)
    assert any("Sin historial de precios todavía" in c.value for c in at.caption)

    next(b for b in at.button if b.key == "inv_actualizar").click().run()
    sin_errores(at)
    assert sorted(s for s, _ in enviados) == ["FICTA", "FICTB", "USDMXN=X"]   # solo símbolos y periodo
    assert {r for _, r in enviados} <= {"1y", "2y"}                    # periodo estándar, no la fecha exacta
    detalle = at.dataframe[0].value
    assert list(detalle["Título o inversión"]) == ["FICTA", "FICTB", "Cetes 28 días (a plazo)"]
    assert list(detalle["Valor al final"])[:2] == ["$1,200.00", "$1,045.00"]          # 10 × 120; 5 × 11 × 19
    at.toggle(key="inv_separar").set_value(True).run()                # una línea por título
    sin_errores(at)

    at.multiselect(key="inv_instrumentos").set_value(["FICTB"]).run()
    sin_errores(at)
    assert list(at.dataframe[0].value["Título o inversión"]) == ["FICTB"]
    at.multiselect(key="inv_cuentas").set_value([cetes]).run()      # FICTB ya no está en esa cuenta: se quita
    sin_errores(at)
    assert list(at.dataframe[0].value["Título o inversión"]) == ["Cetes 28 días (a plazo)"]
    at.selectbox(key="inv_periodo").set_value("todo").run()
    sin_errores(at)

    at.radio(key="inv_vista").set_value("oficial").run()
    at.multiselect(key="inv_cuentas").set_value([]).run()
    sin_errores(at)
    por_cuenta = at.dataframe[0].value
    assert list(por_cuenta["Cuenta"]) == ["Casa de Bolsa Ficticia", "Cetes Ficticios"]
    assert list(por_cuenta["Ganancia"])[0] == "$100.00"                 # el ajuste al valor oficial


def test_inversiones_sin_cuentas_de_inversion(con_datos):
    at = abrir(_pagina("inversiones"))
    sin_errores(at)
    assert any("Aún no tienes cuentas de inversión" in i.value for i in at.info)


def seleccionar(at: AppTest, clave: str, fila: int) -> AppTest:
    """Simula el clic en un renglón de una tabla."""
    at.session_state[clave] = {"selection": {"rows": [fila], "columns": [], "cells": []}}
    return at.run()


def test_contabilidad_tecnica(raiz, con_datos):
    at = abrir(_pagina("contabilidad"))
    sin_errores(at)
    assert [t.label for t in at.tabs] == ["Situación financiera", "Resultados", "Flujo de efectivo",
                                          "Balanza de comprobación", "Bienes"]
    assert any("Activo = Pasivo + Patrimonio" in s.value for s in at.success)
    assert any("Sumas iguales" in s.value for s in at.success)
    assert any(m.label == "Lo que vales (Patrimonio)" for m in at.metric)
    situacion = at.dataframe[0].value
    fila = list(situacion["Concepto"]).index("\u2003\u2003Débito Ficticio")
    seleccionar(at, "conta_sel_situacion", fila)
    sin_errores(at)
    assert any(m.value == "#### Detalle de Débito Ficticio" for m in at.markdown)
    balanza = next(d.value for d in at.dataframe if "Cuenta" in d.value.columns and "Debe" in d.value.columns)
    assert balanza["Cuenta"].iloc[-1] == "SUMAS IGUALES"
    assert balanza["Debe"].iloc[-1] == balanza["Haber"].iloc[-1]
    seleccionar(at, "conta_sel_balanza", list(balanza["Cuenta"]).index("Débito Ficticio"))
    sin_errores(at)
    assert any(set(d.value.columns) >= {"Debe", "Haber", "Contrapartida"} for d in at.dataframe)
    at.toggle(key="conta_subcuentas").set_value(True).run()
    at.toggle(key="conta_resultados_sub").set_value(True).run()
    sin_errores(at)
    for periodo in ("anio_pasado", "mes", "mes_pasado", "12m"):
        at.selectbox(key="conta_periodo").set_value(periodo).run()
        sin_errores(at)
    at.selectbox(key="conta_comparar").set_value("no").run()
    sin_errores(at)
    at.selectbox(key="conta_periodo").set_value("rango").run()
    sin_errores(at)


def test_bienes_desde_contabilidad_tecnica(raiz, con_datos):
    at = abrir(_pagina("contabilidad"))
    at.selectbox(key="bien_nuevo_clase").set_value("auto").run()
    formulario = [t for t in at.text_input if t.label == "Nombre"][0]
    formulario.set_value("Auto Ficticio")
    [n for n in at.number_input if n.label == "Lo que vale hoy"][0].set_value(200_000)
    boton(at, "Agregar bien").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    (bien,) = lib.bienes()
    assert lib.cuenta(bien.cuenta_id).nombre == "Auto Ficticio" and bien.tasa_anual == 15
    assert any(m.label == "Tus bienes valen hoy" for m in at.metric)
    [n for n in at.number_input if n.label == "Valor según el avalúo"][0].set_value(210_000)
    boton(at, "Guardar avalúo").click().run()
    sin_errores(at)
    assert sesion_en(raiz).libro.bien(bien.cuenta_id).avaluos[0].valor == 21_000_000
    assert any(s.value.startswith("Cuadra") for s in at.success)


def test_convertir_un_gasto_en_un_bien_desde_el_historial(raiz, con_datos):
    from motor import movimientos as mov

    s = sesion_en(raiz)
    with s.cambio() as lib:
        gasto = mov.registrar_gasto(lib, lib.hoy(), con_datos["debito"], con_datos["cat"]["ALIMENTOS"], 999,
                                    "Laptop ficticia")
    at = abrir(_pagina("historial"))
    tabla = at.dataframe[0].value
    seleccionar(at, "historial_tabla", list(tabla["Descripción"]).index("Laptop ficticia"))
    sin_errores(at)
    assert "Convertir en un bien" in [t.label for t in at.tabs]
    fila = list(tabla["Descripción"]).index("Laptop ficticia")
    at.selectbox(key=f"bien_clase_{gasto.id}").set_value("computadora")
    next(b for b in at.button if b.key == f"convertir_bien_{gasto.id}").click()
    seleccionar(at, "historial_tabla", fila)                  # la tabla conserva el renglón elegido
    sin_errores(at)
    lib = sesion_en(raiz).libro
    assert lib.operacion(gasto.id).tipo.value == "transferencia" and len(lib.bienes()) == 1


def test_deudas_tarjetas_y_prestamos(raiz, con_datos):
    from motor import categorias, prestamos

    s = sesion_en(raiz)
    hoy = s.libro.hoy()
    with s.cambio() as lib:
        cuentas.editar(lib, con_datos["tdc"], tasa_anual=60, cat=80)
        categorias.editar(lib, con_datos["cat"]["NOMINA"], principal=True)
        perfil.ajustar(lib, ingreso_esperado=20_000)
    at = abrir(_pagina("deudas"))
    sin_errores(at)
    assert any(m.label == "Parte de tu ingreso" for m in at.metric)
    assert any(m.label == "Pago mínimo estimado" for m in at.metric)
    # Agregar un préstamo desde el formulario.
    [t for t in at.text_input if t.label == "Nombre"][0].set_value("Préstamo Ficticio")
    [n for n in at.number_input if n.label == "Monto que solicitaste"][0].set_value(30_000)
    [n for n in at.number_input if n.label == "Tasa de interés anual (%)"][-1].set_value(24)   # la de la tarjeta va antes
    boton(at, "Agregar préstamo").click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    (p,) = lib.prestamos()
    assert cuentas.saldo(lib, p.cuenta_id) == -30_000 and p.plazo_meses == 12
    assert any(m.label == "Debes hoy" and m.value == "$30,000.00" for m in at.metric)
    boton(at, "Registrar pago").click().run()                 # con el pago mensual e intereses sugeridos
    sin_errores(at)
    assert -30_000 < cuentas.saldo(sesion_en(raiz).libro, p.cuenta_id) < -27_000
    assert any(t.label == "Simulador" for t in at.tabs)
    assert prestamos.estado(sesion_en(raiz).libro, p.cuenta_id, hoy).pagado > 0


def test_presupuestos_ingresos_sugeridos_y_proyeccion(raiz, con_datos):
    at = abrir(_pagina("presupuestos"))
    sin_errores(at)
    assert [t.label for t in at.tabs][:3] == ["Tus ingresos", "¿Cuánto puedes gastar?", "Proyección del mes"]
    at.selectbox[0].set_value(con_datos["cat"]["NOMINA"])
    boton(at, "Guardar").click().run()
    sin_errores(at)
    assert sesion_en(raiz).libro.categoria(con_datos["cat"]["NOMINA"]).principal
    assert any(m.label == "Gasto proyectado al cierre" for m in at.metric)


def test_iva_en_configuracion(raiz, con_datos):
    at = abrir(_pagina("configuracion"))
    [n for n in at.number_input if n.label == "IVA / VAT (%)"][0].set_value(21)
    [b for b in at.button if b.label == "Guardar"][1].click().run()   # el segundo «Guardar» de Tu perfil: el IVA
    sin_errores(at)
    assert sesion_en(raiz).libro.perfil.iva == 21


# ------------------------------------------------------------ contraseña


@pytest.fixture
def scrypt_rapido(monkeypatch):
    from motor import cifrado

    monkeypatch.setattr(cifrado, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})


def campo(at: AppTest, etiqueta: str):
    return [t for t in at.text_input if t.label == etiqueta][-1]


def _con_contrasena(raiz, contrasena="mi perro come tacos"):
    from motor import cifrado, seguridad

    kit = cifrado.nuevo_kit()
    seguridad.activar(sesion_en(raiz), contrasena, contrasena, kit, kit, carpeta_respaldos=raiz / "Respaldos")
    return kit


def test_poner_contrasena_paso_a_paso(raiz, con_datos, scrypt_rapido):
    at = abrir(_pagina("configuracion"))
    assert "Seguridad" in [t.label for t in at.tabs]
    boton(at, "Establecer una contraseña para TALLY").click().run()
    sin_errores(at)
    # Paso 1: contraseñas distintas → aviso claro; iguales → siguiente.
    campo(at, "Contraseña").input("mi perro come tacos")
    campo(at, "Escríbela otra vez").input("mi perro come churros")
    boton(at, "Siguiente").click().run()
    assert any("no son iguales" in e.value for e in at.error)
    campo(at, "Contraseña").input("mi perro come tacos")
    campo(at, "Escríbela otra vez").input("mi perro come tacos")
    campo(at, "Pista (opcional)").input("mi mascota y su comida")
    boton(at, "Siguiente").click().run()
    sin_errores(at)
    kit = at.session_state["_seg_kit"]
    assert any(c.value == kit for c in at.code)
    # Paso 2: no se puede seguir sin confirmar que se guardó el Kit.
    assert next(b for b in at.button if b.key == "seg_kit_siguiente").disabled
    at.checkbox(key="seg_kit_guardado").check().run()
    next(b for b in at.button if b.key == "seg_kit_siguiente").click().run()
    # Paso 3: una llave equivocada no avanza; la correcta (en minúsculas y sin guiones) sí.
    campo(at, "Escribe la llave de tu Kit").input(kit[:-1] + ("A" if kit[-1] != "A" else "B"))
    campo(at, "Escribe tu contraseña otra vez").input("mi perro come tacos")
    boton(at, "Comprobar").click().run()
    assert at.error
    campo(at, "Escribe la llave de tu Kit").input(kit.lower().replace("-", ""))
    campo(at, "Escribe tu contraseña otra vez").input("mi perro come tacos")
    boton(at, "Comprobar").click().run()
    sin_errores(at)
    # Paso 4: activar.
    assert sesion_en(raiz).libro.perfil.nombre == "Usuario Ficticio"
    next(b for b in at.button if b.key == "seg_activar").click().run()
    sin_errores(at)
    assert any("ya tiene contraseña" in str(t.value) for t in at.toast)
    assert b"Usuario Ficticio" not in (raiz / "Datos" / "tally.db").read_bytes()
    assert "_seg_contrasena" not in at.session_state                 # la contraseña no se queda en memoria
    assert [t.label for t in at.tabs if t.label == "Quitar la contraseña"]
    # Bloquear ahora → pide contraseña.
    next(b for b in at.button if b.key == "bloquear_ahora").click().run()
    assert at.title[0].value == "🔒 Tus datos están protegidos"
    assert not [b for b in at.button if b.label == "Bloquear ahora"]


def test_pantalla_de_entrada(raiz, con_datos, scrypt_rapido):
    _con_contrasena(raiz)
    at = abrir()
    assert at.title[0].value == "🔒 Tus datos están protegidos"
    assert not any("Usuario Ficticio" in str(m.value) for m in at.markdown)       # nada visible sin contraseña
    campo(at, "Contraseña").input("no es esta para nada")
    boton(at, "Entrar").click().run()
    assert any("no es la contraseña" in e.value for e in at.error)
    campo(at, "Contraseña").input("mi perro come tacos")
    boton(at, "Entrar").click().run()
    sin_errores(at)
    assert at.title[0].value != "🔒 Tus datos están protegidos"
    at.switch_page(_pagina("historial")).run()
    sin_errores(at)
    # Bloqueo automático: tras 10 minutos sin usar TALLY.
    from portal.componentes import candado

    candado._estado_de(str(raiz / "Datos" / "tally.db")).ultimo_uso -= 11 * 60
    at.run()
    assert at.title[0].value == "🔒 Tus datos están protegidos"


def test_entrar_con_varios_intentos_fallidos_pide_esperar(raiz, con_datos, scrypt_rapido):
    _con_contrasena(raiz)
    at = abrir()
    for _ in range(3):
        campo(at, "Contraseña").input("no es esta para nada")
        boton(at, "Entrar").click().run()
    assert any("Olvidaste tu contraseña" in c.value for c in at.caption)
    campo(at, "Contraseña").input("mi perro come tacos")
    boton(at, "Entrar").click().run()
    assert any("espera" in w.value for w in at.warning)                # aun con la buena, hay que esperar
    from portal.componentes import candado

    candado._estado_de(str(raiz / "Datos" / "tally.db")).intentos.acierto()


def test_olvide_mi_contrasena_con_el_kit(raiz, con_datos, scrypt_rapido):
    kit = _con_contrasena(raiz)
    at = abrir()
    campo(at, "Llave de tu Kit de emergencia").input(" " + kit.lower() + " ")
    campo(at, "Contraseña nueva").input("frase nueva y larga")
    campo(at, "Escríbela otra vez").input("frase nueva y larga")
    boton(at, "Poner mi contraseña nueva y entrar").click().run()
    sin_errores(at)
    assert at.title[0].value != "🔒 Tus datos están protegidos"
    from motor import seguridad

    assert seguridad.entrar(raiz / "Datos" / "tally.db", "frase nueva y larga")


def test_cambiar_y_quitar_la_contrasena_desde_configuracion(raiz, con_datos, scrypt_rapido):
    from motor import seguridad
    from portal.componentes import candado

    kit = _con_contrasena(raiz)
    ruta = raiz / "Datos" / "tally.db"
    candado._estado_de(str(ruta)).llave = seguridad.entrar(ruta, "mi perro come tacos")
    at = abrir(_pagina("configuracion"))
    sin_errores(at)
    campo(at, "Contraseña actual (o la llave de tu Kit)").input("mi perro come tacos")
    campo(at, "Contraseña nueva").input("frase nueva y larga")
    campo(at, "Escríbela otra vez").input("frase nueva y larga")
    boton(at, "Cambiar contraseña").click().run()
    sin_errores(at)
    assert seguridad.entrar(ruta, "frase nueva y larga")
    campo(at, "Llave de tu Kit").input(kit)
    boton(at, "Comprobar").click().run()
    assert any("Tu Kit abre tus datos" in s.value for s in at.success)
    campo(at, "Escribe tu contraseña (o la llave de tu Kit)").input("frase nueva y larga")
    boton(at, "Quitar la contraseña").click().run()
    assert any("Marca la casilla" in e.value for e in at.error)
    campo(at, "Escribe tu contraseña (o la llave de tu Kit)").input("frase nueva y larga")
    next(c for c in at.checkbox if c.label == "Sí, quiero quitar la contraseña").check()
    boton(at, "Quitar la contraseña").click().run()
    sin_errores(at)
    assert seguridad.config(ruta) is None
    assert b"Usuario Ficticio" in ruta.read_bytes() or sesion_en(raiz).libro.perfil.nombre == "Usuario Ficticio"
    at.switch_page(_pagina("historial")).run()
    sin_errores(at)


def _restaurar_app(ruta: str) -> None:
    from pathlib import Path

    from portal.componentes import respaldo

    respaldo.revisar_y_restaurar(Path(ruta), "prueba", pedir_confirmacion=False)


def test_restaurar_respaldo_con_contrasena_en_tally_nuevo(raiz, tmp_path_factory, scrypt_rapido):
    from motor import seguridad

    vieja = tmp_path_factory.mktemp("pc_vieja")
    s = Sesion(vieja / "Datos" / "tally.db")
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        cuentas.crear(lib, "Débito de la otra PC", "debito", saldo_inicial=777)
    kit = _con_contrasena(vieja)
    s = Sesion(vieja / "Datos" / "tally.db", llave=seguridad.entrar(vieja / "Datos" / "tally.db",
                                                                      "mi perro come tacos"))
    respaldo = respaldos.crear(s, vieja / "Respaldos")

    at = AppTest.from_function(_restaurar_app, args=(str(respaldo),), default_timeout=30)
    at.run()
    sin_errores(at)
    assert any("Este respaldo tiene contraseña" in i.value for i in at.info)
    assert not [b for b in at.button if b.label == "Restaurar este respaldo"]       # primero la contraseña
    at.text_input(key="prueba_secreto_respaldo").input("no es la buena").run()
    assert any("No coincide" in e.value for e in at.error)
    at.text_input(key="prueba_secreto_respaldo").input(kit.lower()).run()
    sin_errores(at)
    assert any(m.label == "Perfil" and m.value == "Usuario Ficticio" for m in at.metric)
    boton(at, "Restaurar este respaldo").click().run()
    sin_errores(at)
    ruta = raiz / "Datos" / "tally.db"
    assert seguridad.config(ruta) is not None                          # adoptó la contraseña del respaldo
    llave = seguridad.entrar(ruta, "mi perro come tacos")
    lib = Sesion(ruta, llave=llave).libro
    assert cuentas.saldo(lib, cuentas.buscar(lib, "Débito de la otra PC").id) == 777


# ------------------------------------------------------------ importar del banco

MOVS_BANCO = ("Fecha\tDescripción\tCargos\tAbonos\n"
              "15/07/2026\tCOMPRA OXXO 1234\t85.50\t\n"
              "16/07/2026\tPAGO NOMINA FICTICIA\t\t15,000.00\n"
              "17/07/2026\tSPEI ENVIADO FICTICIO\t500.00\t\n")


def _banco(raiz, texto=MOVS_BANCO) -> AppTest:
    at = abrir(_pagina("cargar"))
    assert [t.label for t in at.tabs][:2] == ["🏦 Desde tu banco", "📄 Con la plantilla de TALLY"]
    at.selectbox(key="banco_cuenta").set_value(cuentas.buscar(sesion_en(raiz).libro, "Débito Ficticio").id).run()
    at.text_area(key="banco_texto_0").input(texto).run()
    sin_errores(at)
    return at


def _editar(at: AppTest, cambios: dict) -> None:
    """Simula cambios en la tabla editable (AppTest no la maneja directamente)."""
    clave = at.session_state["_banco_clave"]
    at.session_state[f"banco_editor_{clave}"] = {"edited_rows": cambios, "added_rows": [], "deleted_rows": []}


def test_importar_del_banco_pegando_la_tabla(raiz, con_datos):
    at = _banco(raiz)
    assert {m.label: m.value for m in at.metric if m.label in ("Movimientos", "Salió", "Entró")} == {
        "Movimientos": "3", "Salió": "$585.50", "Entró": "$15,000.00"}
    assert any("Te falta elegir" in w.value for w in at.warning)                 # el SPEI no se adivina
    assert next(b for b in at.button if b.key == "banco_importar").disabled
    cambios = {2: {"Subcategoría o cuenta": "↔ Ahorro Ficticio"}}
    _editar(at, cambios)
    at.run()
    assert any("1 transferencia" in m.value and "1 gasto" in m.value for m in at.markdown)
    _editar(at, cambios)
    next(b for b in at.button if b.key == "banco_importar").click().run()
    sin_errores(at)
    assert any("Se importaron 3" in str(t.value) for t in at.toast)
    lib = sesion_en(raiz).libro
    nuevos = {op.descripcion: op.tipo.value for op in lib.operaciones() if op.descripcion.isupper()}
    assert nuevos == {"COMPRA OXXO 1234": "gasto", "PAGO NOMINA FICTICIA": "ingreso",
                      "SPEI ENVIADO FICTICIO": "transferencia"}
    assert at.text_area(key="banco_texto_1").value == ""                        # el formulario quedó vacío
    # Pegar lo mismo otra vez: todo aparece como «ya está» y no se marca para cargar.
    at.text_area(key="banco_texto_1").input(MOVS_BANCO).run()
    assert any("No hay movimientos marcados" in i.value for i in at.info)


def test_importar_del_banco_lo_que_falte_a_otros(raiz, con_datos):
    at = _banco(raiz)
    next(c for c in at.checkbox if c.key and c.key.startswith("banco_otros_")).check().run()
    boton_ = next(b for b in at.button if b.key == "banco_importar")
    assert boton_.label == "Importar 3 movimiento(s)" and not boton_.disabled
    boton_.click().run()
    sin_errores(at)
    lib = sesion_en(raiz).libro
    spei = next(op for op in lib.operaciones() if op.descripcion == "SPEI ENVIADO FICTICIO")
    assert spei.tipo.value == "gasto"


def test_importar_del_banco_signo_y_columnas(raiz, con_datos):
    texto = "Fecha\tConcepto\tImporte\n15/07/2026\tCOMPRA FICTICIA\t-100.00\n16/07/2026\tDEPOSITO FICTICIO\t50.00\n"
    at = _banco(raiz, texto)
    radio = next(r for r in at.radio if r.key and r.key.startswith("banco_signo_"))
    assert radio.value == 0
    assert next(m for m in at.metric if m.label == "Salió").value == "$100.00"
    radio.set_value(1).run()                                                    # «al revés»
    assert next(m for m in at.metric if m.label == "Salió").value == "$50.00"
    assert any(e.label.startswith("¿Leí mal alguna columna?") for e in at.expander)


def test_importar_del_banco_texto_que_no_es_estado_de_cuenta(raiz, con_datos):
    at = abrir(_pagina("cargar"))
    at.text_area(key="banco_texto_0").input("hola\nesto no tiene movimientos").run()
    assert any("No encontré movimientos" in e.value for e in at.error)
