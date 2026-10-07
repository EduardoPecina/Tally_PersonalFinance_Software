"""Importar movimientos del banco (motor/bancos.py). Solo datos ficticios: bancos, comercios y montos inventados."""

import io
from datetime import date, datetime

import pytest

from motor import bancos, categorias, cuentas, importacion, movimientos
from motor.bancos import Columnas, Movimiento
from motor.errores import ErrorValidacion
from motor.sesion import Sesion
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia

from conftest import AHORA

# ------------------------------------------------------------------ archivos ficticios

CSV_MEXICO = """Banco Ficticio S.A.
Cuenta: ****0000,Periodo: Julio 2026
Fecha Operación,Fecha Liquidación,Descripción,Referencia,Cargos,Abonos,Saldo
01/07/2026,01/07/2026,PAGO NOMINA EMPRESA FICTICIA,123,,"15,000.00","20,000.00"
03/07/2026,04/07/2026,COMPRA OXXO 1234 SUC CENTRO,998,85.50,,"19,914.50"
05/07/2026,05/07/2026,NETFLIX.COM,777,219.00,,"19,695.50"
Total,,,,304.50,"15,000.00",
"""

CSV_ESPANA = ("Fecha;Concepto;Importe;Saldo\n"
              "15/07/2026;Supermercado Ficticio;-45,30;1.200,00\n"
              "16/07/2026;Nómina Ficticia;2.100,00;3.300,00\n"
              "17/07/2026;Bizum recibido;10,00;3.310,00\n")

ESTADO_TARJETA = """ESTADO DE CUENTA TARJETA FICTICIA   Periodo del 01/06/2026 al 30/06/2026
SALDO ANTERIOR                              1,000.00
02-jun   03-jun   WALMART SUPERCENTER 0001          850.00
05-jun   05-jun   UBER *TRIP                        120.50
10-jun   10-jun   SU PAGO GRACIAS                -1,000.00
15-jun   15-jun   INTERESES                          45.10
PAGO MINIMO                                         300.00
TOTAL CARGOS                                      1,015.60
"""

ESTADO_DEBITO = """BANCO FICTICIO   ESTADO DE CUENTA   DEL 01/07/2026 AL 31/07/2026
FECHA OPER LIQ DESCRIPCION                  CARGOS ABONOS SALDO
Saldo anterior                                            5,000.00
01/JUL 01/JUL SPEI RECIBIDO EMPRESA FICTICIA  12,000.00  17,000.00
02/JUL 02/JUL PAGO TARJETA FICTICIA           2,500.00   14,500.00
03/JUL 03/JUL CFE SUMINISTRADOR              480.00      14,020.00
"""


def pdf(lineas: list[str], *mas_paginas: list[str]) -> bytes:
    """Un PDF mínimo con texto (como el estado de cuenta que manda el banco), de una o varias páginas."""
    def escapar(t):
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    paginas = [lineas, *mas_paginas]
    fuente = 3 + 2 * len(paginas)
    objetos = ["<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(paginas)))}] "
               f"/Count {len(paginas)} >>"]
    for i, hoja in enumerate(paginas):
        contenido = "BT /F1 9 Tf 30 800 Td 12 TL\n" + "".join(f"({escapar(ln)}) Tj T*\n" for ln in hoja) + "ET"
        objetos += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {fuente} 0 R >> >> >>",
                    f"<< /Length {len(contenido.encode('cp1252'))} >>\nstream\n{contenido}\nendstream"]
    objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    salida = b"%PDF-1.4\n"
    posiciones = []
    for n, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{n} 0 obj\n{objeto}\nendobj\n".encode("cp1252")
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += "".join(f"{p:010d} 00000 n \n" for p in posiciones).encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return salida


