from typing import Union
import reflex as rx

def status_row(name: str, ip: str, online: bool, icon: Union[str, rx.Component], on_rdp=None):
    color = rx.cond(online, "green", "red")
    punto_status = rx.cond(online, "🟢", "🔴")
    texto_status = rx.cond(online, " En línea", " Sin conexión")
    icon_style = {"transition": "transform 0.2s", "_hover": {"transform": "scale(1.4)"}}
    style_clickable = {"cursor": "pointer"} if on_rdp is not None else {}

    # Construcción del elemento del icono
    if isinstance(icon, str):
        icon_element = rx.icon(icon, color=color, style=icon_style)
    else:
        # Asegurar que el componente recibe color y tamaño (si es nuestro icono, tiene get_style)
        icon_element = icon
        # Si el componente no maneja el color/tamaño automáticamente, puedes forzarlo:
        # icon_element = icon
        # o si lo prefieres, puedes clonar la prop con .clone
        # icon_element = icon.create(size=20, color=color)

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
        width="100%", align="center", spacing="3", style=style_clickable,
    )

    if on_rdp is not None:
        return rx.popover.root(
            rx.popover.trigger(rx.box(row_content, width="100%")),
            rx.popover.content(
                rx.button(f"Conectar con {name} ⌘", on_click=on_rdp, variant="soft", style={"border": "3px solid #000000", "border-radius": "12px", "padding": "8px 16px", "cursor": "pointer"}),
                style={"padding": "0", "margin": "0", "boxShadow": "none", "border": "none", "minWidth": "auto", "minHeight": "auto"}
            ),
        )
    return row_content

