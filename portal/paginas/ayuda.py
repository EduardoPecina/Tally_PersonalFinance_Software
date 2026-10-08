"""❓ Guía y ayuda: primeros pasos (se marcan solos), «¿Cómo hago…?» y las palabras que usa TALLY."""

from __future__ import annotations

import streamlit as st

from motor import guia
from portal.componentes.sesion import ejecutar, libro, sesion
from portal.navegacion import enlace, paginas

# (pregunta, respuesta, página, texto del enlace)
COMO_HAGO = (
    ("Registrar un gasto, un ingreso o un movimiento entre mis cuentas",
     "En **Registrar** eliges qué fue, la subcategoría, la cuenta, el importe y la fecha. Si dejas la subcategoría "
     "vacía y tienes una regla automática para esa descripción, se usa la de la regla. Antes de guardar, TALLY te "
     "avisa si algo parece un error de dedo (una cuenta que quedaría en negativo, una fecha de otro año…). Pasar "
     "dinero entre tus cuentas es una **transferencia**: no es gasto.", "registrar", "Ir a Registrar"),
    ("Pagar mi tarjeta de crédito",
     "Registrar → **Pago de tarjeta**. No es un gasto: el gasto fue cuando compraste. En **Deudas** ves cuánto pagar "
     "para no generar intereses y, en el Resumen, cuándo vence cada tarjeta.", "deudas", "Ir a Deudas"),
    ("Una compra a meses sin intereses",
     "Regístrala como gasto con tu tarjeta y escribe los **meses sin intereses**. Cuenta completa como gasto el día "
     "que compraste; tu tarjeta solo te pide una mensualidad en cada corte.", "registrar", "Ir a Registrar"),
    ("Un cargo que me van a devolver (verificación de Amazon, depósito de un hotel…)",
     "Registrar → Gasto → **Cargo temporal**. No cuenta como gasto: queda en «Te deben» hasta que lo marques como "
     "devuelto en el Resumen.", "registrar", "Ir a Registrar"),
    ("Subir el estado de cuenta de mi banco",
     "**Cargar datos → Desde tu banco**: el Excel o CSV de tu banca en línea, el PDF del estado de cuenta o lo que "
     "copies de la página. TALLY sugiere la subcategoría de cada movimiento (por tus reglas, por lo que elegiste "
     "antes o por el comercio) y aparta lo que ya tenías para no duplicarlo. Con el botón ⚡ conviertes lo que "
     "elijas en una regla para la próxima vez.", "cargar", "Ir a Cargar datos"),
    ("Que mis movimientos se acomoden solos",
     "**Categorías › ⚡ Reglas automáticas**: «si la descripción dice OXXO, va a SNACKS Y ANTOJOS». Se usan al "
     "importar, al registrar sin subcategoría y en la plantilla de Excel. También corrigen tu historial de un jalón "
     "y te sugieren reglas con lo que más se repite.", "categorias", "Ir a Categorías"),
    ("Guardar el ticket o la factura de un gasto",
     "En **Historial** elige el movimiento → **📎 Comprobantes** (o adjúntalo al registrar). Fotos, PDF o el XML de "
     "la factura. Se guardan dentro de tus datos, cifrados si tienes contraseña, y van en tus respaldos. En "
     "**Impuestos** ves qué deducibles no tienen comprobante y descargas todos los del año en un .zip.",
     "historial", "Ir al Historial"),
    ("Salir de mis deudas",
     "**Deudas → Plan para salir de deudas**: pones cuánto puedes pagar al mes entre todas y TALLY te dice cuánto "
     "pagar a cada una, cuándo terminas y cuánto te ahorras en intereses. Guárdalo y el Resumen te lo recuerda.",
     "deudas", "Ir a Deudas"),
    ("Saber cuánto puedo gastar",
     "En **Ingresos** configuras tu nómina (quincena, catorcena, semana o mes) y en **Presupuestos** cuánto quieres "
     "gastar en cada categoría; TALLY te sugiere montos con lo que sueles gastar y te avisa si vas pasado.",
     "presupuestos", "Ir a Presupuestos"),
    ("Ahorrar para algo",
     "**Metas de ahorro**: lo que quieres juntar, para cuándo y dónde lo guardas. Incluye tu fondo de emergencia, "
     "calculado con tus gastos esenciales.", "metas", "Ir a Metas de ahorro"),
    ("Ver cómo me fue en el mes",
     "**Cierre de mes**: lo que entró y salió, contra tus presupuestos, lo que faltó registrar y qué hacer el mes "
     "que sigue. Se descarga en Excel.", "cierre", "Ir a Cierre de mes"),
    ("Mis impuestos",
     "**Impuestos**: tus gastos deducibles del año (tú eliges qué cuenta y con qué topes, para cualquier país) y el "
     "cálculo o la revisión de un recibo o factura.", "impuestos", "Ir a Impuestos"),
    ("Corregir o borrar un movimiento",
     "**Historial**: busca el movimiento, selecciónalo (casilla a la izquierda) y usa Editar o Eliminar. Todo queda "
     "en la bitácora.", "historial", "Ir al Historial"),
    ("Encontrar errores en mis datos",
     "**Salud de tus datos**: movimientos que parecen duplicados, cuentas en negativo, fechas de otro año, tarjetas "
     "con datos incompletos… Cada cosa dice dónde se arregla.", "salud", "Ir a Salud de tus datos"),
    ("Respaldar, o pasar TALLY a otra computadora",
     "**Respaldos y bitácora → Descargar respaldo**: un .zip con todo (también tus comprobantes). En la otra "
     "computadora, al abrir TALLY elige «Ya usaba TALLY» y súbelo. Además, TALLY hace un respaldo automático cada "
     "día.", "respaldos", "Ir a Respaldos"),
    ("Proteger mis datos con contraseña",
     "**Configuración → Seguridad**. Todo se cifra en tu computadora. Guarda bien tu **Kit de emergencia**: sin tu "
     "contraseña ni tu Kit, nadie (ni TALLY) puede abrir tus datos.", "configuracion", "Ir a Configuración"),
)