# Imita el formato de un estado de cuenta de débito mexicano: el saldo solo en algunos renglones, el concepto
# en los renglones de abajo (con referencias y claves), el encabezado repetido en cada hoja y los totales del banco.
# Todo inventado.
DEBITO_PAGINA_1 = """Cuenta Ficticia Plus
PAGINA 1 / 2
Periodo DEL 01/03/2026 AL 31/03/2026
No. de Cuenta 0000000000
Saldo Promedio 1,000.00   Saldo Anterior 500.00
Depositos / Abonos (+) 3 9,100.00
Retiros / Cargos (-) 5 9,250.00
Saldo Promedio Gravable 0.00   Saldo Final 350.00
Detalle de Movimientos Realizados
FECHA                                                              SALDO
OPER LIQ DESCRIPCION   REFERENCIA   CARGOS   ABONOS   OPERACION   LIQUIDACION
02/MAR 02/MAR RETIRO CAJERO AUTOMATICO          500.00
MAR02 10:00 BCO 0000 FOLIO:1111   Referencia ******0000
05/MAR 06/MAR SPEI RECIBIDOBANCO FICTICIO              100.00     100.00
0000000Regalo cumple   Referencia 0000000000 000
00000000000000000000
PERSONA FICTICIA UNO""".splitlines()
DEBITO_PAGINA_2 = """Cuenta Ficticia Plus
PAGINA 2 / 2
No. de Cuenta 0000000000
15/MAR 15/MAR PAGO DE NOMINA                         6,000.00
EMPRESA FICTICIA SA DE CV   Referencia 0000
15/MAR 15/MAR SPEI ENVIADO BILLETERA FICTICIA   1,900.00
0000000Ahorro Marzo   Referencia 0000
YO BILLETERA FICTICIA
15/MAR 15/MAR SPEI ENVIADO CASA DE BOLSA FICTICIA   1,500.00
0000000Inversion Marzo   Referencia 0000
15/MAR 15/MAR SPEI ENVIADO TARJETA FICTICIA   2,600.00     100.00     100.00
0000000Pago TDC   Referencia 0000
20/MAR 20/MAR SPEI RECIBIDOBANCO FICTICIO              3,000.00
25/MAR 25/MAR RETIRO CAJERO AUTOMATICO          2,750.00
Total de Movimientos
TOTAL IMPORTE CARGOS 9,250.00   TOTAL MOVIMIENTOS CARGOS 5
TOTAL IMPORTE ABONOS 9,100.00   TOTAL MOVIMIENTOS ABONOS 3""".splitlines()


def centavos(lectura):
    return [m.centavos for m in lectura.movimientos]


# ------------------------------------------------------------------ leer


def test_csv_de_un_banco_mexicano_con_encabezado_y_totales():
    fuente = bancos.leer("movimientos.csv", CSV_MEXICO.encode("utf-8"))
    columnas = bancos.detectar(fuente.tabla)
    assert (columnas.fecha, columnas.descripcion, columnas.cargo, columnas.abono, columnas.encabezado) == \
        (0, (2,), 4, 5, 2)
    lectura = bancos.interpretar(fuente)
    assert [m.descripcion for m in lectura.movimientos] == [
        "PAGO NOMINA EMPRESA FICTICIA", "COMPRA OXXO 1234 SUC CENTRO", "NETFLIX.COM"]
    assert centavos(lectura) == [1_500_000, -8_550, -21_900]
    assert lectura.movimientos[0].fecha == date(2026, 7, 1)
    assert (lectura.entra, lectura.sale) == (1_500_000, 30_450)          # el renglón «Total» no cuenta
    assert (lectura.desde, lectura.hasta) == (date(2026, 7, 1), date(2026, 7, 5))
    assert lectura.cargos_negativos is None and lectura.supuestos == 0


def test_csv_espanol_con_coma_decimal_y_un_solo_importe():
    lectura = bancos.interpretar(bancos.leer("cuenta.csv", CSV_ESPANA.encode("cp1252")))
    assert centavos(lectura) == [-4_530, 210_000, 1_000]                 # el saldo confirma el signo
    assert lectura.cargos_negativos is True
    assert lectura.movimientos[1].descripcion == "Nómina Ficticia"


def test_importe_con_signo_sin_saldo():
    sin_saldo = "\n".join(ln.rsplit(";", 1)[0] for ln in CSV_ESPANA.splitlines())
    lectura = bancos.interpretar(bancos.leer("x.csv", sin_saldo.encode()))
    assert centavos(lectura) == [-4_530, 210_000, 1_000]                 # en una cuenta de banco, menos = sale
    tarjeta = ("Fecha,Descripcion,Monto\n01/07/2026,TIENDA FICTICIA,500.00\n02/07/2026,CAFE FICTICIO,80.00\n"
               "05/07/2026,PAGO RECIBIDO,-580.00\n")
    lectura = bancos.interpretar(bancos.leer("tdc.csv", tarjeta.encode()), credito=True)
    assert centavos(lectura) == [-50_000, -8_000, 58_000] and lectura.cargos_negativos is False
    # El usuario puede decir lo contrario.
    lectura = bancos.interpretar(bancos.leer("tdc.csv", tarjeta.encode()), credito=True, cargos_negativos=True)
    assert centavos(lectura) == [50_000, 8_000, -58_000]
    solo_positivos = "Fecha,Descripcion,Monto\n01/07/2026,TIENDA FICTICIA,500.00\n02/07/2026,CAFE,80.00\n"
    assert centavos(bancos.interpretar(bancos.leer("x.csv", solo_positivos.encode()))) == [-50_000, -8_000]


