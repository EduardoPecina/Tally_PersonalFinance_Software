"""Perfil local del usuario (solo su nombre, para la bienvenida).

No hay cuentas de usuario ni inicio de sesión: el perfil vive en el mismo
archivo de datos que las finanzas.
"""

from __future__ import annotations

from dataclasses import replace

from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Perfil
from motor.textos import normalizar_nombre


def necesita_bienvenida(libro: Libro) -> bool:
    """True la primera vez que se abre TALLY (aún no hay perfil)."""
    return libro.perfil is None


def configurar(libro: Libro, nombre: str) -> Perfil:
    nombre = normalizar_nombre(nombre)
    if libro.perfil is None:
        libro.perfil = Perfil(nombre=nombre, creado_en=libro.ahora())
    else:
        libro.perfil = replace(libro.perfil, nombre=nombre)
    return libro.perfil


MAXIMO_RESPALDOS = 100
MAXIMO_DIAS_PARA_RECLAMAR = 365
TEMAS = {"claro": "Claro", "oscuro": "Oscuro"}
# La clave «acento» se queda así (ya está guardada en los perfiles y en los nombres de los .ico); se muestra «Violeta».
ICONOS = {"claro": "Claro", "oscuro": "Oscuro", "acento": "Violeta", "gris": "Gris"}


def ajustar(
    libro: Libro,
    *,
    nombre: str | None = None,
    respaldo_diario: bool | None = None,
    respaldos_a_conservar: int | None = None,
    periodo_inicial: str | None = None,
    tema: str | None = None,
    icono: str | None = None,
    dias_para_reclamar: int | None = None,
    actualizar_precios: bool | None = None,
) -> Perfil:
    """Cambia las preferencias (página Configuración). Solo cambia lo que se indique."""
    from motor.reportes import PERIODOS

    if libro.perfil is None:
        raise ErrorValidacion("Primero escribe tu nombre en la bienvenida.")
    cambios: dict = {}
    if nombre is not None:
        cambios["nombre"] = normalizar_nombre(nombre)
    if respaldo_diario is not None:
        cambios["respaldo_diario"] = bool(respaldo_diario)
    if respaldos_a_conservar is not None:
        if isinstance(respaldos_a_conservar, bool) or not 1 <= int(respaldos_a_conservar) <= MAXIMO_RESPALDOS:
            raise ErrorValidacion(f"Conserva entre 1 y {MAXIMO_RESPALDOS} respaldos automáticos.")
        cambios["respaldos_a_conservar"] = int(respaldos_a_conservar)
    if periodo_inicial is not None:
        if periodo_inicial not in PERIODOS:
            raise ErrorValidacion("Ese periodo no existe.")
        cambios["periodo_inicial"] = periodo_inicial
    if tema is not None:
        if tema not in TEMAS:
            raise ErrorValidacion("Ese tema no existe.")
        cambios["tema"] = tema
    if icono is not None:
        if icono not in ICONOS:
            raise ErrorValidacion("Ese ícono no existe.")
        cambios["icono"] = icono
    if dias_para_reclamar is not None:
        if isinstance(dias_para_reclamar, bool) or not 1 <= int(dias_para_reclamar) <= MAXIMO_DIAS_PARA_RECLAMAR:
            raise ErrorValidacion(f"Los días para reclamar van de 1 a {MAXIMO_DIAS_PARA_RECLAMAR}.")
        cambios["dias_para_reclamar"] = int(dias_para_reclamar)
    if actualizar_precios is not None:
        cambios["actualizar_precios"] = bool(actualizar_precios)
    libro.perfil = replace(libro.perfil, **cambios)
    return libro.perfil