PALABRAS = (
    ("Categoría, subcategoría y clasificación",
     "La **categoría** es la caja (SALUD); la **subcategoría** es lo que lleva cada movimiento (DENTISTA); la "
     "**clasificación** dice para qué fue (Necesidad, Disfrute, Estabilidad…)."),
    ("Transferencia", "Dinero que pasa de una cuenta tuya a otra (al ahorro, a pagar tu tarjeta). No es gasto ni "
                      "ingreso: solo cambia de lugar."),
    ("Disponible y patrimonio", "**Disponible** es lo que puedes usar ya (débito, efectivo…). **Patrimonio** es todo "
                                "lo que tienes menos todo lo que debes."),
    ("Corte y fecha límite de pago", "El **corte** es el día en que tu tarjeta junta lo que compraste en el mes; la "
                                     "**fecha límite** es hasta cuándo puedes pagarlo."),
    ("Pago para no generar intereses y pago mínimo",
     "Si pagas lo del último corte completo, no pagas intereses. El **mínimo** solo evita atrasos: lo demás genera "
     "intereses (y caros)."),
    ("Avalancha y bola de nieve", "Dos formas de pagar deudas: **avalancha**, primero la de tasa más alta (pagas "
                                  "menos intereses); **bola de nieve**, primero la más chica (terminas una pronto)."),
    ("Deducible", "Un gasto que tu país te deja restar de tus impuestos (médicos, colegiaturas…). Guarda su "
                  "comprobante."),
    ("Regla automática", "«Si la descripción dice esto, va a esta subcategoría»: así TALLY acomoda solo lo que "
                         "importas o registras."),
)


