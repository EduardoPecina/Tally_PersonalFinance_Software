"""Página de «TALLY se cerró».

Sin esto, al apagarse el servidor Streamlit muestra «Connection error… restart it in your terminal», que asusta
y no explica nada. Basado en el aviso del Portal de Honorarios.
"""

from __future__ import annotations

import json

AVISO = """
    <div id="tally-cerrado" style="font-family: 'Source Sans Pro', 'Segoe UI', sans-serif; max-width: 560px;
                margin: 15vh auto; padding: 28px 32px; border: 1px solid #ECECEE; border-left: 6px solid #6B53F1;
                border-radius: 12px; color: #101014; background: #ffffff; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);">
      <h2 style="margin-top: 0;">TALLY se cerró</h2>
      <p>Todo quedó guardado. Ya puedes cerrar esta pestaña.</p>
      <p style="color: #6b7280;">Para volver a abrirlo: doble clic en <b>TALLY</b> en tu Escritorio.</p>
    </div>"""


def pagina_cerrado() -> str:
    """JavaScript para ``st.html(..., unsafe_allow_javascript=True)``: reemplaza la página por el aviso.

    Ojo: ``st.html`` limpia el HTML (DOMPurify) y borra un ``<script>`` cuyo texto contenga etiquetas; por eso
    el aviso va con los ``<`` escritos como ``\\x3c`` (JavaScript los convierte de vuelta).
    """
    aviso = json.dumps(AVISO).replace("<", "\\x3c")
    return """<script>
(function () {
  const w = window.parent, d = w.document;
  d.title = "TALLY (cerrado)";
  d.body.style.background = "#FAFAFA";
  // Streamlit, al perder la conexión, agrega su ventana de «Connection error»: se oculta todo lo que no sea
  // este aviso, incluso lo que se agregue después.
  const estilo = d.createElement("style");
  estilo.textContent = "body > :not(#tally-cerrado) { display: none !important; }";
  d.head.appendChild(estilo);
  d.body.innerHTML = """ + aviso + """;
})();
</script>"""
