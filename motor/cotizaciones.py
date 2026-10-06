"""Precio aproximado de un título en internet. Solo de consulta y solo cuando el usuario lo pide.

Lo único que sale de la computadora es el **símbolo** (por ejemplo ``IVVPESO.MX``, ``AAPL`` o ``BTC-USD``):
nunca cuántos títulos tienes, cuánto pagaste ni ningún otro dato o archivo de TALLY. No hay cuenta, contraseña
ni llave.

La fuente es el servicio de gráficas de Yahoo Finance (el mismo que usa su página): cubre la BMV (``.MX``),
NASDAQ/NYSE, ETFs, cripto y tipos de cambio (``USDMXN=X``). No es un servicio oficial: si algún día cambia, la
consulta avisa que no pudo leer la respuesta y el usuario puede escribir el precio a mano. Los precios pueden
tener retraso; son aproximados.

Usa solo la biblioteca estándar. Sin internet (o si la red lo bloquea) lo dice de inmediato: la primera
consulta va sola y, si no hay conexión, ya no se intentan las demás.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?range=5d&interval=1d"
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIEMPO_ESPERA = 10           # segundos por consulta
SIMULTANEAS = 4
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

    @property
    def ok(self) -> bool:
        return self.precio is not None


def simbolo_tipo_de_cambio(moneda: str) -> str:
    """El símbolo del tipo de cambio a pesos: USD → USDMXN=X."""
    return f"{moneda.upper()}MXN=X"


def enviar(simbolo: str) -> str:
    """Hace la consulta HTTPS. Lo único que viaja es el símbolo, dentro de la dirección."""
    if not _SIMBOLO.match(simbolo):
        raise ValueError(f"símbolo no válido: {simbolo!r}")
    url = URL.format(simbolo=urllib.parse.quote(simbolo, safe=""))
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:  # noqa: S310 - URL fija https
        return respuesta.read().decode("utf-8")


def leer(simbolo: str, texto: str) -> Cotizacion:
    """Extrae precio, moneda, hora y nombre de la respuesta de Yahoo."""
    try:
        datos = json.loads(texto)["chart"]
    except (ValueError, KeyError, TypeError):
        return Cotizacion(simbolo, error="la respuesta no se pudo leer")
    resultado = datos.get("result") or []
    if not resultado:
        descripcion = (datos.get("error") or {}).get("description") or "sin datos"
        return Cotizacion(simbolo, error=f"no se encontró «{simbolo}» ({descripcion}); revisa el símbolo")
    meta = resultado[0].get("meta") or {}
    try:
        precio = Decimal(str(meta["regularMarketPrice"]))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return Cotizacion(simbolo, error="la respuesta no trae precio")
    if not precio.is_finite() or precio <= 0:
        return Cotizacion(simbolo, error="la respuesta no trae un precio válido")
    momento = meta.get("regularMarketTime")
    return Cotizacion(
        simbolo, precio=precio, moneda=str(meta.get("currency") or "").upper(),
        momento=datetime.fromtimestamp(momento) if isinstance(momento, (int, float)) else None,
        nombre=str(meta.get("longName") or meta.get("shortName") or ""),
    )


def consultar_uno(simbolo: str, enviar: Enviar | None = None) -> Cotizacion:
    enviar = enviar or _enviar_por_omision()
    try:
        return leer(simbolo, enviar(simbolo))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return Cotizacion(simbolo, error=f"no se encontró «{simbolo}»; revisa el símbolo")
        return Cotizacion(simbolo, error=f"el servicio respondió con error HTTP {error.code}")
    except (urllib.error.URLError, OSError) as error:          # sin internet, proxy, red bloqueada, tiempo agotado
        return Cotizacion(simbolo, error=f"sin conexión ({getattr(error, 'reason', error)})", sin_conexion=True)
    except ValueError as error:
        return Cotizacion(simbolo, error=str(error))


def consultar(simbolos: list[str], enviar: Enviar | None = None
              ) -> tuple[dict[str, Cotizacion], dict[str, Decimal], str]:
    """Precios de ``simbolos`` y los tipos de cambio que hagan falta para pasarlos a pesos.

    Devuelve ``({símbolo: Cotizacion}, {moneda: pesos por unidad}, aviso)``. ``aviso`` está vacío si todo salió
    bien; si no, dice qué faltó.
    """
    enviar = enviar or _enviar_por_omision()
    unicos = list(dict.fromkeys(simbolos))
    if not unicos:
        return {}, {}, ""
    primera = consultar_uno(unicos[0], enviar)
    if primera.sin_conexion:
        sin_red = {s: replace(primera, simbolo=s) for s in unicos}
        return sin_red, {}, (f"No hay conexión con el servicio de precios: {primera.error}. Revisa tu internet o, "
                             "si la red de tu trabajo lo bloquea, escribe los precios a mano.")
    resultado = {unicos[0]: primera, **_en_paralelo(unicos[1:], enviar)}
    monedas = sorted({c.moneda for c in resultado.values() if c.ok and c.moneda and c.moneda != "MXN"})
    cambios = _en_paralelo([simbolo_tipo_de_cambio(m) for m in monedas], enviar)
    tipos = {m: c.precio for m, c in zip(monedas, cambios.values()) if c.ok}
    avisos = [f"{s}: {c.error}" for s, c in resultado.items() if not c.ok]
    avisos += [f"tipo de cambio {m}/MXN: no se pudo consultar" for m in monedas if m not in tipos]
    return resultado, tipos, "; ".join(avisos)


def _enviar_por_omision() -> Enviar:
    return globals()["enviar"]          # se busca al llamar, para poder sustituirlo en pruebas


def _en_paralelo(simbolos: list[str], enviar: Enviar) -> dict[str, Cotizacion]:
    if not simbolos:
        return {}
    with ThreadPoolExecutor(min(SIMULTANEAS, len(simbolos))) as grupo:
        return dict(zip(simbolos, grupo.map(lambda s: consultar_uno(s, enviar), simbolos)))