def avance_actual() -> guia.Avance:
    return guia.avance(libro(), con_contrasena=sesion().almacen.desbloqueado)


def tarjeta_en_el_resumen() -> None:
    """En el Resumen, mientras falten pasos (y no la ocultes): cuánto llevas y el siguiente paso."""
    lib = libro()
    av = avance_actual()
    if not guia.se_muestra_en_el_resumen(lib, av):
        return
    siguiente = av.siguiente
    with st.container(border=True):
        st.markdown(f"**🚀 Primeros pasos** · {av.hechos} de {av.total}")
        st.progress(av.hechos / av.total)
        st.markdown(f"Siguiente: **{siguiente.titulo}**. {siguiente.porque}")
        a, b, c = st.columns([2, 2, 1], vertical_alignment="center")
        with a:
            enlace(siguiente.pagina, f"Ir a {paginas()[siguiente.pagina].title}", "➡️")
        with b:
            enlace("ayuda", "Ver la guía completa", "❓")
        if c.button("Ocultar", key="guia_ocultar", help="Ya no sale aquí; sigue en Guía y ayuda."):
            if ejecutar(guia.ocultar, exito="Guía oculta: la encuentras en Guía y ayuda"):
                st.rerun()


def mostrar() -> None:
    st.title("Guía y ayuda")
    st.caption("Lo que conviene configurar para sacarle jugo a TALLY, cómo se hace cada cosa y las palabras que "
               "usa. Tus datos se quedan en esta computadora: TALLY no se conecta a tu banco ni a ninguna nube.")
    _primeros_pasos()
    st.subheader("¿Cómo hago…?")
    buscado = st.text_input("Buscar", key="ayuda_buscar", placeholder="tarjeta, factura, respaldo, deudas…")
    encontrados = [x for x in COMO_HAGO if _coincide(buscado, x[0] + " " + x[1])]
    if not encontrados:
        st.caption("No encontré nada con eso. Prueba con otra palabra.")
    for pregunta, respuesta, pagina, texto in encontrados:
        with st.expander(pregunta, expanded=bool(buscado.strip()) and len(encontrados) <= 3):
            st.markdown(respuesta)
            enlace(pagina, texto, "➡️")
    st.subheader("Palabras que usa TALLY")
    for palabra, significado in PALABRAS:
        st.markdown(f"**{palabra}.** {significado}")


def _primeros_pasos() -> None:
    lib = libro()
    av = avance_actual()
    st.subheader(f"🚀 Primeros pasos · {av.hechos} de {av.total}")
    st.progress(av.hechos / av.total)
    if av.completo:
        st.success("¡Ya tienes todo lo esencial! Lo de abajo es opcional.", icon="🎉")
    for paso in av.pasos:
        with st.container(border=True):
            izquierda, derecha = st.columns([4, 1], vertical_alignment="center")
            marca = "✅" if paso.hecho else "⬜"
            opcional = " :gray[(opcional)]" if paso.opcional else ""
            izquierda.markdown(f"{marca} **{paso.titulo}**{opcional}  \n:gray[{paso.porque}]")
            if not paso.hecho:
                with derecha:
                    enlace(paso.pagina, "Hacerlo", "➡️")
    oculta = bool(lib.perfil and lib.perfil.guia_oculta)
    mostrar_en_resumen = st.toggle("Mostrar los primeros pasos en el Resumen", value=not oculta,
                                   key="guia_en_resumen", disabled=av.completo,
                                   help="Mientras te falte algo. Cuando completes lo esencial ya no sale.")
    if mostrar_en_resumen == oculta and not av.completo:
        if ejecutar(lambda lib_: guia.ocultar(lib_, not mostrar_en_resumen)):
            st.rerun()


def _coincide(buscado: str, texto: str) -> bool:
    from motor.textos import clave

    palabras = clave(buscado).split()
    texto = clave(texto)
    return all(p in texto for p in palabras)
