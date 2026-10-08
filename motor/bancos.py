"""Importar los movimientos de tu banco: el archivo de tu banca en línea (Excel o CSV), lo que copias de su página
o de tu estado de cuenta, o el PDF del estado de cuenta.

Todo pasa en tu PC: TALLY no se conecta a tu banco ni manda el archivo a ningún lado.

1. :func:`leer` (un archivo) o :func:`de_texto` (lo pegado) → :class:`Fuente`.
2. :func:`interpretar` → :class:`Lectura` con los movimientos: fecha, descripción e importe con signo.

   - En una **tabla** (Excel, CSV, una tabla copiada) encuentra solas las columnas por sus títulos (o por su
     contenido, si no tienen). Se pueden corregir con :class:`Columnas`.
   - En **texto sin columnas** (PDF) toma los renglones que empiezan con una fecha y terminan con un importe.
     Si el renglón trae el saldo, con él sabe si el dinero entró o salió.

3. :func:`revisar` → una :class:`Propuesta` por movimiento: la subcategoría (o cuenta) sugerida y si parece
   que ya está en TALLY.

   - **Sugerencias:** primero lo que tú elegiste antes para una descripción igual o parecida (TALLY aprende de
     tu historial); si no hay, por el nombre de comercios conocidos (OXXO, Walmart, Netflix, CFE…).
   - **Duplicados:** un movimiento de TALLY en la misma cuenta, por el mismo importe y a pocos días (el banco
     puede registrar una compra días después de que la hiciste). Cada uno se empareja una sola vez.

4. :func:`para_cargar` → lo que recibe :func:`motor.importacion.cargar`, que aplica las reglas de siempre:
   todo o nada, transferencias una sola vez y nada duplicado.

Convención de importes: en centavos; **positivo = entra** (abono), **negativo = sale** (cargo), para cualquier
tipo de cuenta. En una tarjeta de crédito, una compra sale (sube tu deuda) y un pago entra.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html.parser import HTMLParser

from motor import categorias, reglas_categorias
from motor.errores import ErrorValidacion
from motor.importacion import Archivo, Bloque, Destino, Linea, clave_destino, decodificar
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Operacion, TipoCuenta, TipoOperacion
from motor.textos import clave

TIPOS_DE_ARCHIVO = ("csv", "txt", "tsv", "xlsx", "xls", "pdf")
DIAS_DE_TOLERANCIA = 4          # el banco puede registrar una compra unos días después de que la hiciste
MAXIMO_RENGLONES = 20_000
XLS_ANTIGUO = ("Este es un archivo de Excel antiguo (.xls) que TALLY no puede leer. Ábrelo con Excel y usa "
               "Archivo → Guardar como → «Libro de Excel (.xlsx)» o «CSV», y súbelo otra vez.")


class PdfConContrasena(ErrorValidacion):
    """El PDF está protegido: muchos bancos le ponen contraseña (por ejemplo, tu RFC o tu fecha de nacimiento)."""


# ===================================================================== leer el archivo


@dataclass(frozen=True, slots=True)
class Fuente:
    """Lo que trae el archivo, todavía sin interpretar."""

    nombre: str
    tabla: tuple[tuple[str, ...], ...] = ()      # Excel, CSV o una tabla pegada
    texto: str = ""                               # PDF o texto pegado sin columnas
    es_pdf: bool = False

    @property
    def es_tabla(self) -> bool:
        return bool(self.tabla)


def leer(nombre: str, datos: bytes, *, contrasena_pdf: str = "") -> Fuente:
    """Excel (.xlsx), CSV o texto, el «Excel» que en realidad es una página web (.xls de algunos bancos) o PDF."""
    if not datos:
        raise ErrorValidacion("El archivo está vacío.")
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if datos[:5] == b"%PDF-" or extension == "pdf":
        return Fuente(nombre, texto=_texto_de_pdf(datos, contrasena_pdf), es_pdf=True)
    if datos[:4] == b"PK\x03\x04" or extension == "xlsx":
        return Fuente(nombre, tabla=_tabla_de_xlsx(datos))
    if datos[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ErrorValidacion(XLS_ANTIGUO)
    texto = decodificar(datos)
    if re.search(r"<\s*table", texto[:500_000], re.IGNORECASE):
        return Fuente(nombre, tabla=_tabla_de_html(texto))
    return de_texto(texto, nombre=nombre, permitir_coma=extension != "txt")


def de_texto(texto: str, *, nombre: str = "Texto pegado", permitir_coma: bool = False) -> Fuente:
    """Lo que el usuario pega: una tabla (copiada de Excel o de la página del banco) o texto suelto (de un PDF)."""
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise ErrorValidacion("No hay nada que leer: sube un archivo o pega tus movimientos.")
    separador = _separador(lineas, permitir_coma=permitir_coma)
    if separador:
        return Fuente(nombre, tabla=_tabla_de_csv(lineas, separador))
    return Fuente(nombre, texto="\n".join(lineas))


def _separador(lineas: list[str], *, permitir_coma: bool) -> str | None:
    """El separador de columnas, si el texto es una tabla: el que deja más renglones con el mismo número de
    columnas (al menos 3: fecha, descripción, importe). La coma solo en archivos .csv: en un texto suelto suele
    ser la de los miles (1,234.56)."""
    muestra = lineas[:300]
    mejor, puntos = None, 0
    for separador in ("\t", ";", "|") + ((",",) if permitir_coma else ()):
        anchos = Counter(len(fila) for fila in csv.reader(muestra, delimiter=separador))
        ancho, veces = max(anchos.items(), key=lambda av: (av[1], av[0]))
        if ancho >= 3 and veces >= max(2, len(muestra) * 0.4) and veces * ancho > puntos:
            mejor, puntos = separador, veces * ancho
    return mejor


def _tabla_de_csv(lineas: list[str], separador: str) -> tuple[tuple[str, ...], ...]:
    filas = tuple(tuple(c.strip() for c in fila) for fila in csv.reader(lineas, delimiter=separador))
    return _sin_vacias(filas)


def _sin_vacias(filas) -> tuple[tuple[str, ...], ...]:
    limpias = tuple(f for f in filas if any(c.strip() for c in f))
    if len(limpias) > MAXIMO_RENGLONES:
        raise ErrorValidacion(f"El archivo tiene más de {MAXIMO_RENGLONES:,} renglones. Divídelo en partes "
                              "(por ejemplo, un archivo por año).")
    return limpias


class _Tablas(HTMLParser):
    """Las celdas de las tablas de una página web (lo que algunos bancos entregan como «.xls»)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.filas: list[tuple[str, ...]] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []
        elif tag == "br" and self._celda is not None:
            self._celda.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._fila is not None and self._celda is not None:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            self.filas.append(tuple(self._fila))
            self._fila = None

    def handle_data(self, data):
        if self._celda is not None:
            self._celda.append(data)


def _tabla_de_html(texto: str) -> tuple[tuple[str, ...], ...]:
    lector = _Tablas()
    lector.feed(texto)
    lector.close()
    filas = _sin_vacias(lector.filas)
    if not filas:
        raise ErrorValidacion("El archivo no tiene ninguna tabla con datos.")
    return filas


def _tabla_de_xlsx(datos: bytes) -> tuple[tuple[str, ...], ...]:
    try:
        import openpyxl
    except ImportError:
        raise ErrorValidacion("Falta un componente para leer Excel. Vuelve a correr INSTALAR.bat.") from None
    try:
        documento = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    except Exception:                                   # zip dañado, no es un Excel, etc.
        raise ErrorValidacion("No pude abrir este archivo de Excel. Ábrelo con Excel, guárdalo otra vez como "
                              "«Libro de Excel (.xlsx)» o «CSV» y vuelve a subirlo.") from None
    mejor: tuple[tuple[str, ...], ...] = ()
    try:
        for hoja in documento.worksheets:               # la hoja con más datos
            filas = _sin_vacias(tuple(_celda(v) for v in fila) for fila in hoja.iter_rows(values_only=True))
            if len(filas) > len(mejor):
                mejor = filas
    finally:
        documento.close()
    if not mejor:
        raise ErrorValidacion("El archivo de Excel no tiene datos.")
    return mejor


def _celda(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float):
        return format(Decimal(str(round(valor, 2))).normalize(), "f")
    return " ".join(str(valor).split())


