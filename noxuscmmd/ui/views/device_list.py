import reflex as rx
from ...domains.security.state import SecurityState
from ...domains.infra.state import InfraState
from ...domains.cameras.state import CameraState
from ...domains.notifications.state import PushState
from ...domains.notifications.push import VAPID_PUBLIC as _VAPID_PUBLIC
from ...domains.devices import registry
from ...domains.devices.registry_state import RegistryState
from ...domains.nodes.state import NodesState
from ...domains.nodes.host_actions_state import HostActionsState
from ..dashboard.state import DashboardState
from ..components.status_row import status_row

VAPID_PUBLIC = _VAPID_PUBLIC

# Script de arrastre de marcadores del plano de planta — mismo patrón que el
# de las ventanas flotantes (ui/pages/dashboard.py): un único listener
# delegado en document, position % relativa al contenedor.
#
# El arrastre NO guarda nada por sí solo: va acumulando las posiciones nuevas
# en window.__nxPlanPending (id del elemento -> {top,left}), y es el botón
# "Listo" del editor quien se lo lleva entero al servidor de una tacada (ver
# floor_plan.py y NodesState.save_floor_positions). Así una sesión de
# recolocar iconos es UNA escritura, y o se guarda todo o no se guarda nada,
# en vez de depender de que cada suelta individual llegue bien.
_PLAN_DRAG_SCRIPT = """
(function(){
    if (window.__nxPlanDragInit) return;
    window.__nxPlanDragInit = true;
    window.__nxPlanPending = window.__nxPlanPending || {};

    // Solo se arrastra con el modo edición activo (el contenedor lleva
    // entonces la clase nx-plan-editing — ver DashboardState.editing_floor_plan):
    // fuera de ese modo el plano es de solo lectura y cada marcador se limita
    // a ejecutar su acción (abrir puerta, encender luz, ver stream...).
    function editing(el){
        var c = el.closest('.nx-plan-container');
        return c && c.classList.contains('nx-plan-editing') ? c : null;
    }

    // En modo edición se anula el clic del marcador en fase de captura, para
    // que recolocar un icono no dispare ademas su accion real.
    document.addEventListener('click', function(e){
        var marker = e.target.closest && e.target.closest('.nx-plan-marker');
        if (marker && editing(marker)) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);

    document.addEventListener('pointerdown', function(e){
        var marker = e.target.closest('.nx-plan-marker');
        if (!marker) return;
        var container = editing(marker);
        if (!container) return;
        var id = marker.getAttribute('data-nx-id');
        if (!id) return;
        // OJO: aquí NO se puede llamar a e.preventDefault(). Cancelar un
        // pointerdown suprime los eventos de ratón de compatibilidad
        // (mousedown/mouseup/click), incluido el clic que el propio plano
        // necesita fuera del modo edición. Para lo que se quería evitar
        // (seleccionar texto al arrastrar) basta el user-select:none del
        // marcador, y el scroll táctil ya lo corta touch-action.
        try { marker.setPointerCapture(e.pointerId); } catch (err) {}
        marker.style.transition = 'none';

        var rect = container.getBoundingClientRect();

        // Los listeners van en document, no en el marcador: si por lo que sea
        // la captura del puntero no llega a activarse, un arrastre rápido que
        // se salga del icono seguiría funcionando igual.
        function onMove(ev){
            var left = Math.max(0, Math.min(100, (ev.clientX - rect.left) / rect.width * 100));
            var top = Math.max(0, Math.min(100, (ev.clientY - rect.top) / rect.height * 100));
            marker.style.left = left.toFixed(1) + '%';
            marker.style.top = top.toFixed(1) + '%';
            window.__nxPlanPending[id] = {top: top.toFixed(1) + '%', left: left.toFixed(1) + '%'};
        }
        function onUp(ev){
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
            document.removeEventListener('pointercancel', onUp);
            marker.style.transition = '';
            try { marker.releasePointerCapture(ev.pointerId); } catch (err) {}
        }
        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
        document.addEventListener('pointercancel', onUp);
    });
})();
"""


# Lo ejecuta el botón "Listo": se lleva TODAS las posiciones acumuladas y deja
# el acumulador vacío. Devuelve "{}" si no se movió nada.
PLAN_COMMIT_SCRIPT = (
    "(function(){var p = window.__nxPlanPending || {};"
    " window.__nxPlanPending = {}; return JSON.stringify(p);})()"
)

# Lo ejecuta el botón "Editar plano" al ENTRAR: descarta cualquier resto de
# una sesión anterior que no llegara a guardarse.
PLAN_RESET_SCRIPT = "window.__nxPlanPending = {};"


