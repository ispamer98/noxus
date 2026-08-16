"""
Selector de "Sensor" reutilizado por la pestaña Grupos: agrupa los sensores
estáticos del registry (puerta principal, tampers...) junto a los sensores
dados de alta en caliente sobre nodos (domains/nodes). Mismo patrón que
node_select.py.
"""
import reflex as rx

from ....domains.devices import registry
from ....domains.nodes.state import NodesState
from .form_dialog import select_content


def sensor_select(on_change) -> rx.Component:
    return rx.select.root(
        rx.select.trigger(placeholder="Añadir sensor al grupo...", width="100%"),
        select_content(
            rx.select.group(
                rx.select.label("Sensores del sistema"),
                *[rx.select.item(s.name, value=sid) for sid, s in registry.binary_sensors().items()],
            ),
            rx.select.group(
                rx.select.label("Sensores adicionales"),
                rx.foreach(NodesState.sensors, lambda s: rx.select.item(s["name"], value=s["id"])),
            ),
        ),
        on_change=on_change,
        value="",
    )
