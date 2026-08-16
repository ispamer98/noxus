"""
Tokens de diseño del Centro de Control (dashboard nuevo, /panel).

Mantiene el mismo lenguaje visual que ya usa la vista clásica (header.py):
azul de acento, verde online, rojo alarma/peligro, naranja aviso, violeta PTZ.
Centralizado aquí para no repetir literales de color por todo el shell nuevo.
"""

BG_APP = "#05070a"
BG_SIDEBAR = "#0a0f16"
BG_TOPBAR = "rgba(10, 15, 22, 0.85)"
BG_CARD = "rgba(255, 255, 255, 0.035)"
BG_CARD_HOVER = "rgba(255, 255, 255, 0.06)"
BG_WINDOW = "#0d1420"

BORDER = "rgba(255, 255, 255, 0.08)"
BORDER_STRONG = "rgba(255, 255, 255, 0.16)"

ACCENT = "#38bdf8"
DANGER = "#ef4444"
SUCCESS = "#22c55e"
WARNING = "#f97316"
PURPLE = "#a78bfa"
MUTED = "#94a3b8"
TEXT = "#e2e8f0"

FONT_MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"


def alpha(hex_color: str, a: float) -> str:
    """rgba() a partir de un hex '#rrggbb' — para fondos translúcidos de icono/estado."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {a})"
