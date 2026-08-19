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
from ...domains.notifications.alertas_state import AlertasState
from ...domains.security.logs_state import LogsState
from ...domains.automations.state import AutomationsState
from ...domains.cameras.wall_state import VideoWallState
from ...domains.infra.backups_state import BackupsState
from ...domains.auth.admin_state import AuthAdminState
from ...domains.auth.state import AuthState
from ...domains.security.arming_state import ArmingState
from ..components.dialogs import photo_dialog
from ..views.camera_view import camera_dialogs
from ..views.device_list import check_existing_subscription_event
from ..dashboard import theme
from ...domains.notifications.state import PushState
from ..dashboard.sidebar import sidebar, mobile_bottom_nav
from ..dashboard.components.alertas import banner_alertas
from ..dashboard.components.desconocidos import banner_desconocidos
from ..dashboard.components.paleta import paleta_comandos
from ..dashboard.components.pulsacion_larga import pulsacion_larga
from ..dashboard.topbar import topbar
from ..dashboard.state import DashboardState
from ..dashboard.windows import floating_windows_layer, equipo_windows_layer
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
from ..dashboard.views.metricas import metricas_view
from ..dashboard.views.instalador import instalador_view
from ..dashboard.views.accesorios import accesorios_view
from ..dashboard.views.movimiento import movimiento_view
from ..dashboard.views.presencia import presencia_view
from ..dashboard.views.voz import voz_view
from ..dashboard.views.system import system_view
from ..dashboard.views.usuarios import usuarios_view
from ..dashboard.views.inventario import inventario_view
from ..dashboard.views.modos import modos_view
from ..dashboard.views.retardos import retardos_view
from ..dashboard.components.armado import dialogo_armado

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


# La densidad "Pro" aprieta el panel entero desde un solo sitio: se marca la raiz
# con data-densidad="pro" y estas reglas hacen el resto. Es CSS y no props de
# cada componente a proposito — con props habria que tocar las treinta vistas y
# acordarse en cada componente nuevo; asi lo gana todo el panel de golpe, incluso
# lo que se escriba manana.
#
# Se aprieta el espacio y se baja un punto la tipografia, y NO se toca el tamano
# de los objetivos pulsables por debajo de lo razonable: "cabe mas" no puede
# significar "no le aciertas".
_DENSIDAD_CSS = """
[data-densidad="pro"] { font-size: 0.94rem; }
[data-densidad="pro"] .rt-Card,
[data-densidad="pro"] .rx-Stack { gap: 0.4rem; }
[data-densidad="pro"] .rt-Card { padding: 9px 11px; }
[data-densidad="pro"] .rt-BadgeRoot { padding-top: 0; padding-bottom: 0; }
"""

def _sin_permiso() -> rx.Component:
    return rx.vstack(
        rx.icon("lock", size=28, color=theme.MUTED),
        rx.text("Esta pantalla es de configuración", size="3", weight="bold",
                color=theme.TEXT),
        rx.text(
            "Este dispositivo no tiene permiso para verla. Pídeselo a quien "
            "administre el panel.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.button("Volver al resumen", size="2", variant="soft",
                  on_click=DashboardState.set_view("overview")),
        spacing="3", align="center", padding="48px 16px", width="100%",
    )


def _solo_camaras(vista: rx.Component) -> rx.Component:
    """El Mural y CCTV piden permiso de cámaras.

    Mirar ya es acceso: sin esto, un invitado que abre el Mural no puede tocar
    ningún botón pero ve el interior de la casa en directo, que es justo lo que
    hay que impedir. Y se comprueba aquí y no solo en el menú porque a estas
    pantallas se llega escribiendo ?vista=video_wall en la barra de direcciones.

    Lo que se VE, ojo: que no se pueda mover una cámara ni sonar su sirena lo
    deciden los manejadores de CameraState."""
    return rx.cond(AuthState.puede_camaras, vista, _sin_permiso_camaras())


def _sin_permiso_camaras() -> rx.Component:
    return rx.vstack(
        rx.icon("video-off", size=28, color=theme.MUTED),
        rx.text("No tienes acceso a las cámaras", size="3", weight="bold",
                color=theme.TEXT),
        rx.text(
            "Este dispositivo no puede ver la imagen de las cámaras de la casa. "
            "Pídeselo a quien administre el panel.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.button("Volver al resumen", size="2", variant="soft",
                  on_click=DashboardState.set_view("overview")),
        spacing="3", align="center", padding="48px 16px", width="100%",
    )


