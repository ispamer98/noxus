"""
Pantalla «CCTV» (dentro de Ajustes): dar de alta, editar, ocultar y abrir
cualquier cámara de la casa.

Todas las cámaras comparten la misma ficha, formulario y visor.

El vídeo en directo NO se pinta aquí: esta pantalla solo identifica la cámara
y da acceso a sus acciones; el preview real vive en la ventana flotante que
abre el botón «Abrir» (ver ui/dashboard/windows.py).
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from .. import theme
from ..state import DashboardState
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select
from ..components.floor_fields import floor_plan_fields
from ..components.icon_picker import icon_field
from ..components.form_dialog import select_content

_CAMERA_ICONS = ["cctv", "video", "camera", "radar", "webcam", "rotate-cw"]

_CAMERA_KIND_OPTIONS = [
    ("embed", "URL embebible (MJPEG, HLS, página de stream)"),
    ("go2rtc", "go2rtc — nombre de stream ya configurado"),
    ("rtsp", "RTSP directo / ONVIF (solo referencia)"),
]

# · URL embebible: cualquier dirección que cargue sola en un iframe (visor web MJPEG, HLS,
# la página de otro go2rtc...). · go2rtc: escribe solo el nombre del stream (ej: jardin) tal
# como está en go2rtc; el panel genera la URL del visor automáticamente.
# · RTSP/ONVIF: pega la URL rtsp://usuario:clave@ip:554/... — los navegadores no reproducen
# RTSP directamente, así que aquí solo se guarda para copiarla y abrirla en VLC u otro reproductor.


def _live_badge() -> rx.Component:
    return rx.badge(
        rx.hstack(rx.icon("circle", size=6, color=theme.DANGER), rx.text("EN VIVO"), spacing="1", align="center"),
        variant="soft", size="1", color_scheme="red",
    )


def _dynamic_camera_card(cam: dict) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon(cam["icon"].to(str), size=20, color=theme.ACCENT),
            padding="10px",
            border_radius="10px",
            background=theme.alpha(theme.ACCENT, 0.14),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(cam["name"], size="2", weight="bold", color=theme.TEXT),
                rx.badge(cam["kind"], variant="soft", size="1", color_scheme="gray"),
                _live_badge(),
                spacing="2", align="center",
            ),
            rx.text("Cámara configurada", size="1", color=theme.MUTED),
            spacing="0", align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("maximize-2", size=14),
            "Abrir",
            on_click=DashboardState.open_window(cam["id"]),
            size="1",
            variant="surface",
            color_scheme="blue",
        ),
        actions_menu(
            edit_content=_edit_camera_dialog(cam),
            on_remove=NodesState.delete_camera(cam["id"]),
            remove_confirm_title="¿Eliminar cámara?",
            remove_confirm_description=confirm_delete("la cámara", cam["name"]),
        ),
        spacing="3",
        align="center",
        width="100%",
        background=theme.BG_CARD, class_name="nx-card",
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        wrap="wrap",
    )


def _edit_camera_dialog(cam: dict) -> rx.Component:
    return form_dialog_content(
        icon="video",
        title="Ajustes de la cámara",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.el.input(name="entity_id", value=cam["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=cam["name"])),
                field("Tipo de conexión", styled_select(
                    "Tipo de conexión",
                    select_content(*[rx.select.item(label, value=val) for val, label in _CAMERA_KIND_OPTIONS]),
                    name="kind", default_value=cam["kind"],
                )),
                field("Stream o URL", styled_input(name="url", default_value=cam["url"])),
                rx.grid(
                    field("Icono", icon_field(
                        name="icon", key=cam["id"].to(str) + ":icon",
                        default_value=cam["icon"].to(str), options=_CAMERA_ICONS,
                    )),
                    *floor_plan_fields(
                        False,
                        rx.cond(cam["floor_icon"], cam["floor_icon"].to(str), "cctv"),
                        key=cam["id"].to(str),
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_camera,
        ),
    )


def _add_camera_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Añadir cámara", size="2", variant="surface", color_scheme="blue"),
        ),
        form_dialog_content(
            icon="video",
            title="Nueva cámara",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Cámara Jardín")),
                    field("Tipo de conexión", styled_select(
                        "Tipo de conexión",
                        select_content(*[rx.select.item(label, value=val) for val, label in _CAMERA_KIND_OPTIONS]),
                        name="kind", default_value="embed",
                    )),
                    field("Stream o URL", styled_input(name="url", placeholder="https://...")),
                    field("Icono", icon_field(
                        name="icon", key="nueva_camara:icon",
                        default_value="cctv", options=_CAMERA_ICONS,
                    )),
                    dialog_footer(confirm_label="Añadir"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_camera,
                reset_on_submit=True,
            ),
        ),
    )


def cctv_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.spacer(),
            _add_camera_dialog(),
            width="100%",
            align="center",
            wrap="wrap",
        ),
        rx.vstack(
            rx.foreach(NodesState.cameras, _dynamic_camera_card),
            spacing="2",
            width="100%",
        ),
        spacing="3",
        width="100%",
        max_width="720px",
    )
