"""Vista "Modos de la casa": qué modos hay y qué lanza cada uno.

No hay editor de acciones aquí a propósito. Un modo dice QUÉ reglas ejecuta, y
las reglas se montan donde se han montado siempre, en Automatizaciones. Meter
un segundo editor habría significado dos sitios donde se define lo que hace la
casa, y dos sitios que se contradicen a la primera de cambio.
"""
import reflex as rx

from .. import theme
from ..state import DashboardState
from ....domains.modes.state import ModesState


def _regla(item: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.checkbox(
            checked=item["elegida"].to(bool),
            on_change=lambda _: ModesState.alternar_regla(item["id"]),
        ),
        rx.text(item["nombre"], size="1", color=theme.TEXT),
        align="center", spacing="2", width="100%",
    )


def _editor() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.text("Editar modo", size="3", weight="bold", color=theme.TEXT),
            ),
            rx.vstack(
                rx.text("Nombre", size="1", color=theme.MUTED),
                rx.input(value=ModesState.ed_nombre,
                         on_change=ModesState.set_ed_nombre, width="100%"),
                rx.text("Para qué es", size="1", color=theme.MUTED),
                rx.input(value=ModesState.ed_descripcion,
                         on_change=ModesState.set_ed_descripcion,
                         placeholder="No hay nadie en casa", width="100%"),
                rx.text("Qué lanza al ponerlo", size="1", color=theme.MUTED),
                rx.text(
                    "Las reglas se crean en Automatizaciones. Aquí solo se "
                    "elige cuáles van con este modo.",
                    size="1", color=theme.MUTED, style={"line-height": "1.5"},
                ),
                rx.cond(
                    ModesState.reglas_disponibles.length() > 0,
                    rx.vstack(
                        rx.foreach(ModesState.reglas_disponibles, _regla),
                        spacing="1", width="100%", max_height="220px",
                        overflow_y="auto",
                    ),
                    rx.text("Todavía no hay ninguna automatización creada.",
                            size="1", color=theme.MUTED),
                ),
                rx.hstack(
                    rx.button("Borrar este modo", variant="soft",
                              color_scheme="red", size="1",
                              on_click=ModesState.borrar(ModesState.editando)),
                    rx.spacer(),
                    rx.button("Cancelar", variant="soft", color_scheme="gray",
                              on_click=ModesState.cerrar_editor),
                    rx.button("Guardar", on_click=ModesState.guardar),
                    spacing="2", width="100%", align="center",
                ),
                spacing="2", width="100%",
            ),
            max_width="480px",
        ),
        open=ModesState.editando != "",
        on_open_change=lambda abierto: rx.cond(
            abierto, rx.noop(), ModesState.cerrar_editor()),
    )


def _ficha(modo: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon(modo["icono"].to(str), size=18, color=modo["color"].to(str)),
            padding="10px", border_radius="10px",
            background=theme.alpha(theme.ACCENT, 0.1),
            border=f"1px solid {theme.BORDER}", flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(modo["nombre"], size="2", weight="bold", color=theme.TEXT),
                rx.cond(
                    modo["activo"].to(bool),
                    rx.text("puesto ahora", size="1", color=theme.SUCCESS),
                ),
                align="center", spacing="2",
            ),
            rx.text(modo["descripcion"], size="1", color=theme.MUTED),
            rx.text(modo["resumen"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(rx.icon("pencil", size=13), size="1", variant="soft",
                  on_click=ModesState.abrir_editor(modo["id"])),
        align="center", spacing="3", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="12px 14px",
    )


def modos_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("house", size=22, color=theme.ACCENT),
            rx.heading("Modos de la casa", size="6", color=theme.TEXT),
            rx.spacer(),
            rx.button(rx.icon("plus", size=15), "Nuevo", size="2",
                      variant="soft", on_click=ModesState.crear),
            rx.button(rx.icon("arrow-left", size=15), "Ajustes", size="2",
                      variant="soft",
                      on_click=DashboardState.set_view("settings_hub")),
            align="center", spacing="2", width="100%", wrap="wrap",
        ),
        rx.text(
            "Un modo es un botón que lanza varias automatizaciones de golpe: "
            "«me voy» apaga, cierra y arma sin tener que acordarse de las nueve "
            "cosas. Además, el modo en el que está la casa se puede usar dentro "
            "de cualquier automatización, como disparador («cuando la casa pase "
            "a Noche») o como condición («solo si está en Fuera»).",
            size="1", color=theme.MUTED, style={"line-height": "1.6"},
        ),
        rx.vstack(
            rx.foreach(ModesState.modos, _ficha),
            spacing="2", width="100%",
        ),
        _editor(),
        spacing="3", width="100%", max_width="820px", align="start",
        on_mount=ModesState.on_load,
    )
