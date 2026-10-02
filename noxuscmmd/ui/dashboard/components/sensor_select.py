"""
Selector de "Sensor" reutilizado por la pestaña Grupos.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from .form_dialog import select_content


def sensor_select(on_change) -> rx.Component:
    return rx.select.root(
        rx.select.trigger(placeholder="Añadir sensor al grupo...", width="100%"),
        select_content(
            rx.select.group(
                rx.select.label("Sensores"),
                rx.foreach(NodesState.sensors, lambda s: rx.select.item(s["name"], value=s["id"])),
            ),
        ),
        on_change=on_change,
        value="",
    )