def test_columna_tipo_debe_haber():
    texto = "Fecha\tConcepto\tImporte\tTipo\n01/07/2026\tRecibo ficticio\t300,00\tD\n02/07/2026\tTraspaso\t50,00\tH\n"
    lectura = bancos.interpretar(bancos.de_texto(texto))
    assert centavos(lectura) == [-30_000, 5_000]


def test_tabla_pegada_desde_la_pagina_del_banco_con_tabuladores():
    texto = ("Fecha\tDescripción\tRetiros\tDepósitos\n"
             "15/07/2026\tFARMACIA FICTICIA\t$125.00\t\n"
             "16/07/2026\tDEPOSITO FICTICIO\t\t$1,000.00\n")
    lectura = bancos.interpretar(bancos.de_texto(texto))
    assert centavos(lectura) == [-12_500, 100_000]


def test_excel_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    libro_excel = openpyxl.Workbook()
    hoja = libro_excel.active
    hoja.append(["Movimientos de la cuenta ficticia"])
    hoja.append([])
    hoja.append(["Fecha", "Concepto", "Cargo", "Abono", "Saldo"])
    hoja.append([datetime(2026, 7, 2), "STARBUCKS FICTICIO", 65.5, None, 934.5])
    hoja.append([datetime(2026, 7, 3), "INTERESES GANADOS", None, 1.23, 935.73])
    hoja.append([datetime(2026, 7, 4), "RESTAURANTE FICTICIO", 0.1 + 0.2, None, 935.43])   # 0.30000000000000004
    salida = io.BytesIO()
    libro_excel.save(salida)
    lectura = bancos.interpretar(bancos.leer("movimientos.xlsx", salida.getvalue()))
    assert [(m.fecha, m.centavos) for m in lectura.movimientos] == [
        (date(2026, 7, 2), -6_550), (date(2026, 7, 3), 123), (date(2026, 7, 4), -30)]


def test_excel_dañado_o_antiguo():
    with pytest.raises(ErrorValidacion, match="No pude abrir este archivo de Excel"):
        bancos.leer("x.xlsx", b"PK\x03\x04no es un excel")
    with pytest.raises(ErrorValidacion, match="Excel antiguo"):
        bancos.leer("x.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    with pytest.raises(ErrorValidacion, match="vacío"):
        bancos.leer("x.csv", b"")


def test_xls_que_en_realidad_es_una_pagina_web():
    html = ("<html><body><table><tr><th>Fecha</th><th>Concepto</th><th>Importe</th></tr>"
            "<tr><td>20/07/2026</td><td>CINEPOLIS&nbsp;FICTICIO</td><td>-150.00</td></tr>"
            "<tr><td>21/07/2026</td><td>ABONO<br>FICTICIO</td><td>99.90</td></tr></table></body></html>")
    lectura = bancos.interpretar(bancos.leer("movimientos.xls", html.encode("cp1252")))
    assert centavos(lectura) == [-15_000, 9_990]
    assert lectura.movimientos[1].descripcion == "ABONO FICTICIO"


def test_texto_de_estado_de_cuenta_de_tarjeta():
    lectura = bancos.interpretar(bancos.de_texto(ESTADO_TARJETA), credito=True, hoy=date(2026, 10, 1))
    assert [(m.fecha, m.descripcion, m.centavos) for m in lectura.movimientos] == [
        (date(2026, 6, 2), "WALMART SUPERCENTER 0001", -85_000),
        (date(2026, 6, 5), "UBER *TRIP", -12_050),
        (date(2026, 6, 10), "SU PAGO GRACIAS", 100_000),
        (date(2026, 6, 15), "INTERESES", -4_510),
    ]                                                         # sin «SALDO ANTERIOR», «PAGO MINIMO» ni «TOTAL»
    assert lectura.supuestos == 3 and lectura.avisos


def test_texto_de_estado_de_cuenta_de_debito_usa_el_saldo():
    lectura = bancos.interpretar(bancos.de_texto(ESTADO_DEBITO), hoy=date(2026, 10, 1))
    assert [(m.fecha, m.centavos, m.supuesto) for m in lectura.movimientos] == [
        (date(2026, 7, 1), 1_200_000, False), (date(2026, 7, 2), -250_000, False), (date(2026, 7, 3), -48_000, False)]


def test_pdf_con_texto():
    datos = pdf(ESTADO_TARJETA.splitlines())
    fuente = bancos.leer("estado.pdf", datos)
    assert fuente.es_pdf and not fuente.es_tabla
    lectura = bancos.interpretar(fuente, credito=True, hoy=date(2026, 10, 1))
    assert centavos(lectura) == [-85_000, -12_050, 100_000, -4_510]


def test_pdf_con_contrasena():
    pypdf = pytest.importorskip("pypdf")
    escritor = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(pdf(ESTADO_TARJETA.splitlines()))))
    escritor.encrypt("FICT800101", algorithm="AES-128")
    salida = io.BytesIO()
    escritor.write(salida)
    with pytest.raises(bancos.PdfConContrasena, match="tiene contraseña"):
        bancos.leer("estado.pdf", salida.getvalue())
    with pytest.raises(bancos.PdfConContrasena, match="no es la contraseña"):
        bancos.leer("estado.pdf", salida.getvalue(), contrasena_pdf="otra")
    fuente = bancos.leer("estado.pdf", salida.getvalue(), contrasena_pdf="FICT800101")
    assert len(bancos.interpretar(fuente, credito=True, hoy=date(2026, 10, 1)).movimientos) == 4