def _texto_de_pdf(datos: bytes, contrasena: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ErrorValidacion("Falta un componente para leer PDF. Vuelve a correr INSTALAR.bat.") from None
    registro = logging.getLogger("pypdf")
    nivel = registro.level
    registro.setLevel(logging.ERROR)                  # avisos técnicos de fuentes que no le importan al usuario
    try:
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted and not lector.decrypt(contrasena or ""):
            raise PdfConContrasena(
                "Este PDF tiene contraseña." if not contrasena else "Esa no es la contraseña del PDF.")
        paginas = []
        for pagina in lector.pages[:300]:
            try:
                paginas.append(pagina.extract_text(extraction_mode="layout") or "")
            except Exception:
                paginas.append(pagina.extract_text() or "")
    except ErrorValidacion:
        raise
    except Exception:
        raise ErrorValidacion("No pude leer este PDF. Si tu banca en línea te deja descargar tus movimientos en "
                              "Excel o CSV, usa ese archivo: es más confiable.") from None
    finally:
        registro.setLevel(nivel)
    texto = _sin_encabezados(paginas)
    if not re.search(r"\d", texto):
        raise ErrorValidacion("Este PDF no tiene texto que TALLY pueda leer (parece una imagen escaneada). "
                              "Descarga tus movimientos en Excel o CSV desde tu banca en línea.")
    return texto


_NUMERO_DE_PAGINA = re.compile(r"\b(P[AÁ]GINA|PAGE|HOJA)\s*\d+\s*(DE|/|OF)\s*\d+\b", re.IGNORECASE)


def _sin_encabezados(paginas: list[str]) -> str:
    """Quita lo que el banco repite en cada hoja (nombre del producto, número de cuenta, «Página 2 de 6»), para
    que no se pegue a la descripción de un movimiento."""
    renglones = [[" ".join(ln.split()) for ln in p.splitlines()] for p in paginas]
    veces = Counter(ln for hoja in renglones for ln in set(hoja) if ln)
    repetidos = {ln for ln, n in veces.items() if n >= 2 and not _FECHA_AL_INICIO.match(ln)} if len(paginas) > 1 else set()
    limpio = []
    for hoja in renglones:
        limpio.extend(ln for ln in hoja if ln and ln not in repetidos and not _NUMERO_DE_PAGINA.fullmatch(ln))
    return "\n".join(limpio)


# ===================================================================== fechas e importes

_MESES = {"ENE": 1, "JAN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
          "AUG": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12}
_FECHA_NUMERICA = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?$")
_FECHA_CON_MES = re.compile(r"^(\d{1,2})[\s/\-.]*([A-Za-zÁÉÍÓÚáéíóú]{3,10})\.?(?:[\s/\-.,]+(\d{2,4}))?$")


def _mes(texto: str) -> int | None:
    k = clave(texto)
    if not k.isalpha() or len(k) < 3:
        return None
    mes = _MESES.get(k[:3])
    nombres = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "SETIEMBRE",
               "OCTUBRE", "NOVIEMBRE", "DICIEMBRE", "JANUARY", "FEBRUARY", "MARCH", "APRIL", "JUNE", "JULY",
               "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER", "SEPT")
    if mes and (len(k) == 3 or any(n.startswith(k) for n in nombres)):
        return mes
    return None


def leer_fecha(texto: str, *, orden: str = "dma", anio: int | None = None) -> date | None:
    """15/07/2026, 15-07-26, 2026-07-15, 15/JUL/2026, 15 julio 2026, 15JUL (con ``anio``), 07/15/2026 (con
    ``orden="mda"``) o el número de serie de Excel. ``None`` si no es una fecha."""
    t = str(texto).strip()
    if not t:
        return None
    t = re.split(r"[ T](?=\d{1,2}:\d{2})", t)[0].strip()          # sin la hora
    if re.fullmatch(r"\d{5}(?:\.\d+)?", t):                        # número de serie de Excel
        n = int(float(t))
        return date(1899, 12, 30) + timedelta(days=n) if 20_000 < n < 80_000 else None
    try:
        if m := _FECHA_NUMERICA.match(t):
            a, b, c = m.groups()
            if len(a) == 4:
                return date(int(a), int(b), int(c)) if c else None
            dia, mes = (int(b), int(a)) if orden == "mda" else (int(a), int(b))
            return date(_anio(c, anio), mes, dia) if (c or anio) else None
        if m := _FECHA_CON_MES.match(t):
            dia, nombre_mes, a = m.groups()
            mes = _mes(nombre_mes)
            if mes and (a or anio):
                return date(_anio(a, anio), mes, int(dia))
    except ValueError:
        return None
    return None


def _anio(texto: str | None, anio: int | None) -> int:
    if not texto:
        return anio  # type: ignore[return-value]
    n = int(texto)
    return n + 2000 if n < 100 else n


def _orden_de_fechas(valores) -> str:
    """Día/mes (como en México y casi toda Latinoamérica y España) salvo que el archivo diga lo contrario."""
    for v in valores:
        m = _FECHA_NUMERICA.match(str(v).strip().split(" ")[0])
        if m and len(m.group(1)) <= 2:
            if int(m.group(1)) > 12:
                return "dma"
            if int(m.group(2)) > 12:
                return "mda"
    return "dma"


_MONEDAS = re.compile(r"MXN|USD|EUR|COP|ARS|CLP|PEN|UYU|US\$|M\.N\.|MN|\$|€", re.IGNORECASE)


def leer_importe(texto: str, *, decimal: str | None = None) -> int | None:
    """«$1,234.56», «-850.00», «(850.00)», «850.00-», «1.234,56» (con ``decimal=","``), «850,5» → centavos con
    signo. ``None`` si no es un importe. «CR» al final cuenta como signo de menos (un abono en la tarjeta)."""
    t = str(texto).strip().replace("−", "-").replace(" ", " ").replace(" ", " ")
    if not t:
        return None
    t = _MONEDAS.sub("", t).strip()
    negativo = False
    if t.upper().endswith("CR"):
        negativo, t = True, t[:-2].strip()
    if t.startswith("(") and t.endswith(")"):
        negativo, t = True, t[1:-1].strip()
    if t.endswith("-"):
        negativo, t = True, t[:-1].strip()
    if t.startswith("-"):
        negativo, t = not negativo, t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()
    t = t.replace(" ", "").replace("'", "")
    if not re.fullmatch(r"\d[\d.,]*", t):
        return None
    if decimal is None:
        if "," in t and "." in t:
            decimal = "," if t.rfind(",") > t.rfind(".") else "."
        elif "," in t:
            decimal = "." if re.fullmatch(r"\d{1,3}(?:,\d{3})+", t) else ","
        else:
            decimal = "." if t.count(".") <= 1 else ","
    miles = "," if decimal == "." else "."
    t = t.replace(miles, "").replace(decimal, ".")
    if t.count(".") > 1:
        return None
    try:
        valor = Decimal(t).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    centavos = int(valor * 100)
    return -centavos if negativo else centavos


def _decimal_de(valores) -> str:
    """Si la columna usa coma decimal (1.234,56 como en Argentina, Colombia o España) o punto (1,234.56)."""
    coma = punto = 0
    for v in valores:
        t = _MONEDAS.sub("", str(v)).strip().rstrip("-)").strip()
        if re.search(r",\d{1,2}$", t) and not re.search(r",\d{1,2}\.", t):
            coma += 1
        elif re.search(r"\.\d{1,2}$", t):
            punto += 1
    return "," if coma > punto else "."


# ===================================================================== columnas de una tabla

FECHA, DESCRIPCION, CARGO, ABONO, IMPORTE, TIPO, SALDO, REFERENCIA = (
    "fecha", "descripcion", "cargo", "abono", "importe", "tipo", "saldo", "referencia")
_PALABRAS = (
    (SALDO, {"SALDO", "BALANCE", "DISPONIBLE"}),
    (FECHA, {"FECHA", "DATE", "DIA", "FEC"}),
    (TIPO, {"TIPO", "NATURALEZA", "SIGNO"}),
    (CARGO, {"CARGO", "CARGOS", "RETIRO", "RETIROS", "DEBITO", "DEBITOS", "DEBE", "SALIDA", "SALIDAS", "EGRESO",
             "EGRESOS", "DEBIT", "DEBITS", "WITHDRAWAL", "WITHDRAWALS", "GASTO", "GASTOS"}),
    (ABONO, {"ABONO", "ABONOS", "DEPOSITO", "DEPOSITOS", "CREDITO", "CREDITOS", "HABER", "ENTRADA", "ENTRADAS",
             "INGRESO", "INGRESOS", "CREDIT", "CREDITS", "DEPOSIT", "DEPOSITS"}),
    (IMPORTE, {"IMPORTE", "MONTO", "CANTIDAD", "AMOUNT", "VALOR", "TOTAL"}),
    (DESCRIPCION, {"DESCRIPCION", "CONCEPTO", "DETALLE", "MOVIMIENTO", "ESTABLECIMIENTO", "COMERCIO",
                   "DESCRIPTION", "NARRATIVA", "LEYENDA", "TRANSACCION", "OPERACION", "DETAILS", "MEMO",
                   "BENEFICIARIO", "NOMBRE", "PAYEE"}),
    (REFERENCIA, {"REFERENCIA", "REF", "FOLIO", "AUTORIZACION", "NUMERO", "RASTREO", "CLAVE"}),
)


def _rol(titulo: str) -> str | None:
    palabras = set(clave(titulo).split())
    for rol, conjunto in _PALABRAS:
        if palabras & conjunto:
            return rol
    return None


@dataclass(frozen=True, slots=True)
class Columnas:
    """Qué columna es cada cosa (índices desde 0). Con CARGO y ABONO separados, o un solo IMPORTE con signo
    (y opcionalmente una columna TIPO que dice si es cargo o abono)."""

    fecha: int
    descripcion: tuple[int, ...] = ()
    cargo: int | None = None
    abono: int | None = None
    importe: int | None = None
    tipo: int | None = None
    encabezado: int | None = None            # renglón de títulos (índice); None si la tabla no tiene
    saldo: int | None = None                 # si la trae: con él se sabe el signo de un importe con signo

    def __post_init__(self) -> None:
        if self.importe is None and self.cargo is None and self.abono is None:
            raise ErrorValidacion("Elige la columna del importe (o las de cargos y abonos).")


