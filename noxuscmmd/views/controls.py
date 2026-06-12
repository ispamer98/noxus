import reflex as rx
from ..state import State
from ..components.button import control_button


def controls_view():
    return rx.vstack(
        rx.grid(
            control_button("Wake PC", "power", "green", State.wake_pc),
            control_button("Apagar PC", "power-off", "red", State.apagar_pc),
            control_button("GPIO 17", "key", "orange", State.gpio_17),
            control_button("Snapshot", "camera", "blue", State.tomar_foto_raspberry),
            control_button("Sensors", "thermometer", "pink", State.medir_temperatura),
            control_button("Reboot", "refresh-cw", "gray", State.restart_raspberry),
            columns="2",
            spacing="4",
            width="100%",
        ),
        
        
        rx.button(
            "🚀 ENVIAR NOTIFICACIÓN A TODOS",
            on_click=State.lanzar_alerta_global,
            color_scheme="red",
            width="100%",
        ),
        
        rx.box(
            rx.text(State.status, size="2", color="#94a3b8", italic=True),
            rx.foreach(State.temperaturas, lambda t: rx.text(t, color="orange.200", font_size="2")),
            width="100%",
            text_align="center",
            padding_top="1em",
        ),
        width="100%",
    )