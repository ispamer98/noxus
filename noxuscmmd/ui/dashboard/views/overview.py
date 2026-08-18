"""
Pestaña "Resumen": totalmente configurable por el usuario.

Se compone de widgets que el propio usuario añade/quita/reordena (guardados
en la colección overview_widgets de nodos_dinamicos.json — ver
domains/nodes/store.py). Hay dos familias:

  · "stat_*"   → contador/indicador de estado (arriba, en rejilla uniforme).
  · "action_*" → acceso rápido que ejecuta algo o navega (abajo, en lista).

Los widgets con target fijo (stat_system, stat_sensors...) no necesitan
target_id; los que apuntan a una entidad concreta (un grupo, una cámara, una
puerta, una luz) lo llevan en target_id y su nombre/icono denormalizados.
El bloque "EQUIPOS DE LA CASA" es fijo (no es un widget) porque no es un dato
suelto sino la rejilla de todos los equipos con su estado de ping en vivo.
"""
import reflex as rx

from ....domains.auth.state import AuthState
from ..components.modos import fila_modos
from ..components.armado import cuenta_atras_salida
from ....domains.security.arming_state import ArmingState
from ....domains.security.state import SecurityState
from ....domains.security.groups_state import GroupsState
from ....domains.security.logs_state import LogsState
from ....domains.infra.state import InfraState
from ....domains.nodes.state import NodesState
from ....domains.nodes.store import ACTION_FAMILIES
from ....domains.nodes.host_actions_state import HostActionsState
from ....domains.automations.state import AutomationsState
from ....domains.devices import registry
from .. import theme

from ..components.enviar_alerta import dialogo_enviar_alerta
from ..components.catalog_picker import catalog_picker
from ..state import DashboardState
from .logs import color_de, bg_de

# Ancho fijo de cada celda de equipo — con esto, y flex="0 0 auto", TODOS
# ocupan exactamente lo mismo pase lo que pase con la longitud del nombre, y
# la rejilla se recoloca sola al añadir/quitar equipos.
_HOST_CELL_WIDTH = "92px"


def _quick_action(icon, label, on_click, color=theme.ACCENT, trailing=None) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=17, color=color, flex_shrink="0"),
        rx.text(label, size="2", color=theme.TEXT, weight="medium"),
        rx.spacer(),
        trailing if trailing is not None else rx.icon("chevron-right", size=15, color=theme.MUTED, flex_shrink="0"),
        on_click=on_click,
        cursor="pointer",
        align="center",
        width="100%",
        padding="12px 14px",
        border_radius="10px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )


def _stat_tile(label, value, icon, color=theme.ACCENT, icon_bg=None, controls=None) -> rx.Component:
    """Como components/stat_tile.stat_tile pero sin `hint` y con ancho de
    celda uniforme + hueco para los controles de edición (mover/quitar)."""
    if icon_bg is None:
        icon_bg = theme.alpha(color, 0.14)
    return rx.hstack(
        rx.box(
            rx.icon(icon, size=18, color=color),
            padding=["8px", "8px", "10px"],
            border_radius="10px",
            background=icon_bg,
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(
                label, size="1", color=theme.MUTED, letter_spacing="0.06em",
                text_transform="uppercase", weight="medium",
                white_space="nowrap", overflow="hidden", text_overflow="ellipsis", max_width="100%",
            ),
            rx.text(
                value, size=rx.breakpoints(initial="3", md="4"), weight="bold", color=theme.TEXT,
                white_space="nowrap", overflow="hidden", text_overflow="ellipsis", max_width="100%",
            ),
            spacing="0", align="start", min_width="0", width="100%",
        ),
        controls if controls is not None else rx.fragment(),
        spacing="3",
        align="center",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding=["12px", "12px", "16px"],
        backdrop_filter="blur(10px)",
        flex="1",
        min_width=["135px", "150px", "200px"],
        overflow="hidden",
        transition="background 0.15s ease, border-color 0.15s ease",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )


def _host_cell(icon, name, online) -> rx.Component:
    """Celda de equipo de ancho FIJO — todos ocupan exactamente lo mismo,
    con el nombre recortado si no cabe, así la rejilla queda alineada sea
    cual sea la longitud de los nombres o cuántos equipos haya."""
    return rx.vstack(
        rx.box(
            rx.icon(icon, size=16, color=rx.cond(online, theme.SUCCESS, theme.MUTED)),
            padding="8px",
            border_radius="8px",
            background=rx.cond(online, theme.alpha(theme.SUCCESS, 0.12), theme.alpha(theme.MUTED, 0.08)),
            border=f"1px solid {rx.cond(online, theme.alpha(theme.SUCCESS, 0.4), theme.BORDER)}",
        ),
        rx.text(
            name, size="1", color=theme.MUTED,
            white_space="nowrap", overflow="hidden", text_overflow="ellipsis",
            max_width="100%", text_align="center",
        ),
        spacing="1",
        align="center",
        width=_HOST_CELL_WIDTH,
        flex="0 0 auto",
    )


