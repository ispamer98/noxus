import reflex as rx
from ..state import State

def status_dot(name, online):
    return rx.hstack(
        rx.text(name, size="2", weight="bold", color="#94a3b8"),
        rx.text(rx.cond(online, "🟢", "🔴"), size="1"),
        spacing="2",
        align="center",
    )

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
            "overflow": "hidden"
        }
    )

def camera_view():
    return rx.vstack(
        rx.hstack(
            rx.icon("video", size=20, color="#818cf8"),
            rx.heading("SISTEMA CCTV", size="3", letter_spacing="0.05em"),
            width="100%",
            align="center",
            px="2",
            pt="2",
        ),
        rx.card(
            rx.vstack(
                rx.hstack(                    
                    status_dot("CÁMARA FIJA", State.cam_fija_online),
                    rx.spacer(),
                    status_dot("DOMO PTZ", State.cam_ptz_online),
                    width="100%",
                ),
                rx.divider(opacity="0.1"),
                rx.grid(
                    rx.dialog.root(
                        rx.dialog.trigger(
                            rx.button("VER FIJA", on_click=State.toggle_fija, variant="surface", width="100%")
                        ),
                        rx.dialog.content(
                            rx.vstack(
                                # Mostramos la imagen que se refresca sola
                                rx.image(src=State.url_snapshot_fija, width="100%", height="auto"),
                                rx.dialog.close(rx.button("CERRAR")),
                            )
                        )
                    ),
                    rx.dialog.root(
                        rx.dialog.trigger(rx.button("CONECTAR PTZ", variant="surface", color_scheme="indigo", width="100%", size="2")),
                        rx.dialog.content(
                            rx.vstack(
                                video_embed_safe(State.url_ptz_embed),
                                rx.center(
                                    rx.vstack(
                                        rx.grid(
                                            rx.box(), rx.button("▲", on_click=lambda: State.move_ptz("0"), variant="soft"), rx.box(),
                                            rx.button("◀", on_click=lambda: State.move_ptz("6"), variant="soft"), 
                                            rx.center(rx.icon("move", size=20, color="#818cf8")), 
                                            rx.button("▶", on_click=lambda: State.move_ptz("2"), variant="soft"),
                                            rx.box(), rx.button("▼", on_click=lambda: State.move_ptz("4"), variant="soft"), rx.box(),
                                            columns="3", spacing="2", pt="4",
                                        ),
                                        rx.text(State.cam_msg, size="2", color="#ff4d4d", weight="bold", pt="2"),
                                    ),
                                    width="100%",
                                ),
                                rx.dialog.close(rx.button("CERRAR", width="100%", color_scheme="gray", variant="soft", mt="4")),
                            ),
                            style={"max_width": "800px", "background": "#0f172a", "padding": "20px"}
                        ),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                spacing="3",
            ),
            width="100%",
            background="rgba(255, 255, 255, 0.03)",
            backdrop_filter="blur(10px)",
            border="1px solid rgba(255, 255, 255, 0.1)",
            padding="4",
        ),
        width="100%",
        spacing="3",
    )