def test_pdf_escaneado_o_dañado():
    with pytest.raises(ErrorValidacion, match="imagen escaneada"):
        bancos.leer("estado.pdf", pdf([]))
    with pytest.raises(ErrorValidacion, match="No pude leer este PDF"):
        bancos.leer("estado.pdf", b"%PDF-1.4 basura")


def test_sin_movimientos_avisa():
    with pytest.raises(ErrorValidacion, match="No encontré"):
        bancos.interpretar(bancos.de_texto("Hola\nEsto no es un estado de cuenta\n"))
    with pytest.raises(ErrorValidacion, match="Pega|pega"):
        bancos.de_texto("   \n  ")


def test_columnas_elegidas_a_mano():
    texto = "A\tB\tC\tD\n15/07/2026\tCOMPRA FICTICIA\t100.00\t900.00\n16/07/2026\tOTRA\t50.00\t850.00\n"
    fuente = bancos.de_texto(texto)
    lectura = bancos.interpretar(fuente, columnas=Columnas(fecha=0, descripcion=(1,), importe=2, encabezado=0),
                                 cargos_negativos=False)
    assert centavos(lectura) == [-10_000, -5_000]
    assert bancos.titulos(fuente.tabla, Columnas(fecha=0, importe=2, encabezado=0)) == ["A", "B", "C", "D"]
    with pytest.raises(ErrorValidacion, match="importe"):
        Columnas(fecha=0)


def test_sin_titulos_decide_por_el_contenido():
    texto = "15/07/2026;COMPRA FICTICIA;100.00;;900.00\n16/07/2026;DEPOSITO;;50.00;950.00\n17/07/2026;X;10.00;;940\n"
    fuente = bancos.leer("x.csv", texto.encode())
    columnas = bancos.detectar(fuente.tabla)
    assert (columnas.fecha, columnas.descripcion, columnas.cargo, columnas.abono) == (0, (1,), 2, 3)
    assert centavos(bancos.interpretar(fuente)) == [-10_000, 5_000, -1_000]


@pytest.mark.parametrize("texto, esperado", [
    ("15/07/2026", date(2026, 7, 15)), ("15-07-26", date(2026, 7, 15)), ("2026-07-15", date(2026, 7, 15)),
    ("15/JUL/2026", date(2026, 7, 15)), ("15 julio 2026", date(2026, 7, 15)), ("15-jul-26", date(2026, 7, 15)),
    ("15/07/2026 13:45", date(2026, 7, 15)), ("2026-07-15T00:00:00", date(2026, 7, 15)),
    ("46218", date(2026, 7, 15)), ("31/02/2026", None), ("hola", None), ("", None), ("15/07", None),
])
def test_fechas(texto, esperado):
    assert bancos.leer_fecha(texto) == esperado


def test_fechas_mes_dia_y_sin_anio():
    assert bancos.leer_fecha("07/15/2026", orden="mda") == date(2026, 7, 15)
    assert bancos.leer_fecha("15/07", anio=2026) == date(2026, 7, 15)
    assert bancos.leer_fecha("02JUN", anio=2026) == date(2026, 6, 2)
    csv = "Date,Description,Amount\n07/15/2026,FICTICIO,-10.00\n07/02/2026,OTRO,-5.00\n"
    assert [m.fecha for m in bancos.interpretar(bancos.leer("x.csv", csv.encode())).movimientos] == [
        date(2026, 7, 15), date(2026, 7, 2)]
    # Estado de cuenta de diciembre a enero: diciembre es del año anterior.
    texto = "Periodo al 10/01/2027\n20-dic COMPRA FICTICIA 100.00\n05-ene OTRA COMPRA FICTICIA 50.00\n"
    lectura = bancos.interpretar(bancos.de_texto(texto), hoy=date(2027, 1, 12))
    assert [m.fecha for m in lectura.movimientos] == [date(2026, 12, 20), date(2027, 1, 5)]


