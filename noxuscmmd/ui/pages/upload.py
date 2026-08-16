import reflex as rx
from ...domains.infra.state import InfraState

def upload_page():
    return rx.center(
        rx.vstack(
            rx.heading("Subida de Archivos"),
            rx.upload(
                id="file_upload",
                border="2px dashed #ccc",
                padding="2em",
            ),
            rx.button("Subir", on_click=InfraState.handle_upload(rx.upload_files(upload_id="file_upload"))),
            rx.button("Volver", on_click=rx.redirect("/"), variant="soft"),
            spacing="4"
        )
    )