def titulos(tabla, columnas: Columnas | None) -> list[str]:
    """Nombre de cada columna para mostrarla: su título o «Columna N»."""
    ancho = max((len(f) for f in tabla), default=0)
    fila = tabla[columnas.encabezado] if columnas and columnas.encabezado is not None else ()
    return [(fila[i] if i < len(fila) and fila[i] else f"Columna {i + 1}") for i in range(ancho)]


def detectar(tabla) -> Columnas:
    """Busca el renglón de títulos (los bancos suelen poner antes el nombre, la cuenta y el periodo). Si no lo
    hay, decide por el contenido de cada columna."""
    for i, fila in enumerate(tabla[:60]):
        roles = [_rol(c) for c in fila]
        if FECHA in roles and ({CARGO, ABONO, IMPORTE} & set(roles)):
            return _por_titulos(tabla, i, roles)
    return _por_contenido(tabla)


def _por_titulos(tabla, encabezado: int, roles: list[str | None]) -> Columnas:
    fila = tabla[encabezado]
    cols = defaultdict(list)
    for i, rol in enumerate(roles):
        if rol:
            cols[rol].append(i)
    fechas = cols[FECHA]
    fecha = next((i for i in fechas if "OPER" in clave(fila[i]) or clave(fila[i]) == "FECHA"), fechas[0])
    descripcion = tuple(cols[DESCRIPCION][:3])
    if not descripcion:                                  # la columna de texto más larga que no sea otra cosa
        datos = tabla[encabezado + 1:encabezado + 201]
        libres = [i for i in range(len(fila)) if roles[i] is None]
        if libres:
            descripcion = (max(libres, key=lambda i: sum(len(re.sub(r"[^A-Za-z]", "", _en(f, i))) for f in datos)),)
    cargo = cols[CARGO][0] if cols[CARGO] else None
    abono = cols[ABONO][0] if cols[ABONO] else None
    importe = cols[IMPORTE][0] if cols[IMPORTE] else None
    if cargo is not None and abono is not None:
        importe = None
    elif importe is None:                                # solo «Cargo» o solo «Abono»: es un importe con signo
        importe, cargo, abono = cargo if cargo is not None else abono, None, None
    else:
        cargo = abono = None
    tipo = cols[TIPO][0] if cols[TIPO] and importe is not None else None
    saldo = cols[SALDO][0] if cols[SALDO] else None
    return Columnas(fecha, descripcion, cargo, abono, importe, tipo, encabezado, saldo)


def _en(fila, i: int) -> str:
    return fila[i] if i < len(fila) else ""


def _por_contenido(tabla) -> Columnas:
    muestra = tabla[:300]
    ancho = max((len(f) for f in muestra), default=0)
    llenas = {i: [f[i] for f in muestra if _en(f, i).strip()] for i in range(ancho)}
    orden = {i: _orden_de_fechas(v) for i, v in llenas.items()}

    def proporcion(i, prueba):
        valores = llenas[i]
        return sum(prueba(v) is not None for v in valores) / len(valores) if valores else 0

    fechas = [(proporcion(i, lambda v, i=i: leer_fecha(v, orden=orden[i])), -i) for i in range(ancho)]
    mejor, menos_i = max(fechas, default=(0, 0))
    if mejor < 0.6:
        raise ErrorValidacion("No encontré una columna con fechas. Revisa que el archivo tenga tus movimientos "
                              "(fecha, descripción e importe).")
    fecha = -menos_i
    numericas = [i for i in range(ancho) if i != fecha and len(llenas[i]) >= len(muestra) * 0.2
                 and proporcion(i, leer_importe) >= 0.8]
    if not numericas:
        raise ErrorValidacion("No encontré una columna con importes. Revisa que el archivo tenga tus movimientos.")
    cargo = abono = importe = None
    if len(numericas) >= 2:
        a, b = numericas[:2]
        ambas = sum(1 for f in muestra if _en(f, a).strip() and _en(f, b).strip())
        if ambas <= len(muestra) * 0.1:                  # una u otra: cargos y abonos
            cargo, abono = a, b
    if cargo is None:
        importe = numericas[0]
    sobrantes = [i for i in numericas if i not in (cargo, abono, importe)]
    texto = [i for i in range(ancho) if i != fecha and i not in numericas]
    descripcion = ((max(texto, key=lambda i: sum(len(re.sub(r"[^A-Za-z]", "", v)) for v in llenas[i])),)
                   if texto else ())
    return Columnas(fecha, descripcion, cargo, abono, importe, None, None, sobrantes[0] if sobrantes else None)


# ===================================================================== movimientos


@dataclass(frozen=True, slots=True)
class Movimiento:
    fila: int                 # renglón del archivo (desde 1), para los mensajes
    fecha: date
    descripcion: str
    centavos: int             # + entra (abono), − sale (cargo)
    supuesto: bool = False    # no se supo con certeza si entra o sale (PDF): revísalo
    del_resumen: bool = False  # no venía en la lista de movimientos: se tomó del resumen (intereses, IVA…)


@dataclass(frozen=True, slots=True)
class Lectura:
    movimientos: tuple[Movimiento, ...]
    columnas: Columnas | None = None             # None si se leyó como texto (PDF)
    cargos_negativos: bool | None = None         # solo con un importe con signo: cómo se entendió el signo
    omitidos: int = 0                            # renglones con fecha que no tenían un importe válido
    avisos: tuple[str, ...] = ()
    total_cargos: int | None = None              # lo que el propio estado de cuenta dice que suman (PDF)
    total_abonos: int | None = None
    saldo_inicial: int | None = None             # del resumen del estado de cuenta (PDF); en tarjetas, la deuda
    saldo_final: int | None = None
    credito: bool = False
    sueltos: tuple[tuple[int, str], ...] = ()    # renglones con importe que no parecieron movimientos (PDF)

    @property
    def falta(self) -> int | None:
        """Lo que no cuadra con los saldos del estado de cuenta (0 = cuadra; + falta que entre, − que salga).
        ``None`` si el estado de cuenta no trae los dos saldos."""
        if self.saldo_inicial is None or self.saldo_final is None:
            return None
        return (self.saldo_final - self.saldo_inicial) * (-1 if self.credito else 1) - (self.entra - self.sale)

    @property
    def entra(self) -> int:
        return sum(m.centavos for m in self.movimientos if m.centavos > 0)

    @property
    def sale(self) -> int:
        return -sum(m.centavos for m in self.movimientos if m.centavos < 0)

    @property
    def desde(self) -> date:
        return min(m.fecha for m in self.movimientos)

    @property
    def hasta(self) -> date:
        return max(m.fecha for m in self.movimientos)

    @property
    def supuestos(self) -> int:
        return sum(m.supuesto for m in self.movimientos)


def interpretar(fuente: Fuente, *, credito: bool = False, columnas: Columnas | None = None,
                cargos_negativos: bool | None = None, hoy: date | None = None) -> Lectura:
    """Los movimientos del archivo. ``credito``: si la cuenta es una tarjeta de crédito (en sus estados de cuenta,
    el saldo es lo que debes y un importe con signo de menos suele ser un pago)."""
    hoy = hoy or date.today()
    if fuente.es_tabla:
        lectura = _de_tabla(fuente.tabla, columnas or detectar(fuente.tabla), cargos_negativos, credito=credito)
    else:
        lectura = _de_texto_libre(fuente.texto, credito=credito, hoy=hoy)
    if not lectura.movimientos:
        raise ErrorValidacion(
            "No encontré movimientos. Revisa que el archivo traiga renglones con fecha, descripción e importe"
            + (" (si es un PDF, prueba con el archivo de Excel o CSV de tu banca en línea)." if fuente.es_pdf
               else "."))
    return lectura


def _de_tabla(tabla, columnas: Columnas, cargos_negativos: bool | None, *, credito: bool = False) -> Lectura:
    datos = list(enumerate(tabla, start=1))[(columnas.encabezado + 1) if columnas.encabezado is not None else 0:]
    orden = _orden_de_fechas(_en(f, columnas.fecha) for _, f in datos)
    numericas = [c for c in (columnas.cargo, columnas.abono, columnas.importe) if c is not None]
    decimal = {c: _decimal_de(_en(f, c) for _, f in datos if _en(f, c)) for c in numericas}
    crudos: list[tuple[int, date, str, int, int | None]] = []        # (fila, fecha, descripción, importe, signo)
    saldos: list[int | None] = []
    omitidos = 0
    for numero, fila in datos:
        fecha = leer_fecha(_en(fila, columnas.fecha), orden=orden)
        if fecha is None:
            continue                                                  # títulos repetidos, totales, notas
        descripcion = " ".join(" ".join(_en(fila, i) for i in columnas.descripcion).split())
        textos = {c: _en(fila, c).strip() for c in numericas}
        valores = {c: leer_importe(t, decimal=decimal[c]) for c, t in textos.items() if t}
        if any(v is None for v in valores.values()) or not valores:
            omitidos += bool(textos and any(textos.values()))           # un importe que no se entiende
            continue
        if columnas.importe is not None:
            importe = valores[columnas.importe]
            signo = _signo_de_tipo(_en(fila, columnas.tipo)) if columnas.tipo is not None else None
            if signo is not None:
                importe = abs(importe)
        else:
            importe = abs(valores.get(columnas.abono) or 0) - abs(valores.get(columnas.cargo) or 0)
            signo = 1
        if not importe:
            continue
        crudos.append((numero, fecha, descripcion, importe, signo))
        saldos.append(leer_importe(_en(fila, columnas.saldo)) if columnas.saldo is not None else None)
    if columnas.importe is not None and cargos_negativos is None:
        cargos_negativos = _signo_por_saldo(crudos, saldos, credito)
        if cargos_negativos is None:
            sin_tipo = [imp for *_, imp, signo in crudos if signo is None]
            negativos, positivos = sum(i < 0 for i in sin_tipo), sum(i > 0 for i in sin_tipo)
            if not negativos or not positivos:
                cargos_negativos = bool(negativos)        # todos del mismo signo: casi siempre son gastos
            else:
                # En una cuenta de banco, lo que sale va con menos. En una tarjeta varía: el signo que más se
                # repite es el de las compras.
                cargos_negativos = True if not credito else negativos >= positivos
    movimientos = []
    for numero, fecha, descripcion, importe, signo in crudos:
        if signo is None:
            signo = 1 if cargos_negativos else -1
        movimientos.append(Movimiento(numero, fecha, descripcion, importe * signo))
    usa_signo = columnas.importe is not None and columnas.tipo is None
    return Lectura(tuple(movimientos), columnas, cargos_negativos if usa_signo else None, omitidos)