@pytest.mark.parametrize("texto, decimal, esperado", [
    ("$1,234.56", None, 123_456), ("-850.00", None, -85_000), ("(850.00)", None, -85_000),
    ("850.00-", None, -85_000), ("1.234,56", None, 123_456), ("850,5", None, 85_050), ("1,234", None, 123_400),
    ("1.234", ",", 123_400), ("−45,30", None, -4_530), ("1 234,56 €", None, 123_456), ("850.00 CR", None, -85_000),
    ("MXN 99.99", None, 9_999), ("+10", None, 1_000), ("abc", None, None), ("", None, None), ("1.2.3", ".", None),
])
def test_importes(texto, decimal, esperado):
    assert bancos.leer_importe(texto, decimal=decimal) == esperado


# ------------------------------------------------------------------ sugerencias


def mov(descripcion, centavos_, fecha=date(2026, 7, 15), fila=1):
    return Movimiento(fila, fecha, descripcion, centavos_)


def sugerida(libro, cuenta_id, descripcion, centavos_):
    (p,) = bancos.revisar(libro, cuenta_id, [mov(descripcion, centavos_)])
    return bancos.etiqueta_destino(libro, p.destino) if p.destino else "", p.motivo


@pytest.mark.parametrize("descripcion, centavos_, esperada", [
    ("COMPRA OXXO 1234 SUC CENTRO", -8_550, "SNACKS Y ANTOJOS"),
    ("OXXO GAS 0044", -50_000, "GASOLINA"),
    ("UBER *EATS PENDING", -23_000, "COMIDA A DOMICILIO"),
    ("UBER *TRIP HELP.UBER.COM", -12_000, "TAXI Y APPS DE VIAJE"),
    ("CFE SUMINISTRADOR DE SERVICIOS", -48_000, "LUZ"),
    ("COMISION FEDERAL DE ELECTRICIDAD", -48_000, "LUZ"),
    ("COMISION POR ANUALIDAD", -60_000, "COMISIONES BANCARIAS"),
    ("NETFLIX.COM", -21_900, "STREAMING DE VIDEO"),
    ("AMAZON PRIME*MX", -9_900, "MEMBRESIAS"),
    ("AMZN MKTP MX", -45_000, "COMPRAS EN LINEA"),
    ("WAL-MART SUPERCENTER", -85_000, "DESPENSA"),
    ("SMART FIT FICTICIO", -49_900, "GIMNASIO"),
    ("FARMACIAS FICTICIAS DEL CENTRO", -20_000, "MEDICINAS Y FARMACIA"),
    ("PAGO NOMINA EMPRESA FICTICIA", 1_500_000, "NOMINA"),
    ("INTERESES GANADOS", 123, "INTERESES Y RENDIMIENTOS"),
    ("INTERESES", -4_510, "INTERESES DE TARJETAS"),
    ("DEVOLUCION AMAZON MX", 45_000, "COMPRAS EN LINEA"),          # reembolso: resta del gasto
    ("SPEI ENVIADO A FICTICIO", -100_000, ""),
    ("ANDREA FICTICIA", -100_000, ""),
])
def test_sugerencias_por_comercio(libro, ctas, descripcion, centavos_, esperada):
    etiqueta, motivo = sugerida(libro, ctas.debito, descripcion, centavos_)
    assert etiqueta.endswith(esperada) if esperada else etiqueta == ""
    if not esperada:
        assert motivo


def test_aprende_de_tu_historial(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 3), ctas.debito, cat("DESPENSA"), 90, "OXXO SUC CENTRO 1111")
    etiqueta, motivo = sugerida(libro, ctas.debito, "COMPRA OXXO 9999 SUC CENTRO", -8_550)
    assert etiqueta.endswith("DESPENSA") and "OXXO SUC CENTRO 1111" in motivo       # gana a «SNACKS»
    etiqueta, motivo = sugerida(libro, ctas.credito, "OXXO SUC CENTRO 2222", -8_550)  # también en otra cuenta
    assert etiqueta.endswith("DESPENSA") and motivo.startswith("Como")
    # Lo que salió no se sugiere para lo que entra.
    assert sugerida(libro, ctas.debito, "OXXO SUC CENTRO", 8_550)[0] == ""


