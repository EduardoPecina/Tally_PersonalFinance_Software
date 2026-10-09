"""Contraseña opcional de TALLY: cifrado, Kit de emergencia, respaldos y casos de error. Solo datos ficticios.

Lo más sensible de TALLY: estas pruebas buscan que **nunca** se pierdan datos y que **nunca** quede nada legible
en el disco con la contraseña puesta.
"""

import json
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

from conftest import AHORA
from motor import categorias, cifrado, cuentas, movimientos, perfil, respaldos, seguridad
from motor.errores import ErrorBloqueado, ErrorContrasena, ErrorDatos, ErrorValidacion
from motor.persistencia import Almacen
from motor.sesion import Sesion

CONTRASENA = "mi perro come tacos"
# Textos únicos para buscarlos en los archivos: si aparecen con la contraseña puesta, algo quedó sin cifrar.
SECRETOS = [b"Banco Supersecreto Ficticio", b"Pizza Misteriosa Ficticia", b"Usuaria Confidencial", b"98765.43"]


def reloj():
    return AHORA


@pytest.fixture(autouse=True)
def scrypt_rapido(monkeypatch):
    """scrypt real es lento a propósito; en pruebas se usa más ligero (los parámetros se guardan en cada caja)."""
    monkeypatch.setattr(cifrado, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})


@pytest.fixture
def raiz(tmp_path):
    return tmp_path


@pytest.fixture
def sesion(raiz):
    s = Sesion(raiz / "Datos" / "tally.db", reloj=reloj)
    with s.cambio() as libro:
        perfil.configurar(libro, "Usuaria Confidencial")
        banco = cuentas.crear(libro, "Banco Supersecreto Ficticio", "debito", saldo_inicial="98765.43",
                              fecha_creacion=date(2026, 7, 1)).id
        movimientos.registrar_gasto(libro, date(2026, 7, 3), banco, categorias.buscar(libro, "ALIMENTOS").id, 120,
                                    "Pizza Misteriosa Ficticia")
    return s


def _carpeta(raiz: Path) -> Path:
    return raiz / "Respaldos"


def _activar(sesion, raiz, kit=None):
    kit = kit or cifrado.nuevo_kit()
    resultado = seguridad.activar(sesion, CONTRASENA, CONTRASENA, kit, kit, carpeta_respaldos=_carpeta(raiz))
    return kit, resultado


def _bytes_en_disco(raiz: Path) -> bytes:
    """Todo lo que TALLY dejó en Datos y Respaldos (incluye el WAL y el contenido de los .zip)."""
    total = b""
    for ruta in raiz.rglob("*"):
        if ruta.is_file():
            total += ruta.read_bytes()
            if ruta.suffix == ".zip":
                with zipfile.ZipFile(ruta) as zz:
                    total += b"".join(zz.read(n) for n in zz.namelist())
    return total


def _hay_secretos(raiz: Path) -> list[bytes]:
    contenido = _bytes_en_disco(raiz)
    return [s for s in SECRETOS if s in contenido]


# ------------------------------------------------------------------ el Kit


def test_el_kit_tolera_errores_de_tecleo_y_detecta_letras_cambiadas():
    kit = cifrado.nuevo_kit()
    assert len(kit) == 29 and kit.count("-") == 5
    assert all(c in cifrado.ALFABETO for c in kit.replace("-", ""))
    for variante in (kit.lower(), kit.replace("-", " "), kit.replace("-", ""), f"TALLY-{kit}", f"  {kit}  "):
        assert cifrado.normalizar_kit(variante) == kit
    confusa = kit.replace("0", "O").replace("1", "I")               # O por 0 e I por 1: se entienden
    assert cifrado.normalizar_kit(confusa) == kit
    with pytest.raises(ErrorValidacion, match="faltan"):
        cifrado.normalizar_kit(kit[:-3])
    with pytest.raises(ErrorValidacion, match="sobran"):
        cifrado.normalizar_kit(kit + "AB")


# Una llave fija (no al azar): así la prueba da siempre lo mismo. Con 2 caracteres de verificación (10 bits), 1 de
# cada 1,024 letras cambiadas pasa el filtro; en esta llave, cambiar la «X» del 4.º grupo por «B».
KIT_FIJO = "7M1E-V8N2-FW9P-3GXA-Q4HY-BRGP"
COLADO = KIT_FIJO[:17] + "B" + KIT_FIJO[18:]