# Paleta de los marcadores del plano.
#
# Solo hay DOS colores que ponga el sistema, y los dos significan algo que
# está pasando ahora mismo: rojo = abierto/alarma, ámbar = pulso de apertura
# en curso. Todo lo demás (el estado EN REPOSO) es del usuario y sale del
# selector de color del plano.
_RED, _GREEN, _BLUE, _AMBER, _GREY = "#ef4444", "#22c55e", "#38bdf8", "#f59e0b", "#64748b"
_PURPLE, _CYAN, _SLATE = "#a78bfa", "#22d3ee", "#cbd5e1"

# Color en reposo cuando no se ha elegido ninguno: el MISMO para sensores,
# cámaras, puertas y luces, y neutro a propósito.
#
# Antes cada familia traía aquí su color fijo (verde los sensores/tampers,
# azul las cámaras, ámbar las luces) y ese fijo era el que se veía casi
# siempre: el selector solo pintaba algo en la mitad de los casos y en el
# resto parecía no hacer nada. Ahora la familia NO decide color — decide el
# usuario, y el sistema solo pisa su elección cuando hay alarma o pulso.
_RESTING_DEFAULT = _SLATE

# Colores elegibles para el estado EN REPOSO de un marcador (ver
# NodesState.set_floor_color). El rojo no está: se reserva para "abierto /
# alarma" y lo pone el sistema, nunca el usuario. "claro" es el mismo valor
# que _RESTING_DEFAULT, para poder volver al aspecto de fábrica después de
# haber elegido otro.
FLOOR_COLORS = {
    "": _RESTING_DEFAULT, "claro": _SLATE, "verde": _GREEN, "azul": _BLUE,
    "morado": _PURPLE, "ambar": _AMBER, "cian": _CYAN, "gris": _GREY,
}


def _resting_color(color_key):
    """Color del marcador EN REPOSO: lo que se haya elegido en el selector del
    plano y, si no hay nada elegido, _RESTING_DEFAULT — igual para todas las
    familias. Ninguna recibe ya un color por defecto propio.

    `color_key` es un Var (viene del estado), así que la traducción se hace con
    rx.match, no con un dict de Python. Puede llegar a null (las entidades
    dadas de alta desde la web guardan floor_color=None mientras no se toque
    el selector): un switch sobre null cae en la rama por defecto, que es
    justo lo que se quiere."""
    if color_key is None:
        return _RESTING_DEFAULT
    return rx.match(
        color_key,
        *[(k, v) for k, v in FLOOR_COLORS.items() if k],
        _RESTING_DEFAULT,
    )


def _quiet(subtle, *activos):
    """Combina el ajuste "integrado" del usuario con el estado en vivo: solo
    se pinta discreto MIENTRAS ESTÁ EN REPOSO. Si alguno de `activos` está a
    True (abierto, encendido, pulso en marcha) devuelve False, y el marcador
    recupera su aspecto llamativo — así lo sutil nunca tapa una alerta."""
    if subtle is None:
        return None
    resultado = subtle
    for activo in activos:
        resultado = rx.cond(activo, False, resultado)
    return resultado


def _marker_animation(alarmed, animation_override):
    """La animación base es el parpadeo de ALARMA (`alarmed`: sensor o puerta
    abierta): rojo, con halo y a 0.35s por ciclo — el mismo tipo de latido que
    el pulso de apertura de una puerta pero mucho más rápido, para que se
    distinga de un simple "hay algo pasando" y no se pueda pasar por alto.
    `animation_override` (hoy solo ese pulso de apertura) tiene prioridad
    cuando está activo, porque es un evento puntual que interesa más que el
    estado."""
    # nxAlarmPulse, no "pulse": lleva el translate(-50%,-50%) del centrado
    # dentro de sus keyframes (ver noxuscmmd.py). Con el "pulse" genérico, la
    # animación pisaba el transform del marcador y el icono se descolocaba al
    # cambiar de estado.
    base = rx.cond(alarmed, "nxAlarmPulse 0.35s ease-out infinite", "none") if alarmed is not None else "none"
    if animation_override is None:
        return base
    return rx.cond(animation_override != "", animation_override, base)


