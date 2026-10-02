"""Piezas comunes del visor genérico de cámaras."""
import reflex as rx


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


def open_in_browser_button(url: str):
    """Abre el stream en una pestaña real del navegador."""
    return rx.button(
        rx.icon("external-link", size=16),
        on_click=rx.call_script(f"window.open('{url}', '_blank')"),
        variant="ghost",
        size="1",
        title="Abrir la cámara en una pestaña aparte",
    )