def test_la_verificacion_atrapa_casi_cualquier_letra_cambiada():
    assert cifrado.normalizar_kit(KIT_FIJO) == KIT_FIJO
    colados, total = [], 0
    for i, c in enumerate(KIT_FIJO):
        if c == "-":
            continue
        for otro in cifrado.ALFABETO:
            if otro != c:
                total += 1
                try:
                    cifrado.normalizar_kit(KIT_FIJO[:i] + otro + KIT_FIJO[i + 1:])
                    colados.append(KIT_FIJO[:i] + otro + KIT_FIJO[i + 1:])
                except ErrorValidacion:
                    pass
    assert total == 24 * 31 and colados == [COLADO]                 # 743 de 744 se detectan al teclear


def test_una_letra_cambiada_que_se_cuela_no_abre_nada_y_lo_dice():
    config, _llave = cifrado.preparar(CONTRASENA, KIT_FIJO, ahora=AHORA)
    assert cifrado.abrir_con_kit(config, KIT_FIJO.lower())
    with pytest.raises(ErrorContrasena, match="letra o número cambiado"):
        cifrado.abrir_con_kit(config, COLADO)
    with pytest.raises(ErrorContrasena, match="no es la de estos datos"):
        cifrado.abrir_con_kit(config, cifrado.nuevo_kit())          # otra llave (termina distinto)
    assert len({cifrado.nuevo_kit() for _ in range(200)}) == 200          # siempre distinto


def test_reglas_de_la_contrasena():
    with pytest.raises(ErrorValidacion, match="al menos 8"):
        cifrado.validar_contrasena("corta")
    with pytest.raises(ErrorValidacion, match="no son iguales"):
        cifrado.validar_contrasena(CONTRASENA, CONTRASENA + "x")
    with pytest.raises(ErrorValidacion, match="pista"):
        cifrado.validar_contrasena(CONTRASENA, pista=f"es {CONTRASENA}")
    cifrado.validar_contrasena("  mi perro come tacos ", CONTRASENA)     # los espacios de los lados no cuentan


def test_cajas_contrasena_y_kit():
    kit = cifrado.nuevo_kit()
    config, llave = cifrado.preparar("ñandú con acentos", kit, ahora=datetime(2026, 7, 20))
    assert cifrado.abrir_con_contrasena(config, "ñandú con acentos") == llave
    assert cifrado.abrir_con_contrasena(config, "ñandú con acentos") == llave   # otra forma de escribir ñ y ú
    assert cifrado.abrir_con_kit(config, kit.lower()) == llave
    assert cifrado.abrir(config, kit) == llave and cifrado.abrir(config, "ñandú con acentos") == llave
    with pytest.raises(ErrorContrasena, match="no es la contraseña"):
        cifrado.abrir_con_contrasena(config, "Ñandú con acentos")      # distingue mayúsculas
    with pytest.raises(ErrorContrasena, match="no es la de estos datos"):
        cifrado.abrir_con_kit(config, cifrado.nuevo_kit())
    with pytest.raises(ErrorContrasena):
        cifrado.abrir(config, "cualquier otra cosa")
    assert config.kit_final == kit[-4:] and config.kit_creado == "2026-07-20"
    assert "llave" not in config.a_json() or llave.hex() not in config.a_json()   # la llave nunca va en claro
    nueva = cifrado.cambiar_contrasena(config, llave, "otra frase larga")
    assert cifrado.abrir_con_contrasena(nueva, "otra frase larga") == llave
    assert cifrado.abrir_con_kit(nueva, kit) == llave                   # el Kit sigue sirviendo
    with pytest.raises(ErrorContrasena):
        cifrado.abrir_con_contrasena(nueva, "ñandú con acentos")


def test_un_registro_movido_o_modificado_se_detecta():
    cifrador = cifrado.Cifrador(b"k" * 32)
    texto = cifrador.cifrar({"nombre": "Ficticio"}, "entidad:cuenta:A")
    assert cifrador.descifrar(texto, "entidad:cuenta:A") == {"nombre": "Ficticio"}
    with pytest.raises(ErrorDatos, match="modificado"):
        cifrador.descifrar(texto, "entidad:cuenta:B")                 # el mismo dato en otro lugar
    roto = texto[:-6] + ("A" if texto[-6] != "A" else "B") + texto[-5:]
    with pytest.raises(ErrorDatos):
        cifrador.descifrar(roto, "entidad:cuenta:A")
    with pytest.raises(ErrorDatos, match="sin cifrar"):
        cifrador.descifrar('{"nombre": "x"}', "entidad:cuenta:A")
    assert cifrador.cifrar({"a": 1}, "x") != cifrador.cifrar({"a": 1}, "x")    # nunca dos veces igual