def _signo_por_saldo(crudos, saldos, credito: bool) -> bool | None:
    """Con la columna de saldo se sabe con certeza: si el saldo cambia igual que el importe, el signo del importe
    es el del dinero (en una tarjeta, el saldo es lo que debes: al revés). Sirve en orden ascendente o
    descendente."""
    directos = inversos = 0
    for (a, b) in zip(range(len(crudos)), range(1, len(crudos))):
        sa, sb = saldos[a], saldos[b]
        if sa is None or sb is None:
            continue
        ia, ib = crudos[a][3], crudos[b][3]
        if sb - sa == ib or sa - sb == ia:
            directos += 1
        elif sb - sa == -ib or sa - sb == -ia:
            inversos += 1
    if directos == inversos:
        return None
    mismo_signo = directos > inversos        # el importe tiene el signo con que cambia el saldo
    sale_negativo = mismo_signo if not credito else not mismo_signo
    return sale_negativo


_TIPOS_SALE = ("CARGO", "RETIRO", "DEBITO", "DEBE", "SALIDA", "EGRESO", "GASTO", "DEBIT", "WITHDRAW", "COMPRA")
_TIPOS_ENTRA = ("ABONO", "DEPOSITO", "CREDITO", "HABER", "ENTRADA", "INGRESO", "CREDIT", "DEPOSIT")


def _signo_de_tipo(texto: str) -> int | None:
    k = clave(texto) or texto.strip()
    if k in ("D", "-") or k.startswith(_TIPOS_SALE):
        return -1
    if k in ("H", "A", "+") or k.startswith(_TIPOS_ENTRA):
        return 1
    return None                    # «C» puede ser cargo o crédito: mejor no adivinar


# ----------------------------------------------------------- texto sin columnas (PDF)

_FECHA_AL_INICIO = re.compile(
    r"^\s*(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
    r"|\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?"
    r"|\d{1,2}[\s/\-.]?[A-Za-zÁÉÍÓÚáéíóú]{3,10}\.?(?:[\s/\-.]\d{4}|[/\-.]\d{2}(?!\d))?)(?=\s|$)")
_UN_IMPORTE = r"[-\u2212(+]?\s?\$?\s?(?:\d{1,3}(?:[,.']\d{3})+|\d+)[.,]\d{2}\)?"
_IMPORTE_AL_FINAL = re.compile(rf"(?:^|\s)({_UN_IMPORTE}(?:-|\s?CR)?)\s*(?:MXN|USD|EUR|M\.?N\.?)?\s*$",
                               re.IGNORECASE)
_IMPORTE = re.compile(rf"(?<![\d.,])({_UN_IMPORTE})(?![\d])")
_NO_ES_MOVIMIENTO = ("PAGO MINIMO", "PAGO PARA NO GENERAR", "LIMITE DE CREDITO", "CREDITO DISPONIBLE",
                     "FECHA LIMITE", "FECHA DE CORTE", "PERIODO DEL")
_EMPIEZA_COMO_RESUMEN = ("SALDO", "SUBTOTAL", "TOTAL DE", "TOTAL CARGOS", "TOTAL ABONOS", "TOTAL IMPORTE",
                         "TOTAL A PAGAR", "TOTAL DEPOSITOS", "TOTAL RETIROS")
_SALDO_INICIAL = ("SALDO ANTERIOR", "SALDO INICIAL", "SALDO AL CORTE ANTERIOR", "SALDO REVOLVENTE ANTERIOR",
                  "ADEUDO ANTERIOR", "SALDO DEUDOR ANTERIOR", "SALDO DEL CORTE ANTERIOR")
_SALDO_FINAL = ("SALDO FINAL", "SALDO AL CORTE", "REVOLVENTE AL CORTE", "SALDO ACTUAL", "NUEVO SALDO",
                "SALDO DEUDOR TOTAL", "SALDO TOTAL", "ADEUDO TOTAL")
_TOTAL_CARGOS = ("TOTAL IMPORTE CARGOS", "TOTAL DE CARGOS", "TOTAL CARGOS", "TOTAL DE RETIROS", "TOTAL RETIROS",
                 "COMPRAS/RETIROS", "COMPRAS Y CARGOS", "COMPRAS Y DISPOSICIONES", "CARGOS DEL PERIODO",
                 "CARGOS REGULARES", "COMPRAS DEL PERIODO")
_TOTAL_ABONOS = ("TOTAL IMPORTE ABONOS", "TOTAL DE ABONOS", "TOTAL ABONOS", "TOTAL DE DEPOSITOS",
                 "TOTAL DEPOSITOS", "PAGOS/REEMBOLSOS", "PAGOS Y ABONOS", "PAGOS Y BONIFICACIONES",
                 "PAGOS Y CREDITOS", "ABONOS DEL PERIODO", "PAGOS DEL PERIODO")
# Cargos que algunas tarjetas solo ponen en el resumen, no en la lista de movimientos.
_CARGOS_DEL_RESUMEN = {"intereses": ("INTERESES", "INTERES ORDINARIO", "INTERESES ORDINARIOS"),
                       "comisiones": ("COMISIONES COBRADAS", "COMISIONES", "TOTAL COMISIONES"),
                       "iva": ("IVA", "I.V.A.")}
_NOMBRE_DEL_RESUMEN = {"intereses": "INTERESES", "comisiones": "COMISIONES", "iva": "IVA"}
_NO_ES_SUELTO = ("SALDO", "TOTAL", "PAGO MINIMO", "PAGO PARA NO GENERAR", "LIMITE", "CREDITO DISPONIBLE",
                 "INTERES", "COMISION", "IVA", "CAT", "TASA", "PROMEDIO", "GAT", "ISR", "PAGOS MENSUALES",
                 "COMPRAS", "PAGOS", "ABONOS", "CARGOS", "DEPOSITOS", "RETIROS", "RENDIMIENTO", "APROXIMAD",
                 "INFORMATIVO")
_FIN_DE_DETALLE = ("TOTAL", "SALDO", "PAGINA", "DETALLE", "FECHA", "RESUMEN", "ESTADO DE CUENTA", "PERIODO")
_PALABRAS_ENTRA = ("ABONO", "DEPOSITO", "DEP EFECTIVO", "RECIBID", "NOMINA", "SU PAGO", "GRACIAS", "DEVOLUCION",
                   "REEMBOLSO", "BONIFICACION", "CASHBACK", "INTERESES GANADOS", "RENDIMIENTO", "REVERSO",
                   "CANCELACION", "TRASPASO A FAVOR")
_PALABRAS_SALE = ("RETIRO", "ENVIAD", "COMPRA", "CARGO", "COMISION", "DOMICILIACION", "DISPOSICION", "PAGO DE SERV")
_MAXIMO_POR_TRAMO = 14          # renglones sin saldo entre dos saldos que se pueden resolver (2^14 combinaciones)


@dataclass(slots=True)
class _Renglon:
    fila: int
    fecha: date
    descripcion: str
    importes: list[str]
    detalle: list[str]