def _solo_ajustes(vista: rx.Component) -> rx.Component:
    """Las pantallas de configuración enseñan el mapa de la casa —qué sensores
    hay, en qué pin, con qué IP— y eso no es para cualquiera. Se puede llegar a
    ellas escribiendo ?vista=... en la barra de direcciones, así que la
    comprobación va aquí y no solo en el menú.

    Es solo lo que se VE: lo que se puede tocar lo deciden los manejadores."""
    return rx.cond(AuthState.puede_ajustes, vista, _sin_permiso())


def _content() -> rx.Component:
    return rx.match(
        DashboardState.active_view,
        ("overview", overview_view()),
        ("alarm", alarm_view()),
        ("groups", groups_view()),
        ("floor_plan", floor_plan_view()),
        ("video_wall", _solo_camaras(video_wall_view())),
        ("cctv", _solo_camaras(cctv_view())),
        ("access", access_view()),
        ("lights", lights_view()),
        ("ir_remotes", ir_remotes_view()),
        ("automations", automations_view()),
        ("equipment", equipment_view()),
        ("settings_hub", _solo_ajustes(settings_hub_view())),
        ("system", _solo_ajustes(system_view())),
        ("usuarios", _solo_ajustes(usuarios_view())),
        ("inventario", _solo_ajustes(inventario_view())),
        ("modos", _solo_ajustes(modos_view())),
        ("retardos", _solo_ajustes(retardos_view())),
        ("logs", logs_view()),
        # No va envuelta en _solo_ajustes: no es configuración, es una pantalla
        # de consulta como Registros.
        ("metricas", metricas_view()),
        ("voz", _solo_ajustes(voz_view())),
        ("instalador", _solo_ajustes(instalador_view())),
        ("presencia", _solo_ajustes(presencia_view())),
        ("accesorios", _solo_ajustes(accesorios_view())),
        ("movimiento", _solo_ajustes(movimiento_view())),
        overview_view(),
    )