def _marker(entity_id, icon, color, title, top, left, on_click=None, alarmed=None,
            animation_override=None, subtle=None) -> rx.Component:
    """Marcador genérico del plano — el MISMO componente para sensores,
    cámaras, puertas y luces: solo cambian icono, color, título y qué hace al
    pulsarlo. `color` puede ser un Var (rx.cond) para los que tienen estado en
    vivo. Arrastrable solo en modo edición (ver _PLAN_DRAG_SCRIPT); fuera de
    ese modo el cursor es de "pulsable" y el clic ejecuta su acción."""
    editing = DashboardState.editing_floor_plan
    props = {}
    if on_click is not None:
        props["on_click"] = on_click
    return rx.box(
        rx.icon(icon, size=14, color=color),
        # rgba() no se puede componer con un Var, así que el relleno/halo se
        # hacen con color-mix/box-shadow sobre currentColor-like: usamos el
        # propio color con transparencia vía CSS color-mix, soportado en todos
        # los navegadores objetivo (Safari 16.2+, Chrome 111+).
        background=(
            rx.cond(subtle, "transparent", f"color-mix(in srgb, {color} 22%, transparent)")
            if subtle is not None else f"color-mix(in srgb, {color} 22%, transparent)"
        ),
        # Modo "integrado": sin aro ni fondo, solo el icono con un brillo
        # suave — parece un piloto del propio aparato dibujado en el plano en
        # vez de una chapa de interfaz encima.
        #
        # OJO: quien llama pasa aquí `subtle` YA combinado con el estado (ver
        # _sensor_marker y compañía), de forma que el modo integrado solo
        # aplica EN REPOSO. En cuanto el elemento se abre/dispara recupera aro,
        # halo y palpitado: discreto mientras todo va bien, imposible de pasar
        # por alto cuando salta.
        border=rx.cond(subtle, "none", f"2px solid {color}") if subtle is not None else f"2px solid {color}",
        border_radius="50%",
        padding=rx.cond(subtle, "2px", "6px") if subtle is not None else "6px",
        box_shadow=rx.cond(subtle, "none", f"0 0 12px {color}") if subtle is not None else f"0 0 12px {color}",
        filter=rx.cond(subtle, f"drop-shadow(0 0 5px {color})", "none") if subtle is not None else "none",
        opacity=rx.cond(subtle, "0.9", "1") if subtle is not None else "1",
        transition="opacity 0.15s ease",
        _hover={"opacity": "1"},
        animation=_marker_animation(alarmed, animation_override),
        class_name="nx-plan-marker",
        position="absolute",
        top=top,
        left=left,
        transform="translate(-50%, -50%)",
        cursor=rx.cond(editing, "grab", "pointer"),
        title=title,
        z_index="10",
        touch_action="none",
        # Sustituye al preventDefault() que no se puede usar en pointerdown
        # (ver _PLAN_DRAG_SCRIPT): evita que arrastrar seleccione texto.
        user_select="none",
        # Lo lee el script de arrastre para saber qué elemento está moviendo.
        data_nx_id=entity_id,
        **props,
    )


def _sensor_marker(entity_id, name, icon, is_open, top, left, on_click=None, subtle=None,
                    color=None) -> rx.Component:
    """Sensor (incluidos los tampers): en reposo, el color elegido en el plano;
    abierto/activo, ROJO parpadeando rápido. El rojo de alarma lo pone el
    sistema y no se puede cambiar desde el selector, a propósito, para que
    ningún ajuste estético pueda esconder un aviso."""
    return _marker(
        entity_id, icon,
        rx.cond(is_open, _RED, _resting_color(color)),
        rx.cond(is_open, name + ": ABIERTO", name + ": Cerrado"),
        top, left, on_click=on_click, alarmed=is_open,
        subtle=_quiet(subtle, is_open),
    )


def _camera_marker(entity_id, name, icon, top, left, on_click, subtle=None, color=None) -> rx.Component:
    """Cámara: no tiene estado de alarma, así que siempre va del color elegido
    en el plano. Al pulsarla se abre su stream."""
    return _marker(entity_id, icon, _resting_color(color), name + " — ver stream", top, left,
                   on_click=on_click, subtle=subtle)


