import reflex as rx
from .pages.index import index_page
from .pages.upload import upload_page
from .state import State
 

STYLE = {
    "@keyframes pulse": {
        "0%": {"opacity": "0.6", "transform": "scale(1)"},
        "100%": {"opacity": "1", "transform": "scale(1.05)"},
    }
}


app = rx.App(
    theme=rx.theme(appearance="dark", accent_color="blue"),
    style=STYLE,   # <--- Aquí inyectamos la animación
    head_components=[
        rx.el.link(rel="manifest", href="/manifest.json"),
    ],
    admin_dash=False,
)
 
# IMPORTANTE: on_load se gestiona vía on_mount en index_page para evitar
# que Reflex arranque los background tasks múltiples veces (una por conexión
# WebSocket nueva). El flag _BACKGROUND_STARTED en state.py lo protege además.
app.add_page(index_page, route="/", title="Noxus Pro")
app.add_page(upload_page, route="/upload")
 