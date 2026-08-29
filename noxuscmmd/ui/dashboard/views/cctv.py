"""
Pantalla «CCTV» (dentro de Ajustes): dar de alta, editar, ocultar y abrir
cualquier cámara de la casa.

DOS FAMILIAS DE TARJETA, y no es capricho: "Cámara Fija" y "Cámara PTZ" son
las dos que trae la instalación de fábrica (registry.py, con su propio
control de movimiento — ver ui/views/camera_view.py) y no se pueden borrar,
solo ocultar; el resto son cámaras que el usuario ha ido añadiendo con
"Añadir cámara" (domains/nodes), que sí se pueden borrar del todo. De ahí
`_camera_card` (fija/PTZ) y `_dynamic_camera_card` (las añadidas) como
funciones separadas aunque se vean casi iguales.

El vídeo en directo NO se pinta aquí: esta pantalla solo identifica la cámara
y da acceso a sus acciones; el preview real vive en la ventana flotante que
abre el botón «Abrir» (ver ui/dashboard/windows.py).
"""
import reflex as rx

from ....domains.cameras.state import CameraState
from ....domains.nodes.state import NodesState
from ....domains.devices import registry
from ....domains.devices.registry_state import RegistryState
from .. import theme
from ..state import DashboardState
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select
from ..components.hidden_card import hidden_entities_card
from ..components.floor_fields import floor_plan_fields
from ..components.icon_picker import icon_field

_CAMERA_ICONS = ["cctv", "video", "camera", "radar", "webcam", "rotate-cw"]

_CAMERA_KIND_OPTIONS = [
    ("embed", "URL embebible (MJPEG, HLS, página de stream)"),
    ("go2rtc", "go2rtc — nombre de stream ya configurado"),
    ("rtsp", "RTSP directo / ONVIF (solo referencia)"),
]

# · URL embebible: cualquier dirección que cargue sola en un iframe (visor web MJPEG, HLS,
# la página de otro go2rtc...). · go2rtc: escribe solo el nombre del stream (ej: jardin) tal
# como está en tu go2rtc — se genera la URL automáticamente igual que Cámara Fija/PTZ.
# · RTSP/ONVIF: pega la URL rtsp://usuario:clave@ip:554/... — los navegadores no reproducen
# RTSP directamente, así que aquí solo se guarda para copiarla y abrirla en VLC u otro reproductor.


def _live_badge() -> rx.Component:
    return rx.badge(
        rx.hstack(rx.icon("circle", size=6, color=theme.DANGER), rx.text("EN VIVO"), spacing="1", align="center"),
        variant="soft", size="1", color_scheme="red",
    )


def _edit_static_camera_dialog(entity_id: str, name: str, tuya_device_id: str, icon: str,
                                show_on_floor: bool, floor_icon: str) -> rx.Component:
    return form_dialog_content(
        icon="video",
        title=f"Editar {name}",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=entity_id, type="hidden"),
                field("Nombre", styled_input(name="name", default_value=name)),
                field(
                    "ID de dispositivo Tuya",
                    styled_input(name="tuya_device_id", default_value=tuya_device_id),
                    hint="Déjalo vacío si esta cámara no usa Tuya (privacidad/sirena).",
                ),
                field("Icono", icon_field(
                    name="icon", key=entity_id + ":icon",
                    default_value=icon, options=_CAMERA_ICONS,
                )),
                *floor_plan_fields(show_on_floor, floor_icon, default_icon="cctv", key=entity_id),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=RegistryState.submit_edit_entity,
        ),
    )


