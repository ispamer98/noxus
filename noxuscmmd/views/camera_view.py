import reflex as rx
from ..state import State
import os

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

def camera_dialog_fija():
    """Diálogo de la cámara fija"""
    return rx.dialog.root(
        rx.dialog.trigger(rx.box()),
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text("Cámara Fija", size="3", weight="bold"),
                    rx.spacer(),
                    # 1. ELIMINADO: rx.badge de MODO PC / MODO MÓVIL
                    rx.button(
                        rx.icon("refresh-cw", size=16),
                        on_click=State.toggle_cam_mode,
                        variant="ghost",
                        size="1",
                        title="Cambiar entre modo PC y modo Móvil",
                    ),
                ),
                # 2. ELIMINADO: rx.text con la URL del stream
                rx.cond(
                    State.cam_mode == "mobile",
                    rx.vstack(
                        # 3. ELIMINADO: rx.text "Modo móvil: usa el reproductor nativo..."
                        video_embed_safe(State.url_fija_stream),
                        # 4. COMENTADO: Botones "Forzar modo PC" y "Abrir en navegador"
                        # rx.hstack(
                        #     rx.button(
                        #         "📱 Forzar modo PC",
                        #         on_click=State.toggle_cam_mode,
                        #         size="2",
                        #         variant="soft",
                        #         color_scheme="blue",
                        #     ),
                        #     rx.button(
                        #         "📺 Abrir en navegador",
                        #         on_click=rx.call_script(
                        #             f"window.open('{State.url_fija_stream}', '_blank')"
                        #         ),
                        #         size="2",
                        #         variant="solid",
                        #         color_scheme="green",
                        #     ),
                        #     spacing="2",
                        #     width="100%",
                        # ),
                        spacing="3",
                        width="100%",
                    ),
                    video_embed_safe(State.url_fija_stream),
                ),
                rx.divider(),
                # 5. COMENTADO: Switch de Modo Privacidad
                # rx.hstack(
                #     rx.text("🔒 Modo privacidad:", size="2"),
                #     rx.switch(
                #         on_change=lambda val: State.toggle_privacy(os.getenv("ID_FIJA_TUYA"), val),
                #     ),
                #     spacing="3",
                #     width="100%",
                # ),
                rx.button(
                    "CERRAR",
                    on_click=State.toggle_fija_stream,
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
        open=State.show_fija_stream,
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
                    # 1. ELIMINADO: rx.badge de MODO PC / MODO MÓVIL
                    rx.button(
                        rx.icon("refresh-cw", size=16),
                        on_click=State.toggle_cam_mode,
                        variant="ghost",
                        size="1",
                        title="Cambiar entre modo PC y modo Móvil",
                    ),
                ),
                # 2. ELIMINADO: rx.text con la URL del stream
                rx.cond(
                    State.cam_mode == "mobile",
                    rx.vstack(
                        # 3. ELIMINADO: rx.text "Modo móvil: usa el reproductor nativo..."
                        video_embed_safe(State.url_ptz_stream),
                        # 4. COMENTADO: Botones "Forzar modo PC" y "Abrir en navegador"
                        # rx.hstack(
                        #     rx.button(
                        #         "📱 Forzar modo PC",
                        #         on_click=State.toggle_cam_mode,
                        #         size="2",
                        #         variant="soft",
                        #         color_scheme="blue",
                        #     ),
                        #     rx.button(
                        #         "📺 Abrir en navegador",
                        #         on_click=rx.call_script(
                        #             f"window.open('{State.url_ptz_stream}', '_blank')"
                        #         ),
                        #         size="2",
                        #         variant="solid",
                        #         color_scheme="green",
                        #     ),
                        #     spacing="2",
                        #     width="100%",
                        # ),
                        spacing="3",
                        width="100%",
                    ),
                    video_embed_safe(State.url_ptz_stream),
                ),
                rx.divider(),
                rx.text("🎮 Control PTZ:", size="2", weight="bold"),
                ptz_control_buttons(),
                rx.text(State.cam_msg, size="1", color="gray"),
                rx.divider(),
                # 5. COMENTADO: Switch de Modo Privacidad
                # rx.hstack(
                #     rx.text("🔒 Modo privacidad:", size="2"),
                #     rx.switch(
                #         on_change=lambda val: State.toggle_privacy(os.getenv("ID_PTZ_TUYA"), val),
                #     ),
                #     spacing="3",
                #     width="100%",
                # ),
                rx.button(
                    "CERRAR",
                    on_click=State.toggle_ptz_stream,
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
        open=State.show_ptz_stream,
    )

def camera_dialogs():
    """Agrupa ambos diálogos para usarlos en index.py"""
    return rx.vstack(
        camera_dialog_fija(),
        camera_dialog_ptz(),
        width="100%",
        spacing="0",
    )