def _door_marker(entity_id, name, icon, is_open, pulsing, top, left, on_click, subtle=None,
                  color=None) -> rx.Component:
    """Puerta: en reposo (cerrada) el color elegido en el plano; ROJO
    parpadeando rápido si el sensor la da por abierta. Al pulsarla se lanza su
    pulso de apertura (igual que el botón "Abrir" de Accesos).

    Mientras el relé está activado (`pulsing`, ver NodesState.pulsing_doors) el
    marcador se pone ámbar y late con un halo que se expande — así se ve que la
    orden salió y está en curso, sin depender de que la puerta tenga sensor de
    estado (muchas solo tienen relé y nunca cambian `is_open`)."""
    return _marker(
        entity_id, icon,
        rx.cond(pulsing, _AMBER, rx.cond(is_open, _RED, _resting_color(color))),
        rx.cond(
            pulsing,
            name + ": ABRIENDO...",
            rx.cond(is_open, name + ": ABIERTA — pulsa para abrir", name + ": Cerrada — pulsa para abrir"),
        ),
        top, left, on_click=on_click, alarmed=is_open,
        subtle=_quiet(subtle, is_open, pulsing),
        # Prevalece sobre la animación "pulse" normal: es la señal de que hay
        # un pulso de apertura en marcha ahora mismo.
        animation_override=rx.cond(pulsing, "nxDoorPulse 0.9s ease-out infinite", ""),
    )


def _light_marker(entity_id, name, icon, is_on, top, left, on_click, subtle=None,
                   color=None) -> rx.Component:
    """Luz: al pulsarla se conmuta. En reposo (apagada) va del color elegido en
    el plano, igual que el resto de familias; encendida se pone ámbar cálido,
    que es el estado que interesa ver de un vistazo.

    Aquí NO hay rojo ni parpadeo: encender una luz no es ninguna alarma. El
    ámbar es lo único que pone el sistema, y solo mientras está encendida."""
    return _marker(
        entity_id, icon,
        rx.cond(is_on, _AMBER, _resting_color(color)),
        rx.cond(is_on, name + ": ENCENDIDA — pulsa para apagar", name + ": Apagada — pulsa para encender"),
        top, left, on_click=on_click, subtle=_quiet(subtle, is_on),
    )


def _factory_sensor_markers() -> list[rx.Component]:
    """Sensores "de fábrica" (puerta_ppal, y cualquier otro con "mostrar en
    el plano" activado) — se enumeran TODOS en Python (el conjunto de
    sensores de fábrica es fijo, viene de registry.binary_sensors()) pero su
    posición/icono/visibilidad se leen de RegistryState.floor_pos, una Var
    reactiva — así el arrastre y el toggle "mostrar en el plano" se ven al
    instante, sin reiniciar el servicio. Los tampers no tienen floor_top
    (se quitaron del plano) así que su rx.cond nunca se muestra."""
    markers = []
    for sid, entity in registry.binary_sensors().items():
        pos = RegistryState.floor_pos[sid]
        default_icon = "door-open" if entity.kind == "door" else "lock"
        icon = rx.cond(pos["icon"] != "", pos["icon"], default_icon)
        is_open = SecurityState.sensor_abierto[sid]
        marker = _sensor_marker(sid, RegistryState.names[sid], icon, is_open, pos["top"], pos["left"],
                                subtle=pos["subtle"] != "", color=pos["color"])
        markers.append(rx.cond(pos["top"] != "", marker, rx.fragment()))
    return markers


def _factory_camera_markers() -> list[rx.Component]:
    """Cámaras "de fábrica" — mismo mecanismo que _factory_sensor_markers
    (posición/icono/visibilidad reactivos vía RegistryState.floor_pos).
    cam_fija/cam_ptz conservan su comportamiento clásico de clic (abren el
    visor de la vista clásica); cualquier otra cámara de fábrica futura
    abriría su ventana flotante del panel nuevo, igual que las dinámicas."""
    markers = []
    for cid, entity in registry.cameras().items():
        pos = RegistryState.floor_pos[cid]
        default_icon = entity.icon or "cctv"
        icon = rx.cond(pos["icon"] != "", pos["icon"], default_icon)
        if cid == "cam_fija":
            on_click = CameraState.toggle_fija_stream
        elif cid == "cam_ptz":
            on_click = CameraState.toggle_ptz_stream
        else:
            on_click = DashboardState.open_window(cid)
        marker = _camera_marker(cid, RegistryState.names[cid], icon, pos["top"], pos["left"], on_click,
                                subtle=pos["subtle"] != "", color=pos["color"])
        markers.append(rx.cond(pos["top"] != "", marker, rx.fragment()))
    return markers


def _dynamic_sensor_marker(s: dict) -> rx.Component:
    """Sensor dado de alta desde la web, ya filtrado a los que tienen
    floor_top (ver NodesState.sensors_on_floor)."""
    icon = rx.cond(s["floor_icon"], s["floor_icon"].to(str), "circle-dot")
    return _sensor_marker(
        s["id"].to(str), s["name"].to(str), icon, s["is_open"],
        s["floor_top"].to(str), s["floor_left"].to(str),
        subtle=s["floor_subtle"], color=s["floor_color"].to(str),
    )


