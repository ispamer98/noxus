import reflex as rx
from ..state import State, DEVICE_CONFIG
import os

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
    return rx.grid(
        rx.box(),
        rx.button("⬆", on_click=State.move_ptz("0"), variant="soft", size="1"),
        rx.box(),
        rx.button("⬅", on_click=State.move_ptz("6"), variant="soft", size="1"),
        rx.button("⏹", on_click=State.move_ptz("stop"), variant="soft", size="1", color_scheme="red"),
        rx.button("➡", on_click=State.move_ptz("2"), variant="soft", size="1"),
        rx.box(),
        rx.button("⬇", on_click=State.move_ptz("4"), variant="soft", size="1"),
        rx.box(),
        columns="3",
        spacing="1",
        width="100%",
        justify="center",
    )

def device_controls_view():
    devices_ui = [
        ("server",    State.server_online,    "Servidor", "network"),
        ("pc",        State.pc_online,        "PC",       "monitor"),
        ("portatil",  State.portatil_online,  "Portátil", "laptop"),
        ("raspberry", State.raspberry_online, "Raspberry","grape"),
        ("pi_zero",   State.pi_zero_online,   "Pi Zero",  "microchip"),
    ]
    
    control_icons = rx.hstack(
        *[
            rx.popover.root(
                rx.popover.trigger(
                    rx.button(
                        rx.icon(icono, size=28, color=rx.cond(online_var, "#4ade80", "#64748b")),
                        variant="ghost",
                        size="3",
                        title=name,
                    )
                ),
                rx.popover.content(
                    rx.vstack(
                        action_button("Apagar", "power-off", "red",
                                      State.accion_apagar(dk)),
                        action_button("Reiniciar", "refresh-cw", "orange",
                                      State.accion_reiniciar(dk)),
                        action_button("Temperatura", "thermometer", "blue",
                                      State.accion_temperatura(dk)),
                        *acciones_extra_ui(dk),
                        # ── Controles PTZ (solo para Raspberry) ──
                        rx.cond(
                            dk == "raspberry",
                            rx.vstack(
                                rx.divider(),
                                rx.text("🎥 CONTROL PTZ", size="1", weight="bold"),
                                ptz_control_buttons_small(),
                                rx.text(State.cam_msg, size="1", color="gray"),
                                rx.hstack(
                                    rx.text("🔒 Privacidad:", size="1"),
                                    rx.switch(
                                        on_change=lambda val: State.toggle_privacy(
                                            os.getenv("ID_PTZ_TUYA"), val
                                        ),
                                        size="1",
                                    ),
                                    spacing="2",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                        ),
                        # ── Privacidad para cámara fija (solo Pi Zero) ──
                        rx.cond(
                            dk == "pi_zero",
                            rx.vstack(
                                rx.divider(),
                                rx.text("📷 CÁMARA FIJA", size="1", weight="bold"),
                                rx.hstack(
                                    rx.text("🔒 Privacidad:", size="1"),
                                    rx.switch(
                                        on_change=lambda val: State.toggle_privacy(
                                            os.getenv("ID_FIJA_TUYA"), val
                                        ),
                                        size="1",
                                    ),
                                    spacing="2",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                        ),
                        rx.divider(),
                        rx.text("Comando SSH:", size="1", weight="bold"),
                        rx.hstack(
                            rx.input(
                                value=State.custom_command.get(dk, ""),
                                on_change=lambda v: State.set_custom_command(dk, v),
                                placeholder="ls -la",
                                size="1",
                                width="150px",
                            ),
                            rx.button("Enviar", size="1",
                                      on_click=State.ejecutar_comando_personalizado(dk)),
                            spacing="2",
                        ),
                        rx.cond(
                            State.custom_output.get(dk, "") != "",
                            rx.box(
                                rx.code(
                                    State.custom_output.get(dk, ""),
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
            for dk, online_var, name, icono in devices_ui
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
            rx.text(State.status, size="2", color="#94a3b8", italic=True),
            rx.foreach(State.temperaturas, lambda t: rx.text(t, color="orange.200", font_size="2")),
            width="100%",
            text_align="center",
            padding_top="1em",
        ),
        width="100%",
        spacing="3",
    )

def acciones_extra_ui(device_key: str):
    config = DEVICE_CONFIG.get(device_key, {})
    gpio_pins = config.get("gpio_pins", {})
    extras = config.get("acciones_extra", [])
    
    items = []
    
    if gpio_pins:
        for pin, label in gpio_pins.items():
            items.append(
                rx.hstack(
                    rx.text(f"GPIO{pin} ({label})", size="1", width="80px"),
                    rx.button("ON", size="1", color_scheme="green",
                              on_click=State.accion_gpio(device_key, pin, "on")),
                    rx.button("OFF", size="1", color_scheme="red",
                              on_click=State.accion_gpio(device_key, pin, "off")),
                    spacing="2",
                )
            )
    
    for extra in extras:
        items.append(
            action_button(extra["nombre"], "star", "purple", extra["funcion"])
        )
    
    return items