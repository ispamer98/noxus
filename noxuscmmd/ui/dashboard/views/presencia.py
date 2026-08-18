"""
Pantalla «Simulación de presencia» (Ajustes).

Lo que se ve, en este orden: el interruptor, qué se ha aprendido, el plan de HOY
y las luces que pueden participar. El plan va arriba de las luces a propósito:
es lo que permite juzgar si esto hará algo sensato antes de irse una semana.
"""
import reflex as rx

from ....domains.security.presencia_state import PresenciaState
from .. import theme


def _fila_plan(a: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.text(a["hora"], size="2", weight="bold", color=theme.ACCENT,
                min_width="52px"),
        rx.text(a["que"], size="2", color=theme.TEXT),
        align="center", spacing="3", width="100%",
        padding="7px 11px", border_radius="8px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _fila_luz(l: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("lightbulb", size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.vstack(
            rx.text(l["nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.text(l["historial"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.switch(
            checked=l["elegida"],
            on_change=lambda v: PresenciaState.alternar_luz(l["id"], v),
            size="2",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def presencia_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Simulación de presencia", size="5", color=theme.TEXT),
            rx.text(
                "Repite los horarios reales de la casa cuando no hay nadie, en "
                "vez de encender una luz a la misma hora todos los días. Solo "
                "actúa con el sistema ARMADO, y al desarmar se olvida del plan.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),

        rx.hstack(
            rx.switch(checked=PresenciaState.activada,
                      on_change=PresenciaState.alternar, size="3"),
            rx.text(PresenciaState.estado_texto, size="2", color=theme.TEXT),
            align="center", spacing="3", width="100%", wrap="wrap",
            padding="11px", border_radius="10px",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        ),

        rx.vstack(
            rx.text("LO QUE HA APRENDIDO", size="1", color=theme.MUTED,
                    weight="bold", letter_spacing="0.08em"),
            rx.text(PresenciaState.resumen, size="1", color=theme.TEXT),
            rx.cond(
                PresenciaState.descartados > 0,
                rx.text(
                    "Los días descartados son los que parecen pruebas (muchas "
                    "acciones iguales seguidas): contarlos deformaría el patrón.",
                    size="1", color=theme.MUTED,
                ),
            ),
            spacing="2", width="100%", align="start",
        ),

        rx.vstack(
            rx.hstack(
                rx.text("PLAN DE HOY, " + PresenciaState.dia_texto.to(str).upper(),
                        size="1", color=theme.MUTED, weight="bold",
                        letter_spacing="0.08em"),
                rx.spacer(),
                rx.button("Volver a sortear", size="1", variant="surface",
                          on_click=PresenciaState.recalcular,
                          loading=PresenciaState.cargando),
                align="center", width="100%", spacing="3", wrap="wrap",
            ),
            rx.cond(
                PresenciaState.hay_plan,
                rx.vstack(
                    rx.foreach(PresenciaState.plan, _fila_plan),
                    spacing="2", width="100%",
                ),
                rx.box(
                    rx.text(
                        "Hoy no hay nada previsto. Elige abajo al menos una luz "
                        "que pueda encenderse.",
                        size="1", color=theme.MUTED,
                    ),
                    padding="14px", border_radius="10px", width="100%",
                    background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
                ),
            ),
            spacing="2", width="100%", align="start",
        ),

        rx.vstack(
            rx.text("LUCES QUE PUEDEN ENCENDERSE", size="1", color=theme.MUTED,
                    weight="bold", letter_spacing="0.08em"),
            rx.text(
                "Solo las que marques. La del dormitorio suele ser justo la que "
                "no interesa que se encienda sola.",
                size="1", color=theme.MUTED,
            ),
            rx.foreach(PresenciaState.luces, _fila_luz),
            spacing="2", width="100%", align="start",
        ),

        spacing="5", width="100%", align="start", max_width="640px",
        padding_bottom="6",
        on_mount=PresenciaState.on_load,
    )