def _dynamic_camera_marker(c: dict) -> rx.Component:
    """Cámara dada de alta desde la web — su clic abre la ventana flotante
    del panel nuevo (no existe visor para cámaras dinámicas en la vista
    clásica, así que ahí el clic simplemente no hace nada visible)."""
    icon = rx.cond(c["floor_icon"], c["floor_icon"].to(str), "video")
    return _camera_marker(
        c["id"].to(str), c["name"].to(str), icon,
        c["floor_top"].to(str), c["floor_left"].to(str),
        DashboardState.open_window(c["id"]),
        subtle=c["floor_subtle"], color=c["floor_color"].to(str),
    )


def _dynamic_door_marker(d: dict) -> rx.Component:
    """Puerta del sistema — al pulsarla lanza su pulso de apertura, con la
    duración configurada en su propia ficha (pestaña Accesos)."""
    icon = rx.cond(d["floor_icon"], d["floor_icon"].to(str), "door-closed")
    did = d["id"].to(str)
    return _door_marker(
        did, d["name"].to(str), icon,
        NodesState.sensor_state[did], NodesState.pulsing_doors[did],
        d["floor_top"].to(str), d["floor_left"].to(str),
        NodesState.open_door(did),
        subtle=d["floor_subtle"], color=d["floor_color"].to(str),
    )


def _ir_remote_marker(entity_id, name, icon, top, left, on_click, subtle=None, color=None) -> rx.Component:
    """Mando IR: sin estado propio (es transmisor puro, no hay lectura de
    vuelta — ver domains/devices/ir_bus.py), así que igual que una cámara,
    siempre del color elegido en el plano. Al pulsarlo se abre el mando
    virtual en una ventana flotante."""
    return _marker(entity_id, icon, _resting_color(color), name + " — abrir mando", top, left,
                   on_click=on_click, subtle=subtle)


def _dynamic_ir_remote_marker(r: dict) -> rx.Component:
    icon = rx.cond(r["floor_icon"], r["floor_icon"].to(str), r["icon"].to(str))
    return _ir_remote_marker(
        r["id"].to(str), r["name"].to(str), icon,
        r["floor_top"].to(str), r["floor_left"].to(str),
        # Desde el plano el mando sale en modo compacto: solo las teclas, sin
        # el taller de edición, y se cierra al tocar fuera — ver
        # ui/dashboard/views/ir_remotes.py.
        DashboardState.open_window_compact(r["id"]),
        subtle=r["floor_subtle"], color=r["floor_color"].to(str),
    )


def _dynamic_light_marker(l: dict) -> rx.Component:
    """Luz del sistema — al pulsarla se enciende/apaga, igual que desde la
    pestaña Luces."""
    icon = rx.cond(l["floor_icon"], l["floor_icon"].to(str), "lightbulb")
    lid = l["id"].to(str)
    return _light_marker(
        lid, l["name"].to(str), icon, l["is_on"],
        l["floor_top"].to(str), l["floor_left"].to(str),
        NodesState.toggle_light(lid),
        subtle=l["floor_subtle"], color=l["floor_color"].to(str),
    )


def subscribe_push_event():
    """Alta de este dispositivo en las notificaciones. El JavaScript vive en
    domains/notifications/scripts.py: lo necesita también PushState, que es
    quien lo encadena solo al entrar cuando el aparato no está vinculado."""
    return PushState.suscribir


def check_existing_subscription_event():
    """Al montar la página: recupera el nombre de este dispositivo a partir de
    la suscripción que ya tenga el navegador y, si no está vinculado, lo da de
    alta (ver PushState.cargar_usuario_desde_subscripcion)."""
    return PushState.comprobar_suscripcion