def _host_cell_from(host) -> rx.Component:
    return _host_cell(
        host["icon"].to(str), host["name"], NodesState.host_online[host["id"].to(str)],
    )


def _equipment_grid() -> rx.Component:
    """Un único rx.foreach: todos los equipos vienen ya de la misma lista, así
    que la rejilla no tiene que mezclar los construidos en Python con los
    reactivos — y un equipo nuevo aparece aquí sin reiniciar."""
    return rx.vstack(
        rx.text("EQUIPOS DE LA CASA", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
        rx.box(
            rx.flex(
                rx.foreach(NodesState.hosts, _host_cell_from),
                gap="14px",
                wrap="wrap",
                justify="start",
                width="100%",
            ),
            background=theme.BG_CARD,
            border=f"1px solid {theme.BORDER}",
            border_radius="12px",
            padding=["12px", "12px", "18px"],
            width="100%",
        ),
        rx.text(InfraState.status, size="1", color=theme.MUTED, italic=True, padding_top="2"),
        spacing="2",
        width="100%",
        flex="1",
        min_width="280px",
    )


# ── Catálogo de widgets ──────────────────────────────────────────────────────
# Cada entrada de _STAT_BUILDERS/_ACTION_BUILDERS recibe el dict del widget y
# devuelve el componente. Añadir un tipo nuevo de widget es añadir una entrada
# aquí + su opción en _build_widget_catalog (domains/nodes/state.py) — nada más.
def _stat_system(w) -> rx.Component:
    return _stat_tile(
        "Sistema",
        rx.cond(SecurityState.sistema_armado, "ARMADO", "DESARMADO"),
        "shield",
        color=rx.cond(SecurityState.sistema_armado, theme.DANGER, theme.SUCCESS),
        icon_bg=rx.cond(
            SecurityState.sistema_armado,
            theme.alpha(theme.DANGER, 0.14), theme.alpha(theme.SUCCESS, 0.14),
        ),
        controls=_widget_controls(w),
    )


def _stat_main_door(w) -> rx.Component:
    return _stat_tile(
        "Puerta principal",
        rx.cond(SecurityState.puerta_abierta, "ABIERTA", "CERRADA"),
        rx.cond(SecurityState.puerta_abierta, "door-open", "door-closed"),
        color=rx.cond(SecurityState.puerta_abierta, theme.WARNING, theme.SUCCESS),
        icon_bg=rx.cond(
            SecurityState.puerta_abierta,
            theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.SUCCESS, 0.14),
        ),
        controls=_widget_controls(w),
    )


def _stat_open_sensors(w) -> rx.Component:
    return _stat_tile("Abiertos ahora", SecurityState.lista_abiertos, "door-open",
                      color=theme.WARNING, controls=_widget_controls(w))


def _stat_groups(w) -> rx.Component:
    return _stat_tile("Grupos armados", f"{GroupsState.armed_count}/{GroupsState.groups.length()}",
                      "layers", color=theme.PURPLE, controls=_widget_controls(w))


