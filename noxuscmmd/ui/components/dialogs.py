"""
Diálogo genérico para enseñar una foto a pantalla completa — hoy solo lo usa
la cámara Pi Zero (una captura fija, no un stream), ver ui/views/camera_view.py
para los diálogos con vídeo en directo.
"""
import reflex as rx

def photo_dialog(is_open, on_close, image_url):
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Cámara Pi Zero"),
            rx.cond(
                image_url != "",
                rx.image(src=image_url, width="100%"),
                rx.text("Cargando captura...")
            ),
            rx.dialog.close(rx.button("Cerrar", on_click=on_close, mt="4")),
        ),
        open=is_open,
    )
