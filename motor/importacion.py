"""Carga masiva de movimientos desde un archivo de texto (la plantilla de TALLY).

Pensada para pasar a TALLY años de historial que ya estaban en Excel: se copian las columnas de Excel, se
pegan en la plantilla (Excel las separa con TAB) y se sube el archivo. Antes de guardar nada se ve una vista
previa; la carga es todo o nada.

Formato (ver :func:`plantilla`)::

    # comentarios (TALLY los ignora)
    CUENTA: Mi tarjeta de débito          ← empieza un bloque; si la cuenta no existe, se crea
    TIPO: DEBITO                          ← DEBITO, CREDITO, AHORRO, INVERSION, EFECTIVO, POR COBRAR, OTRA
    SALDO INICIAL: 2,000.00               ← solo si se crea la cuenta (en crédito: lo que se debía)
    FECHA  DESCRIPCION  SUBCATEGORIA  CARGO  ABONO  NOTAS
    15/07/2026  Súper  DESPENSA  850.00

Cómo se interpreta cada fila (las mismas reglas de siempre: nada cuenta dos veces):

========================================  =================================================
SUBCATEGORIA                              Resultado
========================================  =================================================
de gasto, en CARGO                        gasto
de gasto, en ABONO                        reembolso (resta del gasto)
de ingreso, en ABONO                      ingreso
de ingreso, en CARGO                      rendimiento negativo (p. ej. pérdida de inversión)
AJUSTE DE SALDO                           ajuste (no es ingreso ni gasto)
el nombre de otra cuenta propia           transferencia; pago de tarjeta si va a una de crédito
========================================  =================================================

- Una transferencia que aparece en los bloques de las dos cuentas se carga una sola vez.
- Lo que ya está en TALLY (misma fecha, tipo, cuentas, subcategorías e importes) no se vuelve a cargar: subir el
  mismo archivo dos veces no duplica nada.
- Los nombres se comparan sin importar mayúsculas, acentos, signos ni espacios.
- Lo que no se reconoce se resuelve con un *mapeo*: a una subcategoría o cuenta existente, o a una subcategoría
  nueva dentro de la categoría elegida.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from motor import categorias, cuentas, temporales
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorTally, ErrorValidacion
from motor.libro import Libro
from motor.modelo import (
    CATEGORIA_AJUSTE,
    CATEGORIA_SALDO_INICIAL,
    ClaseCategoria,
    Cuenta,
    Operacion,
    TipoCuenta,
    TipoOperacion,
)
from motor.movimientos import construir, construir_con_signo
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.textos import clave
from motor.transferencias import construir_transferencia

COLUMNAS = ("FECHA", "DESCRIPCION", "SUBCATEGORIA", "CARGO", "ABONO", "NOTAS")
_ALIAS_COLUMNAS = {
    "FECHA": "FECHA", "DIA": "FECHA",
    "DESCRIPCION": "DESCRIPCION", "CONCEPTO": "DESCRIPCION",
    "SUBCATEGORIA": "SUBCATEGORIA", "CATEGORIA": "SUBCATEGORIA", "SUBCATEGORIA O CUENTA": "SUBCATEGORIA",
    "CARGO": "CARGO", "CARGOS": "CARGO", "RETIRO": "CARGO", "RETIROS": "CARGO", "SALIDA": "CARGO",
    "ABONO": "ABONO", "ABONOS": "ABONO", "DEPOSITO": "ABONO", "DEPOSITOS": "ABONO", "ENTRADA": "ABONO",
    "NOTAS": "NOTAS", "NOTA": "NOTAS",
}
_ENCABEZADOS = {"CUENTA": "cuenta", "TIPO": "tipo", "TIPO DE CUENTA": "tipo", "SALDO INICIAL": "saldo",
                "DEUDA INICIAL": "saldo"}
TIPOS_DE_CUENTA = {
    "DEBITO": TipoCuenta.DEBITO, "TARJETA DE DEBITO": TipoCuenta.DEBITO, "TDD": TipoCuenta.DEBITO,
    "CUENTA DE DEBITO": TipoCuenta.DEBITO, "CREDITO": TipoCuenta.CREDITO, "TARJETA DE CREDITO": TipoCuenta.CREDITO,
    "TDC": TipoCuenta.CREDITO, "AHORRO": TipoCuenta.AHORRO, "CUENTA DE AHORRO": TipoCuenta.AHORRO,
    "INVERSION": TipoCuenta.INVERSION, "CUENTA DE INVERSION": TipoCuenta.INVERSION,
    "EFECTIVO": TipoCuenta.EFECTIVO, "POR COBRAR": TipoCuenta.POR_COBRAR, "OTRA": TipoCuenta.OTRA,
}
SIN_SUBCATEGORIA = {-1: "(SIN SUBCATEGORIA EN CARGOS)", 1: "(SIN SUBCATEGORIA EN ABONOS)"}
_MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9,
          "OCT": 10, "NOV": 11, "DIC": 12, "JAN": 1, "APR": 4, "AUG": 8, "DEC": 12}

# Estado de cada fila en la vista previa.
NUEVO, YA_ESTABA, CONTRAPARTE, PENDIENTE, ERROR = "nuevo", "ya_estaba", "contraparte", "pendiente", "error"


# ===================================================================== lectura


@dataclass(frozen=True, slots=True)
class Linea:
    numero: int            # renglón del archivo (desde 1), para los mensajes
    fecha: date
    descripcion: str
    destino: str           # lo escrito en SUBCATEGORIA (subcategoría o cuenta)
    centavos: int          # positivo: abono (entra); negativo: cargo (sale)
    notas: str = ""


@dataclass(slots=True)
class Bloque:
    numero: int
    cuenta: str
    tipo: TipoCuenta | None = None
    saldo_inicial: int | None = None   # centavos; en crédito, lo que se debía
    lineas: list[Linea] = field(default_factory=list)


@dataclass(slots=True)
class Archivo:
    bloques: list[Bloque] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    @property
    def lineas(self) -> int:
        return sum(len(b.lineas) for b in self.bloques)


def decodificar(datos: bytes) -> str:
    """El Bloc de notas guarda en UTF-8; versiones viejas de Windows, en ANSI (cp1252)."""
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1")


def leer(texto: str) -> Archivo:
    """Separa el texto en bloques de cuenta y filas, sin consultar los datos de TALLY."""
    archivo = Archivo()
    bloque: Bloque | None = None
    columnas: tuple[str, ...] = COLUMNAS
    separador: str | None = None
    for numero, crudo in enumerate(texto.splitlines(), start=1):
        renglon = crudo.strip()
        if not renglon or renglon.startswith("#") or not renglon.strip("\t;|, "):
            continue
        encabezado = _encabezado(renglon)
        if encabezado is not None:
            campo, valor = encabezado
            if campo == "cuenta":
                if not valor:
                    archivo.errores.append(f"Línea {numero}: escribe el nombre de la cuenta después de «CUENTA:».")
                    bloque = None
                    continue
                bloque = Bloque(numero, " ".join(valor.split()))
                archivo.bloques.append(bloque)
            elif bloque is None:
                archivo.errores.append(f"Línea {numero}: «{renglon}» debe ir después de «CUENTA:».")
            elif campo == "tipo":
                if valor:
                    tipo = TIPOS_DE_CUENTA.get(clave(valor))
                    if tipo is None:
                        archivo.errores.append(
                            f"Línea {numero}: tipo de cuenta «{valor}» no reconocido. Usa DEBITO, CREDITO, AHORRO, "
                            "INVERSION, EFECTIVO, POR COBRAR u OTRA.")
                    bloque.tipo = tipo
            elif campo == "saldo" and valor:
                try:
                    bloque.saldo_inicial = _importe(valor)
                except ErrorValidacion as error:
                    archivo.errores.append(f"Línea {numero}: saldo inicial: {error}")
            continue

        separador = _separador(crudo) or separador or "\t"
        celdas = [c.strip() for c in crudo.split(separador)]
        nombres = tuple(_ALIAS_COLUMNAS.get(clave(c), "") for c in celdas)
        if "FECHA" in nombres and len(set(nombres) - {""}) >= 3:     # la fila de títulos, en cualquier orden
            columnas = nombres
            faltan = {"FECHA", "SUBCATEGORIA", "CARGO", "ABONO"} - set(columnas)
            if faltan:
                archivo.errores.append(f"Línea {numero}: faltan las columnas {', '.join(sorted(faltan))}.")
            continue
        if bloque is None:
            archivo.errores.append(f"Línea {numero}: antes de los movimientos escribe «CUENTA: <nombre de la cuenta>».")
            continue
        try:
            bloque.lineas.append(_fila(numero, dict(zip(columnas, celdas))))
        except ErrorValidacion as error:
            archivo.errores.append(f"Línea {numero}: {error}")
    if not archivo.bloques and not archivo.errores:
        archivo.errores.append("El archivo no tiene ninguna cuenta. Usa la plantilla de TALLY.")
    for b in archivo.bloques:
        if not b.lineas:
            archivo.errores.append(f"Línea {b.numero}: la cuenta «{b.cuenta}» no tiene movimientos.")
    return archivo


def _encabezado(renglon: str) -> tuple[str, str] | None:
    coincide = re.match(r"^([^:\t;|]{3,30}):(.*)$", renglon)
    if not coincide:
        return None
    campo = _ENCABEZADOS.get(clave(coincide.group(1)))
    if campo is None:
        return None
    return campo, coincide.group(2).strip(" \t;|")


def _separador(renglon: str) -> str | None:
    for separador in ("\t", ";", "|"):
        if separador in renglon:
            return separador
    return None


def _fila(numero: int, celdas: dict[str, str]) -> Linea:
    fecha = leer_fecha(celdas.get("FECHA", ""))
    cargo, abono = celdas.get("CARGO", ""), celdas.get("ABONO", "")
    cargo_c = _importe(cargo) if cargo.strip() else 0
    abono_c = _importe(abono) if abono.strip() else 0
    if cargo_c and abono_c:
        raise ErrorValidacion("llena CARGO o ABONO, no los dos.")
    centavos = abono_c - cargo_c          # un cargo con signo de menos se toma como abono, y al revés
    if centavos == 0:
        raise ErrorValidacion("falta el importe (CARGO o ABONO).")
    return Linea(numero, fecha, " ".join(celdas.get("DESCRIPCION", "").split()),
                 " ".join(celdas.get("SUBCATEGORIA", "").split()), centavos, celdas.get("NOTAS", "").strip())


def leer_fecha(texto: str) -> date:
    """15/07/2026, 15-07-26, 2026-07-15, 15/jul/2026 o 15/07/2026 00:00 (día primero, como en México)."""
    original = texto
    texto = texto.strip().split(" ")[0].split("T")[0]
    partes = re.split(r"[/\-.]", texto)
    try:
        if len(partes) == 3:
            if len(partes[0]) == 4:
                anio, mes, dia = partes
            else:
                dia, mes, anio = partes
            mes_n = _MESES.get(clave(mes)[:3]) if not mes.isdigit() else int(mes)
            anio_n = int(anio)
            if anio_n < 100:
                anio_n += 2000
            if mes_n:
                return date(anio_n, mes_n, int(dia))
    except ValueError:
        pass
    raise ErrorValidacion(f"fecha «{original.strip()}» no válida (usa día/mes/año, por ejemplo 15/07/2026).")


def _importe(texto: str) -> int:
    """$1,234.50 · 1234.5 · (150.00) · -150 · 1 234,50 → centavos con signo."""
    limpio = texto.strip().replace("$", "").replace("MXN", "").replace(" ", "").replace(" ", "")
    negativo = limpio.startswith("-") or (limpio.startswith("(") and limpio.endswith(")"))
    limpio = limpio.strip("-()+")
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(",", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", limpio) else limpio.replace(",", "")
    try:
        valor = Decimal(limpio)
    except InvalidOperation:
        raise ErrorValidacion(f"importe «{texto.strip()}» no válido.") from None
    centavos = a_centavos(valor)
    return -centavos if negativo else centavos


# ===================================================================== interpretación


@dataclass(frozen=True, slots=True)
class Destino:
    """A qué corresponde un nombre que TALLY no reconoció."""

    tipo: str                 # "subcategoria", "cuenta" o "nueva"
    id: str = ""              # subcategoría o cuenta existente; para "nueva", la categoría (rubro) donde se crea

    @classmethod
    def subcategoria(cls, categoria_id: str) -> Destino:
        return cls("subcategoria", categoria_id)

    @classmethod
    def cuenta(cls, cuenta_id: str) -> Destino:
        return cls("cuenta", cuenta_id)

    @classmethod
    def nueva(cls, rubro_id: str) -> Destino:
        return cls("nueva", rubro_id)


@dataclass(frozen=True, slots=True)
class Desconocido:
    """Un nombre de la columna SUBCATEGORIA que no es subcategoría ni cuenta."""

    clave: str
    nombre: str
    filas: int
    cargos: int
    abonos: int

    @property
    def sugerencia(self) -> ClaseCategoria:
        return ClaseCategoria.INGRESO if self.abonos > self.cargos else ClaseCategoria.GASTO


def clave_destino(linea: Linea) -> str:
    """Con qué clave se agrupa lo escrito en SUBCATEGORIA (las vacías, separadas en cargos y abonos)."""
    return clave(linea.destino) or clave(SIN_SUBCATEGORIA[1 if linea.centavos > 0 else -1])


def desconocidos(libro: Libro, archivo: Archivo) -> list[Desconocido]:
    """Nombres que hay que resolver (mapear) antes de cargar, del más usado al menos usado."""
    conocidos = set(_cuentas_por_clave(libro, archivo)) | {clave(c.nombre) for c in libro.categorias()}
    conocidos.add(clave(temporales.NOMBRE_CUENTA))      # se crea sola al cargar
    cuenta: dict[str, list[Linea]] = defaultdict(list)
    for bloque in archivo.bloques:
        for linea in bloque.lineas:
            k = clave_destino(linea)
            if k not in conocidos:
                cuenta[k].append(linea)
    resultado = [
        Desconocido(k, lineas[0].destino.upper() if lineas[0].destino else SIN_SUBCATEGORIA[
            1 if lineas[0].centavos > 0 else -1], len(lineas), sum(ln.centavos < 0 for ln in lineas),
            sum(ln.centavos > 0 for ln in lineas))
        for k, lineas in cuenta.items()
    ]
    return sorted(resultado, key=lambda d: (-d.filas, d.nombre))


@dataclass(frozen=True, slots=True)
class Fila:
    """Una fila de la vista previa."""

    numero: int
    cuenta: str
    fecha: date
    descripcion: str
    tipo: TipoOperacion | None
    destino: str            # «SALUD › DENTISTA» o el nombre de la otra cuenta
    monto: Decimal          # siempre positivo
    sentido: str            # "-" sale, "+" entra, "↔" transferencia
    estado: str             # NUEVO, YA_ESTABA, CONTRAPARTE o ERROR
    detalle: str = ""


@dataclass(slots=True)
class Resultado:
    filas: list[Fila] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    cuentas_nuevas: list[str] = field(default_factory=list)
    subcategorias_nuevas: list[str] = field(default_factory=list)
    pendientes: list[Desconocido] = field(default_factory=list)

    @property
    def nuevos(self) -> int:
        return sum(f.estado == NUEVO for f in self.filas)

    def contar(self, estado: str) -> int:
        return sum(f.estado == estado for f in self.filas)

    @property
    def se_puede_cargar(self) -> bool:
        return not self.errores and not self.pendientes and self.contar(ERROR) == 0 and self.nuevos > 0


def vista_previa(libro: Libro, archivo: Archivo, mapeo: dict[str, Destino] | None = None) -> Resultado:
    """Qué pasaría al cargar, sin tocar los datos (trabaja sobre una copia del libro)."""
    copia = libro_desde_instantanea(instantanea(libro), libro.secuencia, reloj=libro.reloj)
    return _cargar_en(copia, archivo, mapeo or {})


def cargar(libro: Libro, archivo: Archivo, mapeo: dict[str, Destino] | None = None) -> Resultado:
    """Carga todo en el libro (úsese dentro de ``sesion.cambio()``). Si algo no se puede cargar, lanza
    ``ErrorValidacion`` con el detalle y, como es dentro de la sesión, no se guarda nada."""
    resultado = _cargar_en(libro, archivo, mapeo or {})
    problemas = resultado.errores + [f"Línea {f.numero}: {f.detalle}" for f in resultado.filas if f.estado == ERROR]
    if resultado.pendientes:
        problemas.append("Falta decidir a qué corresponde: " + ", ".join(d.nombre for d in resultado.pendientes))
    if problemas:
        raise ErrorValidacion("No se cargó nada. " + " ".join(problemas[:5]))
    return resultado


def _cargar_en(libro: Libro, archivo: Archivo, mapeo: dict[str, Destino]) -> Resultado:
    resultado = Resultado(errores=list(archivo.errores))
    sin_reconocer = desconocidos(libro, archivo)
    resultado.pendientes = [d for d in sin_reconocer if d.clave not in mapeo]

    _preparar_por_recuperar(libro, archivo, resultado)
    cuentas_por_nombre = _preparar_cuentas(libro, archivo, resultado)
    nombres = {d.clave: d.nombre for d in sin_reconocer}
    destinos = _preparar_destinos(libro, {k: v for k, v in mapeo.items() if k in nombres}, nombres, resultado)

    lineas = sorted(((b, ln) for b in archivo.bloques for ln in b.lineas), key=lambda bl: (bl[1].fecha, bl[1].numero))
    propuestas: list[tuple[Bloque, Linea, Operacion | None, str]] = []
    for bloque, linea in lineas:
        cuenta = cuentas_por_nombre.get(clave(bloque.cuenta))
        if cuenta is None:
            continue                                   # el error de la cuenta ya quedó anotado
        try:
            op = _operacion(libro, cuenta, linea, cuentas_por_nombre, destinos)
            propuestas.append((bloque, linea, op, ""))
        except _Pendiente:
            propuestas.append((bloque, linea, None, PENDIENTE))
        except ErrorTally as error:
            propuestas.append((bloque, linea, None, str(error)))

    existentes = Counter(_firma(op) for op in libro.operaciones())
    lado_principal = _lados_principales(propuestas)
    vistas: Counter = Counter()
    for bloque, linea, op, error in propuestas:
        fila = dict(numero=linea.numero, cuenta=bloque.cuenta, fecha=linea.fecha, descripcion=linea.descripcion,
                    monto=a_pesos(abs(linea.centavos)), sentido="+" if linea.centavos > 0 else "-")
        if op is None:
            if error == PENDIENTE:
                resultado.filas.append(Fila(**fila, tipo=None, destino=linea.destino.upper(), estado=PENDIENTE,
                                            detalle="falta decidir a qué corresponde"))
            else:
                resultado.filas.append(Fila(**fila, tipo=None, destino=linea.destino.upper(), estado=ERROR,
                                            detalle=error))
            continue
        firma = _firma(op)
        destino = _describir_destino(libro, op, cuenta_id=cuentas_por_nombre[clave(bloque.cuenta)].id)
        es_transferencia = op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA)
        if es_transferencia:
            fila["sentido"] = "↔"
        if es_transferencia and lado_principal[firma] != clave(bloque.cuenta):
            resultado.filas.append(Fila(**fila, tipo=op.tipo, destino=destino, estado=CONTRAPARTE,
                                        detalle="la misma transferencia viene en la otra cuenta; se carga una vez"))
            continue
        vistas[firma] += 1
        if vistas[firma] <= existentes[firma]:
            resultado.filas.append(Fila(**fila, tipo=op.tipo, destino=destino, estado=YA_ESTABA,
                                        detalle="ya estaba en TALLY; no se duplica"))
            continue
        try:
            libro.agregar_operacion(op)
            resultado.filas.append(Fila(**fila, tipo=op.tipo, destino=destino, estado=NUEVO))
        except ErrorTally as error:
            resultado.filas.append(Fila(**fila, tipo=op.tipo, destino=destino, estado=ERROR, detalle=str(error)))
    resultado.filas.sort(key=lambda f: f.numero)
    return resultado


class _Pendiente(Exception):
    """La fila usa un nombre que todavía no se ha mapeado."""


def _cuentas_por_clave(libro: Libro, archivo: Archivo) -> dict[str, str]:
    """Clave → nombre, de las cuentas existentes y de las que el archivo va a crear."""
    nombres = {clave(c.nombre): c.nombre for c in libro.cuentas()}
    for bloque in archivo.bloques:
        nombres.setdefault(clave(bloque.cuenta), bloque.cuenta)
    return nombres


def _preparar_por_recuperar(libro: Libro, archivo: Archivo, resultado: Resultado) -> None:
    """Si el archivo usa POR RECUPERAR (cargos temporales) y la cuenta no existe, la crea."""
    k = clave(temporales.NOMBRE_CUENTA)
    fechas = [ln.fecha for b in archivo.bloques for ln in b.lineas if clave_destino(ln) == k]
    if not fechas or k in {clave(b.cuenta) for b in archivo.bloques}:
        return
    nueva = temporales.cuenta(libro) is None
    try:
        cuenta = temporales.asegurar_cuenta(libro, min(fechas))
    except ErrorTally as error:
        resultado.errores.append(str(error))
        return
    if nueva:
        resultado.cuentas_nuevas.append(cuenta.nombre)


def _preparar_cuentas(libro: Libro, archivo: Archivo, resultado: Resultado) -> dict[str, Cuenta]:
    existentes = {clave(c.nombre): c for c in libro.cuentas()}
    por_clave: dict[str, Cuenta] = {}
    bloques_por_cuenta: dict[str, list[Bloque]] = defaultdict(list)
    for bloque in archivo.bloques:
        bloques_por_cuenta[clave(bloque.cuenta)].append(bloque)
    for k, bloques in bloques_por_cuenta.items():
        tipos = {b.tipo for b in bloques if b.tipo is not None}
        nombre = bloques[0].cuenta
        if len(tipos) > 1:
            resultado.errores.append(f"La cuenta «{nombre}» aparece con tipos distintos.")
            continue
        cuenta = existentes.get(k)
        if cuenta is not None:
            if tipos and cuenta.tipo not in tipos:
                resultado.errores.append(
                    f"Línea {bloques[0].numero}: «{cuenta.nombre}» ya existe en TALLY y no es de ese tipo.")
                continue
            por_clave[k] = cuenta
            continue
        if not tipos:
            resultado.errores.append(
                f"Línea {bloques[0].numero}: «{nombre}» no existe en TALLY; escribe su TIPO para crearla.")
            continue
        (tipo,) = tipos
        saldo = next((b.saldo_inicial for b in bloques if b.saldo_inicial), 0)
        primera = min((ln.fecha for b in bloques for ln in b.lineas), default=libro.hoy())
        try:
            if tipo is TipoCuenta.CREDITO:
                cuenta = cuentas.crear(libro, nombre, tipo, deuda_inicial=a_pesos(saldo) if saldo else None,
                                       fecha_creacion=primera)
            else:
                cuenta = cuentas.crear(libro, nombre, tipo, saldo_inicial=a_pesos(saldo), fecha_creacion=primera)
        except ErrorTally as error:
            resultado.errores.append(f"Línea {bloques[0].numero}: {error}")
            continue
        por_clave[k] = cuenta
        resultado.cuentas_nuevas.append(cuenta.nombre)
    return por_clave


def _preparar_destinos(libro: Libro, mapeo: dict[str, Destino], nombres: dict[str, str],
                       resultado: Resultado) -> dict[str, Destino]:
    """Valida el mapeo y crea las subcategorías nuevas. Devuelve clave → destino ya resuelto."""
    resueltos: dict[str, Destino] = {}
    for k, destino in mapeo.items():
        try:
            if destino.tipo == "nueva":
                if nombres[k] in SIN_SUBCATEGORIA.values():
                    raise ErrorValidacion("elige una subcategoría existente para las filas sin subcategoría.")
                nueva = categorias.crear(libro, nombres[k], destino.id)
                resultado.subcategorias_nuevas.append(categorias.etiqueta(libro, nueva.id))
                resueltos[k] = Destino.subcategoria(nueva.id)
            elif destino.tipo == "subcategoria":
                libro.categoria(destino.id)
                resueltos[k] = destino
            elif destino.tipo == "cuenta":
                libro.cuenta(destino.id)
                resueltos[k] = destino
            else:
                raise ErrorValidacion("destino no válido.")
        except ErrorTally as error:
            resultado.errores.append(f"«{nombres[k]}»: {error}")
    return resueltos


def _operacion(libro: Libro, cuenta: Cuenta, linea: Linea, cuentas_por_nombre: dict[str, Cuenta],
               destinos: dict[str, Destino]) -> Operacion:
    k = clave_destino(linea)
    otra = cuentas_por_nombre.get(k) if clave(linea.destino) else None
    if otra is None and (encontrada := next((c for c in libro.cuentas() if clave(c.nombre) == k), None)):
        otra = encontrada
    categoria = None
    if otra is None:
        categoria = next((c for c in libro.categorias() if clave(c.nombre) == k), None) if clave(linea.destino) else None
        if categoria is None:
            destino = destinos.get(k)
            if destino is None:
                raise _Pendiente()
            if destino.tipo == "cuenta":
                otra = libro.cuenta(destino.id)
            else:
                categoria = libro.categoria(destino.id)

    centavos, monto = linea.centavos, a_pesos(abs(linea.centavos))
    if otra is not None:
        if otra.id == cuenta.id:
            raise ErrorValidacion("la cuenta de destino es la misma cuenta del bloque.")
        origen, destino = (cuenta, otra) if centavos < 0 else (otra, cuenta)
        tipo = (TipoOperacion.PAGO_TARJETA if destino.tipo is TipoCuenta.CREDITO and origen.tipo is not TipoCuenta.CREDITO
                else TipoOperacion.TRANSFERENCIA)
        return construir_transferencia(linea.fecha, origen.id, destino.id, monto, linea.descripcion, linea.notas,
                                       tipo=tipo)
    if categoria.id == CATEGORIA_SALDO_INICIAL:
        raise ErrorValidacion("el saldo inicial va en el encabezado («SALDO INICIAL:»), no como movimiento.")
    if categoria.id == CATEGORIA_AJUSTE:
        return construir_con_signo(TipoOperacion.AJUSTE, linea.fecha, cuenta.id, categoria.id, a_pesos(centavos),
                                   linea.descripcion, linea.notas)
    if categoria.clase is ClaseCategoria.GASTO:
        tipo = TipoOperacion.GASTO if centavos < 0 else TipoOperacion.REEMBOLSO
        return construir(tipo, linea.fecha, cuenta.id, categoria.id, monto, linea.descripcion, linea.notas)
    if centavos > 0:
        return construir(TipoOperacion.INGRESO, linea.fecha, cuenta.id, categoria.id, monto, linea.descripcion,
                         linea.notas)
    return construir_con_signo(TipoOperacion.RENDIMIENTO, linea.fecha, cuenta.id, categoria.id, a_pesos(centavos),
                               linea.descripcion, linea.notas)


def _firma(op: Operacion) -> tuple:
    """Lo que hace iguales a dos movimientos (para no duplicar): fecha, tipo y partidas (sin descripción)."""
    return (op.fecha, op.tipo.value,
            tuple(sorted((p.cuenta_id or "", p.categoria_id or "", p.importe) for p in op.partidas)))


def _lados_principales(propuestas) -> dict[tuple, str]:
    """Para cada transferencia, el bloque (cuenta) que manda: el que la trae más veces o, si empatan, el primero
    del archivo. Las filas del otro bloque son la misma transferencia vista desde la otra cuenta."""
    conteo: dict[tuple, Counter] = defaultdict(Counter)
    primero: dict[tuple, dict[str, int]] = defaultdict(dict)
    for bloque, linea, op, _ in propuestas:
        if op is not None and op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
            firma, lado = _firma(op), clave(bloque.cuenta)
            conteo[firma][lado] += 1
            primero[firma].setdefault(lado, bloque.numero)
    return {firma: max(lados, key=lambda lado: (lados[lado], -primero[firma][lado])) for firma, lados in conteo.items()}


def _describir_destino(libro: Libro, op: Operacion, *, cuenta_id: str) -> str:
    otras = [p.cuenta_id for p in op.partidas_de_cuenta() if p.cuenta_id != cuenta_id]
    if otras:
        return libro.cuenta(otras[0]).nombre
    (partida,) = op.partidas_de_categoria()
    return categorias.etiqueta(libro, partida.categoria_id)


# ===================================================================== plantillas

_INSTRUCCIONES = """\
# =============================================================================
#  TALLY · PLANTILLA DE CARGA MASIVA · {titulo}
# =============================================================================
#  Sirve para pasar a TALLY los movimientos que ya tenías (por ejemplo, en Excel)
#  sin capturarlos uno por uno.
#
#  CÓMO LLENARLA
#   1. Escribe el nombre de tu cuenta después de «CUENTA:». Si ya existe en TALLY,
#      los movimientos se agregan ahí; si no, TALLY la crea con el TIPO indicado.
#   2. Si TALLY va a crear la cuenta, escribe en «SALDO INICIAL:» {saldo}
#   3. Borra los movimientos de ejemplo y pega los tuyos debajo de la fila FECHA.
#      Desde Excel: acomoda tus columnas en este mismo orden, selecciónalas,
#      cópialas (Ctrl+C) y pégalas aquí (Ctrl+V). Excel las separa con TAB.
#   4. Guarda el archivo y súbelo en TALLY › Cargar datos. Antes de guardar nada
#      verás una vista previa de lo que se va a cargar.
#
#  COLUMNAS (una fila por movimiento)
#   FECHA         día/mes/año, por ejemplo 15/07/2026
#   DESCRIPCION   lo que quieras: «Súper», «Uber», «Quincena»…
#   SUBCATEGORIA  una subcategoría de TALLY (DESPENSA, GASOLINA, NOMINA…; da igual
#                 si usas mayúsculas o acentos). Si el dinero fue a otra de TUS
#                 cuentas, escribe el nombre de esa cuenta.
#                 Si TALLY no la reconoce, en la vista previa eliges a cuál
#                 corresponde o la creas como subcategoría nueva.
#   CARGO         {cargo}
#   ABONO         {abono}
#   NOTAS         opcional
#  En cada fila llena CARGO o ABONO, no los dos. $1,234.50, 1234.5 y 1,234.50 valen.
#
#  CÓMO SE CUENTA (nada se cuenta dos veces)
#   · CARGO con subcategoría de gasto .......... gasto
#   · ABONO con subcategoría de ingreso ........ ingreso
#   · ABONO con subcategoría de gasto .......... devolución (resta de ese gasto)
#   · El nombre de otra de tus cuentas ......... transferencia: NO es gasto.
#     Pagar una tarjeta de crédito es «pago de tarjeta»: el gasto ya se contó
#     al comprar con ella. Si la misma transferencia viene también en la otra
#     cuenta, TALLY la carga una sola vez.
#   · POR RECUPERAR ............................ cargo temporal: lo que te
#     cobran para verificar tu tarjeta y te devuelven después (Amazon, hotel…).
#     El cargo y su devolución llevan POR RECUPERAR; NO es gasto.
#{extra}#   · Lo que ya esté en TALLY no se vuelve a cargar: subir el mismo archivo
#     dos veces no duplica nada.
#
#  Las líneas que empiezan con # son instrucciones: TALLY las ignora.
#  Un archivo puede traer varias cuentas: cada una empieza con «CUENTA:».
# =============================================================================
"""

_POR_TIPO = {
    TipoCuenta.DEBITO: dict(
        titulo="TARJETA DE DEBITO", nombre="Mi tarjeta de débito", tipo="DEBITO",
        saldo="cuánto tenía\n#      ANTES del primer movimiento de la lista (o déjalo en 0).",
        cargo="dinero que SALIÓ: compras, retiros, pagos, envíos a otra cuenta",
        abono="dinero que ENTRÓ: nómina, depósitos, devoluciones",
        extra="#   · Retirar efectivo: CARGO con RETIROS DE EFECTIVO (cuenta como gasto).\n",
        filas=(("01/07/2026", "Quincena", "NOMINA", "", "12,500.00"),
               ("02/07/2026", "Súper de la semana", "DESPENSA", "1,284.60", ""),
               ("03/07/2026", "Gasolina", "GASOLINA", "800.00", ""),
               ("05/07/2026", "Comida con amigos", "RESTAURANTES", "450.00", ""),
               ("08/07/2026", "Cajero", "RETIROS DE EFECTIVO", "500.00", ""),
               ("10/07/2026", "Devolución de una compra", "COMPRAS EN LINEA", "", "299.00"),
               ("15/07/2026", "Gimnasio", "GIMNASIO", "650.00", ""))),
    TipoCuenta.CREDITO: dict(
        titulo="TARJETA DE CREDITO", nombre="Mi tarjeta de crédito", tipo="CREDITO",
        saldo="cuánto DEBÍAS\n#      antes del primer movimiento de la lista (o déjalo en 0).",
        cargo="compras y cargos (suben tu deuda): súper, intereses, comisiones",
        abono="lo que baja tu deuda: pagos a la tarjeta, devoluciones",
        extra=("#   · Un pago a la tarjeta: ABONO con el nombre de la cuenta desde la que\n"
               "#     pagaste (por ejemplo, tu tarjeta de débito).\n"
               "#   · Intereses o comisiones: CARGO con INTERESES DE TARJETAS o\n"
               "#     COMISIONES BANCARIAS.\n"),
        filas=(("04/07/2026", "Súper", "DESPENSA", "980.50", ""),
               ("06/07/2026", "Netflix", "STREAMING DE VIDEO", "299.00", ""),
               ("09/07/2026", "Uber", "TAXI Y APPS DE VIAJE", "135.00", ""),
               ("12/07/2026", "Tenis para correr", "CALZADO", "1,899.00", ""),
               ("14/07/2026", "Devolución tenis", "CALZADO", "", "1,899.00"),
               ("03/08/2026", "Intereses del periodo", "INTERESES DE TARJETAS", "85.30", ""))),
    TipoCuenta.AHORRO: dict(
        titulo="CUENTA DE AHORRO", nombre="Mi cuenta de ahorro", tipo="AHORRO",
        saldo="cuánto tenía\n#      ANTES del primer movimiento de la lista (o déjalo en 0).",
        cargo="dinero que SALIÓ: retiros o traspasos a otra cuenta",
        abono="dinero que ENTRÓ: depósitos, traspasos, intereses",
        extra=("#   · Intereses que te paga el banco: ABONO con INTERESES Y RENDIMIENTOS\n"
               "#     (cuentan como ingreso). Pueden ser diarios, uno por fila.\n"),
        filas=(("01/07/2026", "Intereses", "INTERESES Y RENDIMIENTOS", "", "3.25"),
               ("02/07/2026", "Intereses", "INTERESES Y RENDIMIENTOS", "", "3.26"),
               ("31/07/2026", "Intereses de julio", "INTERESES Y RENDIMIENTOS", "", "98.40"))),
    TipoCuenta.INVERSION: dict(
        titulo="CUENTA DE INVERSION", nombre="Mi inversión", tipo="INVERSION",
        saldo="cuánto valía tu\n#      inversión ANTES del primer movimiento de la lista (o déjalo en 0).",
        cargo="dinero que SALIÓ (retiros) o una pérdida de valor",
        abono="dinero que ENTRÓ (aportaciones) o una ganancia",
        extra=("#   · Ganancia: ABONO con INTERESES Y RENDIMIENTOS (o DIVIDENDOS).\n"
               "#     Pérdida: CARGO con INTERESES Y RENDIMIENTOS (resta del ingreso).\n"
               "#   · Aportar o retirar dinero: el nombre de la cuenta de origen o destino.\n"),
        filas=(("31/07/2026", "Rendimiento de julio", "INTERESES Y RENDIMIENTOS", "", "412.80"),
               ("31/08/2026", "Minusvalía de agosto", "INTERESES Y RENDIMIENTOS", "150.25", ""),
               ("15/09/2026", "Dividendo", "DIVIDENDOS", "", "57.00"))),
}

_TRANSFERENCIAS_DE_EJEMPLO = {
    TipoCuenta.DEBITO: (("20/07/2026", "Pago de la tarjeta", "Mi tarjeta de crédito", "1,414.50", ""),
                        ("21/07/2026", "Al ahorro", "Mi cuenta de ahorro", "2,000.00", ""),
                        ("22/07/2026", "Aportación", "Mi inversión", "1,500.00", "")),
    TipoCuenta.CREDITO: (("20/07/2026", "Pago recibido", "Mi tarjeta de débito", "", "1,414.50"),),
    TipoCuenta.AHORRO: (("21/07/2026", "Depósito de la quincena", "Mi tarjeta de débito", "", "2,000.00"),),
    TipoCuenta.INVERSION: (("22/07/2026", "Aportación", "Mi tarjeta de débito", "", "1,500.00"),),
}

TIPOS_CON_PLANTILLA = tuple(_POR_TIPO)


def plantilla(tipo: TipoCuenta | None = None) -> str:
    """Texto de la plantilla para un tipo de cuenta, o con las cuatro cuentas si ``tipo`` es ``None``.

    Los ejemplos son ficticios. La de todas incluye transferencias entre las cuentas (aparecen en los dos
    lados y se cargan una vez), para ver cómo funcionan.
    """
    tipos = [TipoCuenta(tipo)] if tipo is not None else list(_POR_TIPO)
    datos = _POR_TIPO[tipos[0]] if len(tipos) == 1 else dict(
        titulo="TODAS MIS CUENTAS", saldo="cuánto tenía\n#      (en crédito: cuánto debías) ANTES del primer "
        "movimiento de la lista.", cargo="dinero que SALIÓ de la cuenta (en crédito: compras, suben tu deuda)",
        abono="dinero que ENTRÓ a la cuenta (en crédito: pagos y devoluciones)",
        extra="".join(_POR_TIPO[t]["extra"] for t in tipos))
    texto = _INSTRUCCIONES.format(**{k: datos[k] for k in ("titulo", "saldo", "cargo", "abono", "extra")})
    for t in tipos:
        d = _POR_TIPO[t]
        filas = list(d["filas"]) + (list(_TRANSFERENCIAS_DE_EJEMPLO[t]) if len(tipos) > 1 else [])
        filas.sort(key=lambda f: leer_fecha(f[0]))
        texto += f"\nCUENTA: {d['nombre']}\nTIPO: {d['tipo']}\nSALDO INICIAL: 0\n\n"
        texto += "\t".join(COLUMNAS) + "\n"
        texto += "".join("\t".join((*fila, "")) + "\n" for fila in filas)
    return texto


def nombre_de_plantilla(tipo: TipoCuenta | None = None) -> str:
    sufijo = _POR_TIPO[TipoCuenta(tipo)]["tipo"].lower() if tipo is not None else "todas_mis_cuentas"
    return f"TALLY_plantilla_{sufijo}.txt"

