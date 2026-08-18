"""El desplegable de «esto impide armar» y la cuenta atrás de salida.

Aparece solo cuando hay algo abierto. Con la casa cerrada, armar sigue siendo
un toque y esto no se ve nunca — que es la diferencia entre una alarma que se
usa y una que cansa.
"""
import reflex as rx

from .. import theme
from ....domains.security.arming_state import ArmingState


def _abierto(item: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("door-open", size=14, color=theme.WARNING, flex_shrink="0"),
        rx.text(item["nombre"], size="1", color=theme.TEXT),
        align="center", spacing="2", width="100%",
        padding="8px 10px", border_radius="8px",
        background=theme.alpha(theme.WARNING, 0.07),
        border=f"1px solid {theme.alpha(theme.WARNING, 0.22)}",
    )


def dialogo_armado() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("shield-alert", size=18, color=theme.WARNING),
                    rx.text("Esto impide armar", size="3", weight="bold",
                            color=theme.TEXT),
                    align="center", spacing="2",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Si armas ahora, esto se queda sin vigilar.",
                    size="1", color=theme.MUTED,
                ),
                rx.vstack(
                    rx.foreach(ArmingState.abiertos, _abierto),
                    spacing="1", width="100%", max_height="220px",
                    overflow_y="auto",
                ),
                rx.vstack(
                    rx.button(
                        rx.icon("shield-check", size=15),
                        "Armar excluyendo esto",
                        on_click=ArmingState.armar_excluyendo,
                        color_scheme="red", size="2", width="100%",
                    ),
                    rx.button(
                        rx.icon("clock", size=15),
                        "Armar cuando cierren",
                        on_click=ArmingState.armar_al_cerrar,
                        variant="soft", size="2", width="100%",
                    ),
                    rx.button(
                        "Dejarlo", on_click=ArmingState.cerrar,
                        variant="soft", color_scheme="gray", size="2",
                        width="100%",
                    ),
                    spacing="2", width="100%",
                ),
                rx.text(
                    "Lo que se deje fuera queda apuntado en los registros, y "
                    "vuelve a vigilarse en cuanto se desarme.",
                    size="1", color=theme.MUTED, style={"line-height": "1.5"},
                ),
                spacing="3", width="100%",
            ),
            max_width="420px",
        ),
        open=ArmingState.hay_dialogo,
        on_open_change=lambda abierto: rx.cond(
            abierto, rx.noop(), ArmingState.cerrar()),
    )


def cuenta_atras_salida() -> rx.Component:
    """Mientras corre el tiempo para salir. Con su botón de cancelar, porque
    lo primero que se hace cuando uno se arrepiente es querer pararlo."""
    return rx.cond(
        ArmingState.contando != "",
        rx.hstack(
            rx.icon("timer", size=20, color=theme.WARNING, flex_shrink="0"),
            rx.vstack(
                rx.text("Saliendo de casa", size="2", weight="bold",
                        color=theme.TEXT),
                rx.text("Se armará al terminar la cuenta.", size="1",
                        color=theme.MUTED),
                spacing="0", align="start",
            ),
            rx.spacer(),
            rx.text(ArmingState.restantes.to_string() + " s", size="5",
                    weight="bold", color=theme.WARNING,
                    font_family=theme.FONT_MONO),
            rx.button("Cancelar", size="1", variant="soft", color_scheme="gray",
                      on_click=ArmingState.cancelar_cuenta, flex_shrink="0"),
            align="center", spacing="3", width="100%",
            padding="12px 14px", border_radius="12px",
            background=theme.alpha(theme.WARNING, 0.1),
            border=f"1px solid {theme.alpha(theme.WARNING, 0.4)}",
        ),
    )
