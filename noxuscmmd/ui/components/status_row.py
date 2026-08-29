"""
Fila reusable "icono + nombre + estado en línea/fuera de línea + IP", con
acceso a escritorio remoto opcional. La usa ui/views/device_list.py para
pintar cada equipo de la lista de "Equipos" desde un `rx.foreach`, de ahí que
todos sus parámetros (name, ip, icon, online) puedan ser Vars y no solo
valores fijos.
"""
from typing import Union
import reflex as rx


def status_row(name, ip, online, icon: Union[str, rx.Component], on_rdp=None,
               con_rdp=None):
    """Fila de un equipo con su estado en vivo.

    `name`, `ip`, `icon` y `online` pueden ser Vars: esta fila se pinta ahora
    dentro de un rx.foreach sobre los equipos reales (ver
    device_list.infra_hosts_card), no desde una lista escrita a mano.

    `con_rdp` es la condición —normalmente una Var— de si ese equipo ofrece
    escritorio remoto. Va aparte de `on_rdp` porque dentro de un foreach no se
    puede decidir en Python si hay botón o no: el manejador se pasa siempre y
    es la condición la que decide si se enseña.
    """
    color = rx.cond(online, "green", "red")
    punto_status = rx.cond(online, "🟢", "🔴")
    texto_status = rx.cond(online, " En línea", " Sin conexión")
    icon_style = {"transition": "transform 0.2s", "_hover": {"transform": "scale(1.4)"}}

    icon_element = rx.icon(icon, color=color, style=icon_style) if isinstance(icon, (str, rx.Var)) else icon

    row_content = rx.hstack(
        icon_element,
        rx.text(name, weight="medium"),
        rx.spacer(),
        rx.hstack(
            rx.text(punto_status, size="1"),
            rx.text(texto_status, color=color, display=["none", "none", "block"], white_space="nowrap"),
            rx.text(ip, color="gray.300", size="2", white_space="nowrap"),
            spacing="2", align="center",
        ),
        width="100%", align="center", spacing="3",
        style={"cursor": "pointer"} if on_rdp is not None else {},
    )

    if on_rdp is None:
        return row_content

    boton = rx.popover.root(
        rx.popover.trigger(rx.box(row_content, width="100%")),
        rx.popover.content(
            rx.button(
                rx.icon("monitor-play", size=14), "Escritorio remoto",
                on_click=on_rdp, variant="soft",
                style={"border-radius": "10px", "padding": "8px 16px", "cursor": "pointer"},
            ),
            style={"padding": "0", "margin": "0", "boxShadow": "none", "border": "none",
                   "minWidth": "auto", "minHeight": "auto"},
        ),
    )
    return boton if con_rdp is None else rx.cond(con_rdp, boton, row_content)