def test_intentos_esperan_cada_vez_mas():
    ahora = [0.0]
    intentos = cifrado.Intentos(reloj=lambda: ahora[0])
    intentos.fallo()
    intentos.fallo()
    assert intentos.espera() == 0                                   # los primeros dos, sin espera
    intentos.fallo()
    assert intentos.espera() == 2
    ahora[0] += 2
    intentos.fallo()
    assert intentos.espera() == 4
    for _ in range(10):
        intentos.fallo()
    assert intentos.espera() == 60                                  # nunca más de un minuto
    intentos.acierto()
    assert intentos.espera() == 0 and intentos.fallidos == 0


# ------------------------------------------------------------ activar


def test_activar_cifra_todo_y_no_deja_nada_legible(sesion, raiz):
    respaldos.crear(sesion, _carpeta(raiz))                          # un respaldo guardado de antes
    assert _hay_secretos(raiz)                                       # (antes, sí se ven)
    antes = sesion.almacen.estado_guardado
    kit, resultado = _activar(sesion, raiz)
    assert resultado.respaldos_convertidos == 2 and not resultado.respaldos_con_problemas  # el previo + el de seguridad
    assert _hay_secretos(raiz) == []                                  # nada legible: ni base, ni WAL, ni respaldos
    assert sesion.almacen.estado_guardado == antes
    with pytest.raises(ErrorBloqueado):
        Sesion(raiz / "Datos" / "tally.db", reloj=reloj)
    llave = seguridad.entrar(raiz / "Datos" / "tally.db", CONTRASENA)
    otra = Sesion(raiz / "Datos" / "tally.db", reloj=reloj, llave=llave)
    assert otra.almacen.estado_guardado == antes
    assert len(otra.almacen.bitacora()) == len(sesion.almacen.bitacora())


def test_lo_nuevo_tambien_se_guarda_cifrado(sesion, raiz):
    _activar(sesion, raiz)
    with sesion.cambio() as libro:
        cuentas.crear(libro, "Cuenta Nueva Ficticia Reservada", "ahorro", fecha_creacion=date(2026, 7, 10))
    assert b"Cuenta Nueva Ficticia Reservada" not in _bytes_en_disco(raiz)
    llave = seguridad.entrar(raiz / "Datos" / "tally.db", CONTRASENA)
    otra = Sesion(raiz / "Datos" / "tally.db", reloj=reloj, llave=llave)
    assert any(c.nombre == "Cuenta Nueva Ficticia Reservada" for c in otra.libro.cuentas())
    # La bitácora también se lee bien (y está cifrada).
    assert any(r.despues and r.despues.get("nombre") == "Cuenta Nueva Ficticia Reservada"
               for r in otra.almacen.bitacora())


def test_no_se_activa_sin_comprobar_el_kit_ni_con_contrasenas_distintas(sesion, raiz):
    kit = cifrado.nuevo_kit()
    with pytest.raises(ErrorValidacion, match="no es la de tu Kit"):
        seguridad.activar(sesion, CONTRASENA, CONTRASENA, kit, cifrado.nuevo_kit(), carpeta_respaldos=_carpeta(raiz))
    with pytest.raises(ErrorValidacion, match="no son iguales"):
        seguridad.activar(sesion, CONTRASENA, "otra cosa larga", kit, kit, carpeta_respaldos=_carpeta(raiz))
    assert seguridad.config(raiz / "Datos" / "tally.db") is None
    assert not list(_carpeta(raiz).glob("*.zip"))                    # ni siquiera se hizo el respaldo
    _activar(sesion, raiz)
    with pytest.raises(ErrorValidacion, match="ya tienen contraseña"):
        _activar(sesion, raiz)


