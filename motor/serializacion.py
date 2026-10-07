"""Conversión entre entidades del motor y diccionarios JSON.

Es el formato estable que usan la base de datos, los respaldos y la
bitácora. Fechas en ISO 8601, importes en centavos enteros.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

from motor.errores import ErrorDatos
from motor.libro import Libro
from motor.modelo import (
    Avaluo,
    Bien,
    Categoria,
    ClaseCategoria,
    Cuenta,
    Grupo,
    InversionPlazo,
    MetodoDepreciacion,
    Operacion,
    Meta,
    Aporte,
    Prestamo,
    Recurrente,
    OperacionValor,
    Partida,
    Perfil,
    Rubro,
    TipoCuenta,
    TipoOperacion,
    TipoOperacionValor,
)

# Tipos de entidad, en el orden en que se cargan.
ENTIDADES = ("perfil", "grupo", "rubro", "categoria", "cuenta", "operacion", "valor", "plazo", "bien",
             "prestamo", "recurrente", "meta")
ID_PERFIL = "perfil"


def _fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _momento(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def _iso(valor: date | datetime | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    return valor.isoformat()


# ---------------------------------------------------------------- a dict


def perfil_a_dict(p: Perfil) -> dict:
    return {"nombre": p.nombre, "moneda": p.moneda, "creado_en": _iso(p.creado_en),
            "respaldo_diario": p.respaldo_diario, "respaldos_a_conservar": p.respaldos_a_conservar,
            "periodo_inicial": p.periodo_inicial, "tema": p.tema, "icono": p.icono,
            "dias_para_reclamar": p.dias_para_reclamar, "clasificaciones": p.clasificaciones,
            "actualizar_precios": p.actualizar_precios, "iva": str(p.iva), "ingreso_esperado": p.ingreso_esperado,
            "meta_ahorro": p.meta_ahorro}


def grupo_a_dict(g: Grupo) -> dict:
    return {"id": g.id, "nombre": g.nombre, "orden": g.orden}


def rubro_a_dict(r: Rubro) -> dict:
    return {"id": r.id, "nombre": r.nombre, "clase": r.clase.value, "orden": r.orden,
            **({"presupuesto": r.presupuesto} if r.presupuesto is not None else {})}


def categoria_a_dict(c: Categoria) -> dict:
    return {
        "id": c.id, "nombre": c.nombre, "clase": c.clase.value, "grupo_id": c.grupo_id,
        "activa": c.activa, "principal": c.principal, "orden": c.orden, "rubro_id": c.rubro_id,
        **({"secundario": True} if c.secundario else {}),
    }


def cuenta_a_dict(c: Cuenta) -> dict:
    return {
        "id": c.id, "nombre": c.nombre, "tipo": c.tipo.value, "fecha_creacion": _iso(c.fecha_creacion),
        "en_disponible": c.en_disponible, "moneda": c.moneda, "activa": c.activa,
        "institucion": c.institucion, "notas": c.notas, "orden": c.orden,
        "limite_credito": c.limite_credito, "dia_corte": c.dia_corte, "dia_pago": c.dia_pago,
        "dias_para_pagar": c.dias_para_pagar, "dias_habiles": c.dias_habiles, "recorrer_inhabil": c.recorrer_inhabil,
        **({"plusvalia_registrada": c.plusvalia_registrada} if c.plusvalia_registrada else {}),
        **({"tasa_anual": str(c.tasa_anual)} if c.tasa_anual is not None else {}),
        **({"cat": str(c.cat)} if c.cat is not None else {}),
        **({"tasa_incluye_iva": True} if c.tasa_incluye_iva else {}),
    }


def valor_a_dict(v: OperacionValor) -> dict:
    return {"id": v.id, "cuenta_id": v.cuenta_id, "fecha": _iso(v.fecha), "tipo": v.tipo.value, "simbolo": v.simbolo,
            "titulos": str(v.titulos), "precio": str(v.precio), "moneda": v.moneda,
            "tipo_cambio": str(v.tipo_cambio), "comision": str(v.comision), "notas": v.notas}


def plazo_a_dict(p: InversionPlazo) -> dict:
    return {"id": p.id, "cuenta_id": p.cuenta_id, "nombre": p.nombre, "fecha_inicio": _iso(p.fecha_inicio),
            "monto": p.monto, "tasa_anual": str(p.tasa_anual), "plazo_dias": p.plazo_dias, "notas": p.notas}


def operacion_a_dict(op: Operacion) -> dict:
    return {
        "id": op.id, "fecha": _iso(op.fecha), "tipo": op.tipo.value,
        "partidas": [
            {"importe": p.importe, "cuenta_id": p.cuenta_id, "categoria_id": p.categoria_id} for p in op.partidas
        ],
        "descripcion": op.descripcion, "notas": op.notas, "secuencia": op.secuencia,
        "creado_en": _iso(op.creado_en), "modificado_en": _iso(op.modificado_en),
        **({"msi": op.msi} if op.msi else {}),
        **({"liquida": op.liquida} if op.liquida else {}),
    }


# ---------------------------------------------------------------- desde dict


def perfil_desde_dict(d: dict) -> Perfil:
    return Perfil(nombre=d["nombre"], moneda=d.get("moneda", "MXN"), creado_en=_momento(d["creado_en"]),
                  respaldo_diario=d.get("respaldo_diario", True),
                  respaldos_a_conservar=d.get("respaldos_a_conservar", 10),
                  periodo_inicial=d.get("periodo_inicial", "mes_actual"), tema=d.get("tema", "claro"),
                  icono=d.get("icono", "claro"), dias_para_reclamar=d.get("dias_para_reclamar", 45),
                  clasificaciones=d.get("clasificaciones", 1),
                  actualizar_precios=d.get("actualizar_precios", False), iva=Decimal(d.get("iva", "16")),
                  ingreso_esperado=d.get("ingreso_esperado"), meta_ahorro=d.get("meta_ahorro", 10))


def grupo_desde_dict(d: dict) -> Grupo:
    return Grupo(id=d["id"], nombre=d["nombre"], orden=d.get("orden", 0))


def rubro_desde_dict(d: dict) -> Rubro:
    return Rubro(id=d["id"], nombre=d["nombre"], clase=ClaseCategoria(d["clase"]), orden=d.get("orden", 0),
                 presupuesto=d.get("presupuesto"))


def categoria_desde_dict(d: dict) -> Categoria:
    return Categoria(
        id=d["id"], nombre=d["nombre"], clase=ClaseCategoria(d["clase"]), grupo_id=d.get("grupo_id"),
        activa=d.get("activa", True), principal=d.get("principal", False), orden=d.get("orden", 0),
        rubro_id=d.get("rubro_id"),   # los datos anteriores a la 0.4 no tienen rubros (motor/catalogo.py)
        secundario=d.get("secundario", False),
    )


def cuenta_desde_dict(d: dict) -> Cuenta:
    return Cuenta(
        id=d["id"], nombre=d["nombre"], tipo=TipoCuenta(d["tipo"]), fecha_creacion=_fecha(d["fecha_creacion"]),
        en_disponible=d["en_disponible"], moneda=d.get("moneda", "MXN"), activa=d.get("activa", True),
        institucion=d.get("institucion", ""), notas=d.get("notas", ""), orden=d.get("orden", 0),
        limite_credito=d.get("limite_credito"), dia_corte=d.get("dia_corte"), dia_pago=d.get("dia_pago"),
        dias_para_pagar=d.get("dias_para_pagar"), dias_habiles=d.get("dias_habiles", False),
        recorrer_inhabil=d.get("recorrer_inhabil", True), plusvalia_registrada=d.get("plusvalia_registrada", 0),
        tasa_anual=Decimal(d["tasa_anual"]) if d.get("tasa_anual") is not None else None,
        cat=Decimal(d["cat"]) if d.get("cat") is not None else None,
        tasa_incluye_iva=d.get("tasa_incluye_iva", False),
    )


def valor_desde_dict(d: dict) -> OperacionValor:
    return OperacionValor(
        id=d["id"], cuenta_id=d["cuenta_id"], fecha=_fecha(d["fecha"]), tipo=TipoOperacionValor(d["tipo"]),
        simbolo=d["simbolo"], titulos=Decimal(d["titulos"]), precio=Decimal(d["precio"]), moneda=d.get("moneda", "MXN"),
        tipo_cambio=Decimal(d.get("tipo_cambio", "1")), comision=Decimal(d.get("comision", "0")), notas=d.get("notas", ""),
    )


def bien_a_dict(b: Bien) -> dict:
    return {"id": b.cuenta_id, "cuenta_id": b.cuenta_id, "clase": b.clase, "metodo": b.metodo.value,
            "vida_anios": str(b.vida_anios), "tasa_anual": str(b.tasa_anual), "rescate": str(b.rescate),
            "avaluos": [{"fecha": _iso(a.fecha), "valor": a.valor} for a in b.avaluos],
            "fecha_baja": _iso(b.fecha_baja) if b.fecha_baja else None, "operaciones_baja": list(b.operaciones_baja)}


def bien_desde_dict(d: dict) -> Bien:
    return Bien(
        cuenta_id=d["cuenta_id"], clase=d.get("clase", "otro"), metodo=MetodoDepreciacion(d["metodo"]),
        vida_anios=Decimal(d.get("vida_anios", "0")), tasa_anual=Decimal(d.get("tasa_anual", "0")),
        rescate=Decimal(d.get("rescate", "0")),
        avaluos=tuple(Avaluo(_fecha(a["fecha"]), a["valor"]) for a in d.get("avaluos", [])),
        fecha_baja=_fecha(d["fecha_baja"]) if d.get("fecha_baja") else None,
        operaciones_baja=tuple(d.get("operaciones_baja", [])),
    )


def prestamo_a_dict(p: Prestamo) -> dict:
    return {"id": p.cuenta_id, "cuenta_id": p.cuenta_id, "clase": p.clase, "monto": p.monto,
            "tasa_anual": str(p.tasa_anual), "plazo_meses": p.plazo_meses, "fecha_inicio": _iso(p.fecha_inicio),
            "iva": str(p.iva) if p.iva is not None else None, "pago_pactado": p.pago_pactado,
            "dia_pago": p.dia_pago, "cat": str(p.cat) if p.cat is not None else None}


def recurrente_a_dict(r: Recurrente) -> dict:
    return {"id": r.id, "nombre": r.nombre, "tipo": r.tipo.value, "monto": r.monto, "cuenta_id": r.cuenta_id,
            "frecuencia": r.frecuencia, "inicio": _iso(r.inicio), "categoria_id": r.categoria_id,
            "destino_id": r.destino_id, "fin": _iso(r.fin), "suscripcion": r.suscripcion, "activa": r.activa,
            "notas": r.notas}


def recurrente_desde_dict(d: dict) -> Recurrente:
    return Recurrente(
        id=d["id"], nombre=d["nombre"], tipo=TipoOperacion(d["tipo"]), monto=d["monto"], cuenta_id=d["cuenta_id"],
        frecuencia=d["frecuencia"], inicio=_fecha(d["inicio"]), categoria_id=d.get("categoria_id"),
        destino_id=d.get("destino_id"), fin=_fecha(d.get("fin")), suscripcion=d.get("suscripcion", False),
        activa=d.get("activa", True), notas=d.get("notas", ""),
    )


def meta_a_dict(m: Meta) -> dict:
    return {"id": m.id, "nombre": m.nombre, "objetivo": m.objetivo, "cuenta_id": m.cuenta_id,
            "fecha_limite": _iso(m.fecha_limite), "emergencia": m.emergencia, "creada": _iso(m.creada),
            "activa": m.activa, "notas": m.notas,
            "aportes": [{"fecha": _iso(a.fecha), "centavos": a.centavos, "operacion_id": a.operacion_id}
                        for a in m.aportes]}


def meta_desde_dict(d: dict) -> Meta:
    return Meta(
        id=d["id"], nombre=d["nombre"], objetivo=d["objetivo"], cuenta_id=d.get("cuenta_id"),
        fecha_limite=_fecha(d.get("fecha_limite")), emergencia=d.get("emergencia", False),
        creada=_fecha(d.get("creada")), activa=d.get("activa", True), notas=d.get("notas", ""),
        aportes=tuple(Aporte(_fecha(a["fecha"]), a["centavos"], a.get("operacion_id", ""))
                      for a in d.get("aportes", [])),
    )


def prestamo_desde_dict(d: dict) -> Prestamo:
    return Prestamo(
        cuenta_id=d["cuenta_id"], clase=d.get("clase", "otro"), monto=d["monto"],
        tasa_anual=Decimal(d["tasa_anual"]), plazo_meses=d["plazo_meses"], fecha_inicio=_fecha(d["fecha_inicio"]),
        iva=Decimal(d["iva"]) if d.get("iva") is not None else None, pago_pactado=d.get("pago_pactado"),
        dia_pago=d.get("dia_pago"), cat=Decimal(d["cat"]) if d.get("cat") is not None else None,
    )


def plazo_desde_dict(d: dict) -> InversionPlazo:
    return InversionPlazo(
        id=d["id"], cuenta_id=d["cuenta_id"], nombre=d["nombre"], fecha_inicio=_fecha(d["fecha_inicio"]),
        monto=d["monto"], tasa_anual=Decimal(d["tasa_anual"]), plazo_dias=d["plazo_dias"], notas=d.get("notas", ""),
    )


def operacion_desde_dict(d: dict) -> Operacion:
    return Operacion(
        id=d["id"], fecha=_fecha(d["fecha"]), tipo=TipoOperacion(d["tipo"]),
        partidas=tuple(
            Partida(importe=p["importe"], cuenta_id=p.get("cuenta_id"), categoria_id=p.get("categoria_id"))
            for p in d["partidas"]
        ),
        descripcion=d.get("descripcion", ""), notas=d.get("notas", ""), secuencia=d.get("secuencia", 0),
        creado_en=_momento(d.get("creado_en")), modificado_en=_momento(d.get("modificado_en")),
        msi=d.get("msi", 0),
        liquida=d.get("liquida", ""),
    )


# ---------------------------------------------------------------- libro

Instantanea = dict[str, dict[str, dict]]
"""``{tipo_de_entidad: {id: datos}}``: el estado completo de un libro."""


def instantanea(libro: Libro) -> Instantanea:
    return {
        "perfil": {ID_PERFIL: perfil_a_dict(libro.perfil)} if libro.perfil else {},
        "grupo": {g.id: grupo_a_dict(g) for g in libro.grupos()},
        "rubro": {r.id: rubro_a_dict(r) for r in libro.rubros()},
        "categoria": {c.id: categoria_a_dict(c) for c in libro.categorias()},
        "cuenta": {c.id: cuenta_a_dict(c) for c in libro.cuentas()},
        "operacion": {op.id: operacion_a_dict(op) for op in libro.operaciones()},
        "valor": {v.id: valor_a_dict(v) for v in libro.valores()},
        "plazo": {p.id: plazo_a_dict(p) for p in libro.plazos()},
        "bien": {b.id: bien_a_dict(b) for b in libro.bienes()},
        "prestamo": {p.id: prestamo_a_dict(p) for p in libro.prestamos()},
        "recurrente": {r.id: recurrente_a_dict(r) for r in libro.recurrentes()},
        "meta": {m.id: meta_a_dict(m) for m in libro.metas()},
    }


def libro_desde_instantanea(
    datos: Instantanea, secuencia: int = 0, *, reloj: Callable[[], datetime] | None = None
) -> Libro:
    """Reconstruye un libro y verifica que esté íntegro; si no, ``ErrorDatos``."""
    try:
        perfil = datos.get("perfil", {}).get(ID_PERFIL)
        libro = Libro.desde_estado(
            perfil=perfil_desde_dict(perfil) if perfil else None,
            grupos=[grupo_desde_dict(d) for d in datos.get("grupo", {}).values()],
            categorias=[categoria_desde_dict(d) for d in datos.get("categoria", {}).values()],
            rubros=[rubro_desde_dict(d) for d in datos.get("rubro", {}).values()],
            cuentas=[cuenta_desde_dict(d) for d in datos.get("cuenta", {}).values()],
            operaciones=[operacion_desde_dict(d) for d in datos.get("operacion", {}).values()],
            valores=[valor_desde_dict(d) for d in datos.get("valor", {}).values()],
            plazos=[plazo_desde_dict(d) for d in datos.get("plazo", {}).values()],
            bienes=[bien_desde_dict(d) for d in datos.get("bien", {}).values()],
            prestamos=[prestamo_desde_dict(d) for d in datos.get("prestamo", {}).values()],
            recurrentes=[recurrente_desde_dict(d) for d in datos.get("recurrente", {}).values()],
            metas=[meta_desde_dict(d) for d in datos.get("meta", {}).values()],
            secuencia=secuencia,
            reloj=reloj,
        )
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as error:
        raise ErrorDatos(f"Los datos guardados están dañados o incompletos ({error}).") from error
    problemas = verificar_integridad(libro)
    if problemas:
        raise ErrorDatos("Los datos guardados no cuadran: " + "; ".join(problemas[:5]))
    return libro


def verificar_integridad(libro: Libro) -> list[str]:
    """Problemas estructurales del libro (vacía si todo está bien)."""
    problemas = []
    cuentas = {c.id for c in libro.cuentas()}
    categorias = {c.id for c in libro.categorias()}
    grupos = {g.id for g in libro.grupos()}
    rubros = {r.id: r for r in libro.rubros()}
    for rubro in rubros.values():
        if rubro.clase is ClaseCategoria.SISTEMA:
            problemas.append(f"la categoría «{rubro.nombre}» no puede ser del sistema")
    for categoria in libro.categorias():
        if categoria.grupo_id is not None and categoria.grupo_id not in grupos:
            problemas.append(f"la subcategoría «{categoria.nombre}» apunta a una clasificación inexistente")
        if categoria.rubro_id is not None:
            rubro = rubros.get(categoria.rubro_id)
            if rubro is None:
                problemas.append(f"la subcategoría «{categoria.nombre}» apunta a una categoría inexistente")
            elif rubro.clase is not categoria.clase:
                problemas.append(f"la subcategoría «{categoria.nombre}» no es del mismo tipo que su categoría")
    for registro in [*libro.valores(), *libro.plazos()]:
        if registro.cuenta_id not in cuentas:
            problemas.append("una compra de títulos o inversión a plazo usa una cuenta inexistente")
    for prestamo in libro.prestamos():
        if libro.cuenta(prestamo.cuenta_id).tipo is not TipoCuenta.PRESTAMO:
            problemas.append(f"«{libro.cuenta(prestamo.cuenta_id).nombre}» tiene datos de préstamo pero no lo es")
    for bien in libro.bienes():
        if libro.cuenta(bien.cuenta_id).tipo is not TipoCuenta.BIEN:
            problemas.append(f"«{libro.cuenta(bien.cuenta_id).nombre}» tiene datos de bien pero no es un bien")
    for op in libro.operaciones():
        if sum(p.importe for p in op.partidas) != 0:
            problemas.append(f"el movimiento del {op.fecha} no suma cero")
        for p in op.partidas:
            if p.cuenta_id is not None and p.cuenta_id not in cuentas:
                problemas.append(f"el movimiento del {op.fecha} usa una cuenta inexistente")
            if p.categoria_id is not None and p.categoria_id not in categorias:
                problemas.append(f"el movimiento del {op.fecha} usa una categoría inexistente")
    return problemas

