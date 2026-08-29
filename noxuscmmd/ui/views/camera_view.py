"""
Diálogos de las DOS cámaras "de fábrica" (Fija y PTZ, ver domains/cameras/
state.py): vídeo en directo embebido, control de movimiento para la PTZ, y un
modo PC/Móvil que cambia cómo se acomoda el vídeo en pantalla.

Las cámaras dadas de alta después por el usuario (domains/nodes) no pasan por
aquí: tienen su propia ventana flotante genérica (ver
ui/dashboard/views/cctv.py y ui/dashboard/windows.py). Estas dos son un caso
aparte porque llevan controles propios (el PTZ) que no tiene sentido
generalizar para una cámara cualquiera.
"""
import reflex as rx
from ...domains.cameras.state import CameraState


def video_embed_safe(url: str):
    return rx.box(
        rx.el.iframe(
            src=url,
            style={"width": "100%", "height": "100%", "border": "none"},
            allow="autoplay; fullscreen",
        ),
        style={
            "width": "100%",
            "aspect_ratio": "16 / 9",
            "border_radius": "8px",
            "background": "#000",
            "overflow": "hidden",
        },
    )


def ptz_control_buttons():
    """Botones de control PTZ (arriba, abajo, izquierda, derecha, stop)"""
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


def open_in_browser_button(url: str):
    """Abre el stream en una pestaña real del navegador. Necesario cuando la
    cámara está detrás de Cloudflare Access: la pantalla de login de Access
    bloquea su propio renderizado dentro de un iframe (frame-ancestors), así
    que dentro del diálogo solo se ve una página en blanco hasta que te
    autenticas en una pestaña normal."""
    return rx.button(
        rx.icon("external-link", size=16),
        on_click=rx.call_script(f"window.open('{url}', '_blank')"),
        variant="ghost",
        size="1",
        title="Abrir en el navegador (necesario para iniciar sesión en Cloudflare Access)",
    )


def camera_dialog_fija():
    """Diálogo de la cámara fija"""
    return rx.dialog.root(
        rx.dialog.trigger(rx.box()),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Cámara Fija", size="3", weight="bold"),
                    rx.spacer(),
                    open_in_browser_button(CameraState.url_fija_stream),
                    rx.button(
                        rx.icon("refresh-cw", size=16),
                        on_click=CameraState.toggle_cam_mode,
                        variant="ghost",
                        size="1",
                        title="Cambiar entre modo PC y modo Móvil",
                    ),
                ),
                rx.cond(
                    CameraState.cam_mode == "mobile",
                    rx.vstack(
                        video_embed_safe(CameraState.url_fija_stream),
                        spacing="3",
                        width="100%",
                    ),
                    video_embed_safe(CameraState.url_fija_stream),
                ),
                rx.divider(),
                rx.button(
                    "CERRAR",
                    on_click=CameraState.toggle_fija_stream,
                    size="2",
                    variant="ghost",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "max_width": "800px",
                "background": "#0f172a",
                "padding": "20px",
            },
        ),
        open=CameraState.show_fija_stream,
    )


def camera_dialog_ptz():
    """Diálogo de la cámara PTZ con controles de movimiento"""
    return rx.dialog.root(
        rx.dialog.trigger(rx.box()),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Cámara PTZ", size="3", weight="bold"),
                    rx.spacer(),
                    open_in_browser_button(CameraState.url_ptz_stream),
                    rx.button(
                        rx.icon("refresh-cw", size=16),
                        on_click=CameraState.toggle_cam_mode,
                        variant="ghost",
                        size="1",
                        title="Cambiar entre modo PC y modo Móvil",
                    ),
                ),
                rx.cond(
                    CameraState.cam_mode == "mobile",
                    rx.vstack(
                        video_embed_safe(CameraState.url_ptz_stream),
                        spacing="3",
                        width="100%",
                    ),
                    video_embed_safe(CameraState.url_ptz_stream),
                ),
                rx.divider(),
                rx.text("🎮 Control PTZ:", size="2", weight="bold"),
                ptz_control_buttons(),
                rx.text(CameraState.cam_msg, size="1", color="gray"),
                rx.divider(),
                rx.button(
                    "CERRAR",
                    on_click=CameraState.toggle_ptz_stream,
                    size="2",
                    variant="ghost",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "max_width": "800px",
                "background": "#0f172a",
                "padding": "20px",
            },
        ),
        open=CameraState.show_ptz_stream,
    )


def camera_dialogs():
    """Agrupa ambos diálogos para usarlos en index.py"""
    return rx.vstack(
        camera_dialog_fija(),
        camera_dialog_ptz(),
        width="100%",
        spacing="0",
    )