def test_si_algo_falla_a_medio_camino_no_cambia_nada(sesion, raiz, monkeypatch):
    antes = sesion.almacen.estado_guardado

    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("disco lleno (simulado)")

    original = Almacen._poner_meta
    llamadas = []

    def poner_meta(conexion, clave, valor):
        llamadas.append(clave)
        if clave == "cifrado":
            falla()
        return original(conexion, clave, valor)

    monkeypatch.setattr(Almacen, "_poner_meta", staticmethod(poner_meta))
    with pytest.raises(ErrorDatos, match="No cambió nada"):
        _activar(sesion, raiz)
    monkeypatch.undo()
    assert seguridad.config(raiz / "Datos" / "tally.db") is None
    otra = Sesion(raiz / "Datos" / "tally.db", reloj=reloj)          # abre normal, sin contraseña
    assert otra.almacen.estado_guardado == antes


def test_si_la_verificacion_no_coincide_se_deshace(sesion, raiz, monkeypatch):
    antes = sesion.almacen.estado_guardado

    def verificacion_mala(*args):
        raise ErrorDatos("La verificación de tus datos no coincidió. No se cambió nada.")

    monkeypatch.setattr(seguridad, "_verificar", verificacion_mala)
    with pytest.raises(ErrorDatos, match="no coincidió"):
        _activar(sesion, raiz)
    assert seguridad.config(raiz / "Datos" / "tally.db") is None
    assert Sesion(raiz / "Datos" / "tally.db", reloj=reloj).almacen.estado_guardado == antes


def test_un_dato_cifrado_modificado_por_fuera_no_se_abre_en_silencio(sesion, raiz):
    _activar(sesion, raiz)
    ruta = raiz / "Datos" / "tally.db"
    with sqlite3.connect(ruta) as conexion:
        tipo, i, datos = conexion.execute("SELECT tipo, id, datos FROM entidades WHERE tipo='cuenta'").fetchone()
        conexion.execute("UPDATE entidades SET datos = ? WHERE tipo = ? AND id = ?",
                         (datos[:-8] + "AAAAAAAA", tipo, i))
    llave = seguridad.entrar(ruta, CONTRASENA)
    with pytest.raises(ErrorDatos):
        Sesion(ruta, reloj=reloj, llave=llave)


# ------------------------------------------------------- cambiar, olvidar, quitar


def test_cambiar_contrasena_y_el_kit_sigue_igual(sesion, raiz):
    kit, _ = _activar(sesion, raiz)
    ruta = raiz / "Datos" / "tally.db"
    with pytest.raises(ErrorContrasena):
        seguridad.cambiar_contrasena(sesion, "no es esta", "frase nueva larga", "frase nueva larga")
    seguridad.cambiar_contrasena(sesion, CONTRASENA, "frase nueva larga", "frase nueva larga", pista="la nueva")
    with pytest.raises(ErrorContrasena):
        seguridad.entrar(ruta, CONTRASENA)
    llave = seguridad.entrar(ruta, "frase nueva larga")
    assert cifrado.abrir_con_kit(seguridad.config(ruta), kit) == llave
    assert seguridad.config(ruta).pista == "la nueva"
    seguridad.cambiar_contrasena(sesion, kit, "otra frase distinta", "otra frase distinta")    # con el Kit
    assert seguridad.entrar(ruta, "otra frase distinta") == llave


def test_olvide_mi_contrasena_con_el_kit(sesion, raiz):
    kit, _ = _activar(sesion, raiz)
    ruta = raiz / "Datos" / "tally.db"
    antes = sesion.almacen.estado_guardado
    with pytest.raises(ErrorValidacion, match="error al escribir"):
        seguridad.recuperar(ruta, kit[:-1] + ("A" if kit[-1] != "A" else "B"), "nueva frase larga",
                            "nueva frase larga")
    with pytest.raises(ErrorContrasena, match="no es la de estos datos"):
        seguridad.recuperar(ruta, cifrado.nuevo_kit(), "nueva frase larga", "nueva frase larga")
    llave = seguridad.recuperar(ruta, kit.lower().replace("-", " "), "nueva frase larga", "nueva frase larga")
    assert Sesion(ruta, reloj=reloj, llave=llave).almacen.estado_guardado == antes        # no se perdió nada
    assert seguridad.entrar(ruta, "nueva frase larga") == llave
    assert seguridad.recuperar(ruta, kit, "y otra mas larga", "y otra mas larga") == llave  # el Kit sirve siempre


