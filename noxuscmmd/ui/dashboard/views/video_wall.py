"""
Vista "Mural": rejilla de cámaras en vivo persistente, al estilo del visor
de un NVR (HikCentral y compañía). Eliges un reparto (1/4/6/8/9/16), tocas un
hueco vacío para colocar una cámara y se queda tal cual la próxima vez que
entres — ver domains/cameras/wall_state.py para el porqué de "tocar" en vez
de "arrastrar" (esta versión de Reflex no tiene arrastrar-soltar nativo, y
lo contrario tampoco funcionaría bien en el móvil).

Cada hueco reutiliza EXACTAMENTE el mismo iframe que ya usan las ventanas
flotantes de cámara suelta (mismo criterio de negociación WebRTC/MSE/HLS de
domains/cameras/wall.py) — no hay una segunda forma de reproducir vídeo en
toda la app, solo un sitio más donde se planta.
"""
import reflex as rx

from ....domains.cameras.wall_state import VideoWallState
from .. import theme
from ..components.catalog_picker import catalog_picker

_ASPECTO = "16 / 9"


def _layout_button(l: dict) -> rx.Component:
    activo = VideoWallState.layout == l["id"]
    return rx.button(
        l["label"],
        on_click=VideoWallState.set_layout(l["id"]),
        size="1",
        variant=rx.cond(activo, "solid", "surface"),
        color_scheme="blue",
    )


def _wall_header() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Mural", size="5", color=theme.TEXT),
                rx.text("Todas las cámaras que hayas colocado, siempre en el mismo sitio.",
                        size="1", color=theme.MUTED),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.button(
                rx.icon("refresh-cw", size=13), "PC / Móvil",
                on_click=VideoWallState.toggle_cam_mode, size="2", variant="soft",
                title="Cambia el orden de negociación del vídeo — prueba esto si una "
                      "cámara no arranca en tu red.",
            ),
            rx.button(
                rx.icon("trash-2", size=13), "Vaciar",
                on_click=VideoWallState.clear_all, size="2", variant="soft", color_scheme="red",
            ),
            width="100%", align="center", wrap="wrap", spacing="2",
        ),
        rx.hstack(
            rx.foreach(VideoWallState.layouts, _layout_button),
            spacing="2", wrap="wrap",
        ),
        spacing="3", width="100%", align="start",
    )


def _slot_empty(slot_id) -> rx.Component:
    return rx.box(
        rx.icon("plus", size=24, color=theme.MUTED),
        on_click=VideoWallState.open_picker(slot_id),
        cursor="pointer",
        display="flex", align_items="center", justify_content="center",
        width="100%", aspect_ratio=_ASPECTO,
        background=theme.BG_CARD, border=f"1px dashed {theme.BORDER}",
        border_radius="10px",
        transition="border-color 0.15s ease, background 0.15s ease",
        _hover={"border_color": theme.ACCENT, "background": theme.BG_CARD_HOVER},
        title="Toca para colocar una cámara",
    )


def _slot_video(cam: dict) -> rx.Component:
    """El vídeo en sí, o —si es RTSP y el navegador no puede reproducirlo—
    la URL para copiar y abrir con VLC, mismo plan B que ya usa la ventana
    flotante de cámara suelta."""
    return rx.cond(
        cam["playable"].to(bool),
        rx.el.iframe(
            src=cam["stream_url"].to(str),
            style={"width": "100%", "height": "100%", "border": "none"},
            allow="autoplay; fullscreen",
        ),
        rx.center(
            rx.vstack(
                rx.icon("video-off", size=18, color=theme.MUTED),
                rx.code(cam["stream_url"], size="1", style={"word_break": "break-all"}),
                rx.icon("copy", size=13, color=theme.MUTED, cursor="pointer",
                        on_click=rx.set_clipboard(cam["stream_url"]),
                        title="Copiar URL RTSP"),
                spacing="1", align="center",
            ),
            width="100%", height="100%", padding="10px",
        ),
    )


def _slot_filled(slot_id, camera_id) -> rx.Component:
    cam = VideoWallState.cameras_by_id[camera_id]
    return rx.box(
        _slot_video(cam),
        rx.hstack(
            rx.text(cam["name"], size="1", color="white", weight="bold",
                    white_space="nowrap", overflow="hidden", text_overflow="ellipsis"),
            rx.spacer(),
            rx.icon("replace", size=13, color="white", cursor="pointer",
                    on_click=VideoWallState.open_picker(slot_id).stop_propagation,
                    title="Cambiar cámara"),
            rx.icon("x", size=13, color="white", cursor="pointer",
                    on_click=VideoWallState.clear_slot(slot_id).stop_propagation,
                    title="Quitar del mural"),
            align="center", spacing="2", width="100%",
            position="absolute", top="0", left="0", padding="6px 8px",
            background="linear-gradient(to bottom, rgba(0,0,0,0.65), transparent)",
        ),
        position="relative", width="100%", aspect_ratio=_ASPECTO,
        border_radius="10px", overflow="hidden", background="#000",
        border=f"1px solid {theme.BORDER}",
    )


def _slot_cell(slot_id) -> rx.Component:
    camera_id = VideoWallState.slots.get(slot_id, "")
    return rx.cond(
        camera_id != "",
        _slot_filled(slot_id, camera_id),
        _slot_empty(slot_id),
    )


def _grid(cols: int) -> rx.Component:
    return rx.box(
        rx.foreach(VideoWallState.slot_ids, _slot_cell),
        display="grid",
        # UNA columna en móvil siempre, sea cual sea el reparto elegido — no
        # es solo estética: con dos o más columnas en una pantalla estrecha,
        # el hueco se queda tan poco ancho que el reproductor de vídeo
        # (la página stream.html de go2rtc, ajena a nosotros) media su tamaño
        # mal y el vídeo sale a medio encajar, mitad negro. Una columna evita
        # el problema de raíz: cada hueco es siempre lo bastante ancho.
        style={"grid_template_columns": rx.breakpoints(initial="1fr", sm=f"repeat({cols}, 1fr)")},
        gap="10px",
        width="100%",
    )


def video_wall_view() -> rx.Component:
    return rx.vstack(
        _wall_header(),
        rx.match(
            VideoWallState.layout,
            ("1", _grid(1)),
            ("2h", _grid(2)),
            ("2v", _grid(1)),
            ("4", _grid(2)),
            ("6", _grid(3)),
            ("8", _grid(4)),
            ("9", _grid(3)),
            ("16", _grid(4)),
            _grid(2),
        ),
        catalog_picker(
            is_open=VideoWallState.picker_open,
            title="Elegir cámara",
            sections=VideoWallState.picker_sections,
            query=VideoWallState.picker_query,
            on_query=VideoWallState.set_picker_query,
            on_pick=VideoWallState.pick,
            on_close=VideoWallState.close_picker,
            on_open_change=VideoWallState.picker_open_change,
            icon="video",
            empty_text="No hay ninguna cámara dada de alta todavía — añade una desde CCTV.",
        ),
        spacing="4",
        width="100%",
    )
