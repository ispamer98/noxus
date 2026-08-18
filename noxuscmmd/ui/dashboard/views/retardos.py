"""Vista "Retardos": el margen para salir y el margen para entrar.

Dos ideas que conviene tener delante al configurarlos:

- El de SALIDA es por grupo: es el tiempo que tardas en llegar a la puerta y
  salir, y no depende de por dónde salgas.
- El de ENTRADA puede ser por elemento: la puerta por la que entras necesita
  margen para llegar al panel y desarmar; una ventana del salón, ninguno —
  quien entra por ahí no viene a desarmar nada.
"""
import reflex as rx

from .. import theme
from ..state import DashboardState
from ....domains.security.retardos_state import RetardosState


def _campo(valor, al_cambiar) -> rx.Component:
    return rx.input(
        value=valor, on_blur=al_cambiar, type="number",
        width="82px", size="1",
    )


def _fila_grupo(g: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.hstack(
                rx.text(g["nombre"], size="2", weight="bold", color=theme.TEXT),
                rx.cond(
                    g["principal"] != "",
                    rx.text("principal", size="1", color=theme.ACCENT),
                ),
                align="center", spacing="2",
            ),
            # .to(str) antes de concatenar: dentro de un foreach el valor de una
            # clave es una Var, y pegarle un texto a pelo revienta al compilar.
            rx.text(g["miembros"].to(str) + " elementos", size="1",
                    color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.vstack(
            rx.text("Salir", size="1", color=theme.MUTED),
            _campo(g["salida"],
                   lambda v: RetardosState.poner_grupo(g["id"], "salida", v)),
            spacing="1", align="center",
        ),
        rx.vstack(
            rx.text("Entrar", size="1", color=theme.MUTED),
            _campo(g["entrada"],
                   lambda v: RetardosState.poner_grupo(g["id"], "entrada", v)),
            spacing="1", align="center",
        ),
        align="center", spacing="3", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="12px 14px",
    )


def _fila_elemento(e: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(e["nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.text(e["tipo"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.vstack(
            rx.text("Entrar", size="1", color=theme.MUTED),
            _campo(e["entrada"],
                   lambda v: RetardosState.poner_elemento(e["id"], v)),
            spacing="1", align="center",
        ),
        align="center", spacing="3", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="12px 14px",
    )


def retardos_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("timer", size=22, color=theme.ACCENT),
            rx.heading("Retardos", size="6", color=theme.TEXT),
            rx.spacer(),
            rx.button(rx.icon("arrow-left", size=15), "Ajustes", size="2",
                      variant="soft",
                      on_click=DashboardState.set_view("settings_hub")),
            align="center", spacing="2", width="100%", wrap="wrap",
        ),
        rx.text(
            "En segundos. 0 = sin retardo, que es como funcionaba hasta ahora: "
            "armar arma en el acto y abrir con la casa armada avisa en el acto.",
            size="1", color=theme.MUTED, style={"line-height": "1.6"},
        ),
        rx.hstack(
            rx.icon("info", size=15, color=theme.MUTED, flex_shrink="0"),
            rx.text(
                "«Salir» es la cuenta atrás desde que pulsas armar hasta que la "
                "casa queda armada de verdad. «Entrar» es lo que tienes para "
                "desarmar desde que abres, antes de que salte el aviso.",
                size="1", color=theme.MUTED, style={"line-height": "1.5"},
            ),
            align="start", spacing="2", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
            border_radius="10px", padding="10px 12px",
        ),

        rx.text("Por grupo", size="1", weight="bold", color=theme.MUTED,
                margin_top="6px"),
        rx.vstack(
            rx.foreach(RetardosState.grupos, _fila_grupo),
            spacing="2", width="100%",
        ),

        rx.text("Por elemento", size="1", weight="bold", color=theme.MUTED,
                margin_top="6px"),
        rx.text(
            "Solo el de entrada, y solo si quieres que ese elemento tenga uno "
            "distinto del de su grupo. En 0 hereda el del grupo.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.vstack(
            rx.foreach(RetardosState.elementos, _fila_elemento),
            spacing="2", width="100%",
        ),

        spacing="3", width="100%", max_width="820px", align="start",
        on_mount=RetardosState.on_load,
    )