def test_quitar_la_contrasena_deja_todo_como_antes(sesion, raiz):
    respaldos.crear(sesion, _carpeta(raiz))
    antes = sesion.almacen.estado_guardado
    kit, _ = _activar(sesion, raiz)
    with pytest.raises(ErrorContrasena):
        seguridad.desactivar(sesion, "no es la contraseña", carpeta_respaldos=_carpeta(raiz))
    resultado = seguridad.desactivar(sesion, kit, carpeta_respaldos=_carpeta(raiz))     # también con el Kit
    assert resultado.respaldos_convertidos == 2
    assert seguridad.config(raiz / "Datos" / "tally.db") is None
    assert Sesion(raiz / "Datos" / "tally.db", reloj=reloj).almacen.estado_guardado == antes
    for ruta in _carpeta(raiz).glob("*.zip"):
        assert respaldos.contrasena_de(ruta) is None and respaldos.inspeccionar(ruta).perfil == "Usuaria Confidencial"


def test_comprobar_kit_y_bloqueo(sesion, raiz):
    kit, _ = _activar(sesion, raiz)
    assert not seguridad.comprobar_kit(sesion, cifrado.nuevo_kit())
    assert seguridad.comprobar_kit(sesion, kit)
    config = seguridad.config(raiz / "Datos" / "tally.db")
    assert config.kit_comprobado.startswith("2026-07-20")
    assert not config.recordatorio_kit(date(2026, 8, 1)) and config.recordatorio_kit(date(2026, 11, 1))
    assert seguridad.ajustar_bloqueo(sesion, 30).bloqueo_minutos == 30
    with pytest.raises(ErrorValidacion):
        seguridad.ajustar_bloqueo(sesion, 999)


def test_tiempos_del_bloqueo_automatico(sesion, raiz):
    with pytest.raises(ErrorValidacion, match="no tienen contraseña"):          # sin contraseña no hay bloqueo
        seguridad.ajustar_bloqueo(sesion, 10)
    _activar(sesion, raiz)
    assert seguridad.config(raiz / "Datos" / "tally.db").bloqueo_minutos == 10           # viene encendido
    for minutos in (5, 10, 15, 25, 30, 45, 60, 0):                                      # 0 = apagado
        assert seguridad.ajustar_bloqueo(sesion, minutos).bloqueo_minutos == minutos
        assert seguridad.config(raiz / "Datos" / "tally.db").bloqueo_minutos == minutos
    for invalido in (20, 90, 240, -5, True, "10"):
        with pytest.raises(ErrorValidacion, match="5, 10, 15, 25, 30 o 45 minutos"):
            seguridad.ajustar_bloqueo(sesion, invalido)


# ----------------------------------------------------------------- respaldos


def test_respaldo_cifrado_en_otra_pc_con_contrasena_o_kit(sesion, raiz, tmp_path_factory):
    kit, _ = _activar(sesion, raiz)
    antes = sesion.almacen.estado_guardado
    respaldo = respaldos.crear(sesion, _carpeta(raiz))
    manifiesto = json.loads(zipfile.ZipFile(respaldo).read("manifiesto.json"))
    assert "resumen" not in manifiesto and "cifrado" in manifiesto            # sin nombre ni montos
    assert respaldos.contrasena_de(respaldo).llave_id == seguridad.config(raiz / "Datos" / "tally.db").llave_id
    assert respaldos.inspeccionar(respaldo, llave=sesion.almacen.llave).cifrado     # en esta PC, sin pedir nada

    for secreto in (CONTRASENA, kit):
        otra_pc = tmp_path_factory.mktemp("otra_pc")
        nueva = Sesion(otra_pc / "Datos" / "tally.db", reloj=reloj)            # TALLY recién instalado
        with pytest.raises(ErrorBloqueado, match="tiene contraseña"):
            respaldos.inspeccionar(respaldo)
        with pytest.raises(ErrorContrasena):
            respaldos.restaurar(nueva, respaldo, carpeta_seguridad=otra_pc / "Respaldos", secreto="no es")
        resultado = respaldos.restaurar(nueva, respaldo, carpeta_seguridad=otra_pc / "Respaldos", secreto=secreto)
        assert resultado.adopto_contrasena and resultado.con_kit == (secreto == kit)
        assert nueva.almacen.estado_guardado == antes
        # La PC nueva quedó con la misma contraseña y el mismo Kit.
        llave = seguridad.entrar(otra_pc / "Datos" / "tally.db", CONTRASENA)
        assert Sesion(otra_pc / "Datos" / "tally.db", reloj=reloj, llave=llave).almacen.estado_guardado == antes
        assert cifrado.abrir_con_kit(seguridad.config(otra_pc / "Datos" / "tally.db"), kit) == llave
        assert not [s for s in SECRETOS if s in (otra_pc / "Datos" / "tally.db").read_bytes()]


