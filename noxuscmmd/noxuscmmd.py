import reflex as rx
from .pages.index import index_page
from .pages.upload import upload_page
from .state import State



app = rx.App(
    theme=rx.theme(appearance="dark", accent_color="blue"),
    head_components=[
        rx.el.link(rel="manifest", href="/manifest.json"),
    ],
    style={
        "show_built_with_reflex": False,
    },
    admin_dash=False,
)
app.add_page(index_page, route="/", title="Noxus Pro", on_load=State.actualizar_estados)
app.add_page(upload_page, route="/upload")