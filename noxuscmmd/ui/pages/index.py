import reflex as rx
from ...domains.security.state import SecurityState
from ...domains.infra.state import InfraState
from ...domains.devices.registry_state import RegistryState
from ..views.header import header_view
from ..views.device_list import device_list_view
from ..views.device_controls import device_controls_view
from ..views.camera_view import camera_dialogs
from ..components.dialogs import photo_dialog


def index_page():
    return rx.box(
        rx.script(
            """
            window.addEventListener('pagehide', () => {
                if (window.socket) { window.socket.close(); }
            });
            """
        ),
        rx.link(
            rx.icon("layout-dashboard", size=15, color="#475569"),
            href="/panel",
            position="fixed",
            top="10px",
            right="10px",
            z_index="100",
            padding="6px",
            border_radius="8px",
            opacity="0.4",
            transition="opacity 0.15s ease",
            _hover={"opacity": "1"},
            title="Centro de Control (en pruebas)",
        ),
        rx.center(
            rx.vstack(
                header_view(),
                device_list_view(),
                device_controls_view(),
                camera_dialogs(),
                photo_dialog(
                    InfraState.dialog_foto_abierto,
                    InfraState.toggle_dialog,
                    InfraState.last_rpi_photo,
                ),
                spacing="6",
                width="100%",
                max_width="450px",
                padding_y="4em",
                padding_x="1.5em",
            ),
        ),
        on_mount=[SecurityState.on_load, InfraState.on_load, RegistryState.on_load],
        min_height="100vh",
        background="radial-gradient(circle at center, #0f172a 0%, #000000 100%)",
    )