def test_respaldo_viejo_tras_cambiar_contrasena(sesion, raiz, tmp_path_factory):
    kit, _ = _activar(sesion, raiz)
    viejo = respaldos.crear(sesion, _carpeta(raiz))
    seguridad.cambiar_contrasena(sesion, CONTRASENA, "frase nueva larga", "frase nueva larga")
    # En esta PC, con TALLY abierto, se restaura sin pedir nada.
    respaldos.restaurar(sesion, viejo, carpeta_seguridad=_carpeta(raiz))
    assert seguridad.entrar(raiz / "Datos" / "tally.db", "frase nueva larga")      # conserva tu contraseña actual
    # En otra PC: con la contraseña de ESE día o con el Kit, no con la nueva.
    otra_pc = tmp_path_factory.mktemp("otra_pc")
    nueva = Sesion(otra_pc / "Datos" / "tally.db", reloj=reloj)
    with pytest.raises(ErrorContrasena):
        respaldos.inspeccionar(viejo, secreto="frase nueva larga")
    assert respaldos.inspeccionar(viejo, secreto=CONTRASENA).cifrado
    assert respaldos.inspeccionar(viejo, secreto=kit).movimientos == 2
    respaldos.restaurar(nueva, viejo, carpeta_seguridad=otra_pc / "Respaldos", secreto=kit)


def test_respaldo_sin_contrasena_en_tally_con_contrasena(sesion, raiz, tmp_path_factory):
    otra_pc = tmp_path_factory.mktemp("otra_pc")
    plano = respaldos.crear(sesion, otra_pc)                              # de antes de poner la contraseña
    _activar(sesion, raiz)
    respaldos.restaurar(sesion, plano, carpeta_seguridad=_carpeta(raiz))
    assert _hay_secretos(raiz) == []                                      # se guarda cifrado con tu contraseña
    assert seguridad.config(raiz / "Datos" / "tally.db") is not None


def test_copia_sin_contrasena_solo_con_la_sesion_abierta(sesion, raiz):
    _activar(sesion, raiz)
    copia = respaldos.crear(sesion, raiz / "USB", sin_contrasena=True)
    assert respaldos.contrasena_de(copia) is None
    assert respaldos.inspeccionar(copia).perfil == "Usuaria Confidencial"
    bloqueada = Almacen(raiz / "Datos" / "tally.db")
    with pytest.raises(ErrorBloqueado):
        respaldos._crear_desde(bloqueada, AHORA, raiz / "USB", "x", sin_contrasena=True)


def test_el_instalador_respalda_y_mueve_datos_con_contrasena_sin_conocerla(sesion, raiz, tmp_path_factory):
    kit, _ = _activar(sesion, raiz)
    ruta = raiz / "Datos" / "tally.db"
    destino = tmp_path_factory.mktemp("instalador")
    respaldo = respaldos.respaldar_archivo_de_datos(ruta, destino)         # sin llave
    assert respaldos.contrasena_de(respaldo) is not None
    assert respaldos.inspeccionar(respaldo, secreto=kit).movimientos == 2
    assert respaldos.leer_perfil(ruta) is None                            # el perfil está cifrado: no se lee
    copia = respaldos.copiar_archivo_de_datos(ruta, destino / "nuevo" / "tally.db")
    llave = seguridad.entrar(copia, CONTRASENA)
    assert Sesion(copia, reloj=reloj, llave=llave).almacen.estado_guardado == sesion.almacen.estado_guardado


