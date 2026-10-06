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
    assert list(tabla.columns) == ["Fecha", "Descripción", "Subcategoría o cuenta", "Cargo", "Abono", "Saldo"]
    assert tabla.iloc[0]["Saldo"] == "$7,620.00"                  # 5000 + 4000 − 80 − 1000 − 300, saldo corrido
    assert boton(at, "Agregar movimiento")
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
