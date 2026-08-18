"""
Pantalla «Detección de movimiento» (Ajustes).

Compara dos fotogramas de la misma cámara cada pocos segundos y avisa si ha
cambiado lo suficiente. Ni la cámara ni go2rtc tienen que saber nada de esto.
"""
import reflex as rx

from ....domains.cameras.movimiento_state import SENSIBILIDADES, MovimientoState
from .. import theme
from ..components.form_dialog import select_content, styled_select


def _fila_camara(c: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("video", size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.vstack(
            rx.text(c["nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.cond(
                c["sirve"],
                rx.text("Puede dar fotogramas", size="1", color=theme.MUTED),
                rx.text("No da fotogramas: no se puede vigilar así", size="1",
                        color=theme.MUTED),
            ),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.switch(
            checked=c["elegida"], disabled=~c["sirve"],
            on_change=lambda v: MovimientoState.alternar_camara(c["id"], v),
            size="2",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def movimiento_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Detección de movimiento", size="5", color=theme.TEXT),
            rx.text(
                "Compara dos fotogramas seguidos de cada cámara marcada y avisa "
                "si ha cambiado lo suficiente. Guarda la imagen del momento en "
                "el registro, igual que hace la alarma.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),

        rx.hstack(
            rx.switch(checked=MovimientoState.activada,
                      on_change=MovimientoState.alternar, size="3"),
            rx.text(MovimientoState.estado_texto, size="2", color=theme.TEXT),
            align="center", spacing="3", width="100%", wrap="wrap",
            padding="11px", border_radius="10px",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        ),

        rx.hstack(
            rx.switch(checked=MovimientoState.solo_armado,
                      on_change=MovimientoState.alternar_solo_armado, size="2"),
            rx.vstack(
                rx.text("Solo con la casa armada", size="2", color=theme.TEXT),
                rx.text(
                    "Recomendado. Mirar las cámaras de dentro de casa mientras "
                    "la familia está dentro no es vigilar, es otra cosa.",
                    size="1", color=theme.MUTED,
                ),
                spacing="0", align="start",
            ),
            align="center", spacing="3", width="100%", wrap="wrap",
        ),

        rx.vstack(
            rx.text("SENSIBILIDAD", size="1", color=theme.MUTED, weight="bold",
                    letter_spacing="0.08em"),
            styled_select(
                "Sensibilidad",
                select_content(
                    *[rx.select.item(etiqueta, value=str(valor))
                      for etiqueta, valor in SENSIBILIDADES],
                ),
                value=MovimientoState.umbral.to_string(),
                on_change=MovimientoState.poner_umbral,
            ),
            rx.text(
                "Un cambio de luz general (encender una lámpara, el amanecer) no "
                "cuenta como movimiento: se iguala el brillo antes de comparar.",
                size="1", color=theme.MUTED,
            ),
            spacing="2", width="100%", align="start",
        ),

        rx.vstack(
            rx.text("CÁMARAS QUE SE VIGILAN", size="1", color=theme.MUTED,
                    weight="bold", letter_spacing="0.08em"),
            rx.foreach(MovimientoState.camaras, _fila_camara),
            spacing="2", width="100%", align="start",
        ),

        spacing="5", width="100%", align="start", max_width="640px",
        padding_bottom="6",
        on_mount=MovimientoState.on_load,
    )