def test_un_parecido_lejano_no_gana_a_un_comercio_conocido(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 3), ctas.debito, cat("INTERESES DE PRESTAMOS"), 90,
                                "Intereses préstamo auto ficticio")
    assert sugerida(libro, ctas.credito, "INTERESES", -1_230)[0].endswith("INTERESES DE TARJETAS")
    # Sin comercio conocido, el parecido sí ayuda.
    movimientos.registrar_gasto(libro, date(2026, 6, 3), ctas.debito, cat("REGALOS"), 90, "Tienda Lulú Ficticia Centro")
    etiqueta, motivo = sugerida(libro, ctas.debito, "LULU FICTICIA", -5_000)
    assert etiqueta.endswith("REGALOS") and motivo.startswith("Parecido")


def test_aprende_transferencias_a_tus_cuentas(libro, ctas):
    registrar_transferencia(libro, date(2026, 6, 1), ctas.debito, ctas.ahorro, 1000, "TRASPASO A MI AHORRO FICTICIO")
    registrar_pago_tarjeta(libro, date(2026, 6, 20), ctas.debito, ctas.credito, 500, "PAGO TARJETA FICTICIA")
    assert sugerida(libro, ctas.debito, "TRASPASO A MI AHORRO FICTICIO 0707", -100_000)[0] == "↔ Ahorro Ficticio"
    assert sugerida(libro, ctas.debito, "PAGO TARJETA FICTICIA", -50_000)[0] == "↔ Tarjeta Ficticia"
    # Desde la tarjeta, el pago llega de la cuenta de débito.
    assert sugerida(libro, ctas.credito, "PAGO TARJETA FICTICIA", 50_000)[0] == "↔ Banco Ficticio Débito"


def test_no_sugiere_subcategorias_archivadas(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 3), ctas.debito, cat("RESTAURANTES"), 90, "FONDA FICTICIA")
    categorias.archivar(libro, cat("RESTAURANTES"))
    assert sugerida(libro, ctas.debito, "FONDA FICTICIA", -9_000)[0] == ""
    categorias.archivar(libro, cat("SNACKS Y ANTOJOS"))
    assert sugerida(libro, ctas.debito, "OXXO", -9_000)[0] == ""


def test_nucleo_y_propagar():
    assert bancos.nucleo("COMPRA OXXO 1234 SUC CENTRO REF 998877") == ("OXXO", "CENTRO")
    a, b, c = mov("TIENDITA FICTICIA 01", -100), mov("TIENDITA FICTICIA 02", -200), mov("TIENDITA FICTICIA", 300)
    assert bancos.propagar([(a, "sub:x"), (b, ""), (c, "")]) == [(a, "sub:x"), (b, "sub:x"), (c, "")]


# ------------------------------------------------------------------ duplicados


def test_duplicados_misma_cuenta_importe_y_pocos_dias(libro, ctas, cat):
    ya = movimientos.registrar_gasto(libro, date(2026, 7, 15), ctas.debito, cat("DESPENSA"), 850, "Súper")
    movimientos.registrar_gasto(libro, date(2026, 7, 15), ctas.credito, cat("DESPENSA"), 120, "Otra cuenta")
    lista = [mov("WALMART", -85_000, date(2026, 7, 17), 1),          # el banco lo registró dos días después
             mov("WALMART", -85_000, date(2026, 7, 18), 2),          # otra compra igual: no es la misma
             mov("FICTICIO", -12_000, date(2026, 7, 15), 3),         # mismo importe pero en otra cuenta
             mov("WALMART", -85_000, date(2026, 7, 25), 4)]          # muy lejos
    propuestas = bancos.revisar(libro, ctas.debito, lista)
    assert [p.duplicado.id if p.duplicado else None for p in propuestas] == [ya.id, None, None, None]
    assert [p.cargar for p in propuestas] == [False, True, True, True]


def test_pago_de_tarjeta_ya_registrado_desde_el_debito(libro, ctas):
    pago = registrar_pago_tarjeta(libro, date(2026, 6, 9), ctas.debito, ctas.credito, 1000, "Pago")
    (p,) = bancos.revisar(libro, ctas.credito, [mov("SU PAGO GRACIAS", 100_000, date(2026, 6, 10))])
    assert p.duplicado.id == pago.id


# ------------------------------------------------------------------ cargar


