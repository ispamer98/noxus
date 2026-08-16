"""
Capa de ventanas flotantes del dashboard. Reutiliza las piezas ya factorizadas
de ui/views/camera_view.py (video_embed_safe, ptz_control_buttons,
open_in_browser_button) sobre CameraState — no duplica lógica de streaming,
solo la presenta en una ventana arrastrable en vez de un rx.dialog centrado.
"""
import reflex as rx

from ..views.camera_view import video_embed_safe, ptz_control_buttons, open_in_browser_button
from ...domains.cameras.state import CameraState
from ...domains.nodes.state import NodesState
from . import theme
from .components.floating_window import floating_window
from .state import DashboardState


def _mode_toggle_button() -> rx.Component:
    return rx.button(
        rx.icon("refresh-cw", size=14),
        "Modo PC / Móvil",
        on_click=CameraState.toggle_cam_mode,
        size="1",
        variant="soft",
    )


def _tuya_extra_controls(cam_entity_id: str) -> rx.Component:
    """Privacidad y sirena — usan Tuya LAN (tinytuya) si TUYA_LOCAL_IP/KEY_*
    están configurados, si no caen a Tuya cloud (privacidad) o avisan que
    falta configurar (sirena, solo tiene ruta local)."""
    return rx.vstack(
        rx.divider(border_color=theme.BORDER),
        rx.text("Extra (Tuya)", size="1", color=theme.MUTED, letter_spacing="0.05em", weight="bold"),
        rx.hstack(
            rx.button(
                rx.icon("eye-off", size=14),
                "Privacidad ON",
                on_click=CameraState.toggle_privacy(cam_entity_id, True),
                size="1",
                variant="soft",
            ),
            rx.button(
                rx.icon("eye", size=14),
                "Privacidad OFF",
                on_click=CameraState.toggle_privacy(cam_entity_id, False),
                size="1",
                variant="soft",
            ),
            rx.button(
                rx.icon("siren", size=14),
                "Sirena",
                on_click=CameraState.trigger_siren(cam_entity_id),
                size="1",
                variant="soft",
                color_scheme="red",
            ),
            spacing="2",
            wrap="wrap",
        ),
        spacing="2",
        width="100%",
    )


def _cam_fija_window() -> rx.Component:
    return floating_window(
        rx.vstack(
            rx.hstack(
                open_in_browser_button(CameraState.url_fija_stream),
                _mode_toggle_button(),
                spacing="2",
            ),
            video_embed_safe(CameraState.url_fija_stream),
            _tuya_extra_controls("cam_fija"),
            spacing="3",
            width="100%",
        ),
        window_id="cam_fija",
        title="Cámara Fija — Entrada Principal",
        icon="cctv",
        is_open=DashboardState.open_windows.contains("cam_fija"),
        on_close=DashboardState.close_window("cam_fija"),
        accent=theme.ACCENT,
        top="8%",
        left="6%",
        width="620px",
    )


def _cam_ptz_window() -> rx.Component:
    return floating_window(
        rx.vstack(
            rx.hstack(
                open_in_browser_button(CameraState.url_ptz_stream),
                _mode_toggle_button(),
                spacing="2",
            ),
            video_embed_safe(CameraState.url_ptz_stream),
            rx.divider(border_color=theme.BORDER),
            rx.text("Control PTZ", size="2", weight="bold", color=theme.TEXT),
            ptz_control_buttons(),
            rx.text(CameraState.cam_msg, size="1", color=theme.MUTED),
            _tuya_extra_controls("cam_ptz"),
            spacing="3",
            width="100%",
        ),
        window_id="cam_ptz",
        title="Cámara PTZ — Motorizada",
        icon="rotate-cw",
        is_open=DashboardState.open_windows.contains("cam_ptz"),
        on_close=DashboardState.close_window("cam_ptz"),
        accent=theme.PURPLE,
        top="12%",
        left="34%",
        width="620px",
    )


_STREAM_MODES = "webrtc,mse,hls,mp4"


def _dynamic_camera_window(cam: dict) -> rx.Component:
    go2rtc_url = f"https://cam.noxuscmmd.uk/stream.html?src={cam['url']}&mode={_STREAM_MODES}"
    content = rx.match(
        cam["kind"],
        (
            "go2rtc",
            rx.vstack(
                open_in_browser_button(go2rtc_url),
                video_embed_safe(go2rtc_url),
                spacing="3",
                width="100%",
            ),
        ),
        (
            "rtsp",
            rx.vstack(
                # Los navegadores no reproducen RTSP directamente: se guarda solo para copiarla y
                # abrirla en VLC u otro reproductor compatible.
                rx.hstack(
                    rx.code(cam["url"], size="1", style={"word_break": "break-all"}),
                    rx.icon(
                        "copy",
                        size=15,
                        cursor="pointer",
                        on_click=rx.set_clipboard(cam["url"]),
                        title="Copiar URL RTSP",
                        _hover={"color": theme.ACCENT},
                    ),
                    align="start",
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.vstack(
            open_in_browser_button(cam["url"]),
            video_embed_safe(cam["url"]),
            spacing="3",
            width="100%",
        ),
    )
    return floating_window(
        content,
        window_id=cam["id"],
        title=cam["name"],
        icon=cam["icon"].to(str),
        is_open=DashboardState.open_windows.contains(cam["id"].to(str)),
        on_close=DashboardState.close_window(cam["id"]),
        accent=theme.ACCENT,
        top="10%",
        left="15%",
        width="620px",
    )


def floating_windows_layer() -> rx.Component:
    return rx.fragment(
        _cam_fija_window(),
        _cam_ptz_window(),
        rx.foreach(NodesState.cameras, _dynamic_camera_window),
    )
