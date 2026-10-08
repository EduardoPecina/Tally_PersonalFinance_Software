"""Poner, cambiar, recuperar y quitar la contraseña de TALLY, a prueba de errores.

Cada paso delicado sigue la misma receta:

1. **Comprobar antes de tocar**: la contraseña escrita dos veces, y la llave del Kit escrita de vuelta (así
   sabemos que la guardaste antes de cifrar nada).
2. **Respaldo de seguridad** de tus datos tal como están.
3. **Convertir en una sola transacción** (todo o nada: si se va la luz, tus datos quedan como estaban).
4. **Verificar**: se vuelven a leer los datos con la llave y deben ser idénticos. Si no, se deshace.
5. **Tus respaldos guardados** se convierten igual (cifrados con la misma llave, o sin cifrar al quitarla).

La llave maestra y el Kit nunca cambian mientras tengas contraseña: el Kit abre todo, siempre.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from motor import cifrado, respaldos, rutas
from motor.errores import ErrorContrasena, ErrorDatos, ErrorValidacion
from motor.persistencia import Almacen
from motor.sesion import Sesion


@dataclass(frozen=True, slots=True)
class Resultado:
    config: cifrado.Config | None
    respaldos_convertidos: int
    respaldos_con_problemas: list[str]
    respaldo_de_seguridad: Path | None = None


def config(ruta_datos: Path | str | None = None) -> cifrado.Config | None:
    """La contraseña de los datos (sin abrirlos), o ``None`` si no tienen."""
    return Almacen(ruta_datos or rutas.archivo_datos()).config_cifrado()


def activar(sesion: Sesion, contrasena: str, confirmacion: str, kit: str, kit_escrito: str, *, pista: str = "",
            carpeta_respaldos: Path | str | None = None) -> Resultado:
    """Pone la contraseña. ``kit`` es la llave que TALLY te dio y ``kit_escrito`` la que escribiste de vuelta."""
    if sesion.almacen.config_cifrado() is not None:
        raise ErrorValidacion("Tus datos ya tienen contraseña.")
    cifrado.validar_contrasena(contrasena, confirmacion, pista)
    kit = cifrado.normalizar_kit(kit)
    if cifrado.normalizar_kit(kit_escrito) != kit:
        raise ErrorValidacion("La llave que escribiste no es la de tu Kit. Revísala con calma: debe ser idéntica.")
    carpeta = Path(carpeta_respaldos or rutas.carpeta_respaldos())
    seguridad = respaldos.de_seguridad(sesion, "antes_de_poner_contrasena", carpeta)
    antes = sesion.almacen.estado_guardado
    bitacora_antes = len(sesion.almacen.bitacora())
    nueva, llave = cifrado.preparar(contrasena, kit, pista=pista, ahora=sesion.libro.ahora())
    sesion.almacen.activar_cifrado(nueva, llave)
    try:
        _verificar(sesion.almacen.ruta, llave, antes, bitacora_antes)
    except BaseException:
        sesion.almacen.desactivar_cifrado()           # se deshace: tus datos quedan como estaban
        raise
    convertidos, problemas = respaldos.convertir_carpeta(carpeta, llave, nueva)
    return Resultado(nueva, convertidos, problemas, seguridad)


def desactivar(sesion: Sesion, contrasena: str, *, carpeta_respaldos: Path | str | None = None) -> Resultado:
    """Quita la contraseña: tus datos y tus respaldos guardados vuelven a quedar sin cifrar, como antes."""
    actual = _requiere(sesion)
    llave = cifrado.abrir(actual, contrasena)          # con tu contraseña (o tu Kit)
    antes = sesion.almacen.estado_guardado
    bitacora_antes = len(sesion.almacen.bitacora())
    sesion.almacen.desactivar_cifrado()
    _verificar(sesion.almacen.ruta, None, antes, bitacora_antes)
    convertidos, problemas = respaldos.convertir_carpeta(carpeta_respaldos or rutas.carpeta_respaldos(), llave, None)
    return Resultado(None, convertidos, problemas)


def cambiar_contrasena(sesion: Sesion, actual: str, nueva: str, confirmacion: str, *,
                       pista: str | None = None) -> cifrado.Config:
    """Otra contraseña. Tu Kit sigue siendo el mismo y sigue abriendo todo."""
    config_actual = _requiere(sesion)
    llave = cifrado.abrir(config_actual, actual)
    cifrado.validar_contrasena(nueva, confirmacion, config_actual.pista if pista is None else pista)
    nueva_config = cifrado.cambiar_contrasena(config_actual, llave, nueva, pista=pista)
    sesion.almacen.guardar_config(nueva_config)
    return nueva_config


def recuperar(ruta_datos: Path | str | None, kit: str, nueva: str, confirmacion: str, *,
              pista: str | None = None) -> bytes:
    """«Olvidé mi contraseña»: con la llave del Kit pones una contraseña nueva. Devuelve la llave maestra (para
    entrar de una vez). No se pierde nada."""
    almacen = Almacen(ruta_datos or rutas.archivo_datos())
    actual = almacen.config_cifrado()
    if actual is None:
        raise ErrorValidacion("Tus datos no tienen contraseña.")
    llave = cifrado.abrir_con_kit(actual, kit)
    cifrado.validar_contrasena(nueva, confirmacion, actual.pista if pista is None else pista)
    nueva_config = cifrado.cambiar_contrasena(actual, llave, nueva, pista=pista)
    almacen.guardar_config(replace(nueva_config, kit_comprobado=datetime.now().isoformat(timespec="seconds")))
    return llave


def entrar(ruta_datos: Path | str | None, contrasena: str) -> bytes:
    """La llave maestra con tu contraseña (``ErrorContrasena`` si no es)."""
    actual = config(ruta_datos)
    if actual is None:
        raise ErrorValidacion("Tus datos no tienen contraseña.")
    return cifrado.abrir_con_contrasena(actual, contrasena)


def comprobar_kit(sesion: Sesion, kit: str) -> bool:
    """«¿Todavía tienes tu Kit?»: True si la llave abre tus datos (y se anota la fecha). No cambia nada más."""
    actual = _requiere(sesion)
    try:
        cifrado.abrir_con_kit(actual, kit)
    except ErrorContrasena:
        return False
    sesion.almacen.guardar_config(replace(actual, kit_comprobado=sesion.libro.ahora().isoformat(timespec="seconds")))
    return True


def ajustar_bloqueo(sesion: Sesion, minutos: int) -> cifrado.Config:
    """Tras cuántos minutos sin usar TALLY se vuelve a pedir la contraseña: uno de ``cifrado.OPCIONES_BLOQUEO``, o 0
    para apagar el bloqueo automático. Solo con contraseña: sin ella no hay pantalla a donde volver a entrar."""
    if isinstance(minutos, bool) or not isinstance(minutos, int) or minutos not in (0, *cifrado.OPCIONES_BLOQUEO):
        raise ErrorValidacion("El bloqueo automático es de 5, 10, 15, 25, 30 o 45 minutos, o de 1 hora (o apagado).")
    nueva = replace(_requiere(sesion), bloqueo_minutos=int(minutos))
    sesion.almacen.guardar_config(nueva)
    return nueva


# ---------------------------------------------------------------- internos


def _requiere(sesion: Sesion) -> cifrado.Config:
    actual = sesion.almacen.config_cifrado()
    if actual is None:
        raise ErrorValidacion("Tus datos no tienen contraseña.")
    return actual


def _verificar(ruta: Path, llave: bytes | None, antes: dict, bitacora_antes: int) -> None:
    """Vuelve a leer el archivo desde cero y exige que sea idéntico a lo que había."""
    almacen = Almacen(ruta)
    if llave is not None:
        almacen.desbloquear(llave)
    almacen.cargar()
    if almacen.estado_guardado != antes or len(almacen.bitacora()) != bitacora_antes:
        raise ErrorDatos("La verificación de tus datos no coincidió. No se cambió nada.")