# Icono y color de cada acción del registro. Antes esto era una cadena de
# rx.cond anidados con una entrada por sensor concreto (PUERTA_ABIERTA,
# TAMPER1_ABIERTO, TAMPER2_ABIERTO...), así que cualquier sensor nuevo caía en
# el icono genérico y se leía distinto que la puerta. Ahora los cambios de
# estado son genéricos (ELEMENTO_ABIERTO/CERRADO, ver domains/nodes/state.py y
# domains/security/state.py) y esto es una simple tabla.
_LOG_META = {
    "ELEMENTO_ABIERTO": ("door-open", "#f97316"),
    "ELEMENTO_CERRADO": ("door-closed", "#22c55e"),
    "ALARMA_DISPARADA": ("triangle-alert", "#ef4444"),
    "ARMADO": ("shield-check", "#22c55e"),
    "DESARMADO": ("shield-off", "#64748b"),
    "ARMADO_GRUPO": ("shield-check", "#f97316"),
    "DESARMADO_GRUPO": ("shield-off", "#64748b"),
    "GRUPO_ALERTA": ("triangle-alert", "#ef4444"),
    "GRUPO_CERRADO": ("shield-check", "#22c55e"),
    # Históricas: entradas escritas antes de unificar el formato. Se mantienen
    # para que el historial antiguo se siga viendo bien.
    "PUERTA_ABIERTA": ("door-open", "#f97316"),
    "PUERTA_CERRADA": ("door-closed", "#22c55e"),
    "TAMPER1_ABIERTO": ("lock-open", "#ef4444"),
    "TAMPER1_CERRADO": ("lock", "#22c55e"),
    "TAMPER2_ABIERTO": ("lock-open", "#ef4444"),
    "TAMPER2_CERRADO": ("lock", "#22c55e"),
}


def _log_icon(accion) -> rx.Component:
    return rx.match(
        accion,
        *[(k, rx.icon(icono, size=16, color=color)) for k, (icono, color) in _LOG_META.items()],
        rx.icon("file-text", size=16, color="#94a3b8"),
    )


def log_row(log: dict):
    """Una fila del historial de eventos. Extraída a función propia para que
    la pestaña "Registros" del dashboard nuevo pinte exactamente igual que
    este popover — misma fuente, mismos iconos, mismo formato."""
    return rx.hstack(
        _log_icon(log["accion"]),
        rx.text(log["timestamp"], size="1", color="#94a3b8", width="150px", font_family="monospace"),
        rx.text(log["usuario"], size="1", color="#38bdf8", width="100px"),
        rx.cond(
            (log["accion"] == "ARMADO") | (log["accion"] == "ARMADO_GRUPO"),
            rx.cond(
                log["detalle"].to(str) != "Armado (sin abiertos)",
                rx.popover.root(
                    rx.popover.trigger(
                        rx.icon("info", size=16, color="#f97316", cursor="pointer")
                    ),
                    rx.popover.content(
                        rx.vstack(
                            rx.text("Elementos abiertos al armar:", weight="bold", color="#e2e8f0"),
                            rx.text(
                                log["detalle"].to(str).replace("Armado con abiertos: ", ""),
                                color="#94a3b8"
                            ),
                            spacing="2",
                        ),
                        background="#1e293b",
                        border="1px solid #475569",
                        padding="12px",
                        border_radius="8px",
                    ),
                ),
            ),
            rx.cond(
                (log["accion"] == "DESARMADO") | (log["accion"] == "DESARMADO_GRUPO"),
                rx.icon("shield-off", size=16, color="#64748b"),
                rx.text(log["detalle"], size="1", color="#e2e8f0", flex="1"),
            ),
        ),
        rx.cond(
            (log["accion"] == "ARMADO") | (log["accion"] == "DESARMADO") | (log["grupo"].to(str) == "TOTAL"),
            rx.badge("TOTAL", size="1", variant="soft", color_scheme="gray"),
            rx.cond(
                (log["accion"] == "ARMADO_GRUPO") | (log["accion"] == "DESARMADO_GRUPO"),
                rx.badge(f"PARCIAL: {log['grupo']}", size="1", variant="soft", color_scheme="purple"),
                rx.fragment(),
            ),
        ),
        spacing="2",
        width="100%",
        align="center",
        padding_y="0.3em",
        border_bottom="1px solid rgba(255,255,255,0.05)",
    )


