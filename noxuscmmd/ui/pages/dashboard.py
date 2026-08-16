"""
Centro de Control (/panel) — banco de pruebas para la futura migración.

Shell tipo NVR profesional (sidebar + topbar + ventanas flotantes
arrastrables) construido encima de los mismos domain states que la vista
clásica (SecurityState, InfraState, CameraState, PushState). No introduce
lógica de negocio nueva: reutiliza device_list_view, device_controls_view,
camera_dialogs y photo_dialog tal cual.
"""
import reflex as rx

from ...domains.security.state import SecurityState
from ...domains.security.groups_state import GroupsState
from ...domains.infra.state import InfraState
from ...domains.nodes.state import NodesState
from ...domains.devices.registry_state import RegistryState
from ...domains.nodes.host_actions_state import HostActionsState
from ...domains.access.state import AccessControlState
from ...domains.security.logs_state import LogsState
from ...domains.automations.state import AutomationsState
from ...domains.cameras.wall_state import VideoWallState
from ..components.dialogs import photo_dialog
from ..views.camera_view import camera_dialogs
from ..views.device_list import check_existing_subscription_event
from ..dashboard import theme
from ...domains.notifications.state import PushState
from ..dashboard.sidebar import sidebar, mobile_bottom_nav
from ..dashboard.topbar import topbar
from ..dashboard.state import DashboardState
from ..dashboard.windows import floating_windows_layer
from ..dashboard.views.overview import overview_view
from ..dashboard.views.settings_hub import settings_hub_view
from ..dashboard.views.cctv import cctv_view
from ..dashboard.views.alarm import alarm_view
from ..dashboard.views.groups import groups_view
from ..dashboard.views.floor_plan import floor_plan_view
from ..dashboard.views.video_wall import video_wall_view
from ..dashboard.views.access import access_view
from ..dashboard.views.lights import lights_view
from ..dashboard.views.ir_remotes import ir_remotes_view, ir_remote_windows_layer
from ..dashboard.views.automations import automations_view
from ..dashboard.views.equipment import equipment_view
from ..dashboard.views.logs import logs_view

_DRAG_AND_CLOCK_SCRIPT = """
(function(){
    if (window.__nxDashInit) return;
    window.__nxDashInit = true;
    window.__nxZ = 200;

    document.addEventListener('pointerdown', function(e){
        var closeBtn = e.target.closest('.nx-window-close');
        var win = e.target.closest('.nx-window');
        if (win) {
            window.__nxZ += 1;
            win.style.zIndex = window.__nxZ;
        }
        if (closeBtn) return;
        if (window.innerWidth < 768) return;
        var handle = e.target.closest('.nx-window-handle');
        if (!handle || !win) return;

        var rect = win.getBoundingClientRect();
        win.style.left = rect.left + 'px';
        win.style.top = rect.top + 'px';
        win.style.right = 'auto';
        win.style.margin = '0';

        var startX = e.clientX, startY = e.clientY;
        var baseLeft = rect.left, baseTop = rect.top;

        function onMove(ev){
            var dx = ev.clientX - startX, dy = ev.clientY - startY;
            var newLeft = Math.max(4, Math.min(baseLeft + dx, window.innerWidth - 80));
            var newTop = Math.max(4, Math.min(baseTop + dy, window.innerHeight - 40));
            win.style.left = newLeft + 'px';
            win.style.top = newTop + 'px';
        }
        function onUp(){
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
        }
        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
    });

    function nxTickClock(){
        var el = document.getElementById('nx-clock');
        if (!el) return;
        var now = new Date();
        var d = now.toLocaleDateString('es-ES', {day:'2-digit', month:'2-digit', year:'numeric'});
        var t = now.toLocaleTimeString('es-ES');
        el.textContent = d + '   ' + t;
    }
    nxTickClock();
    setInterval(nxTickClock, 1000);
})();
"""


