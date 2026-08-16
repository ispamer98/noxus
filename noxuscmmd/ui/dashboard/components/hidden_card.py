"""Tarjeta compacta para restaurar entidades estáticas ocultas (registry.hide).
Recibe un dict {entity_id: nombre} ya calculado en Python (build-time, igual
que el resto de edición estática) — si está vacío no pinta nada."""
import reflex as rx

from .. import theme
from ....domains.devices.registry_state import RegistryState


def hidden_entities_card(title: str, items: dict[str, str]) -> rx.Component:
    if not items:
        return rx.fragment()
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("eye-off", size=15, color=theme.MUTED),
                rx.text(f"{title} OCULTOS", size="1", color=theme.MUTED, letter_spacing="0.06em", weight="bold"),
                width="100%",
                align="center",
            ),
            *[
                rx.hstack(
                    rx.text(name, size="2", color=theme.MUTED),
                    rx.spacer(),
                    rx.button(
                        rx.icon("rotate-ccw", size=12),
                        "Restaurar",
                        size="1",
                        variant="ghost",
                        on_click=RegistryState.unhide_entity(entity_id),
                    ),
                    width="100%",
                    align="center",
                )
                for entity_id, name in items.items()
            ],
            # Ocultar/restaurar se guarda ya, pero solo se ve en pantalla tras reiniciar el servicio.
            spacing="2",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.02)",
        border=f"1px dashed {theme.BORDER}",
        padding="3",
    )
