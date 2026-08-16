"""
Selector de "Nodo" reutilizado por los formularios de alta de sensores,
puertas y luces: agrupa los hosts con GPIO fijos del registry (Raspberry,
Pi Zero — accionados por SSH) junto a los nodos dados de alta en caliente,
sea cual sea su tipo (ESP32/MQTT o SSH — ver NodesState._node_ssh, que decide
el transporte mirando registry.gpio_hosts() primero y si no el kind del
nodo dinámico).
"""
import reflex as rx

from ....domains.devices import registry
from ....domains.nodes.state import NodesState
from .form_dialog import select_content


def node_select(name: str = "node_id", default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return rx.select.root(
        rx.select.trigger(placeholder="Nodo", width="100%"),
        select_content(
            rx.select.group(
                rx.select.label("Equipos fijos (SSH)"),
                *[rx.select.item(host.name, value=key) for key, host in registry.gpio_hosts().items()],
            ),
            rx.select.group(
                rx.select.label("Nodos dados de alta"),
                rx.foreach(
                    NodesState.nodes,
                    lambda n: rx.select.item(f"{n['name']} ({n['kind']})", value=n["id"]),
                ),
            ),
        ),
        name=name,
        **kwargs,
    )
