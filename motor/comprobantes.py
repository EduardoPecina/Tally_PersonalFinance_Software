"""Comprobantes: la foto del ticket, el PDF o el XML de la factura, adjuntos a un movimiento.

El archivo se guarda **dentro de tu archivo de datos** (``tally.db``, tabla ``archivos``), cifrado si tienes
contraseña, y viaja en tus respaldos: no queda regado en carpetas ni sale de tu PC. Se guarda en la misma
transacción que el movimiento: o se guardan los dos, o ninguno. Al borrar el movimiento se borran sus comprobantes.

Para tus impuestos: de cada gasto deducible sabes si ya tienes su comprobante, y descargas todos los del año en un
``.zip`` (una carpeta por concepto y un índice para Excel) para tu contador o tu declaración.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath as PurePath     # rutas con «/» en cualquier sistema (también dentro del .zip)

from motor import impuestos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Comprobante

MAXIMO_MB = 10
MAXIMO_BYTES = MAXIMO_MB * 1024 * 1024
MAXIMO_POR_MOVIMIENTO = 20
EXTENSIONES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
               ".heic": "image/heic", ".pdf": "application/pdf", ".xml": "application/xml"}
ACEPTADAS = sorted({e.lstrip(".") for e in EXTENSIONES})          # para el selector de archivos del portal
ICONOS = {"application/pdf": "📄", "application/xml": "🧾"}          # las imágenes: 🖼️
_NOMBRE_INVALIDO = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


def tipo_de(nombre: str, contenido: bytes) -> str:
    """El tipo del archivo por su extensión, comprobando que el contenido sea de verdad eso."""
    extension = PurePath(nombre or "").suffix.lower()
    tipo = EXTENSIONES.get(extension)
    if tipo is None:
        raise ErrorValidacion("Ese tipo de archivo no se puede adjuntar. Usa una foto (JPG, PNG, WEBP, HEIC), un "
                              "PDF o el XML de la factura.")
    inicio = contenido[:64]
    validos = {
        "image/jpeg": inicio.startswith(b"\xff\xd8\xff"),
        "image/png": inicio.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP",
        "image/heic": inicio[4:8] == b"ftyp",
        "application/pdf": b"%PDF-" in contenido[:1024],
        "application/xml": contenido.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"),
    }
    if not validos[tipo]:
        raise ErrorValidacion(f"«{nombre}» no parece ser un archivo {extension.lstrip('.').upper()} válido.")
    return tipo


def limpiar_nombre(nombre: str) -> str:
    """Sin carpetas ni caracteres que Windows no acepta, y no más de 120 caracteres."""
    base = PurePath((nombre or "").replace("\\", "/")).name
    base = _NOMBRE_INVALIDO.sub("_", base).strip(" .") or "comprobante"
    if len(base) > 120:
        raiz, extension = PurePath(base).stem, PurePath(base).suffix
        base = raiz[:120 - len(extension)] + extension
    return base


def huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def adjuntar(libro: Libro, operacion_id: str, nombre: str, contenido: bytes) -> Comprobante:
    """Adjunta un archivo a un movimiento (se guarda junto con él)."""
    libro.operacion(operacion_id)
    contenido = bytes(contenido or b"")
    nombre = limpiar_nombre(nombre)
    if not contenido:
        raise ErrorValidacion(f"«{nombre}» está vacío.")
    if len(contenido) > MAXIMO_BYTES:
        raise ErrorValidacion(f"«{nombre}» pesa {len(contenido) / 1024 / 1024:.1f} MB; el máximo es {MAXIMO_MB} MB. "
                              "Toma la foto con menos resolución o comprime el PDF.")
    tipo = tipo_de(nombre, contenido)
    propios = libro.comprobantes(operacion_id)
    if len(propios) >= MAXIMO_POR_MOVIMIENTO:
        raise ErrorValidacion(f"Un movimiento puede tener hasta {MAXIMO_POR_MOVIMIENTO} comprobantes.")
    firma = huella(contenido)
    if any(c.huella == firma for c in propios):
        raise ErrorValidacion(f"«{nombre}» ya está adjunto a este movimiento.")
    comprobante = Comprobante(id=libro.nuevo_id(), operacion_id=operacion_id, nombre=nombre, tipo=tipo,
                              tamano=len(contenido), huella=firma, agregado=libro.ahora())
    return libro.guardar_comprobante(comprobante, contenido)


def quitar(libro: Libro, comprobante_id: str) -> None:
    libro.quitar_comprobante(comprobante_id)


def en_otros_movimientos(libro: Libro, comprobante: Comprobante) -> list[str]:
    """Otros movimientos con el mismo archivo: puede ser un gasto registrado dos veces."""
    return sorted({c.operacion_id for c in libro.comprobantes()
                   if c.huella == comprobante.huella and c.operacion_id != comprobante.operacion_id})


def contenido(sesion, comprobante_id: str) -> bytes:
    """El archivo de un comprobante (descifrado). ``sesion``: la de ``motor/sesion.py``."""
    sesion.libro.comprobante(comprobante_id)
    pendiente = sesion.libro.archivos_nuevos().get(comprobante_id)
    return pendiente if pendiente is not None else sesion.almacen.leer_archivo(comprobante_id)


def es_imagen(comprobante: Comprobante) -> bool:
    return comprobante.tipo.startswith("image/") and comprobante.tipo != "image/heic"   # HEIC: solo descargar


def icono(comprobante: Comprobante) -> str:
    return ICONOS.get(comprobante.tipo, "🖼️")


def tamano(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_ / 1024 / 1024:.1f} MB"


@dataclass(frozen=True, slots=True)
class Resumen:
    cuantos: int
    bytes: int
    movimientos: int


def resumen(libro: Libro) -> Resumen:
    lista = libro.comprobantes()
    return Resumen(len(lista), sum(c.tamano for c in lista), len({c.operacion_id for c in lista}))


def por_movimiento(libro: Libro) -> dict[str, int]:
    """Movimiento → cuántos comprobantes tiene (para la columna 📎 del Historial)."""
    conteo: dict[str, int] = defaultdict(int)
    for c in libro.comprobantes():
        conteo[c.operacion_id] += 1
    return dict(conteo)


# ------------------------------------------------------------------ tus deducibles


@dataclass(frozen=True, slots=True)
class Deducible:
    """Un pago deducible del año y sus comprobantes."""

    concepto: str
    pago: impuestos.Pago
    comprobantes: list[Comprobante]


def deducibles(libro: Libro, anio: int) -> list[Deducible]:
    """Los pagos de tus conceptos deducibles del año (los reembolsos no), con sus comprobantes."""
    por_op: dict[str, list[Comprobante]] = defaultdict(list)
    for c in libro.comprobantes():
        por_op[c.operacion_id].append(c)
    lista = []
    for renglon in impuestos.deducibles(libro, anio).renglones:
        for pago in renglon.pagos:
            if pago.importe > 0:
                lista.append(Deducible(renglon.concepto.nombre, pago, por_op.get(pago.operacion_id, [])))
    return sorted(lista, key=lambda d: (d.concepto, d.pago.fecha, d.pago.descripcion))


def sin_comprobante(libro: Libro, anio: int) -> list[Deducible]:
    return [d for d in deducibles(libro, anio) if not d.comprobantes]


def zip_de_deducibles(sesion, anio: int) -> bytes:
    """Un ``.zip`` con los comprobantes de tus deducibles del año: una carpeta por concepto y ``indice.csv``
    (se abre en Excel) con cada pago, su importe y su archivo, o «SIN COMPROBANTE»."""
    from motor.dinero import formatear

    lista = deducibles(sesion.libro, anio)
    salida = io.BytesIO()
    indice = io.StringIO()
    escritor = csv.writer(indice)
    escritor.writerow(["Concepto", "Fecha", "Descripción", "Subcategoría", "Cuenta", "Importe", "Archivo"])
    usados: set[str] = set()
    with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_DEFLATED) as zz:
        for d in lista:
            fila = [d.concepto, d.pago.fecha.strftime("%d/%m/%Y"), d.pago.descripcion, d.pago.subcategoria,
                    d.pago.cuenta, formatear(d.pago.importe)]
            if not d.comprobantes:
                escritor.writerow([*fila, "SIN COMPROBANTE"])
            for c in d.comprobantes:
                ruta = _ruta_libre(f"{limpiar_nombre(d.concepto)}/{d.pago.fecha:%Y-%m-%d}_{c.nombre}", usados)
                zz.writestr(ruta, contenido(sesion, c.id))
                escritor.writerow([*fila, ruta])
        zz.writestr("indice.csv", "﻿" + indice.getvalue())       # con BOM: Excel lo abre con acentos
    return salida.getvalue()


def _ruta_libre(ruta: str, usados: set[str]) -> str:
    original, n = PurePath(ruta), 2
    while ruta in usados:
        ruta = str(original.with_name(f"{original.stem}_{n}{original.suffix}"))
        n += 1
    usados.add(ruta)
    return ruta


def anios_con_deducibles(libro: Libro, hoy: date | None = None) -> list[int]:
    """Los años que tienen movimientos, del más reciente al más antiguo (para elegir cuál descargar)."""
    hoy = hoy or libro.hoy()
    operaciones = libro.operaciones()
    if not operaciones:
        return [hoy.year]
    return list(range(max(hoy.year, operaciones[-1].fecha.year), operaciones[0].fecha.year - 1, -1))