def _de_texto_libre(texto: str, *, credito: bool, hoy: date) -> Lectura:
    referencia = _fecha_de_referencia(texto, hoy)
    renglones: list[_Renglon] = []
    resumen: dict[str, int | None] = dict.fromkeys(("inicial", "final", "cargos", "abonos", *_CARGOS_DEL_RESUMEN))
    lineas_del_resumen: dict[str, int] = {}
    omitidos = 0
    sueltos: list[tuple[int, str]] = []
    actual: _Renglon | None = None
    for numero, crudo in enumerate(texto.splitlines(), start=1):
        linea = " ".join(crudo.split())
        if not linea:
            continue
        leido = _renglon(numero, linea, referencia)
        if isinstance(leido, _Renglon):
            renglones.append(leido)
            actual = leido
            continue
        omitidos += leido == "sin importe"
        if _suelto(linea, leido):
            sueltos.append((numero, linea))
        for llave, frases in (("inicial", _SALDO_INICIAL), ("final", _SALDO_FINAL), ("cargos", _TOTAL_CARGOS),
                              ("abonos", _TOTAL_ABONOS)):
            if resumen[llave] is None:
                resumen[llave] = _importe_despues(linea, frases)
        for llave, frases in _CARGOS_DEL_RESUMEN.items():
            if resumen[llave] is None and (importe := _importe_al_inicio(linea, frases)) is not None:
                resumen[llave], lineas_del_resumen[llave] = importe, numero
        k = clave(linea)
        if leido or _IMPORTE.search(linea) or any(k.startswith(p) or f" {p}" in f" {k}" for p in _FIN_DE_DETALLE):
            actual = None                                        # aquí termina el detalle del movimiento
        elif actual is not None and len(actual.detalle) < 3 and (extra := _detalle(linea)):
            actual.detalle.append(extra)

    montos, pistas = [], []
    for r in renglones:
        valores = [leer_importe(i) for i in r.importes]
        saldo = valores[1] if len(valores) >= 2 else None
        signo = (1 if credito else -1) if _marcado(r.importes[0]) else None     # «-850.00» o «850.00 CR»
        montos.append((abs(valores[0]), saldo, signo))
        pistas.append(_pista(r.descripcion, credito))
    seguros = _signos_por_saldo(montos, resumen["inicial"], resumen["final"], credito, pistas)

    movimientos = []
    for i, (r, (monto, _, signo)) in enumerate(zip(renglones, montos)):
        descripcion = " · ".join([r.descripcion, *r.detalle])
        seguro = signo is not None or i in seguros
        if i in seguros:
            signo = seguros[i]
        if signo is None:
            signo = 1 if pistas[i] > 0 else -1                   # sin pistas, lo más común: salió
        movimientos.append(Movimiento(r.fila, r.fecha, descripcion, monto * signo, supuesto=not seguro))
    lectura = Lectura(tuple(movimientos), None, None, omitidos, (), resumen["cargos"], resumen["abonos"],
                      resumen["inicial"], resumen["final"], credito)
    if lectura.falta and lectura.falta < 0 and movimientos:
        # Lo que falta para cuadrar, ¿son los intereses, comisiones o IVA del resumen? Se agregan para que los veas.
        candidatos = [(k, resumen[k]) for k in _CARGOS_DEL_RESUMEN if resumen[k]]
        for mascara in range(1, 1 << len(candidatos)):
            elegidos = [c for n, c in enumerate(candidatos) if mascara >> n & 1]
            if sum(monto for _, monto in elegidos) == -lectura.falta:
                corte = _fecha_de_corte(texto) or max(m.fecha for m in movimientos)
                movimientos += [Movimiento(lineas_del_resumen[k], corte, f"{_NOMBRE_DEL_RESUMEN[k]} DEL PERIODO",
                                           -monto, del_resumen=True) for k, monto in elegidos]
                break
    entra = sum(m.centavos for m in movimientos if m.centavos > 0)
    sale = -sum(m.centavos for m in movimientos if m.centavos < 0)
    lectura = Lectura(tuple(movimientos), None, None, omitidos, (), resumen["cargos"], resumen["abonos"],
                      resumen["inicial"], resumen["final"], credito)
    if lectura.falta is not None:
        verificado = lectura.falta == 0                          # cuadra con el saldo anterior y el del corte
    else:
        verificado = (resumen["cargos"] is not None or resumen["abonos"] is not None) and \
            resumen["cargos"] in (None, sale) and resumen["abonos"] in (None, entra)
    if verificado:                                               # si cuadra, los signos están bien
        movimientos = [replace(m, supuesto=False) for m in movimientos]
    avisos = [] if verificado else [
        "Leí este texto lo mejor que pude: revisa cada renglón y compara los totales con tu estado de cuenta."]
    if any(m.supuesto for m in movimientos):
        avisos.append("En los marcados con 🔍 no supe con certeza si el dinero entró o salió: cámbialo en la columna "
                      "«Movimiento» si hace falta.")
    return replace(lectura, movimientos=tuple(movimientos), avisos=tuple(avisos), sueltos=tuple(sueltos[:40]))


def _renglon(numero: int, linea: str, referencia: date) -> _Renglon | str | None:
    """Un movimiento («fecha … descripción … importe [saldo]»), "sin importe" si tiene fecha y texto pero no
    importe, o ``None`` si no es un movimiento."""
    resto, importes = linea, []
    while len(importes) < 4 and (m := _IMPORTE_AL_FINAL.search(resto)):
        importes.insert(0, m.group(1))
        resto = resto[:m.start()]
    fecha_txt = _FECHA_AL_INICIO.match(resto)
    if not fecha_txt or (fecha := _fecha_sin_anio(fecha_txt.group(1), referencia)) is None:
        return None
    resto = resto[fecha_txt.end():]
    if (otra := _FECHA_AL_INICIO.match(resto)) and _fecha_sin_anio(otra.group(1), referencia):
        resto = resto[otra.end():]                                      # fecha de liquidación
    descripcion = " ".join(resto.split())
    descripcion = re.sub(r"\b(RECIBID[OA]|ENVIAD[OA])(?=[A-Za-zÁÉÍÓÚÑáéíóúñ])", r"\1 ", descripcion,
                         flags=re.IGNORECASE)                    # «SPEI RECIBIDOBANCO» → «SPEI RECIBIDO BANCO»
    kd = clave(descripcion)
    if (not re.search(r"[A-Za-z]", descripcion) or kd.startswith(_EMPIEZA_COMO_RESUMEN)
            or any(f" {p} " in f" {kd} " for p in _NO_ES_MOVIMIENTO)):
        return None
    if not importes or not leer_importe(importes[0]):
        return "sin importe"
    return _Renglon(numero, fecha, descripcion, importes, [])


def _pista(descripcion: str, credito: bool) -> int:
    """+1 si las palabras dicen que el dinero entró (ABONO, RECIBIDO, NÓMINA…), −1 si salió (RETIRO, ENVIADO,
    COMPRA…), 0 si no dicen nada. En una tarjeta, un PAGO es dinero que entra."""
    k = f" {clave(descripcion)}"
    if any(f" {p}" in k for p in _PALABRAS_ENTRA) or (credito and " PAGO" in k):
        return 1
    if any(f" {p}" in k for p in _PALABRAS_SALE):
        return -1
    return 0


def _detalle(linea: str) -> str:
    """El concepto que el banco pone en los renglones de abajo (el comercio, para qué fue, quién te pagó),
    sin referencias, claves ni folios."""
    texto = re.split(r"\b(?:REFERENCIA|REF\.?|FOLIO|AUTORIZACION|AUT\.?|RASTREO|CLABE)\b", linea,
                     flags=re.IGNORECASE)[0]
    texto = re.sub(r"\b\d{4,}(?=[A-Za-zÁÉÍÓÚÑáéíóúñ])", "", texto)       # «0000000Concepto» → «Concepto»
    palabras = [w for w in texto.split() if sum(c.isalpha() for c in w) >= max(2, 0.7 * len(w))]
    limpio = " ".join(palabras)
    return limpio if sum(c.isalpha() for c in limpio) >= 5 else ""


