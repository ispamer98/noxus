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
            "overflow": "hidden",
        },
    )

def ptz_button(label: str, direction: str):
    return rx.button(
        label,
        on_click=State.move_ptz(direction),
        variant="soft",
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
                    # ── Cámara fija: stream go2rtc ──────────────────────
                    rx.dialog.root(
                        rx.dialog.trigger(
                            rx.button(
                                "VER FIJA",
                                on_click=State.toggle_fija_stream,
                                variant="surface",
                                width="100%",
                            )
                        ),
                        rx.dialog.content(
                            rx.vstack(
                                video_embed_safe(State.url_fija_stream),
                                rx.button("CERRAR", on_click=State.toggle_fija_stream),
                            ),
                            style={
                                "max_width": "800px",
                                "background": "#0f172a",
                                "padding": "20px",
                            },
                        ),
                        open=State.show_fija_stream,
                    ),
                    # ── PTZ: stream go2rtc + controles ──────────────────
                    rx.dialog.root(
                        rx.dialog.trigger(
                            rx.button(
                                "CONECTAR PTZ",
                                variant="surface",
                                color_scheme="indigo",
                                width="100%",
                                size="2",
                            )
                        ),
                        rx.dialog.content(
                            rx.vstack(
                                video_embed_safe(State.url_ptz_embed),
                                rx.center(
                                    rx.vstack(
                                        rx.grid(
                                            rx.box(),
                                            ptz_button("▲", "0"),
                                            rx.box(),
                                            ptz_button("◀", "6"),
                                            rx.center(rx.icon("move", size=20, color="#818cf8")),
                                            ptz_button("▶", "2"),
                                            rx.box(),
                                            ptz_button("▼", "4"),
                                            rx.box(),
                                            columns="3",
                                            spacing="2",
                                            pt="4",
                                        ),
                                        rx.text(
                                            State.cam_msg,
                                            size="2",
                                            color="#ff4d4d",
                                            weight="bold",
                                            pt="2",
                                        ),
                                    ),
                                    width="100%",
                                ),
                                rx.dialog.close(
                                    rx.button(
                                        "CERRAR",
                                        width="100%",
                                        color_scheme="gray",
                                        variant="soft",
                                        mt="4",
                                    )
                                ),
                            ),
                            style={
                                "max_width": "800px",
                                "background": "#0f172a",
                                "padding": "20px",
                            },
                        ),
                        open=State.show_ptz_stream,
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