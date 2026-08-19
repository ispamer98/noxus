"""
Capa de ventanas flotantes del dashboard. Reutiliza las piezas ya factorizadas
de ui/views/camera_view.py (video_embed_safe, ptz_control_buttons,
open_in_browser_button) sobre CameraState — no duplica lógica de streaming,
solo la presenta en una ventana arrastrable en vez de un rx.dialog centrado.
"""
import reflex as rx

from ..views.camera_view import video_embed_safe, ptz_control_buttons, open_in_browser_button
from ...domains.cameras.state import CameraState
from ...domains.auth.state import AuthState
from ...domains.nodes.host_actions_state import HostActionsState
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


# ── Equipos en el plano ──────────────────────────────────────────────────────
# Un ordenador colocado en el plano abre SU BOTONERA al pulsarlo, en vez de
# encenderse o apagarse de un toque como hace una luz. El motivo es que apagar
# un equipo por un roce en la pantalla del móvil es un destrozo que no se
# deshace: lo que estuviera abierto sin guardar, se pierde. Un panel con sus
# botones cuesta un toque más y no se dispara sin querer.
#
# Lo que sale aquí es lo mismo que ya vive en la pestaña Equipos, no una copia:
# los eventos son los de HostActionsState, con sus permisos y su registro. Aquí
# solo se presentan al lado del sitio de la casa donde está el aparato.
def _accion(icono: str, texto: str, al_pulsar, color: str = "gray") -> rx.Component:
    return rx.button(
        rx.icon(icono, size=14), texto,
        on_click=al_pulsar, size="2", variant="soft", color_scheme=color,
        width="100%", justify="start",
    )


def _boton_propio(boton: rx.Var) -> rx.Component:
    """Uno de los botones que el equipo tenga dados de alta (un comando SSH,
    poner un pin, leer un pin). El icono es fijo porque lo que cambia es lo que
    hace, no de qué tipo es: el nombre que le puso el usuario ya lo dice."""
    return _accion("play", boton["label"].to(str),
                   HostActionsState.run_button(boton["id"].to(str)))


def _equipo_window(host: rx.Var) -> rx.Component:
    hid = host["id"].to(str)
    content = rx.vstack(
        rx.hstack(
            rx.icon(rx.cond(host["online"], "wifi", "wifi-off"), size=14,
                    color=rx.cond(host["online"], "#22c55e", theme.MUTED)),
            rx.text(rx.cond(host["online"], "En línea", "Sin respuesta"),
                    size="2", color=theme.TEXT),
            spacing="2", align="center",
        ),
        rx.divider(border_color=theme.BORDER),
        # Encender solo si hay MAC: sin ella no hay Wake-on-LAN que mandar, y
        # un botón que siempre contesta «este equipo no tiene MAC» es ruido.
        rx.cond(
            host["mac"],
            _accion("power", "Encender por red",
                    HostActionsState.encender_wol(hid), "green"),
        ),
        # Apagar y reiniciar van por SSH: sin usuario configurado no hay por
        # dónde entrar (lo comprueba igualmente accion_rapida antes de tocar
        # nada, esto solo evita enseñar el botón).
        rx.cond(
            host["user"],
            rx.fragment(
                _accion("power-off", "Apagar",
                        HostActionsState.accion_rapida(hid, "apagar"), "red"),
                _accion("rotate-ccw", "Reiniciar",
                        HostActionsState.accion_rapida(hid, "reiniciar"), "amber"),
            ),
        ),
        # `.to(list[dict])` no es adorno: dentro de un foreach los campos del
        # diccionario son `Any`, y recorrer un Any no compila —«Could not
        # foreach over var of type Any»—. Es la misma razón por la que aquí
        # arriba todo lleva `.to(str)`.
        rx.foreach(host["botones"].to(list[dict]), _boton_propio),
        spacing="2", width="100%",
    )
    return floating_window(
        content,
        window_id=host["id"],
        title=host["name"],
        icon=rx.cond(host["floor_icon"], host["floor_icon"].to(str),
                     host["icon"].to(str)),
        is_open=DashboardState.open_windows.contains(hid),
        on_close=DashboardState.close_window(host["id"]),
        accent=theme.ACCENT,
        top="12%",
        left="22%",
        width="280px",
        fullscreen_on_mobile=False,
        # Se cierra tocando fuera: es algo que se saca un momento desde el
        # plano, igual que el mando IR en modo compacto.
        dismiss_on_outside="1",
    )


def equipo_windows_layer() -> rx.Component:
    """Una ventana por equipo COLOCADO EN EL PLANO. Solo para quien puede
    accionarlos: los eventos lo comprueban igual (permisos.EQUIPOS), pero
    tampoco hay por qué montarle la botonera a quien no va a poder usarla."""
    return rx.cond(
        AuthState.puede_equipos,
        rx.foreach(NodesState.hosts_on_floor, _equipo_window),
    )