def _plano(texto: str) -> str:
    """MAYÚSCULAS sin acentos, conservando números y signos (para buscar frases sin perder los importes)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if not unicodedata.combining(c))


def _importe_despues(linea: str, frases) -> int | None:
    """El primer importe que sigue a una frase («SALDO ANTERIOR 1,000.00»)."""
    plano = " ".join(_plano(linea).split())
    for frase in frases:
        inicio = 0
        while (i := plano.find(frase, inicio)) >= 0:
            inicio = i + len(frase)
            if frase == "SALDO AL CORTE" and plano[inicio:].startswith(" ANTERIOR"):
                continue
            if m := _IMPORTE.search(plano, inicio):
                return leer_importe(m.group(1))
    return None


def _suelto(linea: str, leido) -> bool:
    """¿Podría ser un movimiento que TALLY no entendió? Un renglón con fecha pero sin importe, o con un importe y
    texto que no es del resumen (saldos, totales, tasas). Se muestran al usuario si las cuentas no cuadran."""
    if leido == "sin importe":
        return True
    importes = [leer_importe(m.group(1)) for m in _IMPORTE.finditer(linea)]
    if "%" in linea or not any(importes) or not re.search(r"[A-Za-z]{3}", linea):
        return False                                             # sin importes, o solo en ceros
    k = f" {clave(linea)} "
    return not any(f" {p}" in k for p in _NO_ES_SUELTO)


def _importe_al_inicio(linea: str, frases) -> int | None:
    """El importe de un renglón del resumen que empieza con la frase («Intereses $ 12.30», «IVA $ 1.97»), no el
    de uno que solo la menciona («Pago para no generar intereses $ 1,234.56»)."""
    plano = " ".join(_plano(linea).split())
    for frase in frases:
        if plano.startswith(frase) and (m := re.match(rf"{re.escape(frase)}[^0-9%]{{0,25}}?\$?\s?({_UN_IMPORTE})",
                                                     plano)):
            return leer_importe(m.group(1))
    return None


def _fecha_de_corte(texto: str) -> date | None:
    """El día del corte: «Fecha de corte 03/10/2026» o el final de «del 04/09/2026 al 03/10/2026»."""
    plano = _plano(texto)
    fecha = r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}[\s/\-.][A-Z]{3,10}[\s/\-.]\d{2,4})"
    for patron in (rf"FECHA DE CORTE\s*:?\s*{fecha}", rf"\bDEL\s+{fecha}\s+AL\s+{fecha}"):
        if m := re.search(patron, plano):
            return leer_fecha(m.groups()[-1])
    return None


def _signos_por_saldo(montos, inicial: int | None, final: int | None, credito: bool,
                      pistas: list[int]) -> dict[int, int]:
    """Índice del renglón → signo, cuando los saldos lo dejan sin duda. Entre dos saldos conocidos, los
    importes con su signo deben sumar la diferencia: si solo una combinación lo cumple, es la buena. Si
    cuadran varias (p. ej. una nómina que se reparte completa en tres envíos), gana la única que no contradice
    las palabras del banco (NÓMINA entra, ENVIADO sale)."""
    factor = -1 if credito else 1                       # en una tarjeta, el saldo es lo que debes
    resueltos: dict[int, int] = {}
    previo, tramo = inicial, []

    def resolver(cierre: int) -> None:
        conocidos = sum(montos[i][0] * montos[i][2] for i in tramo if montos[i][2] is not None)
        dudosos = [i for i in tramo if montos[i][2] is None]
        objetivo = (cierre - previo) * factor - conocidos
        if not dudosos or len(dudosos) > _MAXIMO_POR_TRAMO:
            return
        soluciones = []
        for mascara in range(1 << len(dudosos)):
            suma = sum(montos[i][0] * (1 if mascara >> n & 1 else -1) for n, i in enumerate(dudosos))
            if suma == objetivo:
                soluciones.append(mascara)
        if len(soluciones) > 1:
            soluciones = [m for m in soluciones
                          if all(pistas[i] * (1 if m >> n & 1 else -1) >= 0 for n, i in enumerate(dudosos))]
        if len(soluciones) == 1:                        # una sola forma de cuadrar: sin duda
            for n, i in enumerate(dudosos):
                resueltos[i] = 1 if soluciones[0] >> n & 1 else -1

    for i, (_, saldo, _) in enumerate(montos):
        tramo.append(i)
        if saldo is None:
            continue
        if previo is not None:
            resolver(saldo)
        previo, tramo = saldo, []
    if tramo and previo is not None and final is not None:
        resolver(final)
    return resueltos


def _marcado(importe: str) -> bool:
    t = importe.strip()
    return t.startswith(("-", "\u2212", "(")) or t.endswith(("-", ")")) or t.upper().endswith("CR")


def _fecha_de_referencia(texto: str, hoy: date) -> date:
    """La fecha más reciente con año que aparece en el texto (el corte o el fin del periodo); si no hay, hoy."""
    fechas = []
    for m in re.finditer(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{2}-\d{2}"
                         r"|\d{1,2}[\s/\-.](?:de\s)?[A-Za-zÁÉÍÓÚáéíóú]{3,10}\.?[\s/\-.](?:de\s)?\d{4})\b", texto):
        f = leer_fecha(m.group(1).replace(" de ", " ").replace(" DE ", " "))
        if f and f <= hoy + timedelta(days=60):
            fechas.append(f)
    return max(fechas) if fechas else hoy


def _fecha_sin_anio(texto: str, referencia: date) -> date | None:
    fecha = leer_fecha(texto, anio=referencia.year)
    if fecha is None:
        return None
    if not re.search(r"\d{4}|[/\-.]\d{2}$", texto) and fecha > referencia + timedelta(days=31):
        fecha = fecha.replace(year=fecha.year - 1)                    # estado de cuenta de diciembre a enero
    return fecha


# ===================================================================== sugerencias y duplicados


@dataclass(frozen=True, slots=True)
class Propuesta:
    movimiento: Movimiento
    destino: str = ""                     # "sub:<id>", "cuenta:<id>" o "" (falta elegir)
    motivo: str = ""                      # por qué se sugirió (o qué falta)
    duplicado: Operacion | None = None    # el movimiento de TALLY que parece ser el mismo

    @property
    def cargar(self) -> bool:
        return self.duplicado is None


def destino_subcategoria(categoria_id: str) -> str:
    return f"sub:{categoria_id}"


def destino_cuenta(cuenta_id: str) -> str:
    return f"cuenta:{cuenta_id}"


def etiqueta_destino(libro: Libro, destino: str) -> str:
    tipo, _, ident = destino.partition(":")
    if tipo == "sub":
        return categorias.etiqueta(libro, ident)
    if tipo == "cuenta":
        return f"↔ {libro.cuenta(ident).nombre}"
    return ""


_RUIDO = {
    "COMPRA", "COMPRAS", "PAGO", "PAGOS", "CARGO", "CARGOS", "ABONO", "ABONOS", "TARJETA", "TDC", "TDD", "DEBITO",
    "CREDITO", "REF", "REFERENCIA", "AUT", "AUTORIZACION", "FOLIO", "SUC", "SUCURSAL", "MX", "MEX", "MEXICO",
    "CDMX", "DF", "SA", "CV", "DE", "DEL", "LA", "EL", "LOS", "LAS", "EN", "POR", "POS", "TPV", "WWW", "COM",
    "MXN", "USD", "NO", "NUM", "CON", "AL", "INT", "NAL", "VISA", "MASTERCARD", "MC", "AMEX", "OPERACION",
    "MOV", "CTA", "CUENTA", "FECHA", "HORA", "TRX", "TRANS", "PURCHASE", "ONLINE", "INTERNET", "SPEI", "ENVIADO",
    "ENVIADA", "RECIBIDO", "RECIBIDA", "ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV",
    "DIC", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE",
    "NOVIEMBRE", "DICIEMBRE",
}


def nucleo(descripcion: str) -> tuple[str, ...]:
    """Las palabras que identifican al comercio: sin números, referencias ni palabras de relleno.
    «COMPRA OXXO 1234 SUC CENTRO REF 998877» → («OXXO», «CENTRO»)."""
    return tuple(t for t in clave(descripcion).split()
                 if len(t) >= 2 and not any(c.isdigit() for c in t) and t not in _RUIDO)[:8]


@dataclass(frozen=True, slots=True)
class _Antecedente:
    palabras: frozenset[str]
    primera: str
    destino: str
    sentido: int
    fecha: date
    descripcion: str
    misma_cuenta: bool


class _Historial:
    """Lo que el usuario eligió antes para cada descripción: TALLY aprende de tus movimientos."""

    def __init__(self, libro: Libro, cuenta_id: str) -> None:
        self._por_palabra: dict[str, list[_Antecedente]] = defaultdict(list)
        validos_sub = {c.id for c in libro.categorias() if c.rubro_id and c.activa}
        validas_cuentas = {c.id for c in libro.cuentas() if c.activa and c.id != cuenta_id}
        for op in libro.operaciones():
            palabras = nucleo(op.descripcion) if op.descripcion else ()
            if not palabras:
                continue
            destino, sentido = _destino_de(op, cuenta_id)
            if not destino:
                continue
            tipo, _, ident = destino.partition(":")
            if ident not in (validos_sub if tipo == "sub" else validas_cuentas):
                continue
            misma = any(p.cuenta_id == cuenta_id for p in op.partidas)
            antecedente = _Antecedente(frozenset(palabras), palabras[0], destino, sentido, op.fecha,
                                       op.descripcion, misma)
            for palabra in set(palabras):
                self._por_palabra[palabra].append(antecedente)

    def sugerir(self, movimiento: Movimiento) -> tuple[str, str, bool] | None:
        """(destino, motivo, seguro). Seguro: la misma descripción, o casi (mismo comercio y la mayoría de las
        palabras); si no, es solo un parecido y un comercio conocido pesa más."""
        palabras = nucleo(movimiento.descripcion)
        if not palabras:
            return None
        sentido = 1 if movimiento.centavos > 0 else -1
        conjunto = frozenset(palabras)
        puntos: dict[str, float] = defaultdict(float)
        ejemplo: dict[str, _Antecedente] = {}
        vistos: set[int] = set()
        for palabra in conjunto:
            for a in self._por_palabra.get(palabra, ()):
                if id(a) in vistos or a.sentido != sentido:
                    continue
                vistos.add(id(a))
                parecido = len(conjunto & a.palabras) / len(conjunto | a.palabras)
                seguro = parecido == 1 or (a.primera == palabras[0] and parecido >= 0.5)
                if a.primera == palabras[0]:
                    parecido += 0.25
                if parecido < 0.5:
                    continue
                peso = parecido * (1.5 if a.misma_cuenta else 1.0) * (3 if seguro else 1)
                puntos[a.destino] += peso
                if a.destino not in ejemplo or (parecido, a.fecha) > (_parecido(ejemplo[a.destino], conjunto),
                                                                         ejemplo[a.destino].fecha):
                    ejemplo[a.destino] = a
        if not puntos:
            return None
        destino = max(puntos, key=lambda d: (puntos[d], ejemplo[d].fecha))
        a = ejemplo[destino]
        parecido = _parecido(a, conjunto)
        seguro = parecido == 1 or (a.primera == palabras[0] and parecido >= 0.5)
        return destino, (f"Como «{a.descripcion}» del {a.fecha:%d/%m/%Y}" if a.palabras == conjunto
                         else f"Parecido a «{a.descripcion}» del {a.fecha:%d/%m/%Y}"), seguro


def _parecido(a: _Antecedente, conjunto: frozenset[str]) -> float:
    return len(conjunto & a.palabras) / len(conjunto | a.palabras)


def _destino_de(op: Operacion, cuenta_id: str) -> tuple[str, int]:
    cuentas = op.partidas_de_cuenta()
    if op.tipo in (TipoOperacion.GASTO, TipoOperacion.INGRESO, TipoOperacion.REEMBOLSO, TipoOperacion.RENDIMIENTO):
        ids = {p.categoria_id for p in op.partidas_de_categoria()}
        total = sum(p.importe for p in cuentas)
        if len(ids) == 1 and total:
            return destino_subcategoria(ids.pop()), (1 if total > 0 else -1)
    elif op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        propia = [p for p in cuentas if p.cuenta_id == cuenta_id]
        otras = [p for p in cuentas if p.cuenta_id != cuenta_id]
        if propia and len(otras) == 1:
            return destino_cuenta(otras[0].cuenta_id), (1 if propia[0].importe > 0 else -1)
    return "", 0


# Comercios y palabras conocidas: (sentido, subcategoría del catálogo, patrones). El primero que coincide gana.
# Los patrones van en MAYÚSCULAS sin acentos ni signos; «*» al final acepta cualquier terminación.
_COMERCIOS = (
    (+1, "NOMINA", ("NOMINA", "SUELDO*", "SALARIO*", "PAYROLL")),
    (+1, "AGUINALDO", ("AGUINALDO",)),
    (+1, "DEVOLUCION DE IMPUESTOS", ("DEVOLUCION SAT", "SAT DEVOLUCION", "DEVOLUCION DE IMPUESTOS", "DEVOLUCION ISR")),
    (+1, "INTERESES Y RENDIMIENTOS", ("INTERES*", "RENDIMIENTO*")),
    (+1, "DIVIDENDOS", ("DIVIDENDO*",)),
    (+1, "CASHBACK Y RECOMPENSAS", ("CASHBACK", "CASH BACK", "BONIFICACION*", "RECOMPENSA*")),
    (-1, "COMIDA A DOMICILIO", ("UBER EATS", "UBEREATS", "DIDI FOOD", "DIDIFOOD", "RAPPI", "SIN DELANTAL",
                                "PEDIDOS YA", "PEDIDOSYA", "IFOOD")),
    (-1, "TAXI Y APPS DE VIAJE", ("UBER", "DIDI", "CABIFY", "INDRIVE")),
    (-1, "GASOLINA", ("PEMEX", "GASOLINERA*", "GASOLINERIA*", "SERVICIO GASOLINERO", "OXXO GAS", "G500", "SHELL",
                      "MOBIL", "REPSOL", "HIDROSINA", "PETRO SEVEN", "PETRO 7", "CHEVRON", "TERPEL", "YPF", "BP")),
    (-1, "SNACKS Y ANTOJOS", ("OXXO", "7 ELEVEN", "SEVEN ELEVEN", "7ELEVEN", "CIRCLE K")),
    (-1, "CAFETERIAS", ("STARBUCKS", "CIELITO QUERIDO", "PUNTA DEL CIELO", "ITALIAN COFFEE", "JUAN VALDEZ",
                        "TIM HORTONS", "CAFETERIA*")),
    (-1, "MEMBRESIAS", ("AMAZON PRIME", "AMZN PRIME", "MELI PLUS", "COSTCO MEMBRESIA*")),
    (-1, "GIMNASIO", ("SMART FIT", "SMARTFIT", "SPORTS WORLD", "GIMNASIO*", "GYM", "ANYTIME FITNESS")),
    (-1, "DESPENSA", ("WALMART", "WAL MART", "BODEGA AURRERA", "AURRERA", "SORIANA", "CHEDRAUI", "LA COMER",
                      "CITY MARKET", "FRESKO", "SUPERAMA", "HEB", "H E B", "COSTCO", "SAMS", "SAM S CLUB", "CASA LEY",
                      "CALIMAX", "ALSUPER", "MERZA", "MERCADONA", "CARREFOUR", "LIDL", "ALDI", "EXITO", "JUMBO",
                      "COTO", "OLIMPICA", "SUPERMERCADO*")),
    (-1, "RESTAURANTES", ("RESTAURANT*", "REST", "VIPS", "TOKS", "ITALIANNIS", "MCDONALD*", "MC DONALD*", "BURGER KING",
                          "KFC", "DOMINO*", "PIZZA*", "LITTLE CAESARS", "SUBWAY", "CARLS JR", "TAQUERIA*", "SUSHI*",
                          "WINGSTOP", "CHILIS", "APPLEBEES", "ALITAS*", "BONELESS*",
                          "HAMBURGUES*", "BURGER*")),
    (-1, "MEDICINAS Y FARMACIA", ("FARMACIA*", "BENAVIDES", "SAN PABLO", "FARMATODO", "CRUZ VERDE")),
    (-1, "ANALISIS Y ESTUDIOS", ("CHOPO", "SALUD DIGNA", "LABORATORIO*")),
    (-1, "DENTISTA", ("DENTAL", "DENTISTA")),
    (-1, "HOSPITAL", ("HOSPITAL*",)),
    (-1, "VETERINARIO", ("VETERINARI*",)),
    (-1, "ALIMENTO PARA MASCOTAS", ("PETCO", "MASKOTA")),
    (-1, "LUZ", ("CFE", "COMISION FEDERAL DE ELECTRICIDAD")),
    (-1, "AGUA", ("SACMEX", "SIAPA", "AGUA Y DRENAJE")),
    (-1, "GAS", ("GAS NATURAL", "NATURGY", "GAS LP", "ZETA GAS")),
    (-1, "INTERNET", ("TELMEX", "IZZI", "TOTALPLAY", "TOTAL PLAY", "MEGACABLE", "INFINITUM", "STARLINK")),
    (-1, "RECARGAS Y TELEFONIA", ("TELCEL", "AT T", "ATT", "MOVISTAR", "BAIT", "VIRGIN MOBILE", "RECARGA*")),
    (-1, "TV DE PAGA", ("SKY", "DISH", "DIRECTV")),
    (-1, "STREAMING DE VIDEO", ("NETFLIX", "DISNEY*", "HBO", "PRIME VIDEO", "VIX", "PARAMOUNT", "CRUNCHYROLL",
                                "YOUTUBE PREMIUM", "MUBI", "APPLE TV")),
    (-1, "MUSICA", ("SPOTIFY", "DEEZER", "APPLE MUSIC", "YOUTUBE MUSIC", "TIDAL")),
    (-1, "ALMACENAMIENTO EN LA NUBE", ("ICLOUD", "GOOGLE ONE", "DROPBOX", "GOOGLE STORAGE")),
    (-1, "SERVICIOS DE SOFTWARE", ("MICROSOFT", "ADOBE", "OPENAI", "CHATGPT", "ANTHROPIC", "CANVA", "GITHUB",
                                   "NOTION")),
    (-1, "VIDEOJUEGOS", ("STEAM", "STEAMGAMES", "PLAYSTATION", "PSN", "XBOX", "NINTENDO", "EPIC GAMES")),
    (-1, "COMPRAS EN LINEA", ("AMAZON", "AMZN", "MERCADO LIBRE", "MERCADOLIBRE", "SHEIN", "TEMU", "ALIEXPRESS")),
    (-1, "TIENDAS DEPARTAMENTALES", ("LIVERPOOL", "PALACIO DE HIERRO", "SEARS", "SUBURBIA", "COPPEL", "ELEKTRA",
                                     "SANBORNS", "CORTE INGLES", "FALABELLA", "RIPLEY", "WALDOS")),
    (-1, "CINE", ("CINEPOLIS", "CINEMEX", "CINEMARK", "CINE")),
    (-1, "TRANSPORTE PUBLICO", ("METRO", "METROBUS", "TREN", "MOVILIDAD INTEGRADA")),
    (-1, "CASETAS", ("CAPUFE", "IAVE", "PASE URBANO", "TELEVIA", "CASETA*", "AUTOPISTA*", "PEAJE*")),
    (-1, "ESTACIONAMIENTO", ("ESTACIONAMIENTO*", "PARKING", "PARQUIMETRO*")),
    (-1, "VUELOS", ("AEROMEXICO", "VOLARIS", "VIVA AEROBUS", "VIVAAEROBUS", "LATAM", "AVIANCA", "IBERIA",
                    "COPA AIRLINES", "AMERICAN AIRLINES")),
    (-1, "HOSPEDAJE", ("AIRBNB", "HOTEL*", "BOOKING")),
    (-1, "CURSOS Y CERTIFICACIONES", ("UDEMY", "COURSERA", "PLATZI", "DOMESTIKA")),
    (-1, "IDIOMAS", ("DUOLINGO",)),
    (-1, "LIBROS Y REVISTAS", ("GANDHI", "EL SOTANO", "LIBRERIA*", "KINDLE")),
    (-1, "PAPELERIA", ("OFFICE DEPOT", "OFFICEMAX", "LUMEN", "PAPELERIA*")),
    (-1, "HOGAR Y MANTENIMIENTO", ("HOME DEPOT", "COMEX", "SODIMAC", "LEROY MERLIN", "FERRETERIA*", "TLAPALERIA*")),
    (-1, "MUEBLES Y DECORACION", ("IKEA", "MUEBLERIA*")),
    (-1, "ROPA", ("ZARA", "H M", "PULL BEAR", "BERSHKA", "UNIQLO", "STRADIVARIUS")),
    (-1, "CALZADO", ("PRICE SHOES", "FLEXI", "ZAPATERIA*")),
    (-1, "CORTE DE CABELLO Y ESTETICA", ("BARBERIA*", "ESTETICA*", "PELUQUERIA*")),
    (-1, "LAVANDERIA Y TINTORERIA", ("LAVANDERIA*", "TINTORERIA*")),
    (-1, "DONATIVOS", ("DONATIVO*", "TELETON", "CRUZ ROJA", "UNICEF")),
    (-1, "RETIROS DE EFECTIVO", ("RETIRO CAJERO", "RETIRO EN CAJERO", "RETIRO DE EFECTIVO", "RETIRO EFECTIVO",
                                 "DISPOSICION DE EFECTIVO", "DISPOSICION EFECTIVO", "CAJERO*", "ATM")),
    (-1, "INTERESES DE TARJETAS", ("INTERES*",)),
    (-1, "COMISIONES BANCARIAS", ("COMISION*",)),
    (-1, "ANUALIDADES", ("ANUALIDAD*", "CUOTA ANUAL")),
    (-1, "IMPUESTOS", ("IVA", "ISR", "SAT")),
)
_REGLAS = tuple(
    (sentido, nombre, re.compile("|".join(
        r"(?<![A-Z0-9])" + re.escape(p.rstrip("*")) + (r"[A-Z]*" if p.endswith("*") else "") + r"(?![A-Z0-9])"
        for p in patrones)))
    for sentido, nombre, patrones in _COMERCIOS)
_DEVOLUCION = reglas_categorias.DEVOLUCION
_TRANSFERENCIA = re.compile(r"(?<![A-Z])(SPEI|TRASPASO|TRANSFERENCIA|TRANSF|PAGO TARJETA|PAGO TDC|SU PAGO)"
                            r"(?![A-Z])")


def _por_comercio(libro: Libro, movimiento: Movimiento) -> tuple[str, str] | None:
    texto = clave(movimiento.descripcion)
    sentido = 1 if movimiento.centavos > 0 else -1
    devolucion = sentido > 0 and _DEVOLUCION.search(texto)
    for regla_sentido, nombre, patron in _REGLAS:
        if regla_sentido != sentido and not (devolucion and regla_sentido < 0):
            continue
        if patron.search(texto):
            categoria = categorias.buscar(libro, nombre)
            if categoria is None or not categoria.activa:
                continue
            esperada = ClaseCategoria.INGRESO if regla_sentido > 0 else ClaseCategoria.GASTO
            if categoria.clase is not esperada:
                continue
            motivo = "Devolución: por el nombre del comercio" if regla_sentido != sentido else "Por el nombre del comercio"
            return destino_subcategoria(categoria.id), motivo
    return None


def _por_regla(reglas: reglas_categorias.Indice, movimiento: Movimiento, cuenta_id: str) -> tuple[str, str] | None:
    """Tus reglas automáticas (Categorías › Reglas automáticas) van primero: las pusiste tú."""
    regla = reglas.para_importe(movimiento.descripcion, movimiento.centavos, cuenta_id) if reglas else None
    return (destino_subcategoria(regla.categoria_id), reglas_categorias.motivo(regla)) if regla else None


def revisar(libro: Libro, cuenta_id: str, movimientos) -> list[Propuesta]:
    """Una propuesta por movimiento, en el mismo orden."""
    cuenta = libro.cuenta(cuenta_id)
    historial = _Historial(libro, cuenta_id)
    reglas = reglas_categorias.Indice(libro)
    duplicados = buscar_duplicados(libro, cuenta_id, movimientos)
    propuestas = []
    for i, m in enumerate(movimientos):
        antes = historial.sugerir(m)
        sugerencia = (_por_regla(reglas, m, cuenta_id) or (antes[:2] if antes and antes[2] else None)
                      or _por_comercio(libro, m) or (antes and antes[:2]))
        if sugerencia:
            destino, motivo = sugerencia
        elif _TRANSFERENCIA.search(clave(m.descripcion)):
            destino, motivo = "", ("¿Pagaste la tarjeta desde una de tus cuentas? Elígela."
                                   if cuenta.tipo is TipoCuenta.CREDITO and m.centavos > 0
                                   else "Si fue a una de tus cuentas, elígela; si no, en qué se gastó.")
        else:
            destino, motivo = "", "Falta elegir"
        propuestas.append(Propuesta(m, destino, motivo, duplicados.get(i)))
    return propuestas


def buscar_duplicados(libro: Libro, cuenta_id: str, movimientos) -> dict[int, Operacion]:
    """Índice del movimiento → la operación de TALLY que parece ser la misma: misma cuenta, mismo importe y a lo
    más :data:`DIAS_DE_TOLERANCIA` días de diferencia. Cada operación se empareja con un solo movimiento."""
    if not movimientos:
        return {}
    tolerancia = timedelta(days=DIAS_DE_TOLERANCIA)
    desde = min(m.fecha for m in movimientos) - tolerancia
    hasta = max(m.fecha for m in movimientos) + tolerancia
    por_importe: dict[int, list[Operacion]] = defaultdict(list)
    for op in libro.operaciones(desde, hasta):
        efecto = sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)
        if efecto:
            por_importe[efecto].append(op)
    usadas: set[str] = set()
    encontrados: dict[int, Operacion] = {}
    for i in sorted(range(len(movimientos)), key=lambda i: (movimientos[i].fecha, i)):
        m = movimientos[i]
        candidatas = [op for op in por_importe.get(m.centavos, ())
                      if op.id not in usadas and abs((op.fecha - m.fecha).days) <= DIAS_DE_TOLERANCIA]
        if candidatas:
            palabras = set(nucleo(m.descripcion))
            op = min(candidatas, key=lambda op: (abs((op.fecha - m.fecha).days),
                                                 -len(palabras & set(nucleo(op.descripcion)))))
            usadas.add(op.id)
            encontrados[i] = op
    return encontrados


def sin_reconocer(propuestas) -> list[list[int]]:
    """Los movimientos sin subcategoría sugerida, agrupados por descripción igual o casi igual (y sentido), del
    grupo más grande al más chico: para elegir una vez por grupo."""
    grupos: list[tuple[tuple[str, ...], bool, list[int]]] = []
    for i, p in enumerate(propuestas):
        if p.destino or not p.cargar:
            continue
        palabras, entra = nucleo(p.movimiento.descripcion), p.movimiento.centavos > 0
        grupo = next((g for g in grupos if g[1] == entra and (se_parecen(palabras, g[0]) or palabras == g[0])), None)
        if grupo is None:
            grupos.append((palabras, entra, [i]))
        else:
            grupo[2].append(i)
    return sorted((g[2] for g in grupos), key=lambda indices: (-len(indices), indices[0]))


def de_respaldo(libro: Libro, movimiento: Movimiento) -> str:
    """Para lo que quedó sin elegir: OTROS GASTOS (lo que sale) u OTROS INGRESOS (lo que entra)."""
    nombre = "OTROS INGRESOS" if movimiento.centavos > 0 else "OTROS GASTOS"
    categoria = categorias.buscar(libro, nombre)
    return destino_subcategoria(categoria.id) if categoria and categoria.activa else ""


def se_parecen(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Misma descripción, o casi: el mismo comercio (primera palabra) y la mayoría de las palabras."""
    if not a or not b:
        return False
    juntas, comunes = set(a) | set(b), set(a) & set(b)
    return set(a) == set(b) or (a[0] == b[0] and len(comunes) / len(juntas) >= 0.5)


