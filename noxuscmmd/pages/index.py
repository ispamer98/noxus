import reflex as rx
from ..state import State
from ..views.header import header_view
from ..views.camera_view import camera_view
from ..views.device_list import device_list_view
from ..views.controls import controls_view
from ..components.dialogs import photo_dialog


def index_page():
    return rx.box(
        # Refresco de pings cada 8 s (antes 5 s — reduce carga sin perder frescura)
        rx.box(
            rx.moment(
                interval=8_000,
                on_change=State.actualizar_estados,
            ),
            display="none",
        ),
        rx.center(
            rx.vstack(
                # Botón invisible para navegación interna
                rx.button(
                    "Ir a Subida",
                    on_click=rx.redirect("/upload"),
                    style={"opacity": "0.0000001"},
                    margin_bottom="-2em",
                    margin_top="-5em",
                ),
                header_view(),
                device_list_view(),
                camera_view(),
                controls_view(),
                photo_dialog(
                    State.dialog_foto_abierto,
                    State.toggle_dialog,
                    State.last_rpi_photo,
                ),
                spacing="6",
                width="100%",
                max_width="450px",
                padding_y="4em",
                padding_x="1.5em",
            ),
        ),
        # on_mount → State.on_load (lanza todo en paralelo, no bloquea)
        on_mount=State.on_load,
        min_height="100vh",
        background="radial-gradient(circle at center, #0f172a 0%, #000000 100%)",
    )