def test_cargar_todo_y_volver_a_subir_no_duplica(libro, ctas):
    lectura = bancos.interpretar(bancos.leer("movimientos.csv", CSV_MEXICO.encode()))
    propuestas = bancos.revisar(libro, ctas.debito, lectura.movimientos)
    assert all(p.destino for p in propuestas) and all(p.cargar for p in propuestas)
    archivo, mapeo = bancos.para_cargar(libro, ctas.debito, [(p.movimiento, p.destino) for p in propuestas])
    vista = importacion.vista_previa(libro, archivo, mapeo)
    assert vista.se_puede_cargar and vista.nuevos == 3 and not libro.operaciones()
    resultado = importacion.cargar(libro, archivo, mapeo)
    assert resultado.nuevos == 3
    assert libro.saldo_centavos(ctas.debito) == 1_500_000 - 8_550 - 21_900
    tipos = sorted(op.tipo.value for op in libro.operaciones())
    assert tipos == ["gasto", "gasto", "ingreso"]
    # Subir el mismo archivo otra vez: todo aparece como «ya está».
    otra_vez = bancos.revisar(libro, ctas.debito, lectura.movimientos)
    assert not any(p.cargar for p in otra_vez)
    # Y aunque el usuario lo marcara para cargar, el importador no lo duplica.
    archivo, mapeo = bancos.para_cargar(libro, ctas.debito, [(p.movimiento, p.destino) for p in otra_vez])
    assert importacion.vista_previa(libro, archivo, mapeo).contar(importacion.YA_ESTABA) == 3


def test_cargar_estado_de_tarjeta_con_pago_desde_el_debito(libro, ctas):
    lectura = bancos.interpretar(bancos.de_texto(ESTADO_TARJETA), credito=True, hoy=date(2026, 10, 1))
    propuestas = bancos.revisar(libro, ctas.credito, lectura.movimientos)
    elegidos = [(p.movimiento, p.destino or bancos.destino_cuenta(ctas.debito)) for p in propuestas]
    archivo, mapeo = bancos.para_cargar(libro, ctas.credito, elegidos)
    importacion.cargar(libro, archivo, mapeo)
    assert libro.saldo_centavos(ctas.credito) == -(85_000 + 12_050 + 4_510) + 100_000
    assert libro.saldo_centavos(ctas.debito) == -100_000
    assert {op.tipo.value for op in libro.operaciones()} == {"gasto", "pago_tarjeta"}


def test_devolucion_es_reembolso(libro, ctas, cat):
    m = mov("DEVOLUCION AMAZON MX", 45_000)
    (p,) = bancos.revisar(libro, ctas.debito, [m])
    archivo, mapeo = bancos.para_cargar(libro, ctas.debito, [(m, p.destino)])
    importacion.cargar(libro, archivo, mapeo)
    (op,) = libro.operaciones()
    assert op.tipo.value == "reembolso" and op.partidas_de_categoria()[0].categoria_id == cat("COMPRAS EN LINEA")


def test_sin_elegir_no_se_carga_y_otros_de_respaldo(libro, ctas, cat):
    a, b = mov("ALGO FICTICIO", -1_000, fila=7), mov("ALGO QUE ENTRA", 2_000, fila=8)
    with pytest.raises(ErrorValidacion, match="7, 8"):
        bancos.para_cargar(libro, ctas.debito, [(a, ""), (b, "")])
    assert bancos.de_respaldo(libro, a) == bancos.destino_subcategoria(cat("OTROS GASTOS"))
    assert bancos.de_respaldo(libro, b) == bancos.destino_subcategoria(cat("OTROS INGRESOS"))
    with pytest.raises(ErrorValidacion, match="misma cuenta"):
        bancos.para_cargar(libro, ctas.debito, [(a, bancos.destino_cuenta(ctas.debito))])


def test_si_un_renglon_falla_no_se_carga_nada(tmp_path):
    """Como en el portal: la carga va dentro de ``sesion.cambio()``; si algo falla, no se guarda nada."""
    sesion = Sesion(tmp_path / "tally.db", reloj=lambda: AHORA)
    with sesion.cambio() as lib:
        debito = cuentas.crear(lib, "Débito Ficticio", "debito", fecha_creacion=date(2026, 1, 1)).id
        ahorro = cuentas.crear(lib, "Ahorro Ficticio", "ahorro", fecha_creacion=date(2026, 1, 1)).id
        otros = categorias.buscar(lib, "OTROS GASTOS").id
        cuentas.archivar(lib, ahorro)
    bien = mov("COMPRA FICTICIA", -1_000)
    mal = mov("A UNA CUENTA ARCHIVADA", -1_000, fila=2)
    elegidos = [(bien, bancos.destino_subcategoria(otros)), (mal, bancos.destino_cuenta(ahorro))]
    archivo, mapeo = bancos.para_cargar(sesion.libro, debito, elegidos)
    vista = importacion.vista_previa(sesion.libro, archivo, mapeo)
    assert not vista.se_puede_cargar and vista.contar(importacion.ERROR) == 1
    with pytest.raises(ErrorValidacion, match="No se cargó nada"):
        with sesion.cambio() as lib:
            importacion.cargar(lib, archivo, mapeo)
    assert Sesion(tmp_path / "tally.db", reloj=lambda: AHORA).libro.operaciones() == []
    assert sesion.libro.operaciones() == []