def _aviso_vincular() -> rx.Component:
    """Aviso flotante cuando este accesorio no está vinculado a las
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


def _comprobando() -> rx.Component:
    """Lo que se ve el instante que tarda en resolverse quién es este navegador.

    Existe para no tener que elegir entre dos parpadeos malos: enseñar el panel
    a quien puede no tener acceso, o enseñar «sin acceso» a quien sí lo tiene."""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text("Comprobando el acceso...", size="2", color=theme.MUTED),
            spacing="3", align="center",
        ),
        height="100vh", width="100%",
    )


def _registro_invitado() -> rx.Component:
    """El alta de quien llega con un enlace de invitacion.

    Se le pide el nombre antes de dejarle pasar, y no es burocracia: ese nombre
    es el que queda escrito en el registro junto a cada cosa que haga. Sin el,
    todo lo que toque un invitado se apunta como «Invitado», que con dos
    invitados en casa no distingue a nadie.

    Darse un nombre NO hace el acceso permanente: la caducidad la puso quien
    creo la invitacion, y cuando pasa la hora el acceso se cae solo (ver
    auth/store.rol_de)."""
    return rx.center(
        rx.vstack(
            rx.icon("user-plus", size=32, color=theme.ACCENT),
            rx.text("Te han invitado", size="4", weight="bold", color=theme.TEXT),
            rx.text(
                "Escribe tu nombre para entrar. Tu acceso dura lo que dure la "
                "invitacion y se retira solo al terminar.",
                size="2", color=theme.MUTED, text_align="center",
                max_width="380px",
            ),
            rx.input(
                value=AuthState.nombre_invitado,
                on_change=AuthState.set_nombre_invitado,
                placeholder="Tu nombre",
                size="3", width="100%", max_length=30,
                # Enter entra: es un formulario de un solo campo.
                on_key_down=lambda k: rx.cond(
                    k == "Enter", AuthState.registrarse, rx.noop()),
            ),
            rx.button("Entrar", on_click=AuthState.registrarse, size="3",
                      width="100%"),
            spacing="3", align="center", width="min(360px, 90vw)",
        ),
        height="100vh", width="100%", padding="24px",
    )


def _sin_acceso() -> rx.Component:
    """La puerta cerrada. Un dispositivo sin permiso de entrada NO ve el panel:
    ni el plano, ni el estado de la alarma, ni los nombres de los equipos.

    Se dice qué hacer y nada más. Sin detalles del sistema: a quien está
    probando a ver qué hay tampoco hace falta contarle nada."""
    return rx.center(
        rx.vstack(
            rx.icon("shield-off", size=34, color=theme.MUTED),
            rx.text("Este dispositivo no tiene acceso", size="4", weight="bold",
                    color=theme.TEXT),
            rx.text("Pídele a un administrador que le dé acceso desde "
                    "Ajustes → Dispositivos, o usa un enlace de invitación.",
                    size="2", color=theme.MUTED, text_align="center",
                    max_width="420px"),
            # El nombre sale para que quien lo autorice sepa cuál de la lista es
            # este accesorio. Si no tiene nombre todavía, no se inventa nada.
            rx.cond(
                AuthState.nombre_dispositivo != "",
                rx.badge(AuthState.nombre_dispositivo, size="2",
                         variant="surface"),
            ),
            spacing="3", align="center",
        ),
        height="100vh", width="100%", padding="24px",
    )


def _panel() -> rx.Component:
    return rx.fragment(
        rx.script(_DRAG_AND_CLOCK_SCRIPT),
        rx.hstack(
            sidebar(),
            rx.vstack(
                topbar(),
                # Antes del contenido y en el flujo: una alerta de alarma sin
                # confirmar no puede quedarse en una esquina flotante.
                banner_alertas(),
                banner_desconocidos(),
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
        # El desplegable de «esto impide armar»: al nivel de la pagina para que
        # salga se pulse el armado desde donde se pulse.
        dialogo_armado(),
        mobile_bottom_nav(),
        camera_dialogs(),
        photo_dialog(
            InfraState.dialog_foto_abierto,
            InfraState.toggle_dialog,
            InfraState.last_rpi_photo,
        ),
        floating_windows_layer(),
        ir_remote_windows_layer(),
        equipo_windows_layer(),
        paleta_comandos(),
        pulsacion_larga(),
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
        # LA PUERTA. Sin permiso de entrada no se monta el panel: no es que se
        # esconda con CSS, es que no se pinta. Lo que no está en la página no se
        # puede sacar con las herramientas del navegador.
        #
        # Ojo con lo que esto NO es: seguridad de verdad son las comprobaciones
        # de dentro de cada manejador (auth/permisos.py), porque los eventos
        # viajan por el websocket y se pueden invocar sin pasar por ningún botón.
        # Esto es para que quien no tiene acceso no vea el estado de la casa.
        rx.el.style(_DENSIDAD_CSS),
        # El color de acento de ESTE accesorio. rx.theme envuelve el panel, asi que
        # botones, insignias, interruptores y campos se pintan con el color que
        # cada uno haya elegido en su ficha (ver auth/store.preferencias).
        #
        # Lo que NO cambia son los colores propios del panel (theme.ACCENT y
        # compania), que estan escritos como literales en los componentes: el
        # acento manda en el cromo de Radix, no en el rojo de una alarma ni en el
        # verde de un sensor cerrado, que tienen que significar siempre lo mismo.
        rx.theme(
            rx.cond(
                AuthState.comprobando,
                _comprobando(),
                # El alta del invitado va ANTES de la puerta cerrada: quien llega
            # con un enlace todavia no tiene acceso, asi que sin esto veria
            # «no tienes acceso» con la invitacion en la mano.
            rx.cond(
                AuthState.registrando,
                _registro_invitado(),
                rx.cond(AuthState.tiene_acceso, _panel(), _sin_acceso()),
            ),
            ),
            appearance="dark",
            accent_color=AuthState.acento,
        ),
        on_mount=[
            # El PRIMERO de todos: hasta que no se sabe qué dispositivo es
            # este, no se sabe qué puede hacer ni qué se le debe enseñar.
            AuthState.identificar,
            AuthState.canjear_de_la_url,
            # Vigila en vivo si a este accesorio le cambian el acceso: quitarle el
            # permiso tiene que echarlo en el momento, no al recargar.
            AuthState.vigilar_acceso,
            # Para que el aviso de «dispositivo desconocido» tenga datos en
            # cualquier vista, no solo dentro de Ajustes → Dispositivos.
            AuthAdminState.on_load,
            SecurityState.on_load,
            InfraState.on_load,
            RegistryState.on_load,
            NodesState.on_load,
            GroupsState.on_load,
            HostActionsState.on_load,
            AccessControlState.on_load,
            LogsState.on_load,
            AlertasState.on_load,
            AutomationsState.on_load,
            VideoWallState.on_load,
            BackupsState.on_load,
            check_existing_subscription_event(),
            # El último a propósito: abre la vista que pida ?vista= en la URL y
            # tiene que poder pisar el "overview" de partida. Es lo que hace que
            # los atajos del icono de la aplicación (manifest.json → shortcuts)
            # lleguen a donde dicen.
            DashboardState.aplicar_url,
            # Engancharse a una cuenta atras de salida que ya estuviera corriendo.
            ArmingState.recuperar_cuenta,
        ],
        min_height="100vh",
        width="100%",
        background=f"radial-gradient(circle at top, {theme.BG_TOPBAR} 0%, {theme.BG_APP} 55%)",
        custom_attrs={"data-densidad": AuthState.densidad},
    )