def _camera_card(entity_id: str, default_icon: str, window_id: str, accent: str) -> rx.Component:
    """Tarjeta compacta (mismo formato de fila que Equipos) — el preview real
    de vídeo vive en la ventana flotante que abre el botón "Abrir", aquí solo
    hace falta identificar la cámara y dar acceso a sus acciones."""
    cam_entity = registry.DEVICES.get(entity_id)
    tuya_device_id = getattr(cam_entity, "tuya_device_id", None) or ""
    # RegistryState.icons, no el getattr directo: ese lee registry.DEVICES tal
    # como estaba AL COMPILAR la app (esta tarjeta se construye una sola vez,
    # con "cam_fija"/"cam_ptz" como literales fijos) — cambiar el icono se
    # guardaba pero la tarjeta seguía enseñando el viejo hasta reiniciar el
    # servicio entero. Con la Var reactiva se ve al instante, igual que ya
    # pasa con el nombre.
    icono_guardado = RegistryState.icons[entity_id]
    icon = rx.cond(icono_guardado != "", icono_guardado, default_icon)
    floor_top = getattr(cam_entity, "floor_top", None)
    floor_icon = getattr(cam_entity, "floor_icon", None) or ""
    name = RegistryState.names[entity_id]
    return rx.hstack(
        rx.box(
            rx.icon(icon, size=20, color=accent),
            padding="10px",
            border_radius="10px",
            background=theme.alpha(accent, 0.14),
            flex_shrink="0",
        ),
        rx.hstack(
            rx.text(name, size="2", weight="bold", color=theme.TEXT),
            _live_badge(),
            spacing="2", align="center",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("maximize-2", size=14),
            "Abrir",
            on_click=DashboardState.open_window(window_id),
            size="1",
            variant="surface",
            color_scheme="blue",
        ),
        actions_menu(
            edit_content=_edit_static_camera_dialog(
                entity_id, name, tuya_device_id, icon, bool(floor_top), floor_icon,
            ),
            on_remove=RegistryState.delete_factory_entity(entity_id),
            remove_confirm_title="¿Eliminar cámara?",
            remove_confirm_description=confirm_delete("la cámara", name),
        ),
        spacing="3",
        align="center",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
        wrap="wrap",
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
            rx.text("Cámara añadida manualmente", size="1", color=theme.MUTED),
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
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
        wrap="wrap",
    )


def _edit_camera_dialog(cam: dict) -> rx.Component:
    return form_dialog_content(
        icon="video",
        title="Editar cámara",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=cam["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=cam["name"])),
                field("Tipo de conexión", styled_select(
                    "Tipo de conexión",
                    rx.select.content(*[rx.select.item(label, value=val) for val, label in _CAMERA_KIND_OPTIONS]),
                    name="kind", default_value=cam["kind"],
                )),
                field("URL / nombre de stream / rtsp://...", styled_input(name="url", default_value=cam["url"])),
                field("Icono", icon_field(
                    name="icon", key=cam["id"].to(str) + ":icon",
                    default_value=cam["icon"].to(str), options=_CAMERA_ICONS,
                )),
                *floor_plan_fields(
                    cam["floor_top"],
                    rx.cond(cam["floor_icon"], cam["floor_icon"].to(str), "cctv"),
                    key=cam["id"].to(str),
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
                        rx.select.content(*[rx.select.item(label, value=val) for val, label in _CAMERA_KIND_OPTIONS]),
                        name="kind", default_value="embed",
                    )),
                    field("URL / nombre de stream / rtsp://...", styled_input(name="url", placeholder="https://...")),
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
    hidden = registry.hidden_ids()
    static_cards = []
    hidden_cams = {}
    if "cam_fija" not in hidden:
        static_cards.append(_camera_card("cam_fija", "cctv", "cam_fija", theme.ACCENT))
    else:
        hidden_cams["cam_fija"] = "Cámara Fija"
    if "cam_ptz" not in hidden:
        static_cards.append(_camera_card("cam_ptz", "rotate-cw", "cam_ptz", theme.PURPLE))
    else:
        hidden_cams["cam_ptz"] = "Cámara PTZ"

    return rx.vstack(
        rx.hstack(
            rx.spacer(),
            _add_camera_dialog(),
            width="100%",
            align="center",
            wrap="wrap",
        ),
        rx.vstack(
            *static_cards,
            rx.foreach(NodesState.cameras, _dynamic_camera_card),
            spacing="2",
            width="100%",
        ),
        rx.text(CameraState.cam_msg, size="1", color=theme.MUTED),
        hidden_entities_card("CÁMARAS", hidden_cams),
        spacing="3",
        width="100%",
        max_width="720px",
    )