def test_nombres_iguales_de_cuenta_y_subcategoria_no_se_confunden(libro, ctas, cat):
    cuentas.crear(libro, "Gimnasio", "efectivo", fecha_creacion=date(2026, 1, 1))     # se llama como la subcategoría
    m = mov("SMART FIT", -49_900)
    archivo, mapeo = bancos.para_cargar(libro, ctas.debito, [(m, bancos.destino_subcategoria(cat("GIMNASIO")))])
    importacion.cargar(libro, archivo, mapeo)
    (op,) = libro.operaciones()
    assert op.tipo.value == "gasto"


def test_estado_de_debito_en_varias_hojas_con_saldo_en_algunos_renglones():
    fuente = bancos.leer("estado.pdf", pdf(DEBITO_PAGINA_1, DEBITO_PAGINA_2))
    lectura = bancos.interpretar(fuente, hoy=date(2026, 10, 1))
    assert [(m.fecha, m.centavos) for m in lectura.movimientos] == [
        (date(2026, 3, 2), -50_000), (date(2026, 3, 5), 10_000), (date(2026, 3, 15), 600_000),
        (date(2026, 3, 15), -190_000), (date(2026, 3, 15), -150_000), (date(2026, 3, 15), -260_000),
        (date(2026, 3, 20), 300_000), (date(2026, 3, 25), -275_000)]
    # Con los saldos, sin dudas: hasta la nómina que se reparte completa en tres envíos (las dos formas cuadran
    # con el saldo; las palabras NÓMINA y ENVIADO deciden).
    assert lectura.supuestos == 0
    assert (lectura.total_cargos, lectura.total_abonos) == (lectura.sale, lectura.entra) == (925_000, 910_000)
    assert lectura.avisos == ()                                  # coincide con los totales del banco
    descripciones = [m.descripcion for m in lectura.movimientos]
    assert descripciones[0] == "RETIRO CAJERO AUTOMATICO"                         # sin folios ni referencias
    assert descripciones[1] == "SPEI RECIBIDO BANCO FICTICIO · Regalo cumple · PERSONA FICTICIA UNO"
    assert descripciones[3] == "SPEI ENVIADO BILLETERA FICTICIA · Ahorro Marzo · YO BILLETERA FICTICIA"
    assert not any("Cuenta Ficticia Plus" in d or "PAGINA" in d for d in descripciones)   # sin encabezados


def test_el_mismo_estado_pegado_como_texto():
    lectura = bancos.interpretar(bancos.de_texto("\n".join(DEBITO_PAGINA_1 + DEBITO_PAGINA_2)), hoy=date(2026, 10, 1))
    assert len(lectura.movimientos) == 8 and lectura.supuestos == 0
    assert (lectura.sale, lectura.entra) == (925_000, 910_000)


def test_si_no_cuadra_con_los_totales_del_banco_avisa():
    sin_un_retiro = [ln for ln in DEBITO_PAGINA_2 if not ln.startswith("25/MAR")]
    lectura = bancos.interpretar(bancos.de_texto("\n".join(DEBITO_PAGINA_1 + sin_un_retiro)), hoy=date(2026, 10, 1))
    assert lectura.sale != lectura.total_cargos and lectura.avisos


def test_un_comercio_que_empieza_con_total_no_se_descarta():
    texto = "Periodo al 31/07/2026\n04/JUL TOTAL PLAY FICTICIO 599.00\n05/JUL TOTAL CARGOS 599.00\n"
    lectura = bancos.interpretar(bancos.de_texto(texto), hoy=date(2026, 10, 1))
    assert [m.descripcion for m in lectura.movimientos] == ["TOTAL PLAY FICTICIO"]


def test_propagar_a_los_casi_iguales():
    julio = mov("SPEI ENVIADO BILLETERA FICTICIA · Ahorro Julio · YO BILLETERA FICTICIA", -100)
    agosto = mov("SPEI ENVIADO BILLETERA FICTICIA · Ahorro Agosto · YO BILLETERA FICTICIA", -200)
    otro = mov("SPEI ENVIADO CASA DE BOLSA FICTICIA · Inversion", -300)
    entra = mov("SPEI RECIBIDO BILLETERA FICTICIA · Ahorro Julio", 400)
    resultado = bancos.propagar([(julio, "cuenta:x"), (agosto, ""), (otro, ""), (entra, "")])
    assert [d for _, d in resultado] == ["cuenta:x", "cuenta:x", "", ""]
