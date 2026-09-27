"""
Pantalla «Pruebas» (Ajustes): forzar sensores y conexión de equipos para probar
la alarma y los avisos sin abrir puertas ni apagar nada.

Lo forzado solo lo ve el panel (alarma, pantallas, métricas): no cambia el
sensor real, no lanza automatizaciones ni acciones sobre aparatos, caduca solo y
desaparece al reiniciar. Ver core/pruebas.py.
"""
import reflex as rx

from ....domains.infra.pruebas_state import PruebasState
from .. import theme


def _boton(etiqueta: str, valor: str, actual: rx.Var, alPulsar, color: str) -> rx.Component:
    return rx.button(
        etiqueta, on_click=alPulsar, size="2",
        variant=rx.cond(actual == valor, "solid", "surface"),
        color_scheme=rx.cond(actual == valor, color, "gray"),
    )


def _fila_sensor(s: rx.Var) -> rx.Component:
    sid = s["id"].to(str)
    modo = s["modo"].to(str)
    return rx.hstack(
        rx.vstack(
            rx.text(s["nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.text(s["tipo"].to(str) + " · ahora, de verdad: " + s["real"].to(str),
                    size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.hstack(
            _boton("Real", "real", modo, PruebasState.forzar_sensor(sid, "real"), "blue"),
            _boton("Abierto", "abierto", modo, PruebasState.forzar_sensor(sid, "abierto"), "red"),
            _boton("Cerrado", "cerrado", modo, PruebasState.forzar_sensor(sid, "cerrado"), "green"),
            spacing="2", wrap="wrap",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
    )


def _fila_equipo(h: rx.Var) -> rx.Component:
    hid = h["id"].to(str)
    modo = h["modo"].to(str)
    return rx.hstack(
        rx.vstack(
            rx.text(h["nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.text("ahora, de verdad: " + h["real"].to(str), size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.hstack(
            _boton("Real", "real", modo, PruebasState.forzar_equipo(hid, "real"), "blue"),
            _boton("En línea", "online", modo, PruebasState.forzar_equipo(hid, "online"), "green"),
            _boton("Caído", "caido", modo, PruebasState.forzar_equipo(hid, "caido"), "red"),
            spacing="2", wrap="wrap",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
    )


def _seccion(titulo: str, ayuda: str, filas: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.text(titulo, size="3", weight="bold", color=theme.TEXT),
            rx.text(ayuda, size="1", color=theme.MUTED),
            spacing="0", align="start",
        ),
        filas, spacing="2", width="100%", align="start",
    )


def pruebas_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Pruebas", size="5", color=theme.TEXT),
            rx.text(
                "Fuerza el valor de un sensor o de la conexión de un equipo para "
                "probar la alarma y los avisos sin abrir la puerta. Lo forzado lo ve "
                "el panel (alarma, pantallas, avisos) pero no cambia el sensor real, "
                "no lanza automatizaciones ni actúa sobre ningún aparato. Caduca solo a "
                "los 10 minutos y desaparece al reiniciar el panel.",
                size="1", color=theme.MUTED, style={"line-height": "1.5"},
            ),
            spacing="1", align="start",
        ),
        rx.hstack(
            rx.icon("flask-conical", size=18, color=theme.WARNING),
            rx.text(
                rx.cond(PruebasState.hay_forzados,
                        "Modo prueba activo: hay valores forzados (caducan a las "
                        + PruebasState.caduca + ").",
                        "Todo real: no hay ningún valor forzado."),
                size="2", color=theme.TEXT,
            ),
            rx.spacer(),
            rx.button(rx.icon("rotate-ccw", size=14), "Restablecer todo",
                      on_click=PruebasState.restablecer, size="2", variant="soft",
                      color_scheme="orange", disabled=~PruebasState.hay_forzados),
            align="center", spacing="3", width="100%", wrap="wrap",
            padding="11px", border_radius="10px",
            background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
        ),
        rx.vstack(
            rx.text("Probar que la alarma salta", size="2", weight="bold", color=theme.TEXT),
            rx.text(
                "1) Pon el sensor en «Cerrado». 2) Arma el grupo al que pertenece. "
                "3) Pon el sensor en «Abierto»: saltará como si se hubiera abierto "
                "(aviso a los móviles, sirena de las tablets y foto de la cámara). "
                "Si el grupo tiene retardo de entrada, espera a que acabe. Con «Real» "
                "o «Restablecer todo» vuelve el valor verdadero.",
                size="1", color=theme.MUTED, style={"line-height": "1.5"},
            ),
            spacing="1", align="start", padding="11px", border_radius="10px",
            background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
        ),
        _seccion("Sensores y puertas", "Magnéticos, tampers y puertas con sensor.",
                 rx.vstack(rx.foreach(PruebasState.sensores, _fila_sensor),
                           spacing="2", width="100%")),
        _seccion("Conexión de equipos", "Servidor, PC, móviles, Echo… como si respondieran o no.",
                 rx.vstack(rx.foreach(PruebasState.equipos, _fila_equipo),
                           spacing="2", width="100%")),
        spacing="4", width="100%", align="start",
        on_mount=PruebasState.cargar,
    )
