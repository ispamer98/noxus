"""Tokens de diseño del Centro de Control «Obsidiana» (/panel).

El cian es el acento del panel, el violeta da profundidad al ambiente y los
colores semánticos conservan su significado. Los mismos valores viven como
variables CSS en assets/nx.css.
"""

BG_APP = "#04060b"
BG_SIDEBAR = "rgba(7, 11, 19, 0.6)"
BG_TOPBAR = "rgba(7, 11, 19, 0.5)"
# El segundo tramo va dentro del valor a propósito: Reflex lo inserta en el
# atributo style y así las tarjetas existentes recuperan el cristal sin tener
# que retocar una a una sus props.
BG_CARD = ("linear-gradient(180deg, rgba(255, 255, 255, 0.05), "
           "rgba(255, 255, 255, 0.016)); backdrop-filter: blur(10px)")
BG_CARD_HOVER = "rgba(255, 255, 255, 0.065)"
BG_WINDOW = "#0a0f18"

BORDER = "rgba(255, 255, 255, 0.075)"
BORDER_STRONG = "rgba(255, 255, 255, 0.15)"

ACCENT = "#3ee0ff"
DANGER = "#ff4d5e"
SUCCESS = "#2ee6a6"
WARNING = "#ffa31a"
# Algo encendido conserva el ámbar cálido estrenado con las baldosas nuevas.
LAMP = "#ffc24a"
PURPLE = "#8b7cff"
MUTED = "#8a97aa"
TEXT = "#e8eef7"

FONT_MONO = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"


def alpha(hex_color: str, a: float) -> str:
    """rgba() a partir de un hex '#rrggbb' — para fondos translúcidos de icono/estado."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {a})"
