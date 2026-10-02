"""
Selector de "Nodo" de los formularios de alta de sensores, puertas y luces.
Todos los nodos son iguales (colección `nodes`, todos por MQTT), sea una Pi o
un ESP32: una sola lista.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from .form_dialog import select_content


def node_select(name: str = "node_id", default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return rx.select.root(
        rx.select.trigger(placeholder="Nodo", width="100%"),
        select_content(
            rx.foreach(NodesState.nodes, lambda n: rx.select.item(n["name"], value=n["id"])),
        ),
        name=name,
        **kwargs,
    )
