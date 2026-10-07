"""Contraseña opcional de TALLY: tus datos cifrados en el disco, con un Kit de emergencia por si la olvidas.

Explicado fácil
---------------
- Tus datos se guardan con un **candado** (una llave maestra, secreta y al azar, que nunca se muestra).
- Esa llave maestra se guarda **dos veces**, cada una dentro de su propia caja fuerte:
  1. una que se abre con **tu contraseña** (la del día a día);
  2. otra que se abre con la **llave de tu Kit de emergencia** (por si olvidas la contraseña).
- Cambiar tu contraseña solo cambia la primera caja: la llave maestra y tu Kit **son los mismos para siempre**,
  así que el Kit abre todo: tus datos y todos tus respaldos (aunque hayas cambiado la contraseña muchas veces).
- Sin la contraseña ni el Kit, nadie puede leer tus datos: ni TALLY, ni quien copie el archivo.

Detalles técnicos
-----------------
- Cifrado AES-256-GCM (autenticado: si alguien modifica un dato, TALLY lo detecta). Cada registro va cifrado por
  separado y amarrado a su lugar (``contexto``), así no se pueden intercambiar registros.
- La llave de cada caja se obtiene de la contraseña o del Kit con **scrypt** (lento a propósito: adivinar
  contraseñas por fuerza bruta toma muchísimo tiempo).
- La llave del Kit: 22 caracteres al azar (110 bits) + 2 de verificación, en el alfabeto de Crockford (sin
  I, L, O ni U, para que no se confundan con 1 y 0). Al escribirla, TALLY tolera minúsculas, espacios, guiones y
  esas confusiones, y avisa si hay un error de tecleo antes de intentar abrir.
- AES viene de la librería ``cryptography`` (estándar y auditada); se importa solo cuando se usa, para que el
  resto de TALLY (y el instalador) funcione aunque aún no esté instalada.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime

from motor.errores import ErrorContrasena, ErrorDatos, ErrorValidacion

VERSION = 1
PREFIJO = f"tally-cifrado:{VERSION}:"
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"          # Crockford: sin I, L, O, U
LARGO_AZAR, LARGO_VERIFICACION = 22, 2
MINIMO_CONTRASENA = 8
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
MEMORIA_SCRYPT = 128 * 1024 * 1024
BLOQUEO_MINUTOS = 10
DIAS_PARA_COMPROBAR_KIT = 90


# ------------------------------------------------------------------- AES


def _aes(llave: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:                                   # pragma: no cover - depende de la instalación
        raise ErrorDatos("Falta un componente de seguridad (cryptography). Vuelve a correr INSTALAR.bat.") from None
    return AESGCM(llave)


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.b64decode(texto.encode("ascii"), validate=True)


# --------------------------------------------------------------- contraseñas


def _normalizar(secreto: str) -> bytes:
    """La misma contraseña siempre da los mismos bytes (acentos escritos de distinta forma, espacios al final)."""
    return unicodedata.normalize("NFC", secreto).strip().encode("utf-8")


def _derivar(secreto: bytes, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(secreto, salt=sal, n=n, r=r, p=p, maxmem=MEMORIA_SCRYPT, dklen=32)


def _envolver(llave: bytes, secreto: bytes) -> dict:
    sal, nonce = os.urandom(16), os.urandom(12)
    caja = _derivar(secreto, sal, **SCRYPT)
    return {"sal": _b64(sal), **SCRYPT, "nonce": _b64(nonce),
            "llave": _b64(_aes(caja).encrypt(nonce, llave, b"tally-llave-maestra"))}


def _desenvolver(envoltura: dict, secreto: bytes) -> bytes:
    try:
        caja = _derivar(secreto, _de_b64(envoltura["sal"]), int(envoltura["n"]), int(envoltura["r"]),
                        int(envoltura["p"]))
        return _aes(caja).decrypt(_de_b64(envoltura["nonce"]), _de_b64(envoltura["llave"]), b"tally-llave-maestra")
    except (KeyError, ValueError, TypeError) as error:
        raise ErrorDatos(f"La información de la contraseña está dañada ({error}).") from error
    except Exception as error:                            # InvalidTag: no es la contraseña o la llave correcta
        if type(error).__name__ == "InvalidTag":
            raise ErrorContrasena("No coincide.") from None
        raise


def validar_contrasena(contrasena: str, confirmacion: str | None = None, pista: str = "") -> None:
    """Reglas simples: al menos 8 caracteres, escrita igual dos veces, y que la pista no la revele."""
    texto = unicodedata.normalize("NFC", contrasena or "").strip()
    if len(texto) < MINIMO_CONTRASENA:
        raise ErrorValidacion(f"Tu contraseña necesita al menos {MINIMO_CONTRASENA} caracteres. Una frase corta "
                              "es fácil de recordar y difícil de adivinar: por ejemplo «mi perro come tacos».")
    if confirmacion is not None and unicodedata.normalize("NFC", confirmacion).strip() != texto:
        raise ErrorValidacion("Las dos contraseñas no son iguales. Escríbelas otra vez con calma.")
    if pista and texto.casefold() in pista.casefold():
        raise ErrorValidacion("La pista no puede contener tu contraseña: cualquiera la puede ver.")


# --------------------------------------------------------------- Kit de emergencia


def _verificacion(cuerpo: str) -> str:
    valor = int.from_bytes(hashlib.sha256(cuerpo.encode("ascii")).digest()[:2], "big") >> 6   # 10 bits
    return ALFABETO[valor >> 5] + ALFABETO[valor & 31]


def nuevo_kit() -> str:
    """Una llave de recuperación nueva: ``XXXX-XXXX-XXXX-XXXX-XXXX-XXXX``."""
    cuerpo = "".join(secrets.choice(ALFABETO) for _ in range(LARGO_AZAR))
    completo = cuerpo + _verificacion(cuerpo)
    return "-".join(completo[i:i + 4] for i in range(0, len(completo), 4))


def normalizar_kit(texto: str) -> str:
    """La llave escrita como sea (minúsculas, espacios, guiones, «O» por «0»…) en su forma canónica.

    ``ErrorValidacion`` con un mensaje claro si le faltan o le sobran caracteres, o si hay un error de tecleo.
    """
    limpio = (texto or "").upper().replace("TALLY", "")
    limpio = "".join(c for c in limpio if c.isalnum())
    limpio = limpio.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "U": "V"}))
    largo = LARGO_AZAR + LARGO_VERIFICACION
    if len(limpio) != largo:
        falta = "le faltan" if len(limpio) < largo else "le sobran"
        raise ErrorValidacion(f"La llave tiene {largo} letras y números (6 grupos de 4); a esta {falta} "
                              f"{abs(largo - len(limpio))}. Revísala con calma.")
    if any(c not in ALFABETO for c in limpio):
        raise ErrorValidacion("La llave tiene un carácter que no existe en las llaves de TALLY. Revísala.")
    if _verificacion(limpio[:LARGO_AZAR]) != limpio[LARGO_AZAR:]:
        raise ErrorValidacion("Parece que hay un error al escribir la llave (una letra o número cambiado). "
                              "Compárala letra por letra con tu Kit.")
    return "-".join(limpio[i:i + 4] for i in range(0, largo, 4))


def _bytes_kit(kit: str) -> bytes:
    return normalizar_kit(kit).replace("-", "").encode("ascii")


# ------------------------------------------------------------- configuración


@dataclass(frozen=True, slots=True)
class Config:
    """Lo que se guarda (sin cifrar) para poder abrir: las dos cajas, y datos que ayudan sin revelar nada."""

    version: int
    llave_id: str                  # huella corta de la llave maestra (para reconocer respaldos)
    creado: str                    # cuándo se activó
    contrasena: dict               # la caja que abre tu contraseña
    recuperacion: dict             # la caja que abre tu Kit
    kit_creado: str                # fecha del Kit (para reconocerlo)
    kit_final: str                 # los últimos 4 caracteres de la llave (para reconocerlo, no para abrir)
    pista: str = ""
    bloqueo_minutos: int = BLOQUEO_MINUTOS
    kit_comprobado: str = ""       # la última vez que comprobaste que aún tienes tu Kit

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def de_json(cls, texto: str) -> Config:
        try:
            datos = json.loads(texto)
            return cls(**{k: datos[k] for k in cls.__dataclass_fields__ if k in datos})
        except (ValueError, TypeError) as error:
            raise ErrorDatos(f"La información de la contraseña está dañada ({error}).") from error

    def recordatorio_kit(self, hoy: date) -> bool:
        """True si conviene volver a comprobar que tienes tu Kit (cada 90 días)."""
        ultima = self.kit_comprobado or self.creado
        try:
            return (hoy - datetime.fromisoformat(ultima).date()).days >= DIAS_PARA_COMPROBAR_KIT
        except ValueError:
            return True


def huella(llave: bytes) -> str:
    return hashlib.sha256(b"tally-huella" + llave).hexdigest()[:16]


def preparar(contrasena: str, kit: str, *, pista: str = "", ahora: datetime | None = None,
             bloqueo_minutos: int = BLOQUEO_MINUTOS) -> tuple[Config, bytes]:
    """Una llave maestra nueva, guardada en la caja de la contraseña y en la del Kit."""
    validar_contrasena(contrasena, pista=pista)
    kit = normalizar_kit(kit)
    llave = os.urandom(32)
    momento = (ahora or datetime.now()).isoformat(timespec="seconds")
    config = Config(VERSION, huella(llave), momento, _envolver(llave, _normalizar(contrasena)),
                    _envolver(llave, _bytes_kit(kit)), momento[:10], kit[-4:], pista.strip(),
                    int(bloqueo_minutos), momento)
    return config, llave


def abrir_con_contrasena(config: Config, contrasena: str) -> bytes:
    try:
        llave = _desenvolver(config.contrasena, _normalizar(contrasena or ""))
    except ErrorContrasena:
        raise ErrorContrasena("Esa no es la contraseña. Revisa mayúsculas y acentos, o usa tu Kit de emergencia."
                              ) from None
    return _comprobar(config, llave)


def abrir_con_kit(config: Config, kit: str) -> bytes:
    try:
        llave = _desenvolver(config.recuperacion, _bytes_kit(kit))
    except ErrorContrasena:
        raise ErrorContrasena(f"Esa llave es válida, pero no es la de estos datos. Busca tu Kit del "
                              f"{_fecha(config.kit_creado)} (su llave termina en …{config.kit_final}).") from None
    return _comprobar(config, llave)


def abrir(config: Config, secreto: str) -> bytes:
    """Con la contraseña o con la llave del Kit (lo que el usuario escriba)."""
    try:
        return abrir_con_contrasena(config, secreto)
    except ErrorContrasena:
        try:
            normalizar_kit(secreto)
        except ErrorValidacion:
            raise ErrorContrasena("No coincide con tu contraseña ni con tu Kit de emergencia.") from None
        return abrir_con_kit(config, secreto)


def cambiar_contrasena(config: Config, llave: bytes, nueva: str, *, pista: str | None = None) -> Config:
    """Otra contraseña para la misma llave maestra: el Kit y los respaldos siguen sirviendo."""
    validar_contrasena(nueva, pista=config.pista if pista is None else pista)
    _comprobar(config, llave)
    return replace(config, contrasena=_envolver(llave, _normalizar(nueva)),
                   pista=config.pista if pista is None else pista.strip())


def _comprobar(config: Config, llave: bytes) -> bytes:
    if huella(llave) != config.llave_id:
        raise ErrorDatos("La llave no corresponde a estos datos.")
    return llave


def _fecha(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except ValueError:
        return iso


# ------------------------------------------------------------- cifrar registros


@dataclass(frozen=True)
class Cifrador:
    """Convierte cada registro (un dict o lista JSON) en texto cifrado y de regreso."""

    llave: bytes = field(repr=False)

    def cifrar(self, valor, contexto: str) -> str:
        nonce = os.urandom(12)
        datos = json.dumps(valor, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return PREFIJO + _b64(nonce + _aes(self.llave).encrypt(nonce, datos, contexto.encode("utf-8")))

    def descifrar(self, texto: str, contexto: str):
        if not es_cifrado(texto):
            raise ErrorDatos("Hay un dato sin cifrar en tus datos cifrados. Restaura un respaldo.")
        try:
            crudo = _de_b64(texto[len(PREFIJO):])
            datos = _aes(self.llave).decrypt(crudo[:12], crudo[12:], contexto.encode("utf-8"))
        except ValueError as error:
            raise ErrorDatos(f"Un dato cifrado está dañado ({error}). Restaura un respaldo.") from error
        except Exception as error:
            if type(error).__name__ == "InvalidTag":
                raise ErrorDatos("Un dato cifrado fue modificado por fuera o está dañado. Restaura un respaldo."
                                 ) from None
            raise
        return json.loads(datos)


def es_cifrado(texto) -> bool:
    return isinstance(texto, str) and texto.startswith(PREFIJO)


def contexto_entidad(tipo: str, entidad_id: str) -> str:
    return f"entidad:{tipo}:{entidad_id}"


def contexto_bitacora(campo: str, fecha_hora: str, entidad: str, entidad_id: str, accion: str) -> str:
    return f"bitacora:{campo}:{fecha_hora}:{entidad}:{entidad_id}:{accion}"


# --------------------------------------------------- intentos (contra adivinar)


class Intentos:
    """Tras 3 intentos fallidos, hay que esperar cada vez más (2, 4, 8… hasta 60 segundos)."""

    def __init__(self, reloj=None) -> None:
        import time

        self._reloj = reloj or time.monotonic
        self.fallidos = 0
        self._hasta = 0.0

    def espera(self) -> int:
        """Segundos que faltan para poder intentar de nuevo (0 = ya se puede)."""
        return max(0, int(self._hasta - self._reloj() + 0.999))

    def fallo(self) -> None:
        self.fallidos += 1
        if self.fallidos >= 3:
            self._hasta = self._reloj() + min(2 ** (self.fallidos - 2), 60)

    def acierto(self) -> None:
        self.fallidos, self._hasta = 0, 0.0