def propagar(elegidos: list[tuple[Movimiento, str]]) -> list[tuple[Movimiento, str]]:
    """A los que quedaron sin elegir les pone lo que elegiste para otro con la misma descripción, o casi (y el
    mismo sentido: lo que sale con lo que sale)."""
    conocidos = [(nucleo(m.descripcion), m.centavos > 0, destino) for m, destino in elegidos if destino]
    resultado = []
    for m, destino in elegidos:
        if not destino:
            palabras, entra = nucleo(m.descripcion), m.centavos > 0
            destino = next((d for p, e, d in conocidos if e == entra and se_parecen(palabras, p)), "")
        resultado.append((m, destino))
    return resultado


# ===================================================================== cargar


def para_cargar(libro: Libro, cuenta_id: str, elegidos: list[tuple[Movimiento, str]]) -> tuple[Archivo,
                                                                                                 dict[str, Destino]]:
    """El archivo y el mapeo para :func:`motor.importacion.vista_previa` y :func:`motor.importacion.cargar`."""
    cuenta = libro.cuenta(cuenta_id)
    bloque = Bloque(0, cuenta.nombre)
    mapeo: dict[str, Destino] = {}
    faltan = [m.fila for m, destino in elegidos if not destino]
    if faltan:
        raise ErrorValidacion("Falta elegir la subcategoría o cuenta de los renglones "
                              + ", ".join(str(f) for f in faltan[:10]) + ("…" if len(faltan) > 10 else "") + ".")
    for m, destino in elegidos:
        tipo, _, ident = destino.partition(":")
        if tipo == "sub":
            nombre, resuelto = libro.categoria(ident).nombre, Destino.subcategoria(ident)
        elif tipo == "cuenta":
            if ident == cuenta_id:
                raise ErrorValidacion(f"Renglón {m.fila}: el dinero no puede ir a la misma cuenta.")
            nombre, resuelto = libro.cuenta(ident).nombre, Destino.cuenta(ident)
        else:
            raise ErrorValidacion(f"Renglón {m.fila}: destino no válido.")
        linea = Linea(m.fila, m.fecha, m.descripcion, f"{nombre} #{ident}", m.centavos)
        bloque.lineas.append(linea)
        mapeo[clave_destino(linea)] = resuelto
    return Archivo([bloque]), mapeo