def _stat_group(w) -> rx.Component:
    group = GroupsState.groups_by_id[w["target_id"].to(str)]
    armed = group["armed"].to(bool)
    return _stat_tile(
        w["label"], rx.cond(armed, "ARMADO", "DESARMADO"), "layers",
        color=rx.cond(armed, theme.DANGER, theme.SUCCESS),
        icon_bg=rx.cond(armed, theme.alpha(theme.DANGER, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
        controls=_widget_controls(w),
    )


def _stat_light(w) -> rx.Component:
    on = NodesState.sensor_state[w["target_id"].to(str)]
    return _stat_tile(
        w["label"], rx.cond(on, "ENCENDIDA", "APAGADA"), "lightbulb",
        color=rx.cond(on, theme.WARNING, theme.MUTED),
        icon_bg=rx.cond(on, theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.MUTED, 0.1)),
        controls=_widget_controls(w),
    )


def _stat_sensor(w) -> rx.Component:
    """Estado de UN sensor de fábrica (puerta_ppal, tampers...) — su estado en
    vivo vive en SecurityState, no en NodesState."""
    open_ = SecurityState.sensor_abierto[w["target_id"].to(str)]
    return _stat_tile(
        w["label"], rx.cond(open_, "ABIERTO", "CERRADO"),
        rx.cond(open_, "door-open", "door-closed"),
        color=rx.cond(open_, theme.WARNING, theme.SUCCESS),
        icon_bg=rx.cond(open_, theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
        controls=_widget_controls(w),
    )


def _stat_sensor_dyn(w) -> rx.Component:
    """Igual que _stat_sensor pero para un sensor dado de alta desde la web,
    cuyo estado en vivo llega por NodesState.sensor_state. Son dos tipos de
    widget distintos —y no uno que mire en los dos sitios— porque cuál es la
    fuente se sabe al AÑADIR el widget, no al pintarlo."""
    open_ = NodesState.sensor_state[w["target_id"].to(str)]
    return _stat_tile(
        w["label"], rx.cond(open_, "ABIERTO", "CERRADO"),
        rx.cond(open_, "door-open", "door-closed"),
        color=rx.cond(open_, theme.WARNING, theme.SUCCESS),
        icon_bg=rx.cond(open_, theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
        controls=_widget_controls(w),
    )


def _stat_door(w) -> rx.Component:
    open_ = NodesState.sensor_state[w["target_id"].to(str)]
    return _stat_tile(
        w["label"], rx.cond(open_, "ABIERTA", "CERRADA"),
        rx.cond(open_, "door-open", "door-closed"),
        color=rx.cond(open_, theme.WARNING, theme.SUCCESS),
        icon_bg=rx.cond(open_, theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
        controls=_widget_controls(w),
    )


def _stat_host(w) -> rx.Component:
    """Estado en línea / sin conexión de UN equipo, sea cual sea su origen."""
    online = NodesState.host_online[w["target_id"].to(str)]
    return _stat_tile(
        w["label"], rx.cond(online, "EN LÍNEA", "SIN CONEXIÓN"),
        rx.cond(online, "wifi", "wifi-off"),
        color=rx.cond(online, theme.SUCCESS, theme.MUTED),
        icon_bg=rx.cond(online, theme.alpha(theme.SUCCESS, 0.14), theme.alpha(theme.MUTED, 0.1)),
        controls=_widget_controls(w),
    )


def _stat_host_temp(w) -> rx.Component:
    """Temperatura de CPU de UN equipo — información de verdad concreta, no
    un contador: sube o baja, y sirve para saber si un equipo se está
    calentando antes de que se apague solo. Refrescada por
    HostActionsState.temp_loop cada 30s, solo mientras este widget exista."""
    host_id = w["target_id"].to(str)
    valor = HostActionsState.host_temps.get(host_id, "").to(str)
    hay = valor != ""
    # Sin comparar contra un número exacto (no siempre viene "48.3 °C" limpio:
    # depende del sistema operativo), pero si el texto lleva un "4", "5", "6",
    # "7", "8" o "9" seguido de más dígitos por encima de 60 avisa en ámbar —
    # demasiado frágil para acertar siempre, así que se deja neutro y solo se
    # resalta si el equipo está fuera de línea del todo.
    online = NodesState.host_online[host_id]
    return _stat_tile(
        w["label"], rx.cond(hay, valor, rx.cond(online, "Leyendo...", "Sin conexión")),
        "thermometer",
        color=rx.cond(hay, theme.ACCENT, theme.MUTED),
        icon_bg=rx.cond(hay, theme.alpha(theme.ACCENT, 0.14), theme.alpha(theme.MUTED, 0.1)),
        controls=_widget_controls(w),
    )


def _stat_cameras(w) -> rx.Component:
    total = len(registry.visible_cameras()) + NodesState.cameras.length()
    return _stat_tile("Cámaras", total, "video", color=theme.PURPLE, controls=_widget_controls(w))


def _stat_equipment(w) -> rx.Component:
    return _stat_tile("Equipos", NodesState.hosts.length(), "server",
                      color=theme.ACCENT, controls=_widget_controls(w))


def _stat_nodes(w) -> rx.Component:
    hidden = registry.hidden_ids()
    total = len({k for k in registry.gpio_hosts() if k not in hidden}) + NodesState.nodes.length()
    return _stat_tile("Nodos", total, "cpu", color=theme.ACCENT, controls=_widget_controls(w))


def _stat_sensors(w) -> rx.Component:
    total = len(registry.visible_binary_sensors()) + NodesState.sensors.length()
    return _stat_tile("Sensores", total, "radar", color=theme.ACCENT, controls=_widget_controls(w))


def _stat_lights(w) -> rx.Component:
    # Solo las luces: los accesorios (la tele, el ventilador) comparten
    # colección pero no son luces, y contarlos hacía que el contador dijera
    # cuatro con dos bombillas en casa.
    return _stat_tile("Luces", NodesState.total_luces, "lightbulb",
                      color=theme.WARNING, controls=_widget_controls(w))


def _stat_doors(w) -> rx.Component:
    return _stat_tile("Puertas", NodesState.doors.length(), "door-open",
                      color=theme.WARNING, controls=_widget_controls(w))


def _stat_online_hosts(w) -> rx.Component:
    return _stat_tile("Equipos en línea", InfraState.online_count, "wifi",
                      color=theme.SUCCESS, controls=_widget_controls(w))


def _stat_automation(w) -> rx.Component:
    """Estado de UNA automatización concreta: si está apagada, si nunca se ha
    disparado, o el resultado de la última vez — no un contador de cuántas
    hay (eso no dice nada útil de un vistazo), sino SI la que importa está
    haciendo lo que tiene que hacer."""
    regla = AutomationsState.rules_by_id[w["target_id"].to(str)]
    activa = regla["enabled"].to(bool)
    resultado = regla["last_result"].to(str)
    # theme.alpha() opera sobre un str de Python, no sobre un Var: cada rama
    # se resuelve con un color YA fijo antes de que rx.match/rx.cond elija
    # entre ellas — nunca al revés.
    icono = rx.match(
        resultado,
        ("error", "octagon-x"), ("parcial", "triangle-alert"), ("ok", "check-circle-2"),
        "workflow",
    )
    color = rx.cond(
        ~activa, theme.MUTED,
        rx.match(resultado, ("ok", theme.SUCCESS), ("parcial", theme.WARNING),
                 ("error", theme.DANGER), theme.MUTED),
    )
    icon_bg = rx.cond(
        ~activa, theme.alpha(theme.MUTED, 0.1),
        rx.match(resultado,
                 ("ok", theme.alpha(theme.SUCCESS, 0.14)),
                 ("parcial", theme.alpha(theme.WARNING, 0.14)),
                 ("error", theme.alpha(theme.DANGER, 0.14)),
                 theme.alpha(theme.MUTED, 0.1)),
    )
    valor = rx.cond(
        ~activa, "Desactivada",
        rx.cond(resultado == "", "Sin ejecutar", regla["last_run_text"]),
    )
    return _stat_tile(w["label"], valor, icono, color=color, icon_bg=icon_bg,
                      controls=_widget_controls(w))


def _stat_last_event(w) -> rx.Component:
    """Lo último que ha pasado en TODA la casa, no un contador — el widget
    más "de un vistazo" que hay: no hace falta entrar en Registros para saber
    si acaba de pasar algo. Sin target: siempre mira el evento más reciente,
    da igual qué familia se esté filtrando en la pestaña Registros."""
    evento = LogsState.reciente
    hay = evento.contains("titulo")
    return _stat_tile(
        "Último evento",
        rx.cond(hay, evento["titulo"], "Sin actividad todavía"),
        rx.cond(hay, evento["icono"].to(str), "clock"),
        color=rx.cond(hay, color_de(evento["color"]), theme.MUTED),
        icon_bg=rx.cond(hay, bg_de(evento["color"]), theme.alpha(theme.MUTED, 0.1)),
        controls=_widget_controls(w),
    )


_STAT_BUILDERS = {
    "stat_system": _stat_system,
    "stat_main_door": _stat_main_door,
    "stat_open_sensors": _stat_open_sensors,
    "stat_groups": _stat_groups,
    "stat_group": _stat_group,
    "stat_cameras": _stat_cameras,
    "stat_equipment": _stat_equipment,
    "stat_nodes": _stat_nodes,
    "stat_sensors": _stat_sensors,
    "stat_lights": _stat_lights,
    "stat_doors": _stat_doors,
    "stat_online_hosts": _stat_online_hosts,
    "stat_light": _stat_light,
    "stat_sensor": _stat_sensor,
    "stat_sensor_dyn": _stat_sensor_dyn,
    "stat_door": _stat_door,
    "stat_host": _stat_host,
    "stat_host_temp": _stat_host_temp,
    # Los resúmenes guardados de antes de unificar los equipos pueden llevar
    # todavía widgets con este nombre — se pintan igual que cualquier otro.
    "stat_custom_host": _stat_host,
    "stat_automation": _stat_automation,
    "stat_last_event": _stat_last_event,
}


def _action_arm(w) -> rx.Component:
    # A quien no puede armar no se le pinta el acceso rápido. Es solo la cara
    # visible: quien decide es el manejador, que comprueba el permiso aunque el
    # evento llegue sin haber pasado por aquí.
    return rx.cond(
        AuthState.puede_armar,
        _quick_action(
            rx.cond(SecurityState.sistema_armado, "shield-off", "shield-check"),
            rx.cond(SecurityState.sistema_armado, "Desarmar sistema", "Armar sistema"),
            ArmingState.pedir_armar(""),
            color=rx.cond(SecurityState.sistema_armado, theme.DANGER, theme.SUCCESS),
            trailing=_widget_controls(w),
        ),
    )


def _action_group(w) -> rx.Component:
    gid = w["target_id"].to(str)
    armed = GroupsState.groups_by_id[gid]["armed"].to(bool)
    return rx.cond(
        AuthState.puede_armar,
        _quick_action(
            rx.cond(armed, "shield-off", "shield-check"),
            rx.cond(armed, "Desarmar " + w["label"].to(str), "Armar " + w["label"].to(str)),
            ArmingState.pedir_armar(gid),
            color=rx.cond(armed, theme.DANGER, theme.SUCCESS),
            trailing=_widget_controls(w),
        ),
    )


def _action_camera(w) -> rx.Component:
    return _quick_action(
        w["icon"].to(str), w["label"], DashboardState.open_window(w["target_id"].to(str)),
        color=theme.PURPLE, trailing=_widget_controls(w),
    )


def _action_door(w) -> rx.Component:
    return _quick_action(
        "door-open", "Abrir " + w["label"].to(str), NodesState.open_door(w["target_id"].to(str)),
        color=theme.WARNING, trailing=_widget_controls(w),
    )


def _action_light(w) -> rx.Component:
    """Luces Y accesorios: comparten kind, así que el icono NO puede ser fijo.
    Sale del propio elemento (ver referencias._catalogo, que se lo pone según el
    aspecto) y solo cae en la bombilla si no trae ninguno — que es el caso de
    las luces de siempre."""
    lid = w["target_id"].to(str)
    on = NodesState.sensor_state[lid]
    return _quick_action(
        rx.cond(w["icon"] != "", w["icon"].to(str), "lightbulb"),
        w["label"], NodesState.toggle_light(lid),
        color=rx.cond(on, theme.WARNING, theme.MUTED), trailing=_widget_controls(w),
    )


def _action_rdp(w) -> rx.Component:
    """Abre la sesión remota del equipo. Puesto en el Resumen es lo que
    convierte "meterme en mi sesión del PC" en un solo clic desde la portada
    del panel, sin pasar por Equipos ni desplegar la ficha.

    Un solo botón, sin la descarga de reserva que sí tiene la ficha de Equipos:
    esto es la portada, y aquí no cabe un "y si no funciona, prueba este otro".
    Para que el widget cumpla, el equipo tiene que tener configurado desde qué
    equipo se lanza (ver el campo "Lanzar el escritorio remoto desde")."""
    return _quick_action(
        "monitor-play", "Escritorio remoto a " + w["label"].to(str),
        HostActionsState.open_rdp(w["target_id"].to(str)),
        color=theme.ACCENT, trailing=_widget_controls(w),
    )


def _action_notify(w) -> rx.Component:
    """Enviar una alerta escrita a mano al dispositivo que se elija.

    Es el único widget con formulario: los demás ejecutan algo de un clic, y
    este necesita saber a quién y qué antes de mandar nada. Por eso el acceso
    rápido es el disparador de un diálogo en vez de la acción en sí.

    El diálogo es el de components/enviar_alerta, compartido con el icono de la
    barra de arriba: el mismo formulario abierto desde dos sitios."""
    return dialogo_enviar_alerta(
        rx.box(
            _quick_action("bell-ring", "Enviar alerta", rx.noop(),
                          color=theme.WARNING, trailing=_widget_controls(w)),
            width="100%",
        ),
    )


def _action_view(w) -> rx.Component:
    return _quick_action(
        "layout-grid", "Ir a " + w["label"].to(str), DashboardState.set_view(w["target_id"].to(str)),
        trailing=_widget_controls(w),
    )


def _action_alert(w) -> rx.Component:
    return _quick_action(
        "siren", "Ver registros de eventos", DashboardState.set_view("logs"),
        color=theme.WARNING, trailing=_widget_controls(w),
    )


def _action_ir_button(w) -> rx.Component:
    """Pulsa una tecla concreta de un mando virtual sin salir del Resumen —
    la etiqueta ya trae "Mando · Tecla" y el icono es el DEL MANDO al que
    pertenece (TV, ventilador...), no uno fijo — los dos resueltos por
    referencias.etiqueta_widget al añadir el widget y mantenidos al día por
    referencias.sincronizar()."""
    return _quick_action(
        w["icon"].to(str), w["label"], NodesState.send_ir_button_combined(w["target_id"].to(str)),
        color=theme.ACCENT, trailing=_widget_controls(w),
    )


def _action_ir_remote(w) -> rx.Component:
    """Abre el mando ENTERO en su ventana flotante, con todos sus botones — la
    misma que abre el botón «Abrir mando» de la pestaña Mandos.

    Es lo que se quiere cuando el mando se usa de verdad (subir volumen, cambiar
    de canal): un widget por tecla llenaría el Resumen para hacer lo mismo."""
    return _quick_action(
        w["icon"].to(str), w["label"], DashboardState.open_window(w["target_id"].to(str)),
        color=theme.ACCENT, trailing=_widget_controls(w),
    )


def _action_host_button(w) -> rx.Component:
    """Ejecuta uno de los botones personalizados de un equipo (comando SSH o
    pin) sin entrar en Equipos — para lo que se pulsa a diario (reiniciar un
    servicio, encender un relé) y no necesita el resto de la ficha."""
    return _quick_action(
        "square-mouse-pointer", w["label"],
        HostActionsState.run_button(w["target_id"].to(str)),
        color=theme.ACCENT, trailing=_widget_controls(w),
    )


def _action_host_shutdown(w) -> rx.Component:
    """Apaga el equipo sin entrar en Equipos — mismo verbo que la ficha
    (HostActionsState.accion_rapida), pero avisando con un toast en vez de
    escribirlo en una consola que desde el Resumen no está a la vista."""
    return _quick_action(
        "power", "Apagar " + w["label"].to(str),
        HostActionsState.accion_rapida(w["target_id"].to(str), "apagar"),
        color=theme.DANGER, trailing=_widget_controls(w),
    )


def _action_host_wol(w) -> rx.Component:
    """Enciende el equipo por Wake-on-LAN sin entrar en Equipos."""
    return _quick_action(
        "zap", "Encender " + w["label"].to(str),
        HostActionsState.encender_wol(w["target_id"].to(str)),
        color=theme.SUCCESS, trailing=_widget_controls(w),
    )


_ACTION_BUILDERS = {
    "action_arm": _action_arm,
    "action_group": _action_group,
    "action_camera": _action_camera,
    "action_door": _action_door,
    "action_light": _action_light,
    "action_ir_button": _action_ir_button,
    "action_ir_remote": _action_ir_remote,
    "action_host_button": _action_host_button,
    "action_host_shutdown": _action_host_shutdown,
    "action_host_wol": _action_host_wol,
    "action_view": _action_view,
    "action_logs": _action_alert,
    "action_rdp": _action_rdp,
    "action_notify": _action_notify,
}


def _widget_controls(w) -> rx.Component:
    """Mover ⟨ ⟩ y quitar ✕ de cada widget — solo visibles en modo edición
    (DashboardState.editing_overview), para que el Resumen no se vea lleno de
    controles durante el uso normal."""
    return rx.cond(
        DashboardState.editing_overview,
        rx.hstack(
            rx.icon(
                "chevron-left", size=14, color=theme.MUTED, cursor="pointer",
                on_click=NodesState.move_widget_left(w["id"].to(str)).stop_propagation,
                title="Mover antes",
            ),
            rx.icon(
                "chevron-right", size=14, color=theme.MUTED, cursor="pointer",
                on_click=NodesState.move_widget_right(w["id"].to(str)).stop_propagation,
                title="Mover después",
            ),
            rx.icon(
                "x", size=14, color=theme.DANGER, cursor="pointer",
                on_click=NodesState.delete_widget(w["id"].to(str)).stop_propagation,
                title="Quitar del resumen",
            ),
            spacing="2",
            align="center",
            flex_shrink="0",
        ),
        rx.fragment(),
    )


def _widget(w: dict, builders: dict) -> rx.Component:
    """Un widget se pinta según su "kind". rx.match sobre un Var es la única
    forma de elegir en tiempo de ejecución (los widgets vienen de un
    rx.foreach, no se conocen al compilar)."""
    return rx.match(
        w["kind"],
        *[(kind, build(w)) for kind, build in builders.items()],
        rx.fragment(),
    )


# ── Diálogo "Añadir widget" ──────────────────────────────────────────────────
# value = "<kind>:<target_id>" — un único select para no obligar a elegir
# primero tipo y luego entidad. TODAS las opciones (las fijas y las de cada
# entidad) salen de NodesState.widget_catalog, que se rehace en cada alta/baja
# y al abrir este diálogo: así el desplegable ofrece lo que existe ahora mismo
# sin recargar la página. Añadir un tipo de widget nuevo es añadir su entrada
# en _STAT_BUILDERS/_ACTION_BUILDERS de aquí arriba + su opción en
# _build_widget_catalog (domains/nodes/state.py) — nada más.
def _add_widget_dialog() -> rx.Component:
    """El botón "Añadir widget" y su selector.

    Antes era un `rx.select` con TODAS las opciones seguidas —más de cincuenta
    hoy— y había que recorrerlo entero para saber qué había. Ahora usa el mismo
    selector agrupado y con buscador que los tres bloques de las
    automatizaciones (ui/dashboard/components/catalog_picker.py). El catálogo
    en sí no cambia: sigue saliendo de _build_widget_catalog, que se rehace al
    abrirlo para recoger lo dado de alta desde otra pestaña."""
    return rx.fragment(
        rx.button(rx.icon("plus", size=14), "Añadir widget", size="2",
                  variant="surface", color_scheme="blue",
                  on_click=NodesState.open_widget_picker),
        catalog_picker(
            is_open=NodesState.widget_picker_open,
            title="Añadir widget al resumen",
            sections=NodesState.widget_catalog_filtrado,
            query=NodesState.widget_query,
            on_query=NodesState.set_widget_query,
            on_pick=NodesState.add_widget_desde_selector,
            on_close=NodesState.close_widget_picker,
            on_open_change=NodesState.widget_picker_open_change,
            icon="layout-grid",
        ),
    )


def _familia_seccion(family_id: str, label: str, icon: str) -> rx.Component:
    """Una familia de accesos rápidos (Luces, Puertas, Mandos...) — RECOGIDA:
    solo se ve su cabecera (icono, nombre, cuántos hay) hasta que se toca. Es
    lo que permite tener TODAS las posibilidades del proyecto a la vista sin
    que la pantalla se convierta en una pared de botones — alguien que solo
    quiere abrir la puerta principal no tiene que ver antes los botones de
    las luces, los mandos y los equipos.

    Se despliega de dos formas: tocando su cabecera, o automáticamente
    mientras se está en modo "Personalizar" — editando, todo tiene que verse
    para poder mover o quitar cualquier cosa sin ir abriendo grupo a grupo.

    Una familia sin ningún widget no pinta nada, ni siquiera la cabecera: no
    tiene sentido ofrecer un grupo de Mandos vacío si no hay ningún mando."""
    items = NodesState.actions_by_family[family_id].to(list[dict])
    abierta = DashboardState.open_action_families.contains(family_id) | DashboardState.editing_overview
    return rx.cond(
        items.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=15, color=theme.ACCENT, flex_shrink="0"),
                rx.text(label, size="2", color=theme.TEXT, weight="bold"),
                rx.badge(items.length().to_string(), variant="soft", size="1", color_scheme="gray"),
                rx.spacer(),
                rx.icon(
                    rx.cond(abierta, "chevron-up", "chevron-down"),
                    size=16, color=theme.MUTED, flex_shrink="0",
                ),
                on_click=DashboardState.toggle_action_family(family_id),
                cursor="pointer",
                align="center",
                spacing="2",
                width="100%",
                padding="4px 2px",
            ),
            rx.cond(
                abierta,
                rx.vstack(
                    rx.foreach(items, lambda w: _widget(w, _ACTION_BUILDERS)),
                    spacing="2", width="100%", align="start", padding_top="2",
                ),
            ),
            spacing="2",
            width="100%",
            align="start",
            background=theme.BG_CARD,
            border=f"1px solid {rx.cond(abierta, theme.alpha(theme.ACCENT, 0.35), theme.BORDER)}",
            border_radius="12px",
            padding="12px",
            transition="border-color 0.15s ease",
        ),
    )


def _accesos_rapidos() -> rx.Component:
    """Los accesos rápidos agrupados por familia, recogidos, en una rejilla
    que se acomoda sola: una columna en el móvil, dos o tres según haya
    sitio. El orden de las familias (Alarma, Luces, Puertas, Cámaras, Mandos,
    Equipos, Otros) es fijo — store.ACTION_FAMILIES — así que siempre se
    encuentran en el mismo sitio, dé igual el orden en que se fueran
    añadiendo los widgets. Es el contenido principal del Resumen: todo lo que
    de verdad se puede accionar en la casa, cabe aquí."""
    return rx.vstack(
        rx.text("ACCESOS RÁPIDOS", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        rx.grid(
            *[_familia_seccion(fid, label, icon) for fid, label, icon in ACTION_FAMILIES],
            columns=rx.breakpoints(initial="1", sm="2", xl="3"),
            gap="12px",
            width="100%",
            align_items="start",
        ),
        spacing="3",
        width="100%",
        align="start",
    )


def _barra_estado() -> rx.Component:
    """Lo único que se ve SIEMPRE, sin recoger y sin poder quitarse: si la
    casa está armada. Todo lo demás —incluido "qué fue lo último que pasó"—
    es opcional y vive como widget (stat_last_event) o recogido en "Más
    información": aquí solo va lo que se pidió que se quedara fijo."""
    armado = SecurityState.sistema_armado
    return rx.hstack(
        rx.hstack(
            rx.icon(
                rx.cond(armado, "shield-check", "shield-off"), size=16,
                color=rx.cond(armado, theme.DANGER, theme.SUCCESS), flex_shrink="0",
            ),
            rx.text(
                rx.cond(armado, "Sistema armado", "Sistema desarmado"),
                size="2", weight="medium", color=theme.TEXT, white_space="nowrap",
            ),
            # Un invitado SÍ ve si la casa está armada —es lo que evita que
            # abra una puerta sin saber lo que va a pasar— pero la pastilla no
            # le responde al pulsarla. Enseñarle un botón que va a rechazarle
            # sería peor que no enseñárselo.
            on_click=rx.cond(
                AuthState.puede_armar, ArmingState.pedir_armar(""), rx.noop()),
            cursor=rx.cond(AuthState.puede_armar, "pointer", "default"),
            align="center", spacing="2",
            padding="9px 14px", border_radius="999px", flex_shrink="0",
            background=rx.cond(armado, theme.alpha(theme.DANGER, 0.12), theme.alpha(theme.SUCCESS, 0.12)),
            border=f"1px solid {rx.cond(armado, theme.alpha(theme.DANGER, 0.35), theme.alpha(theme.SUCCESS, 0.35))}",
            _hover={"opacity": "0.85"},
            title=rx.cond(
                AuthState.puede_armar,
                rx.cond(armado, "Pulsa para desarmar", "Pulsa para armar"),
                rx.cond(armado, "Sistema armado", "Sistema desarmado"),
            ),
        ),
        spacing="2",
        width="100%",
        wrap="wrap",
    )


def _mas_informacion() -> rx.Component:
    """Contadores y la rejilla de ping de equipos — RECOGIDO por defecto.
    Es información de "cómo está instalado esto" (cuántos nodos hay, cuántas
    cámaras...), útil para quien mantiene el sistema, pero no algo que se
    accione ni algo urgente — por eso no compite por espacio con los accesos
    rápidos. Sigue siendo la MISMA lista de contadores de siempre y se sigue
    editando igual (Personalizar → Añadir widget); solo cambia que empieza
    escondida."""
    abierto = DashboardState.show_overview_extra
    return rx.vstack(
        rx.hstack(
            rx.icon("info", size=13, color=theme.MUTED, flex_shrink="0"),
            rx.text("Más información", size="1", color=theme.MUTED,
                    letter_spacing="0.06em", weight="bold"),
            rx.spacer(),
            rx.icon(rx.cond(abierto, "chevron-up", "chevron-down"), size=14, color=theme.MUTED),
            on_click=DashboardState.toggle_overview_extra,
            cursor="pointer",
            align="center", spacing="2", width="100%",
        ),
        rx.cond(
            abierto,
            rx.vstack(
                rx.flex(
                    rx.foreach(NodesState.widgets, lambda w: _widget(w, _STAT_BUILDERS)),
                    gap="12px", wrap="wrap", width="100%",
                ),
                _equipment_grid(),
                spacing="4", width="100%", padding_top="3",
            ),
        ),
        spacing="2",
        width="100%",
        align="start",
        padding="10px 12px",
        border_radius="10px",
        background=theme.alpha(theme.MUTED, 0.05),
    )


def overview_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.spacer(),
            rx.cond(
                DashboardState.editing_overview,
                rx.hstack(
                    _add_widget_dialog(),
                    rx.button(
                        rx.icon("check", size=14), "Listo",
                        on_click=DashboardState.toggle_editing_overview,
                        size="2", variant="solid", color_scheme="green",
                    ),
                    spacing="2",
                ),
                rx.button(
                    rx.icon("pencil", size=14),
                    on_click=DashboardState.toggle_editing_overview,
                    size="2", variant="surface", color_scheme="gray",
                ),
            ),
            width="100%",
            align="center",
            wrap="wrap",
        ),
        # La fila de modos va ENCIMA de la barra de estado y fuera de los
        # widgets: no se puede quitar ni recolocar desde "Personalizar", igual
        # que el armado. Es el estado de la casa, no un acceso rápido más.
        fila_modos(),
        cuenta_atras_salida(),
        _barra_estado(),
        _accesos_rapidos(),
        _mas_informacion(),
        spacing="4",
        width="100%",
    )
