"""
El PLANO de la casa: los marcadores que se pintan encima de la imagen y el
arrastre para colocarlos.

Se llamaba así porque este fichero era la vista clásica entera (la lista de
dispositivos de /clasica, retirada en la fase 8.3). De aquella pantalla solo
queda lo que el panel sigue usando: el plano —que la pestaña Plano monta tal
cual, ver ui/dashboard/views/floor_plan.py— y el enganche de la suscripción de
avisos, que se monta una vez a nivel de página.
"""
import reflex as rx
from ...domains.security.state import SecurityState
from ...domains.cameras.state import CameraState
from ...domains.notifications.state import PushState
from ...domains.notifications.push import VAPID_PUBLIC as _VAPID_PUBLIC
from ...domains.devices import registry
from ...domains.devices.registry_state import RegistryState
from ...domains.auth.state import AuthState
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


def _active_color(color_key, por_defecto):
    """Color del marcador CUANDO ESTÁ ACTIVO — encendido, abierto o disparado.

    Si no se ha elegido ninguno, el que pone el sistema para esa familia
    (`por_defecto`): ámbar para lo que se enciende, rojo para lo que se abre o
    salta. Poder elegirlo importa cuando en el mismo plano hay diez marcadores
    y el color es lo único que los distingue de un vistazo."""
    if color_key is None:
        return por_defecto
    return rx.match(
        color_key,
        *[(k, v) for k, v in FLOOR_COLORS.items() if k],
        por_defecto,
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
            animation_override=None, subtle=None, forma="50%") -> rx.Component:
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
        border_radius=forma,
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
                    color=None, color_on=None) -> rx.Component:
    """Sensor (incluidos los tampers): en reposo, el color elegido en el plano;
    abierto/activo, el que se haya elegido para el estado activo y, si no se ha
    elegido ninguno, ROJO parpadeando rápido.

    El PARPADEO no se puede quitar aunque se cambie el color: es lo que hace que
    un aviso no pase desapercibido, y eso no es cuestión de estética."""
    return _marker(
        entity_id, icon,
        rx.cond(is_open, _active_color(color_on, _RED), _resting_color(color)),
        rx.cond(is_open, name + ": ABIERTO", name + ": Cerrado"),
        top, left, on_click=on_click, alarmed=is_open,
        subtle=_quiet(subtle, is_open),
    )


def _camera_marker(entity_id, name, icon, top, left, on_click, subtle=None, color=None,
                   color_on=None) -> rx.Component:
    """Cámara: no tiene estado de alarma, así que siempre va del color elegido
    en el plano. Al pulsarla se abre su stream."""
    return _marker(entity_id, icon, _resting_color(color), name + " — ver stream", top, left,
                   on_click=on_click, subtle=subtle)


def _door_marker(entity_id, name, icon, is_open, pulsing, top, left, on_click, subtle=None,
                  color=None, color_on=None) -> rx.Component:
    """Puerta: en reposo (cerrada) el color elegido en el plano; ROJO
    parpadeando rápido si el sensor la da por abierta. Al pulsarla se lanza su
    pulso de apertura (igual que el botón "Abrir" de Accesos).

    Mientras el relé está activado (`pulsing`, ver NodesState.pulsing_doors) el
    marcador se pone ámbar y late con un halo que se expande — así se ve que la
    orden salió y está en curso, sin depender de que la puerta tenga sensor de
    estado (muchas solo tienen relé y nunca cambian `is_open`)."""
    return _marker(
        entity_id, icon,
        rx.cond(pulsing, _AMBER,
                rx.cond(is_open, _active_color(color_on, _RED), _resting_color(color))),
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
                   color=None, color_on=None) -> rx.Component:
    """Luz: al pulsarla se conmuta. En reposo (apagada) va del color elegido en
    el plano, igual que el resto de familias; encendida se pone ámbar cálido,
    que es el estado que interesa ver de un vistazo.

    Aquí NO hay rojo ni parpadeo: encender una luz no es ninguna alarma. El
    ámbar es lo único que pone el sistema, y solo mientras está encendida."""
    return _marker(
        entity_id, icon,
        rx.cond(is_on, _active_color(color_on, _AMBER), _resting_color(color)),
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
                                subtle=pos["subtle"] != "", color=pos["color"],
                                color_on=pos["color_on"])
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
                                subtle=pos["subtle"] != "", color=pos["color"],
                                color_on=pos["color_on"])
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
        color_on=s["floor_color_on"].to(str),
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
        color_on=c["floor_color_on"].to(str),
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
        color_on=d["floor_color_on"].to(str),
    )


def _ir_remote_marker(entity_id, name, icon, top, left, on_click, subtle=None, color=None) -> rx.Component:
    """Mando IR: sin estado propio (es transmisor puro, no hay lectura de
    vuelta — ver domains/devices/ir_bus.py), así que igual que una cámara,
    siempre del color elegido en el plano. Al pulsarlo se abre el mando
    virtual en una ventana flotante.

    CUADRADO y no redondo, a diferencia de todos los demás: en el mismo plano
    conviven ya los botones de encender y apagar de cada aparato, y un mando no
    es un interruptor —no dice si algo está encendido, abre una botonera—. La
    forma es lo que deja distinguirlos de un vistazo sin tener que leer el
    icono, que es justo lo que no se puede hacer en un plano lleno."""
    return _marker(entity_id, icon, _resting_color(color), name + " — abrir mando", top, left,
                   on_click=on_click, subtle=subtle, forma="7px")


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
        color_on=l["floor_color_on"].to(str),
    )


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
            # La imagen del plano que se está mirando. Ya no es un estático fijo:
            # la sirve /api/plano comprobando la sesión, porque es el mapa de una
            # casa (ver domains/nodes/planos.py).
            src=NodesState.plano_imagen_url,
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
        # Las camaras del plano tambien piden permiso: el marcador abre su
        # imagen en directo, asi que ensenarlo a quien no puede verlas seria
        # dejar la puerta abierta por el otro lado.
        rx.cond(AuthState.puede_camaras, rx.fragment(*_factory_camera_markers())),
        rx.foreach(NodesState.sensors_on_floor, _dynamic_sensor_marker),
        rx.cond(
            AuthState.puede_camaras,
            rx.foreach(NodesState.cameras_on_floor, _dynamic_camera_marker),
        ),
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
        # Con aspect_ratio en vez de una altura fija en vh, el contenedor SIEMPRE mantiene
        # la misma proporción que la imagen sea cual sea el ancho disponible (móvil,
        # popover compacto, pestaña completa...), así que la imagen nunca se recorta ni se
        # desplaza dentro de su caja, y las posiciones en % de los marcadores siempre caen
        # en el mismo punto visual del dibujo.
        #
        # La proporción sale de las medidas del plano que se esté mirando y no de un 1/1
        # fijo: room.png era cuadrada, pero una planta alta puede no serlo, y con la
        # proporción equivocada todos los marcadores caen desplazados.
        aspect_ratio=NodesState.plano_aspecto,
        background="#0f172a",
        border_radius="6px",
        border="1px solid rgba(255, 255, 255, 0.05)",
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


