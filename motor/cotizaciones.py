"""Precio aproximado de un título en internet. Solo consulta datos públicos de mercado.

Qué sale de la computadora (y qué no)
-------------------------------------
- Sale **solo el símbolo bursátil**, dentro de la dirección: ``GET https://…/chart/IVV``. Nada más.
- **No** salen cantidades, precios de compra, saldos, movimientos, patrimonio, nombre ni ningún archivo de
  TALLY. Los cálculos (valor actual, ganancia, rentabilidad) se hacen en tu PC (:mod:`motor.portafolio`).
- Siempre por **HTTPS**, sin cookies, sin cuenta, sin contraseña y sin llave.
- No se registra nada de la consulta en bitácoras ni logs. Lo único que se guarda, en tu PC, son los últimos
  precios públicos obtenidos (``Datos\\precios.json``), para seguir funcionando sin internet.
- Solo se consulta cuando el usuario aprieta el botón (o si él mismo activó «Actualizar precios
  automáticamente»).

El proveedor
------------
Es el servicio de gráficas de Yahoo Finance (el mismo que usa su página): cubre la BMV (``.MX``), NASDAQ/NYSE,
ETFs, cripto y tipos de cambio (``USDMXN=X``). No es oficial: si algún día cambia o desaparece, la consulta lo
detecta (:attr:`Consulta.falla_proveedor`), TALLY sigue funcionando con los últimos precios guardados o los que
escriba el usuario, y cambiar de proveedor solo requiere cambiar :data:`PROVEEDOR`, :func:`enviar` y
:func:`leer`. Los precios pueden tener retraso: son aproximados.

Usa solo la biblioteca estándar. Sin internet (o si la red lo bloquea) lo dice de inmediato: la primera
consulta va sola y, si no hay conexión, ya no se intentan las demás.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from motor import rutas

PROVEEDOR = "Yahoo Finance"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=5d&interval=1d"
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIEMPO_ESPERA = 10           # segundos por consulta
SIMULTANEAS = 4
ARCHIVO_PRECIOS = "precios.json"
_SIMBOLO = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$")

Enviar = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class Cotizacion:
    simbolo: str
    precio: Decimal | None = None
    moneda: str = ""
    momento: datetime | None = None      # cuándo fue ese precio (hora del mercado)
    nombre: str = ""
    error: str = ""
    sin_conexion: bool = False
    falla_proveedor: bool = False        # hubo conexión, pero el servicio no respondió como se espera

    @property
    def ok(self) -> bool:
        return self.precio is not None


@dataclass(frozen=True, slots=True)
class Consulta:
    precios: dict[str, Cotizacion]
    tipos: dict[str, Decimal]            # moneda → pesos por unidad
    aviso: str = ""                      # qué faltó (vacío si todo salió bien)
    sin_conexion: bool = False
    falla_proveedor: bool = False        # ninguna respuesta útil aunque hubo conexión: ¿cambió o cayó el servicio?
    momento: datetime = field(default_factory=datetime.now)


def simbolo_tipo_de_cambio(moneda: str) -> str:
    """El símbolo del tipo de cambio a pesos: USD → USDMXN=X."""
    return f"{moneda.upper()}MXN=X"


# ------------------------------------------------------------------ proveedor


def enviar(simbolo: str) -> str:
    """Hace la consulta HTTPS. Lo único que viaja es el símbolo, dentro de la dirección."""
    if not _SIMBOLO.match(simbolo):
        raise ValueError(f"símbolo no válido: {simbolo!r}")
    url = URL.format(simbolo=urllib.parse.quote(simbolo, safe=""))
    if not url.startswith("https://"):
        raise ValueError("la consulta de precios solo se hace por HTTPS")
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:  # noqa: S310 - URL fija https
        return respuesta.read().decode("utf-8")


def leer(simbolo: str, texto: str) -> Cotizacion:
    """Extrae precio, moneda, hora y nombre de la respuesta del proveedor."""
    try:
        datos = json.loads(texto)["chart"]
    except (ValueError, KeyError, TypeError):
        return Cotizacion(simbolo, error="la respuesta no se pudo leer", falla_proveedor=True)
    resultado = datos.get("result") or []
    if not resultado:
        descripcion = (datos.get("error") or {}).get("description") or "sin datos"
        return Cotizacion(simbolo, error=f"no se encontró «{simbolo}» ({descripcion}); revisa el símbolo")
    meta = resultado[0].get("meta") or {}
    try:
        precio = Decimal(str(meta["regularMarketPrice"]))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return Cotizacion(simbolo, error="la respuesta no trae precio", falla_proveedor=True)
    if not precio.is_finite() or precio <= 0:
        return Cotizacion(simbolo, error="la respuesta no trae un precio válido", falla_proveedor=True)
    momento = meta.get("regularMarketTime")
    return Cotizacion(
        simbolo, precio=precio, moneda=str(meta.get("currency") or "").upper(),
        momento=datetime.fromtimestamp(momento) if isinstance(momento, (int, float)) else None,
        nombre=str(meta.get("longName") or meta.get("shortName") or ""),
    )


# ------------------------------------------------------------------ consultar


def consultar_uno(simbolo: str, enviar: Enviar | None = None) -> Cotizacion:
    enviar = enviar or _enviar_por_omision()
    try:
        return leer(simbolo, enviar(simbolo))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return Cotizacion(simbolo, error=f"no se encontró «{simbolo}»; revisa el símbolo")
        return Cotizacion(simbolo, error=f"el servicio respondió con error HTTP {error.code}", falla_proveedor=True)
    except (urllib.error.URLError, OSError) as error:          # sin internet, proxy, red bloqueada, tiempo agotado
        return Cotizacion(simbolo, error=f"sin conexión ({getattr(error, 'reason', error)})", sin_conexion=True)
    except ValueError as error:
        return Cotizacion(simbolo, error=str(error))


def consultar(simbolos: list[str], enviar: Enviar | None = None) -> Consulta:
    """Precios de ``simbolos`` y los tipos de cambio que hagan falta para pasarlos a pesos."""
    enviar = enviar or _enviar_por_omision()
    unicos = list(dict.fromkeys(simbolos))
    if not unicos:
        return Consulta({}, {})
    primera = consultar_uno(unicos[0], enviar)
    if primera.sin_conexion:
        return Consulta({s: replace(primera, simbolo=s) for s in unicos}, {}, sin_conexion=True, aviso=(
            f"No hay conexión con {PROVEEDOR}: {primera.error}. Revisa tu internet o, si la red de tu trabajo lo "
            "bloquea, escribe los precios a mano."))
    resultado = {unicos[0]: primera, **_en_paralelo(unicos[1:], enviar)}
    monedas = sorted({c.moneda for c in resultado.values() if c.ok and c.moneda and c.moneda != "MXN"})
    cambios = _en_paralelo([simbolo_tipo_de_cambio(m) for m in monedas], enviar)
    tipos = {m: c.precio for m, c in zip(monedas, cambios.values()) if c.ok}
    avisos = [f"{s}: {c.error}" for s, c in resultado.items() if not c.ok]
    avisos += [f"tipo de cambio {m}/MXN: no se pudo consultar" for m in monedas if m not in tipos]
    falla = not any(c.ok for c in resultado.values()) and any(c.falla_proveedor for c in resultado.values())
    return Consulta(resultado, tipos, "; ".join(avisos), falla_proveedor=falla)


def _enviar_por_omision() -> Enviar:
    return globals()["enviar"]          # se busca al llamar, para poder sustituirlo en pruebas


def _en_paralelo(simbolos: list[str], enviar: Enviar) -> dict[str, Cotizacion]:
    if not simbolos:
        return {}
    with ThreadPoolExecutor(min(SIMULTANEAS, len(simbolos))) as grupo:
        return dict(zip(simbolos, grupo.map(lambda s: consultar_uno(s, enviar), simbolos)))


# ------------------------------------------------------- últimos precios guardados


@dataclass(frozen=True, slots=True)
class Guardado:
    valor: Decimal
    moneda: str
    actualizado: datetime     # cuándo lo trajo TALLY


def archivo_precios() -> Path:
    return rutas.carpeta_datos() / ARCHIVO_PRECIOS


def guardar(consulta: Consulta, ruta: Path | None = None) -> None:
    """Agrega a los últimos precios guardados los que sí se obtuvieron (los que fallaron conservan el anterior).

    Solo guarda datos públicos de mercado: símbolo, precio, moneda y hora. Si no se puede escribir, no pasa nada.
    """
    ruta = ruta or archivo_precios()
    datos = _leer_archivo(ruta)
    momento = consulta.momento.isoformat(timespec="seconds")
    for simbolo, c in consulta.precios.items():
        if c.ok:
            datos["precios"][simbolo] = {"valor": str(c.precio), "moneda": c.moneda or "MXN", "actualizado": momento}
    for moneda, valor in consulta.tipos.items():
        datos["tipos"][moneda] = {"valor": str(valor), "moneda": "MXN", "actualizado": momento}
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(ruta.name + ".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporal, ruta)
    except OSError:
        pass


def ultimos(ruta: Path | None = None) -> tuple[dict[str, Guardado], dict[str, Guardado]]:
    """Los últimos precios y tipos de cambio guardados: ``({símbolo: Guardado}, {moneda: Guardado})``."""
    datos = _leer_archivo(ruta or archivo_precios())

    def convertir(seccion: dict) -> dict[str, Guardado]:
        salida = {}
        for clave, d in seccion.items():
            try:
                salida[clave] = Guardado(Decimal(d["valor"]), str(d.get("moneda") or "MXN"),
                                         datetime.fromisoformat(d["actualizado"]))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
        return salida

    return convertir(datos["precios"]), convertir(datos["tipos"])


def _leer_archivo(ruta: Path) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if isinstance(datos.get("precios"), dict) and isinstance(datos.get("tipos"), dict):
            return datos
    except (OSError, ValueError, AttributeError):
        pass
    return {"precios": {}, "tipos": {}}