def logs_popover():
    """Popover que muestra el historial de logs con el formato solicitado."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.icon("clipboard-list", size=18, color="#94a3b8"),
                variant="ghost",
                size="1",
                cursor="pointer",
                aria_label="Ver registros",
                title="Historial de eventos",
            )
        ),
        rx.popover.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("clipboard-list", size=16, color="#94a3b8"),
                    rx.button(
                        "REGISTROS",
                        variant="ghost",
                        size="3",
                        letter_spacing="0.05em",
                        font_weight="bold",
                        padding="0",
                        on_click=SecurityState.refresh_logs,
                        _active={"transform": "scale(1.1)"},
                        _hover={"color": "#e2e8f0"},
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.icon("x", size=14),
                        variant="ghost",
                        size="1",
                        on_click=rx.call_script("document.querySelector('[data-state=open]')?.click()"),
                        title="Cerrar",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.divider(opacity="0.1"),
                rx.box(
                    rx.foreach(SecurityState.logs_recientes, log_row),
                    max_height="350px",
                    overflow_y="auto",
                    width="100%",
                    font_family="monospace",
                ),
                spacing="2",
                width="min(700px, 92vw)",
                padding="8px",
            ),
            background="#111827",
            border="1px solid rgba(255,255,255,0.1)",
            box_shadow="0 10px 25px -5px rgba(0,0,0,0.5)",
            padding="12px",
        ),
    )


def floor_plan_content():
    """Plano de planta con overlays de sensores/cámaras. Extraído a función
    propia para poder reutilizarlo a tamaño completo (pestaña "Plano" del
    dashboard nuevo) además de dentro del popover compacto de
    alarma_control_view. Totalmente data-driven: cualquier sensor o cámara
    (de fábrica o dado de alta desde la web) con "mostrar en el plano"
    activado aparece aquí, en la posición donde se haya arrastrado — no hay
    ninguna entidad hardcodeada (los tampers, en concreto, no tienen
    floor_top y por eso ya no aparecen)."""
    return rx.box(
        rx.script(_PLAN_DRAG_SCRIPT),
        rx.image(
            src="/room.png",
            width="100%",
            height="100%",
            object_fit="contain",
            border_radius="6px",
            opacity="0.9",
            # El plano es decorativo: nada se pulsa sobre él. Dejarlo inerte
            # evita que el navegador arranque SU arrastre nativo de imágenes
            # al mover un marcador por encima (se notaba como si el icono
            # "agarrase" el plano). No se puede cortar con preventDefault en
            # el pointerdown porque eso rompería el guardado — ver
            # _PLAN_DRAG_SCRIPT.
            draggable=False,
            pointer_events="none",
            user_select="none",
        ),
        *_factory_sensor_markers(),
        *_factory_camera_markers(),
        rx.foreach(NodesState.sensors_on_floor, _dynamic_sensor_marker),
        rx.foreach(NodesState.cameras_on_floor, _dynamic_camera_marker),
        rx.foreach(NodesState.doors_on_floor, _dynamic_door_marker),
        rx.foreach(NodesState.lights_on_floor, _dynamic_light_marker),
        rx.foreach(NodesState.ir_remotes_on_floor, _dynamic_ir_remote_marker),
        # nx-plan-editing solo está presente con el modo edición activo: es lo
        # que habilita el arrastre (ver _PLAN_DRAG_SCRIPT).
        class_name=rx.cond(
            DashboardState.editing_floor_plan,
            "nx-plan-container nx-plan-editing",
            "nx-plan-container",
        ),
        position="relative",
        width="100%",
        # room.png es cuadrada (1254x1254) — con aspect_ratio en vez de una altura fija en
        # vh, el contenedor SIEMPRE mantiene la misma proporción que la imagen sea cual sea
        # el ancho disponible (móvil, popover compacto, pestaña completa...), así que la
        # imagen nunca se recorta ni se desplaza dentro de su caja, y las posiciones en %
        # de los sensores/cámara siempre caen en el mismo punto visual de la imagen.
        aspect_ratio="1 / 1",
        background="#0f172a",
        border_radius="6px",
        border="1px solid rgba(255, 255, 255, 0.05)",
    )


def alarma_control_view():
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.popover.root(
                    rx.popover.trigger(
                        rx.button(
                            rx.icon(
                                rx.cond(SecurityState.sistema_armado, "shield-check", "shield-off"),
                                color=rx.cond(SecurityState.sistema_armado, "#ef4444", "#64748b"),
                                size=22,
                            ),
                            variant="ghost",
                            size="1",
                            cursor="pointer",
                            aria_label="Ver plano de sensores",
                            title="Ver mapa de sensores",
                        )
                    ),
                    rx.popover.content(
                        rx.vstack(
                            rx.text("Plano de Planta", size="1", weight="bold", color="#94a3b8"),
                            rx.divider(opacity="0.1"),
                            floor_plan_content(),
                            spacing="2",
                            width="min(340px, 92vw)",
                        ),
                        background="#111827",
                        border="1px solid rgba(255, 255, 255, 0.1)",
                        box_shadow="0 10px 25px -5px rgba(0, 0, 0, 0.5)",
                        padding="10px",
                    ),
                ),
                logs_popover(),
                rx.heading("SEGURIDAD", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                rx.badge(
                    rx.cond(SecurityState.puerta_abierta, "ABIERTA", "CERRADA"),
                    color_scheme=rx.cond(SecurityState.puerta_abierta, "red", "green"),
                    variant="surface"
                ),
                rx.button(
                    rx.icon("triangle-alert", size=18, color="#f97316"),
                    on_click=rx.call_script(
                        """
                        (async function() {
                            let sub = null;
                            try {
                                const reg = await navigator.serviceWorker.ready;
                                const pushSub = await reg.pushManager.getSubscription();
                                if (pushSub) {
                                    sub = {
                                        endpoint: pushSub.endpoint,
                                        keys: {
                                            p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('p256dh')))),
                                            auth: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('auth')))),
                                        }
                                    };
                                }
                            } catch(e) {
                                console.warn('No se pudo obtener la suscripción:', e);
                            }
                            const subscription = sub ? JSON.stringify(sub) : 'null';
                            return subscription;
                        })();
                        """,
                        callback=PushState.lanzar_alerta_global_con_subscripcion
                    ),
                    variant="ghost",
                    size="1",
                    title="Enviar alerta a todos",
                    aria_label="Enviar alerta push a todos los dispositivos",
                ),
                rx.button(
                    rx.icon("bell", size=18),
                    on_click=subscribe_push_event(),
                    variant="ghost",
                    size="1",
                    title="Suscribirse a notificaciones push",
                    aria_label="Suscribirse a notificaciones push",
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.divider(opacity="0.1"),
            rx.hstack(
                rx.text("Monitoreo de Intrusión", size="2", color="#94a3b8"),
                rx.spacer(),
                rx.button(
                    rx.cond(SecurityState.sistema_armado, "DESARMAR", "ARMAR"),
                    on_click=SecurityState.conmutar_alarma,
                    color_scheme=rx.cond(SecurityState.sistema_armado, "red", "green"),
                    variant=rx.cond(SecurityState.sistema_armado, "solid", "surface"),
                    size="2",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        border=rx.cond(SecurityState.sistema_armado, "1px solid rgba(239, 68, 68, 0.3)", "1px solid rgba(255, 255, 255, 0.1)"),
        padding="4",
    )


def cctv_view():
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("video", size=20, color="#818cf8"),
                rx.heading("CCTV", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                rx.vstack(
                    rx.text("H.Ppal", size="1", color="gray"),
                    rx.icon("cctv", size=20, color="#38bdf8"),
                    on_click=CameraState.toggle_fija_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                rx.vstack(
                    rx.text("PTZ", size="1", color="gray"),
                    rx.icon("rotate-cw", size=20, color="#a78bfa"),
                    on_click=CameraState.toggle_ptz_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        border="1px solid rgba(255, 255, 255, 0.1)",
        padding="4",
    )


def _infra_host_row(host) -> rx.Component:
    host_id = host["id"].to(str)
    return status_row(
        host["name"],
        host["ip"],
        NodesState.host_online[host_id],
        host["icon"].to(str),
        on_rdp=HostActionsState.open_rdp(host_id),
        con_rdp=host["puede_rdp"],
    )


def infra_hosts_card():
    """Lista de equipos con estado online/offline en vivo (InfraState.
    actualizar_estados hace ping cada 8s).

    Sale de NodesState.hosts con un rx.foreach, igual que la pestaña Equipos.
    Antes era una lista de siete equipos escrita a mano aquí, con su nombre y
    su icono puestos a mano también, y eso significaba tres cosas: un equipo
    dado de alta desde la web no aparecía nunca, uno renombrado seguía saliendo
    con el nombre viejo, y cambiarle el icono no servía de nada. Ahora esta
    tarjeta enseña exactamente los equipos que hay, como se llamen ahora."""
    return rx.vstack(
        rx.hstack(
            rx.icon("activity", size=20, color="#38bdf8"),
            rx.heading("INFRAESTRUCTURA", size="3", letter_spacing="0.05em"),
            rx.spacer(),
            width="100%",
            align="center",
            px="2",
            pt="2",
        ),
        rx.card(
            rx.vstack(
                rx.foreach(NodesState.hosts, _infra_host_row),
                spacing="2",
                width="100%",
            ),
            width="100%",
            background="rgba(255, 255, 255, 0.03)",
            backdrop_filter="blur(10px)",
            border="1px solid rgba(255, 255, 255, 0.1)",
            padding="4",
        ),
        width="100%",
        spacing="3",
    )


def device_list_view():
    return rx.vstack(
        alarma_control_view(),
        cctv_view(),
        infra_hosts_card(),
        width="100%",
        spacing="3",
    )
