"""Genera los recursos de marca de TALLY (símbolo, logotipos e íconos) a partir del tablero de marca.

Uso:  python docs/marca/generar.py RUTA/A/montserrat-latin-700-normal.woff

La fuente del wordmark es Montserrat Bold (licencia SIL OFL 1.1, @fontsource/montserrat). Solo se usa para
dibujar los PNG; no se distribuye con el programa. Sin la fuente, se usa DejaVu Sans Bold.

Salidas:
  portal/recursos/  marca.png (favicon), logo.png (barra lateral), icono.png, tally.ico (acceso directo)
  docs/marca/       simbolo.svg y las variantes de color para la documentación
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
RECURSOS = RAIZ / "portal" / "recursos"
DOCS = RAIZ / "docs" / "marca"

TINTA = (16, 16, 20, 255)        # #101014, la marca
ACENTO = (107, 83, 241, 255)     # #6B53F1
OSCURO = (19, 22, 21, 255)       # #131615
CLARO = (250, 250, 250, 255)     # #FAFAFA
GRIS = (236, 236, 238, 255)      # #ECECEE
BLANCO = (255, 255, 255, 255)
ESCALA = 4                       # sobremuestreo para bordes suaves

# Geometría del símbolo en unidades de la altura de las barras (H = 1):
# cuatro barras verticales con extremos redondeados y una diagonal que las cruza.
GROSOR = 0.13
SEPARACION = 0.306
DIAGONAL = ((-0.22, 0.93), (1.19, 0.10))
ANCHO_SIMBOLO = 1.19 + 0.22 + GROSOR  # de la punta izquierda de la diagonal a la derecha


def _trazo(dibujo: ImageDraw.ImageDraw, a, b, grosor: float, color) -> None:
    dibujo.line([a, b], fill=color, width=round(grosor))
    for x, y in (a, b):
        r = grosor / 2
        dibujo.ellipse([x - r, y - r, x + r, y + r], fill=color)


def simbolo(alto: int, color=TINTA, fondo=(0, 0, 0, 0)) -> Image.Image:
    """El símbolo solo, con margen justo, sobre fondo transparente (o del color indicado)."""
    h = alto * ESCALA
    g = GROSOR * h
    ancho = round((ANCHO_SIMBOLO + 0.02) * h + g)
    img = Image.new("RGBA", (ancho, round(h + g)), fondo)
    d = ImageDraw.Draw(img)
    x0 = (0.22 + GROSOR / 2 + 0.01) * h + g / 2
    y0 = g / 2
    for i in range(4):
        x = x0 + i * SEPARACION * h
        _trazo(d, (x, y0), (x, y0 + h), g, color)
    (ax, ay), (bx, by) = DIAGONAL
    _trazo(d, (x0 + ax * h, y0 + ay * h), (x0 + bx * h, y0 + by * h), g, color)
    return img.resize((img.width // ESCALA, img.height // ESCALA), Image.LANCZOS)


def mosaico(lado: int, fondo, tinta, borde=None) -> Image.Image:
    """Ícono cuadrado con esquinas redondeadas y el símbolo centrado (variantes Claro/Oscuro/Acento/Gris)."""
    s = lado * ESCALA
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=round(s * 0.22), fill=fondo,
                        outline=borde, width=max(1, s // 128) if borde else 0)
    marca = simbolo(round(lado * 0.46), tinta)
    marca = marca.resize((marca.width * ESCALA, marca.height * ESCALA), Image.LANCZOS)
    img.alpha_composite(marca, ((s - marca.width) // 2, (s - marca.height) // 2))
    return img.resize((lado, lado), Image.LANCZOS)


def logotipo(alto: int, fuente: Path | None, color=TINTA) -> Image.Image:
    """Logotipo horizontal: símbolo + «TALLY» con espaciado amplio."""
    marca = simbolo(alto, color)
    tamano = round(alto * 1.05)
    try:
        letra = ImageFont.truetype(str(fuente), tamano) if fuente else ImageFont.truetype("DejaVuSans-Bold.ttf", tamano)
    except OSError:
        letra = ImageFont.truetype("DejaVuSans-Bold.ttf", tamano)
    espacio = round(tamano * 0.10)
    anchos = [letra.getbbox(c)[2] - letra.getbbox(c)[0] for c in "TALLY"]
    ancho_texto = sum(anchos) + espacio * 4
    caja = letra.getbbox("TALLY")
    alto_texto = caja[3] - caja[1]
    separacion = round(alto * 0.42)
    img = Image.new("RGBA", (marca.width + separacion + ancho_texto + 4, max(marca.height, alto_texto) + 4),
                    (0, 0, 0, 0))
    img.alpha_composite(marca, (0, (img.height - marca.height) // 2))
    d = ImageDraw.Draw(img)
    x, y = marca.width + separacion, (img.height - alto_texto) // 2 - caja[1]
    for c, a in zip("TALLY", anchos):
        d.text((x - letra.getbbox(c)[0], y), c, font=letra, fill=color)
        x += a + espacio
    return img


def svg_simbolo(color: str = "#101014") -> str:
    h = 100
    g = GROSOR * h
    x0 = (0.22 + GROSOR / 2 + 0.01) * h + g / 2
    y0 = g / 2
    ancho = (ANCHO_SIMBOLO + 0.02) * h + g
    lineas = [f'<line x1="{x0 + i * SEPARACION * h:.1f}" y1="{y0:.1f}" x2="{x0 + i * SEPARACION * h:.1f}" '
              f'y2="{y0 + h:.1f}"/>' for i in range(4)]
    (ax, ay), (bx, by) = DIAGONAL
    lineas.append(f'<line x1="{x0 + ax * h:.1f}" y1="{y0 + ay * h:.1f}" x2="{x0 + bx * h:.1f}" y2="{y0 + by * h:.1f}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho:.1f} {h + g:.1f}" role="img" '
            f'aria-label="TALLY">\n  <g stroke="{color}" stroke-width="{g:.1f}" stroke-linecap="round">\n    '
            + "\n    ".join(lineas) + "\n  </g>\n</svg>\n")


def main() -> None:
    fuente = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    RECURSOS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    simbolo(220).save(RECURSOS / "marca.png")                          # favicon de la pestaña
    logotipo(64, fuente).save(RECURSOS / "logo.png")                  # barra lateral
    claro = mosaico(256, BLANCO, TINTA, borde=GRIS)
    claro.save(RECURSOS / "icono.png")
    claro.save(RECURSOS / "tally.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    (DOCS / "simbolo.svg").write_text(svg_simbolo(), encoding="utf-8")
    logotipo(96, fuente).save(DOCS / "logotipo.png")
    for nombre, fondo, tinta, borde in (("claro", BLANCO, TINTA, GRIS), ("oscuro", OSCURO, BLANCO, None),
                                        ("acento", ACENTO, BLANCO, None), ("gris", GRIS, TINTA, None)):
        mosaico(256, fondo, tinta, borde).save(DOCS / f"icono_{nombre}.png")
    print("Recursos de marca generados.")


if __name__ == "__main__":
    main()