def test_restaurar_un_tally_db_cifrado(sesion, raiz, tmp_path_factory):
    _activar(sesion, raiz)
    otra_pc = tmp_path_factory.mktemp("otra_pc")
    nueva = Sesion(otra_pc / "Datos" / "tally.db", reloj=reloj)
    with pytest.raises(ErrorBloqueado):
        respaldos.inspeccionar(raiz / "Datos" / "tally.db")
    resultado = respaldos.restaurar(nueva, raiz / "Datos" / "tally.db", carpeta_seguridad=otra_pc / "R",
                                    secreto=CONTRASENA)
    assert resultado.adopto_contrasena and nueva.almacen.estado_guardado == sesion.almacen.estado_guardado


def test_un_respaldo_cifrado_alterado_no_se_restaura(sesion, raiz, tmp_path_factory):
    _activar(sesion, raiz)
    respaldo = respaldos.crear(sesion, _carpeta(raiz))
    with zipfile.ZipFile(respaldo) as zz:
        manifiesto, datos = json.loads(zz.read("manifiesto.json")), json.loads(zz.read("datos.json"))
    tipo = next(iter(datos["entidades"]))
    i = next(iter(datos["entidades"][tipo]))
    otro_tipo = next(t for t in datos["entidades"] if t != tipo)
    otro_i = next(iter(datos["entidades"][otro_tipo]))
    datos["entidades"][tipo][i] = datos["entidades"][otro_tipo][otro_i]          # registros intercambiados
    crudo = json.dumps(datos).encode()
    import hashlib

    manifiesto["sha256"] = hashlib.sha256(crudo).hexdigest()                   # alguien rehízo la huella
    alterado = tmp_path_factory.mktemp("x") / "alterado.zip"
    with zipfile.ZipFile(alterado, "w") as zz:
        zz.writestr("manifiesto.json", json.dumps(manifiesto))
        zz.writestr("datos.json", crudo)
    with pytest.raises(ErrorDatos, match="modificado"):
        respaldos.inspeccionar(alterado, llave=sesion.almacen.llave)


def test_los_respaldos_automaticos_salen_cifrados(sesion, raiz):
    _activar(sesion, raiz)
    with sesion.cambio() as libro:
        perfil.ajustar(libro, respaldo_diario=True)
    ruta = respaldos.respaldo_automatico(sesion, _carpeta(raiz))
    assert respaldos.contrasena_de(ruta) is not None
    assert _hay_secretos(raiz) == []


def test_contrasena_larga_con_emojis_y_espacios(sesion, raiz):
    contrasena = "🐶 mi perro Ñoño come 🌮 tacos los martes " * 5
    kit = cifrado.nuevo_kit()
    seguridad.activar(sesion, contrasena, contrasena.strip(), kit, kit, carpeta_respaldos=_carpeta(raiz))
    assert seguridad.entrar(raiz / "Datos" / "tally.db", contrasena.strip())
    assert seguridad.entrar(raiz / "Datos" / "tally.db", "  " + contrasena)


def test_si_la_pc_se_apaga_a_medio_cifrar_los_datos_siguen_intactos(sesion, raiz, monkeypatch):
    """Simula un apagón justo antes de confirmar: SQLite descarta la transacción a medias."""
    antes = sesion.almacen.estado_guardado
    original = Almacen._transformar

    def apagon(self, convertir, **kwargs):
        def a_medias(valor, contexto):
            resultado = convertir(valor, contexto)
            if contexto.startswith("bitacora"):
                raise KeyboardInterrupt("se fue la luz (simulado)")
            return resultado
        return original(self, a_medias, **kwargs)

    monkeypatch.setattr(Almacen, "_transformar", apagon)
    with pytest.raises(KeyboardInterrupt):
        _activar(sesion, raiz)
    monkeypatch.undo()
    assert seguridad.config(raiz / "Datos" / "tally.db") is None
    assert Sesion(raiz / "Datos" / "tally.db", reloj=reloj).almacen.estado_guardado == antes


def test_otra_pestana_abierta_sin_contrasena_no_escribe_en_claro(sesion, raiz):
    """Una sesión vieja (abierta antes de poner la contraseña) no puede guardar datos sin cifrar encima."""
    vieja = Sesion(raiz / "Datos" / "tally.db", reloj=reloj)
    _activar(sesion, raiz)
    with pytest.raises((ErrorBloqueado, ErrorDatos)):
        with vieja.cambio() as libro:
            cuentas.crear(libro, "Cuenta Escrita En Claro", "ahorro", fecha_creacion=date(2026, 7, 10))
    assert b"Cuenta Escrita En Claro" not in _bytes_en_disco(raiz)