def _content() -> rx.Component:
    return rx.match(
        DashboardState.active_view,
        ("overview", overview_view()),
        ("alarm", alarm_view()),
        ("groups", groups_view()),
        ("floor_plan", floor_plan_view()),
        ("video_wall", video_wall_view()),
        ("cctv", cctv_view()),
        ("access", access_view()),
        ("lights", lights_view()),
        ("ir_remotes", ir_remotes_view()),
        ("automations", automations_view()),
        ("equipment", equipment_view()),
        ("settings_hub", settings_hub_view()),
        ("logs", logs_view()),
        overview_view(),
    )


def _aviso_vincular() -> rx.Component:
    """Aviso flotante cuando este aparato no está vinculado a las
    notificaciones.

    Hace falta porque el navegador solo concede el permiso de notificaciones
    justo después de un toque: al entrar se intenta vincular solo, pero si el
    permiso no estaba ya dado no hay forma de pedirlo sin que alguien pulse.
    Este es ese botón. Y no es solo por los avisos: sin vincular, todo lo que
    se haga desde aquí se apunta en los registros como "desconocido".

    Va por encima de la barra inferior del móvil para no taparla."""
    return rx.cond(
        PushState.falta_vincular,
        rx.hstack(
            rx.icon("bell-off", size=18, color=theme.WARNING, flex_shrink="0"),
            rx.vstack(
                rx.text("Este dispositivo no está vinculado", size="2",
                        weight="bold", color=theme.TEXT),
                rx.text("Sin vincular no recibe avisos y sus acciones salen sin nombre.",
                        size="1", color=theme.MUTED),
                spacing="0", align="start", min_width="0",
            ),
            rx.spacer(),
            rx.button("Vincular", on_click=PushState.suscribir, size="2",
                      color_scheme="orange", flex_shrink="0"),
            rx.icon("x", size=16, color=theme.MUTED, cursor="pointer",
                    on_click=PushState.descartar_aviso_vincular, flex_shrink="0"),
            align="center", spacing="3",
            position="fixed", bottom=["76px", "76px", "20px"], left="50%",
            transform="translateX(-50%)",
            width="min(560px, calc(100vw - 24px))",
            padding="12px 14px", border_radius="12px",
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.WARNING}",
            box_shadow="0 10px 30px rgba(0,0,0,0.45)",
            z_index="900",
        ),
    )


def dashboard_page() -> rx.Component:
    return rx.box(
        rx.script(
            """
            window.addEventListener('pagehide', () => {
                if (window.socket) { window.socket.close(); }
            });
            """
        ),
        rx.script(_DRAG_AND_CLOCK_SCRIPT),
        rx.hstack(
            sidebar(),
            rx.vstack(
                topbar(),
                rx.box(
                    _content(),
                    width="100%",
                    padding=["14px", "14px", "28px"],
                    padding_bottom=["100px", "100px", "28px"],
                    flex="1",
                    # Centra CUALQUIER vista, tenga o no un max_width propio
                    # (Equipos, Ajustes, Auto sí lo llevan; Registros, CCTV,
                    # Alarma llenan el 100% y con esto no cambian). Antes todo
                    # colgaba pegado al borde izquierdo del hueco disponible,
                    # que en una pantalla ancha con el sidebar abierto se
                    # notaba mucho — un único cambio aquí centra las doce
                    # pestañas de golpe, sin tocar vista por vista.
                    display="flex",
                    justify_content="center",
                ),
                width="100%",
                min_height="100vh",
                spacing="0",
                align="start",
            ),
            width="100%",
            spacing="0",
            align="start",
        ),
        _aviso_vincular(),
        mobile_bottom_nav(),
        camera_dialogs(),
        photo_dialog(
            InfraState.dialog_foto_abierto,
            InfraState.toggle_dialog,
            InfraState.last_rpi_photo,
        ),
        floating_windows_layer(),
        ir_remote_windows_layer(),
        on_mount=[
            SecurityState.on_load,
            InfraState.on_load,
            RegistryState.on_load,
            NodesState.on_load,
            GroupsState.on_load,
            HostActionsState.on_load,
            AccessControlState.on_load,
            LogsState.on_load,
            AutomationsState.on_load,
            VideoWallState.on_load,
            check_existing_subscription_event(),
        ],
        min_height="100vh",
        width="100%",
        background=f"radial-gradient(circle at top, {theme.BG_TOPBAR} 0%, {theme.BG_APP} 55%)",
    )
