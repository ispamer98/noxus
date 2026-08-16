import reflex as rx
from ...domains.infra.state import InfraState
from ...domains.devices import registry


def action_button(text: str, icon: str, color: str, on_click):
    return rx.button(
        rx.hstack(rx.icon(icon, size=16), rx.text(text, size="2")),
        on_click=on_click,
        color_scheme=color,
        width="100%",
        variant="surface",
        size="2",
    )


def ptz_control_buttons_small():
    """Botones PTZ pequeños para el popover"""
    from ...domains.cameras.state import CameraState
    return rx.grid(
        rx.box(),
        rx.button("⬆", on_click=CameraState.move_ptz("0"), variant="soft", size="1"),
        rx.box(),
        rx.button("⬅", on_click=CameraState.move_ptz("6"), variant="soft", size="1"),
        rx.button("⏹", on_click=CameraState.move_ptz("stop"), variant="soft", size="1", color_scheme="red"),
        rx.button("➡", on_click=CameraState.move_ptz("2"), variant="soft", size="1"),
        rx.box(),
        rx.button("⬇", on_click=CameraState.move_ptz("4"), variant="soft", size="1"),
        rx.box(),
        columns="3",
        spacing="1",
        width="100%",
        justify="center",
    )


# Acciones extra registradas por nombre de handler (ver devices/models.py Accion)
_ACCION_HANDLERS = {
    "wake_pc": InfraState.wake_pc,
    "rdp_pc": InfraState.rdp_pc,
    "rdp_portatil": InfraState.rdp_portatil,
    "rdp_raspberry": InfraState.rdp_raspberry,
    "gpio_17_test": InfraState.gpio_17_test,
    "tomar_foto_raspberry": InfraState.tomar_foto_raspberry,
}


def device_controls_view():
    devices_ui = [
        ("server", "Servidor", "network"),
        ("pc", "PC", "monitor"),
        ("portatil", "Portátil", "laptop"),
        ("raspberry", "Raspberry", "grape"),
        ("pi_zero", "Pi Zero", "microchip"),
    ]

    control_icons = rx.hstack(
        *[
            rx.popover.root(
                rx.popover.trigger(
                    rx.button(
                        rx.icon(icono, size=28, color=rx.cond(InfraState.host_online[dk], "#4ade80", "#64748b")),
                        variant="ghost",
                        size="3",
                        title=name,
                    )
                ),
                rx.popover.content(
                    rx.vstack(
                        action_button("Apagar", "power-off", "red",
                                      InfraState.accion_apagar(dk)),
                        action_button("Reiniciar", "refresh-cw", "orange",
                                      InfraState.accion_reiniciar(dk)),
                        action_button("Temperatura", "thermometer", "blue",
                                      InfraState.accion_temperatura(dk)),
                        *acciones_extra_ui(dk),
                        rx.divider(),
                        rx.text("Comando SSH:", size="1", weight="bold"),
                        rx.hstack(
                            rx.input(
                                value=InfraState.custom_command.get(dk, ""),
                                on_change=lambda v: InfraState.set_custom_command(dk, v),
                                placeholder="ls -la",
                                size="1",
                                width="150px",
                            ),
                            rx.button("Enviar", size="1",
                                      on_click=InfraState.ejecutar_comando_personalizado(dk)),
                            spacing="2",
                        ),
                        rx.cond(
                            InfraState.custom_output.get(dk, "") != "",
                            rx.box(
                                rx.code(
                                    InfraState.custom_output.get(dk, ""),
                                    language="bash",
                                    width="100%",
                                ),
                                width="100%",
                                max_height="150px",
                                overflow_y="auto",
                                background="#1a1a1a",
                                padding="8px",
                                border_radius="4px",
                            ),
                        ),
                        spacing="2",
                        width="250px",
                    ),
                ),
            )
            for dk, name, icono in devices_ui
        ],
        spacing="4",
        width="100%",
        justify="between",
    )

    return rx.vstack(
        rx.hstack(
            rx.icon("cpu", size=20, color="#38bdf8"),
            rx.heading("CONTROL POR EQUIPO", size="3", letter_spacing="0.05em"),
            width="100%",
            align="center",
        ),
        rx.divider(opacity="0.1"),
        control_icons,
        rx.divider(opacity="0.2"),
        rx.box(
            rx.text(InfraState.status, size="2", color="#94a3b8", italic=True),
            rx.foreach(InfraState.temperaturas, lambda t: rx.text(t, color="orange.200", font_size="2")),
            width="100%",
            text_align="center",
            padding_top="1em",
        ),
        width="100%",
        spacing="3",
    )


def acciones_extra_ui(device_key: str):
    """Botones de relés (genéricos, por GPIO) + acciones extra del host."""
    items = []

    for relay_id, relay in registry.relays().items():
        if relay.gpio.host != device_key:
            continue
        items.append(
            rx.hstack(
                rx.text(f"{relay.name} (GPIO{relay.gpio.pin})", size="1", width="140px"),
                rx.button("ON", size="1", color_scheme="green",
                          on_click=InfraState.accion_gpio(relay_id, "on")),
                rx.button("OFF", size="1", color_scheme="red",
                          on_click=InfraState.accion_gpio(relay_id, "off")),
                spacing="2",
            )
        )

    host = registry.DEVICES.get(device_key)
    for extra in getattr(host, "acciones_extra", []):
        handler = _ACCION_HANDLERS[extra.handler_name]
        items.append(action_button(extra.nombre, "star", "purple", handler))

    return items
