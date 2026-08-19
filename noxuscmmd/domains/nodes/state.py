"""
Estado reactivo del alta de hardware en caliente (nodos ESP32 + sensores,
puertas, luces, cámaras y equipos extra dados de alta desde la web).

Mismo patrón que SecurityState: un sync_loop de fondo (una vez por proceso,
protegido con _STARTED) que refleja en la UI lo que llega por MQTT, guardado
en JSON compartido (domains/nodes/store.py) para que todos los workers/
sesiones vean lo mismo. No toca SecurityState/InfraState — se engancha al
MQTTBus ya arrancado por SecurityState.on_load vía callback dinámico.
"""
import asyncio
import json
from pathlib import Path

import reflex as rx

from . import store, sensor_events, rdp, referencias, operations, planos
from ..auth import permisos
from ..infra.deshacer import DeshacerState
from ..devices import mqtt_bus, registry, ir_bus
from ..devices.registry_state import RegistryState
from ..security import audit, groups_store, logs
from ..infra.state import InfraState
from ...core import bus
from ...core import sesiones

_STARTED = False

# El registro de pulsos de puerta en curso vive ahora en operations.py, para
# que sea EL MISMO para la web y para el motor de automatizaciones: con dos
# registros separados, "Cortar pulso" desde aquí no cancelaría un pulso
# lanzado por una regla.
_cancel_pulse = operations.cancel_door_pulse


# Icono por defecto de cada familia al ponerla en el plano — el usuario puede
# cambiarlo después desde el propio plano (modo edición) o desde la ficha del
# elemento. Los sensores afinan según su tipo (ver _sensor_default_icon).
_FLOOR_DEFAULT_ICONS = {
    "cameras": "cctv", "factory_cameras": "cctv",
    "doors": "door-closed", "lights": "lightbulb",
}

_SENSOR_KIND_ICONS = {"door": "door-closed", "tamper": "lock", "pir": "radar"}


def _build_floor_catalog(data: dict, plano_actual: str = "",
                         nombres_plano: dict[str, str] | None = None) -> list[dict]:
    """Todo lo que puede aparecer en el plano, en una sola lista plana, para
    que la UI del plano no tenga que saber de qué colección viene cada cosa:
    `ref` ("<colección>:<id>") es lo único que necesita para añadirlo,
    quitarlo o cambiarle el icono."""
    catalog: list[dict] = []

    nombres = nombres_plano or {}

    def add(collection: str, item: dict, kind_label: str, default_icon: str):
        posiciones = item.get("posiciones") or {}
        # En qué OTROS planos está ya colocado. Es lo que permite ofrecer
        # «traerlo de la Planta baja» en vez de tener que colocarlo a ciegas y
        # buscarle el sitio otra vez (ver NodesState.duplicar_desde_plano).
        otros = [p for p in posiciones if p != plano_actual and p in nombres]
        catalog.append({
            "ref": f"{collection}:{item['id']}",
            "label": item.get("name", item["id"]),
            "kind_label": kind_label,
            # "on_floor" es «está en el plano que se está mirando», no «está en
            # alguno»: es lo que decide en qué lista sale.
            "on_floor": plano_actual in posiciones if plano_actual
                        else bool(item.get("floor_top")),
            "origen": otros[0] if otros else "",
            "origen_nombre": nombres.get(otros[0], "") if otros else "",
            "icon": item.get("floor_icon") or default_icon,
            "subtle": bool(item.get("floor_subtle")),
            "color": item.get("floor_color") or "",
            "color_on": item.get("floor_color_on") or "",
        })

    for collection in ("factory_sensors", "sensors"):
        for s in data[collection]:
            add(collection, s, "Sensor", _SENSOR_KIND_ICONS.get(s.get("kind"), "circle-dot"))
    for collection in ("factory_cameras", "cameras"):
        for c in data[collection]:
            add(collection, c, "Cámara", _FLOOR_DEFAULT_ICONS[collection])
    for d in data["doors"]:
        add("doors", d, "Puerta", _FLOOR_DEFAULT_ICONS["doors"])
    for l in data["lights"]:
        # Luces y accesorios comparten colección pero NO grupo en el plano: la
        # tele del salón entre las bombillas no hay quien la encuentre.
        if store.es_luz(l):
            add("lights", l, "Luz", _FLOOR_DEFAULT_ICONS["lights"])
        else:
            add("lights", l, "Accesorio",
                store.ICONO_ASPECTO.get(l.get("aspecto"), "toggle-right"))
    for r in data["ir_remotes"]:
        # El icono por defecto es el propio del mando (TV, ventilador...), no
        # uno fijo por familia como puertas/luces — cada mando IR es de un
        # accesorio distinto.
        add("ir_remotes", r, "Mando IR", r.get("icon") or "tv")
    return catalog


# ── Catálogo del desplegable "Añadir widget" (pestaña Resumen) ───────────────
# Mismo motivo que _build_floor_catalog: la lista de widgets que se pueden
# añadir mezcla colecciones dinámicas (luces, puertas, equipos... y los grupos,
# que viven en otro fichero) con las entidades "de fábrica" del registry, que no
# están en ninguna Var reactiva. Antes se armaba a trozos dentro de la propia
# vista —unos con rx.foreach y otros en Python— y esos últimos se congelaban al
# compilar: dabas de alta o borrabas algo y el desplegable seguía enseñando la
# foto del arranque. Armándolo aquí, en cada _reload(), el desplegable siempre
# ofrece lo que existe AHORA MISMO.
# El valor de cada opción es "<kind>:<target_id>" — lo que espera
# NodesState.submit_add_widget; kind vacío de target para los widgets fijos.
_WIDGETS_GENERALES = [
    # Los tres primeros van primero a propósito: son los que de verdad dicen
    # algo de un vistazo ("¿ha pasado algo?", "¿está todo en orden?"), no un
    # recuento que casi nunca cambia.
    ("Contador · Último evento de la casa", "stat_last_event:"),
    ("Contador · Sistema armado/desarmado", "stat_system:"),
    ("Contador · Puerta principal", "stat_main_door:"),
    ("Contador · Elementos abiertos ahora", "stat_open_sensors:"),
    ("Contador · Grupos armados", "stat_groups:"),
    ("Contador · Nº de cámaras", "stat_cameras:"),
    ("Contador · Nº de equipos", "stat_equipment:"),
    ("Contador · Equipos en línea", "stat_online_hosts:"),
    ("Contador · Nº de nodos", "stat_nodes:"),
    ("Contador · Nº de sensores", "stat_sensors:"),
    ("Contador · Nº de luces", "stat_lights:"),
    ("Contador · Nº de puertas", "stat_doors:"),
    ("Acción · Armar/desarmar el sistema", "action_arm:"),
    ("Acción · Enviar una alerta a un dispositivo", "action_notify:"),
]

_WIDGETS_PESTANAS = [
    ("Acción · Ir a Alarma", "action_view:alarm"),
    ("Acción · Ir a Grupos", "action_view:groups"),
    ("Acción · Ir a Plano", "action_view:floor_plan"),
    ("Acción · Ir a Mural", "action_view:video_wall"),
    ("Acción · Ir a CCTV", "action_view:cctv"),
    ("Acción · Ir a Accesos", "action_view:access"),
    ("Acción · Ir a Luces", "action_view:lights"),
    ("Acción · Ir a Mandos", "action_view:ir_remotes"),
    ("Acción · Ir a Automatizaciones", "action_view:automations"),
    ("Acción · Ir a Equipos", "action_view:equipment"),
    ("Acción · Ir a Ajustes", "action_view:settings_hub"),
    ("Acción · Ir a Registros", "action_view:logs"),
]


# Icono de cada bloque del selector de widgets. Va por el nombre del bloque
# porque es lo único que distingue a las secciones que arma section().
_ICONOS_WIDGET = {
    "Generales": "layout-grid", "Grupos de armado": "layers", "Cámaras": "video",
    "Sensores": "radar", "Puertas": "door-open", "Luces": "lightbulb",
    "Equipos": "server", "Mandos": "gamepad-2", "Botones de equipo": "square-mouse-pointer",
    "Automatizaciones": "workflow", "Ir a una pestaña": "panel-left",
}


def _build_widget_catalog(data: dict) -> list[dict]:
    """Opciones del desplegable "Añadir widget", agrupadas por familia:
    [{"label": "Luces", "options": [{"label": ..., "value": "<kind>:<id>"}]}].
    Las familias sin nada que ofrecer no se incluyen, para no dejar en el
    desplegable un encabezado suelto sin opciones debajo."""
    catalog: list[dict] = []

    def section(label: str, options: list[tuple[str, str]]):
        if options:
            catalog.append({
                "label": label,
                # El icono es de la familia y lo pinta la cabecera de cada
                # bloque del selector (ui/dashboard/components/catalog_picker.py).
                "icon": _ICONOS_WIDGET.get(label, "layout-grid"),
                "options": [{"label": l, "value": v} for l, v in options],
            })

    section("Generales", _WIDGETS_GENERALES)

    grupos = groups_store.read_all()
    section("Grupos de armado", [
        (f"Contador · Estado de {g['name']}", f"stat_group:{g['id']}") for g in grupos
    ] + [
        (f"Acción · Armar/desarmar {g['name']}", f"action_group:{g['id']}") for g in grupos
    ])

    section("Cámaras", [
        (f"Acción · Ver {c.name}", f"action_camera:{cid}")
        for cid, c in registry.visible_cameras().items()
    ] + [
        (f"Acción · Ver {c['name']}", f"action_camera:{c['id']}") for c in data["cameras"]
    ])

    # Los sensores "de fábrica" y los dados de alta desde la web son dos tipos
    # de widget distintos (stat_sensor / stat_sensor_dyn) porque su estado en
    # vivo viene de sitios distintos — ver overview.py.
    section("Sensores", [
        (f"Contador · Estado de {s.name}", f"stat_sensor:{sid}")
        for sid, s in registry.visible_binary_sensors().items()
    ] + [
        (f"Contador · Estado de {s['name']}", f"stat_sensor_dyn:{s['id']}") for s in data["sensors"]
    ])

    section("Puertas", [
        (f"Contador · Estado de {d['name']}", f"stat_door:{d['id']}") for d in data["doors"]
    ] + [
        (f"Acción · Abrir {d['name']}", f"action_door:{d['id']}") for d in data["doors"]
    ])

    # Cada acción se ofrece solo cuando la ficha del equipo tiene lo que hace
    # falta para cumplirla: RDP solo con cuenta de escritorio remoto, apagar/
    # temperatura solo con usuario SSH, encender solo con MAC — lo contrario
    # sería un botón que promete algo que luego no puede hacer.
    section("Equipos", [
        (f"Contador · Estado de {h['name']}", f"stat_host:{h['id']}") for h in data["hosts"]
    ] + [
        (f"Contador · Temperatura de {h['name']}", f"stat_host_temp:{h['id']}")
        for h in data["hosts"] if h.get("user")
    ] + [
        (f"Acción · Escritorio remoto a {h['name']}", f"action_rdp:{h['id']}")
        for h in data["hosts"] if rdp.puede_rdp(h)
    ] + [
        (f"Acción · Apagar {h['name']}", f"action_host_shutdown:{h['id']}")
        for h in data["hosts"] if h.get("user")
    ] + [
        (f"Acción · Encender {h['name']} (WOL)", f"action_host_wol:{h['id']}")
        for h in data["hosts"] if h.get("mac")
    ])

    # Luces y accesorios comparten colección pero se ofrecen por separado, igual
    # que en el menú: quien busca el ventilador no lo busca entre las bombillas.
    _luces = [l for l in data["lights"] if (l.get("aspecto") or "luz") == "luz"]
    _accesorios = [l for l in data["lights"] if (l.get("aspecto") or "luz") != "luz"]

    section("Luces", [
        (f"Contador · Estado de {l['name']}", f"stat_light:{l['id']}") for l in _luces
    ] + [
        (f"Acción · Encender/apagar {l['name']}", f"action_light:{l['id']}") for l in _luces
    ])

    section("Accesorios", [
        (f"Contador · Estado de {l['name']}", f"stat_light:{l['id']}") for l in _accesorios
    ] + [
        (f"Acción · Encender/apagar {l['name']}", f"action_light:{l['id']}") for l in _accesorios
    ])

    # Una tecla de un mando virtual — solo las que YA tienen señal aprendida:
    # ofrecer una que todavía no sabe qué mandar sería un acceso directo a
    # nada. El identificador lleva dos ids ("mando:tecla") en un único
    # target_id — al partirse el widget solo una vez (kind:target_id), el
    # segundo ":" se queda dentro tal cual, y así se recupera en overview.py.
    # El mando ENTERO primero: desde que los aparatos (el ventilador, la tele)
    # tienen su propio apartado y sus teclas se pulsan desde allí, lo que se
    # quiere en el Resumen suele ser el mando de verdad, con todos sus botones.
    # Las teclas sueltas se quedan detrás: siguen valiendo, y quitarlas dejaría
    # sin sentido los widgets que ya haya puestos.
    section("Mandos", [
        (f"Acción · Abrir mando {r['name']}", f"action_ir_remote:{r['id']}")
        for r in data["ir_remotes"]
    ] + [
        (f"Acción · Tecla · {r['name']} · {b['label']}", f"action_ir_button:{r['id']}:{b['id']}")
        for r in data["ir_remotes"] for b in r.get("buttons", []) if b.get("code")
    ])

    nombre_equipo = {h["id"]: h["name"] for h in data["hosts"]}
    section("Botones de equipo", [
        (f"Acción · {nombre_equipo.get(b['host_id'], b['host_id'])} · {b['label']}",
         f"action_host_button:{b['id']}")
        for b in data["host_buttons"]
    ])

    section("Automatizaciones", _catalogo_automatizaciones())

    section("Ir a una pestaña", _WIDGETS_PESTANAS)
    return catalog


def _catalogo_automatizaciones() -> list[tuple[str, str]]:
    """Import perezoso y no arriba del módulo: nodes/ no depende de
    automations/ (es al revés — automations CONSUME nodes), y esto es la
    única excepción, solo para poder ofrecer "Estado de una automatización"
    en el catálogo de widgets. Mismo criterio que ya usa
    referencias._revisar_automatizaciones()."""
    from ..automations import store as auto_store
    try:
        reglas = auto_store.read_all()
    except auto_store.ArchivoCorrupto:
        return []
    return [(f"Contador · Estado de {r['name']}", f"stat_automation:{r['id']}")
            for r in reglas if r["name"]]


# Valor del desplegable "Lanzar desde" que significa "ninguno, desde el
# navegador de quien pulse". No puede ser "" porque un rx.select no deja
# seleccionar una opción con valor vacío.
_SIN_LANZADOR = "navegador"


def _host_para_ui(host: dict) -> dict:
    """Añade a un equipo lo que la tarjeta necesita pero no está guardado en su
    ficha: si tiene SSH y qué acciones especiales le corresponden.

    Los relés y las acciones cableadas (RDP, Wake on LAN, foto) se resuelven
    aquí, en Python, y viajan como datos — dentro de un rx.foreach no se puede
    consultar el registry ni elegir un manejador. `kind` le dice a la tarjeta
    qué pintar y `target` es lo que hay que mandar de vuelta al servidor."""
    extras = [
        {"kind": "relay", "target": relay_id, "label": f"{relay.name} (GPIO{relay.gpio.pin})"}
        for relay_id, relay in registry.relays().items()
        if relay.gpio.host == host["id"]
    ]
    # Las acciones "RDP" de la ficha (rdp_pc, rdp_portatil, rdp_raspberry) se
    # ignoran a propósito: eran manejadores que lanzaban un script EN EL
    # SERVIDOR, y el escritorio remoto tiene que abrirse en el equipo de quien
    # pulsa. Ahora lo pone el bloque de abajo, igual para todos y sin que haga
    # falta que el equipo tenga la acción escrita en su ficha.
    extras += [
        {"kind": "handler", "target": a["handler_name"], "label": a["nombre"]}
        for a in host.get("acciones_extra", [])
        if not a["handler_name"].startswith("rdp_")
    ]
    if rdp.puede_rdp(host):
        usuario_rdp = (host.get("rdp_user") or "").strip()
        extras.append({
            "kind": "rdp",
            "target": host["id"],
            "label": f"Escritorio remoto ({usuario_rdp})" if usuario_rdp else "Escritorio remoto",
            # Con un equipo lanzador configurado, pulsar el botón abre la
            # sesión de verdad y no hay nada que descargar: la tarjeta enseña
            # un botón y solo uno. Sin lanzador dependemos del navegador, que
            # puede no hacer nada, y ahí sí hace falta el de descargar al lado.
            "directo": bool((host.get("rdp_launch_host") or "").strip()),
        })
    # La MAC se guarda como null cuando no hay, pero el formulario necesita
    # texto: un null llega al input como "null" o lo deja sin controlar.
    return {
        **host,
        "mac": host.get("mac") or "",
        "extras": extras,
        "ssh_capable": bool(host.get("user")),
        "puede_rdp": rdp.puede_rdp(host),
        # El desplegable necesita un valor seleccionable siempre; "" no lo es.
        "rdp_launch_host": host.get("rdp_launch_host") or _SIN_LANZADOR,
    }


# Lado de una tecla del mando virtual, en px sobre el cuerpo a tamaño natural
# (mismo valor que _BTN en ui/dashboard/views/ir_remotes.py, contra el que las
# plantillas calculan sus separaciones).
_TECLA = 44

# Cuánto de la altura de la ventana puede ocupar como mucho el cuerpo del
# mando. El resto es para la cabecera de la ventana y sus botones: el mando
# tiene que caber ENTERO sin hacer scroll, que es justo lo que no pasaba con
# un alto fijo de 850px.
_ALTO_MAXIMO_VH = 74


def _pct(valor, total: float) -> float:
    try:
        return float(str(valor).rstrip("%")) / 100 * total
    except (TypeError, ValueError):
        return 0.0


def _placa_de_grupo(grupo: dict, por_id: dict, ancho: float, alto: float,
                     lado: float = _TECLA) -> dict | None:
    """Rectángulo de una placa decorativa, CALCULADO a partir de dónde están
    ahora mismo las teclas que agrupa.

    No se guarda su geometría a propósito: si la placa tuviera coordenadas
    propias, arrastrar una tecla fuera del grupo dejaría el marco flotando en
    medio rodeando un hueco. Derivándola, la placa sigue a sus teclas, se
    estira con ellas y desaparece sola cuando se borran todas."""
    miembros = [por_id[bid] for bid in grupo.get("members", []) if bid in por_id]
    if not miembros:
        return None
    # Coordenadas ya recortadas (render_*): la placa vive en el mismo espacio
    # que las teclas que rodea.
    xs = [_pct(b.get("render_left"), ancho) for b in miembros]
    ys = [_pct(b.get("render_top"), alto) for b in miembros]
    margen = lado / 2 + 9
    x0, x1 = min(xs) - margen, max(xs) + margen
    y0, y1 = min(ys) - margen, max(ys) + margen
    w, h = x1 - x0, y1 - y0
    # Un aro (radius 50%) tiene que ser cuadrado o sale un óvalo.
    if grupo.get("radius") == "50%":
        lado = max(w, h)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x0, y0, w, h = cx - lado / 2, cy - lado / 2, lado, lado
    return {
        "pos_top": f"{(y0 + h / 2) / alto * 100:.2f}%",
        "pos_left": f"{(x0 + w / 2) / ancho * 100:.2f}%",
        "width": f"{w / ancho * 100:.2f}%",
        "height": f"{h / alto * 100:.2f}%",
        "radius": grupo.get("radius", "14px"),
        "tono": grupo.get("tono", "placa"),
    }


# Aire entre la tecla más al borde y el canto de la carcasa.
_MARGEN_CARCASA = _TECLA / 2 + 14
# Suelo del cuerpo recortado: con dos teclas sueltas, ceñirse del todo dejaría
# algo que no parece un mando.
_CUERPO_MINIMO = (200, 190)
# Cuánto de la separación libre entre teclas ocupa una tecla, y sus topes. Es
# lo que hace que un mando con pocos botones los pinte más grandes en vez de
# dejarlos diminutos y perdidos en la carcasa.
_PROPORCION_TECLA = 0.84
_TECLA_MIN, _TECLA_MAX = 34, 66


def _recorte(remote: dict, ancho: int, alto: int) -> tuple[float, float, float, float]:
    """(origen_x, origen_y, ancho, alto) del trozo de carcasa que se pinta.

    El cuerpo guardado es el de la plantilla entera; si se han borrado teclas
    (p.ej. media mitad de abajo) queda un pegote de carcasa vacía. Aquí se
    calcula el recorte que ciñe el cuerpo a las teclas que quedan.

    Se hace AL PINTAR y no tocando el fichero a propósito: las posiciones
    guardadas siguen siendo las mismas, así que esto no puede descolocar nada
    ni acumular error al repetirse. La distribución se ve exactamente igual,
    solo desaparece el hueco muerto."""
    botones = remote.get("buttons", [])
    if not botones:
        return 0.0, 0.0, float(ancho), float(alto)
    xs = [_pct(b.get("pos_left"), ancho) for b in botones]
    ys = [_pct(b.get("pos_top"), alto) for b in botones]
    ancho_util = max(max(xs) - min(xs) + 2 * _MARGEN_CARCASA, _CUERPO_MINIMO[0])
    alto_util = max(max(ys) - min(ys) + 2 * _MARGEN_CARCASA, _CUERPO_MINIMO[1])
    centro_x, centro_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return centro_x - ancho_util / 2, centro_y - alto_util / 2, ancho_util, alto_util


def _lado_de_tecla(botones: list[dict], ancho: int, alto: int) -> float:
    """Cuánto mide una tecla, según lo separadas que estén entre sí.

    Dos teclas cuadradas no se tocan mientras su lado sea menor que la mayor
    de sus dos distancias (horizontal o vertical), así que se toma la más
    apretada de todas las parejas y se deja algo de aire. Con esto un mando de
    pocos botones —o uno al que se le han borrado filas— los pinta grandes en
    vez de dejarlos como cabezas de alfiler en medio de la carcasa."""
    if len(botones) < 2:
        return _TECLA_MAX
    puntos = [
        (_pct(b.get("pos_left"), ancho), _pct(b.get("pos_top"), alto)) for b in botones
    ]
    separacion = min(
        max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        for i, a in enumerate(puntos) for b in puntos[i + 1:]
    )
    return max(_TECLA_MIN, min(_TECLA_MAX, separacion * _PROPORCION_TECLA))


def _remote_para_ui(remote: dict) -> dict:
    """Añade al mando las medidas CSS que la vista necesita pero que no se
    guardan en su ficha.

    El cuerpo se define en px "a tamaño natural" porque las posiciones de sus
    botones son % sobre ESE tamaño. Aquí se traduce a lo que se pinta: el
    cuerpo recortado a las teclas que hay (sin huecos muertos), sus posiciones
    dentro de ese recorte, el tamaño de tecla que le pega a esa distribución,
    y el escalado para que quepa entero en pantalla sin deslizar."""
    ancho = int(remote.get("body_w") or 250)
    alto = int(remote.get("body_h") or 850)
    botones = remote.get("buttons", [])

    origen_x, origen_y, vista_w, vista_h = _recorte(remote, ancho, alto)
    lado = _lado_de_tecla(botones, ancho, alto)

    # Las teclas se recolocan al espacio recortado. Es solo para pintar: en el
    # fichero siguen con sus coordenadas de siempre.
    botones_vista = [
        {
            **b,
            "render_top": f"{(_pct(b.get('pos_top'), alto) - origen_y) / vista_h * 100:.3f}%",
            "render_left": f"{(_pct(b.get('pos_left'), ancho) - origen_x) / vista_w * 100:.3f}%",
        }
        for b in botones
    ]
    por_id = {b["id"]: b for b in botones_vista}
    placas = [
        placa for placa in (
            _placa_de_grupo(g, por_id, vista_w, vista_h, lado) for g in remote.get("groups", [])
        ) if placa is not None
    ]

    limite_vh = _ALTO_MAXIMO_VH * vista_w / vista_h
    return {
        **remote,
        "buttons_render": botones_vista,
        "group_plates": placas,
        # Tres topes a la vez: su tamaño natural, el hueco real que haya de
        # ancho (móvil) y lo que quepa de alto sin hacer scroll.
        "body_css_width": f"min({vista_w:.0f}px, 100%, {limite_vh:.2f}vh)",
        "body_aspect": f"{vista_w:.0f} / {vista_h:.0f}",
        "btn_css_width": f"{lado / vista_w * 100:.2f}%",
        "window_css_width": f"calc(min({vista_w:.0f}px, {limite_vh:.2f}vh) + 56px)",
    }


# ── Elemento de la alarma -> cámara que lo mira ──────────────────────────────
# Valor del desplegable para "ninguna". No puede ser la cadena vacía: el
# desplegable de Reflex (Radix) la reserva para "sin elegir" y protesta si se la
# das como valor de una opción.
SIN_CAMARA = "-"


def _nombre_camara(cam: dict) -> str:
    return (cam.get("name") or cam["id"]).strip()


def _camaras_vigilancia(data: dict) -> list[dict]:
    """Las cámaras a las que se les puede pedir una imagen fija, más la opción
    de ninguna. Las de tipo `embed` o `rtsp` no salen: no hay a quién pedirle un
    fotograma (ver nodes/store.src_de_sensor)."""
    return [
        {"id": SIN_CAMARA, "nombre": "Sin cámara"},
        *({"id": c["id"], "nombre": _nombre_camara(c)}
          for c in data["factory_cameras"]),
        *({"id": c["id"], "nombre": _nombre_camara(c)}
          for c in data["cameras"] if c.get("kind") == "go2rtc"),
    ]


def _elementos_vigilados(data: dict) -> list[dict]:
    """Cada elemento que puede disparar la alarma, con la cámara que tiene
    puesta. Van los de fábrica y los dados de alta desde la web, porque los que
    disparan están repartidos entre las dos colecciones."""
    nombres = {c["id"]: _nombre_camara(c)
               for c in data["factory_cameras"] + data["cameras"]}
    salida = []
    for coleccion in ("factory_sensors", "sensors"):
        for s in data[coleccion]:
            camara = s.get("camara", "") or ""
            existe = camara in nombres
            salida.append({
                "id": s["id"],
                "nombre": (s.get("name") or s["id"]).strip(),
                # Si apunta a una cámara borrada, el desplegable vuelve a "Sin
                # cámara" y el aviso lo cuenta. Dejar seleccionado un id que ya
                # no está en la lista deja el desplegable en blanco y parece que
                # no hay nada puesto, que es peor que decirlo.
                "camara": camara if existe else SIN_CAMARA,
                "aviso": ("la cámara que tenía puesta ya no existe"
                          if camara and not existe else ""),
            })
    return salida


class NodesState(rx.State):
    nodes: list[dict] = []
    sensors: list[dict] = []
    # Qué cámara mira a cada elemento de la alarma, para guardar un fotograma
    # cuando salte (ver ../cameras/fotogramas.py). Los dos van con TODO en str:
    # dentro de un rx.foreach, el valor de una clave que no sea texto tumba el
    # frontend en esta versión de Reflex.
    camaras_vigilancia: list[dict] = []
    elementos_vigilados: list[dict] = []
    # Planos y cuál se está mirando. `plano_actual` es de la SESIÓN: dos
    # personas pueden estar mirando plantas distintas a la vez.
    planos: list[dict] = []
    plano_actual: str = ""
    _nombres_plano: dict[str, str] = {}
    _elementos_por_plano: dict[str, int] = {}
    doors: list[dict] = []
    lights: list[dict] = []
    cameras: list[dict] = []
    hosts: list[dict] = []
    rooms: list[dict] = []
    widgets: list[dict] = []

    @rx.var
    def actions_by_family(self) -> dict[str, list[dict]]:
        """Los accesos rápidos del Resumen, agrupados por familia (Luces,
        Puertas, Mandos...) — ver store.ACTION_FAMILIES para el orden y las
        etiquetas, y store.familia_de() para qué widget cae en cuál. Resuelto
        aquí y no en el frontend: filtrar self.widgets dentro de un
        rx.foreach obliga a condicionales anidados por cada fila."""
        salida: dict[str, list[dict]] = {fid: [] for fid, _, _ in store.ACTION_FAMILIES}
        # Los accesorios usan el mismo kind que las luces ("action_light"), así
        # que la familia no se puede decidir solo con el kind: hace falta mirar a
        # qué apunta. Sin esto, la tele y el ventilador salían bajo «Luces».
        accesorios = {l["id"] for l in self.lights if (l.get("aspecto") or "luz") != "luz"}
        for w in self.widgets:
            familia = store.familia_de(w["kind"])
            if w["kind"] == "action_light" and w.get("target_id") in accesorios:
                familia = "accesorios"
            if familia in salida:
                salida[familia].append(w)
        return salida
    ir_remotes: list[dict] = []
    floor_catalog: list[dict] = []
    widget_catalog: list[dict] = []

    sensor_state: dict[str, bool] = {}
    host_online: dict[str, bool] = {}

    # "<remote_id>:<label>" del botón que se está aprendiendo ahora mismo, o
    # "" si no hay ningún aprendizaje en curso — solo puede haber uno a la vez
    # (un único hub físico), lo lee la UI para poner ese botón concreto en
    # estado "esperando..." (ver ir_remotes.py).
    ir_learning: str = ""

    # Último resultado de aprender/enviar un botón IR, propio (no
    # InfraState.status, que solo se pinta en Resumen/vista clásica): el
    # mando virtual es una ventana flotante que puede estar abierta en
    # cualquier pestaña, así que necesita su propio sitio donde mostrarlo.
    ir_status: str = ""

    # Id del mando cuyo cuerpo se está recolocando ahora mismo ("" = ninguno,
    # modo normal donde tocar un botón lo dispara). Solo uno a la vez, igual
    # que DashboardState.editing_floor_plan — no tiene sentido recolocar dos
    # mandos simultáneamente.
    remote_layout_editing: str = ""

    # Botón que tiene abierto el editor ahora mismo, y los campos que se están
    # editando. Un único editor para todos los botones (en vez de un diálogo
    # por botón dentro del rx.foreach): con mandos de 40 botones, un diálogo
    # por botón multiplica por 40 el árbol de componentes de cada mando.
    editing_button_remote: str = ""
    editing_button_id: str = ""
    editing_button_label: str = ""
    editing_button_icon: str = "circle"
    editing_button_kind: str = "ir"
    editing_button_code: str = ""

    @rx.var
    def ssh_hosts(self) -> list[dict]:
        """Equipos que pueden ejecutar algo por SSH — los únicos que tiene
        sentido ofrecer como lanzadores del escritorio remoto."""
        return [{"id": h["id"], "name": h["name"]} for h in self.hosts if h.get("user")]

    # Puertas con un pulso de apertura en curso ahora mismo — solo para que su
    # marcador del plano lo muestre visualmente (ver open_door). No sustituye a
    # _DOOR_PULSE_TASKS, que es lo que de verdad controla/cancela el pulso: eso
    # es de proceso, y esto es por sesión, solo para pintar.
    pulsing_doors: dict[str, bool] = {}

    # ── Carga inicial ────────────────────────────────────────────────────
    @rx.event
    async def on_load(self):
        global _STARTED
        self._reload()

        # sync_loop es por sesión (cada pestaña necesita ver los cambios que
        # haga cualquier otra), igual que SecurityState.sync_loop.
        yield NodesState.sync_loop

        # Recurso compartido de proceso: solo hace falta uno (evita N
        # conexiones MQTT simultáneas). Escribe al JSON compartido; sync_loop
        # de cada sesión lo recoge de ahí. El ping de equipos ya no está aquí:
        # lo hace InfraState.actualizar_estados para TODOS los equipos, que es
        # además el único bucle que corre también en la vista clásica.
        if not _STARTED:
            _STARTED = True
            yield NodesState.attach_to_mqtt_bus

    def _reload(self):
        # Antes de leer, dejar al día las copias del nombre que hay repartidas
        # por otros ficheros (grupos, niveles de acceso, widgets...). Va aquí
        # porque _reload() se ejecuta después de CADA alta, baja y edición: es
        # el único punto por el que pasan todas, así que no hay forma de
        # renombrar algo y que se quede una copia atrás. Es idempotente y solo
        # escribe si encuentra algo desfasado.
        referencias.sincronizar()
        data = store.read_all()
        self.nodes = data["nodes"]
        self.sensors = data["sensors"]
        self.doors = data["doors"]
        self.lights = data["lights"]
        self.cameras = data["cameras"]
        self.hosts = [_host_para_ui(h) for h in data["hosts"]]
        self.rooms = data["rooms"]
        self.ir_remotes = [_remote_para_ui(r) for r in data["ir_remotes"]]
        self.widgets = sorted(data["overview_widgets"], key=lambda w: w.get("order", 0))
        self.sensor_state = data["sensor_states"]
        self.host_online = data["host_online"]
        self.floor_catalog = _build_floor_catalog(data, self.plano_actual,
                                                  self._nombres_plano)
        self.widget_catalog = _build_widget_catalog(data)
        self.camaras_vigilancia = _camaras_vigilancia(data)
        self.elementos_vigilados = _elementos_vigilados(data)
        self.planos = sorted(data["planos"], key=lambda p: p.get("orden", 0))
        self._nombres_plano = {p["id"]: p["nombre"] for p in self.planos}
        self._elementos_por_plano = {
            p["id"]: sum(
                1 for c in store.COLECCIONES_EN_PLANO for x in data[c]
                if p["id"] in (x.get("posiciones") or {})
            )
            for p in self.planos
        }
        # Al entrar se mira el principal. Y si el que se estaba mirando ya no
        # existe (lo ha borrado otro dispositivo), se vuelve al principal en vez
        # de quedarse enseñando un plano fantasma.
        if not any(p["id"] == self.plano_actual for p in self.planos):
            self.plano_actual = (store.plano_principal(data) or {}).get("id", "")

    # ── Registro de acciones ─────────────────────────────────────────────
    # Todo lo que hace el usuario en esta pestaña queda apuntado con el
    # dispositivo desde el que se hizo (ver ../security/audit.py). En los
    # manejadores de fondo hay que llamarlo DENTRO de un `async with self:`,
    # que es donde se puede pedir el State de la sesión.
    async def _log(self, categoria: str, accion: str, detalle: str = "") -> None:
        await audit.registrar(self, categoria, accion, detalle)

    @staticmethod
    def _nombre(coleccion, item_id: str) -> str:
        """Nombre de un elemento por id, para poder apuntarlo al borrarlo —
        después de borrar ya no hay de dónde sacarlo."""
        return next((x["name"] for x in coleccion if x["id"] == item_id), item_id)

    # ── Catálogo del plano de planta ─────────────────────────────────────
    # Lista ÚNICA con todo lo que puede salir en el plano (sensores, cámaras,
    # puertas y luces; de fábrica o dados de alta desde la web) y si está
    # puesto ya o no. Se recalcula en _reload() —es decir, tras cualquier
    # alta/baja/edición— en vez de ser un @rx.var, porque mezcla colecciones
    # dinámicas con las "de fábrica", que no viven en ninguna Var reactiva.
    @rx.var
    def floor_available(self) -> list[dict]:
        return [e for e in self.floor_catalog if not e["on_floor"]]

    @rx.var
    def floor_available_grouped(self) -> list[dict]:
        """Lo que queda por poner en el plano, partido por tipo (Sensores,
        Cámaras, Puertas, Luces) para que la lista de "añadir" no sea un
        churro plano cuando hay muchos elementos. Se respeta el orden en que
        _build_floor_catalog los genera, y los tipos sin nada pendiente no
        aparecen."""
        grouped: list[dict] = []
        for entry in self.floor_catalog:
            if entry["on_floor"]:
                continue
            section = next((g for g in grouped if g["kind_label"] == entry["kind_label"]), None)
            if section is None:
                section = {"kind_label": entry["kind_label"], "items": []}
                grouped.append(section)
            section["items"].append(entry)
        return grouped

    @rx.var
    def floor_placed(self) -> list[dict]:
        return [e for e in self.floor_catalog if e["on_floor"]]

    @rx.event
    async def add_to_floor(self, ref: str):
        """Coloca un elemento en el centro del plano, listo para arrastrarlo.
        `ref` es "<colección>:<id>" (ver _build_floor_catalog)."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref:
            return
        collection, entity_id = ref.split(":", 1)
        entry = next((e for e in self.floor_catalog if e["ref"] == ref), None)
        icon = entry["icon"] if entry else "circle-dot"
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._place_factory_on_floor(entity_id, icon)
        else:
            store.set_floor_icon(collection, entity_id, icon)
        # La posición se escribe SIEMPRE por aquí, también la de los de fábrica.
        # `_place_factory_on_floor` pasa por apply_override, que solo sabe de
        # floor_top —el espejo del plano principal—, así que colocar algo
        # mirando la segunda planta lo habría puesto en la primera.
        store.set_floor_position(collection, entity_id, "50%", "50%",
                                 self.plano_actual)
        self._reload()
        await self._log(logs.SISTEMA, "PLANO_ELEMENTO_COLOCADO",
                        entry["label"] if entry else ref)

    @rx.event
    async def remove_from_floor(self, ref: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref:
            return
        collection, entity_id = ref.split(":", 1)
        # El nombre hay que cogerlo ANTES de recargar: el catálogo del plano se
        # rehace y la entrada ya no está donde estaba.
        entry = next((e for e in self.floor_catalog if e["ref"] == ref), None)
        # Y la posición también antes de quitarla, que es lo único que hace falta
        # para poder volver a ponerlo donde estaba (ver infra/deshacer.py).
        sitio = self._sitio_actual(collection, entity_id)
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._remove_factory_from_floor(entity_id)
        # Y la posición se quita SIEMPRE por aquí. Sin esto, quitar del plano un
        # elemento de fábrica no hacía nada: apply_override pone floor_top a
        # None, pero floor_top es el espejo de `posiciones`, así que a la lectura
        # siguiente volvía a aparecer donde estaba.
        store.clear_floor_position(collection, entity_id, self.plano_actual)
        self._reload()
        nombre = entry["label"] if entry else ref
        await self._log(logs.SISTEMA, "PLANO_ELEMENTO_QUITADO", nombre)
        if not sitio:
            return
        return DeshacerState.apuntar(
            "plano_quitado",
            {"coleccion": collection, "id": entity_id, "nombre": nombre,
             "plano": self.plano_actual, **sitio},
            f"«{nombre}» quitado del plano",
        )

    def _sitio_actual(self, coleccion: str, entity_id: str) -> dict:
        """{"top","left"} del elemento en el plano que se está mirando, o {}."""
        for item in store.read_all().get(coleccion, []):
            if item.get("id") == entity_id:
                return dict((item.get("posiciones") or {}).get(self.plano_actual)
                            or {})
        return {}

    @rx.event
    async def set_floor_color(self, ref: str, color: str):
        """Color en reposo del marcador. El rojo de "abierto/alarma" sigue
        mandando siempre, así que esto no puede esconder un aviso."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref:
            return
        collection, entity_id = ref.split(":", 1)
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._set_factory_floor_color(entity_id, color)
        else:
            store.set_floor_color(collection, entity_id, color)
        self._reload()

    @rx.event
    async def set_floor_color_on(self, ref: str, color: str):
        """Color del marcador cuando está ACTIVO: encendido, abierto o
        disparado. Vacío = el que pone el sistema para esa familia."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref:
            return
        collection, entity_id = ref.split(":", 1)
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._set_factory_floor_color_on(entity_id, color)
        else:
            store.set_floor_color_on(collection, entity_id, color)
        self._reload()

    @rx.event
    async def toggle_floor_subtle(self, ref: str):
        """Alterna el modo discreto (pequeño y atenuado) de un marcador."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref:
            return
        collection, entity_id = ref.split(":", 1)
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._toggle_factory_floor_subtle(entity_id)
        else:
            store.toggle_floor_subtle(collection, entity_id)
        self._reload()

    @rx.event
    async def set_floor_icon(self, ref: str, icon: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ":" not in ref or not icon:
            return
        collection, entity_id = ref.split(":", 1)
        if collection in ("factory_sensors", "factory_cameras"):
            reg_state = await self.get_state(RegistryState)
            reg_state._set_factory_floor_icon(entity_id, icon)
        else:
            store.set_floor_icon(collection, entity_id, icon)
        self._reload()

    # ── Estancias: agrupación de luces para pintar la pestaña Luces por sala ──
    @rx.var
    def lights_by_room(self) -> dict[str, list[dict]]:
        """Una luz cuyo room_id apunte a una estancia que ya no existe cuenta
        como "sin estancia" (cubo "_none"), igual que si nunca hubiera tenido
        una. store.delete_room ya limpia el room_id al borrar la estancia,
        pero esto rescata además las que quedaron huérfanas antes de que lo
        hiciera: si no, una luz con un room_id fantasma no se pinta en ningún
        sitio y parece borrada."""
        known = {r["id"] for r in self.rooms}
        result: dict[str, list[dict]] = {}
        # Solo las que son LUZ: el ventilador y la tele comparten colección
        # (para heredar plano, resumen, automatizaciones y paleta) pero tienen
        # su propia pestaña, Accesorios. Ver `accesorios` más abajo.
        for l in self.lights:
            if (l.get("aspecto") or "luz") != "luz":
                continue
            room_id = l.get("room_id") or ""
            result.setdefault(room_id if room_id in known else "_none", []).append(l)
        return result

    @rx.var
    def accesorios(self) -> list[dict]:
        """Lo que no es una luz: el ventilador de techo, la tele, un enchufe.

        Misma mecánica que una luz (encender, apagar, guardar el estado) y por
        eso viven en la misma colección; lo que cambia es qué son, y por eso se
        listan aparte."""
        return [l for l in self.lights if (l.get("aspecto") or "luz") != "luz"]

    @rx.var
    def total_luces(self) -> int:
        """Cuántas LUCES hay, sin contar los accesorios (ver `accesorios`)."""
        return sum(1 for l in self.lights if (l.get("aspecto") or "luz") == "luz")

    @rx.var
    def hay_luces(self) -> bool:
        return any((l.get("aspecto") or "luz") == "luz" for l in self.lights)

    @rx.var
    def room_names(self) -> dict[str, str]:
        return {r["id"]: r["name"] for r in self.rooms}

    @rx.event
    async def submit_add_room(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        if not name:
            return
        store.add_room(name)
        self._reload()
        await self._log(logs.SISTEMA, "ESTANCIA_CREADA", name)

    @rx.event
    async def delete_room(self, room_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.rooms, room_id)
        store.delete_room(room_id)
        self._reload()
        await self._log(logs.SISTEMA, "ESTANCIA_ELIMINADA", nombre)

    # ── Enganche al MQTTBus (arrancado por SecurityState.on_load) ─────────
    @rx.event(background=True)
    async def attach_to_mqtt_bus(self):
        bus = None
        for _ in range(40):  # hasta ~10s a que SecurityState arranque el bus
            bus = mqtt_bus.get_running_bus()
            if bus is not None:
                break
            await asyncio.sleep(0.25)
        if bus is None:
            print("⚠️ NodesState: MQTTBus no arrancó a tiempo, sensores dinámicos sin datos en vivo")
            return

        # Mismo callback que usan los sensores de fábrica (ver
        # sensor_events.py): el bus distingue los topics, pero lo que pasa al
        # cambiar de estado es idéntico para todos.
        bus.set_dynamic_callback(sensor_events.on_binary_sensor)
        async with self:
            for s in self.sensors:
                bus.subscribe_dynamic(s["topic"], s["id"])
            for d in self.doors:
                bus.subscribe_dynamic(d["topic_state"], d["id"])
            for l in self.lights:
                # Los accesorios por mando no tienen topic: no hay nada
                # publicando su estado (ver store._campos_luz).
                if l["topic_state"]:
                    bus.subscribe_dynamic(l["topic_state"], l["id"])

    def _subscribe_if_running(self, topic: str, entity_id: str):
        bus = mqtt_bus.get_running_bus()
        if bus is not None:
            bus.subscribe_dynamic(topic, entity_id)

    # ── Sync loop (por sesión): refleja nodos_dinamicos.json en la UI ──────
    # Espera el aviso de quien escribe (core/bus.py) en vez de releer el JSON
    # cada medio segundo: _read() no es barato —cerrojo, json.loads y
    # _apply_defaults entero, planos incluidos— y esto corría dos veces por
    # segundo POR SESIÓN. El tope de 3 s cubre que el fichero lo toque algo de
    # fuera de este proceso.
    @rx.event(background=True)
    async def sync_loop(self):
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.SENSORES, bus.EQUIPOS)
        while True:
            try:
                real_sensors = await asyncio.to_thread(store.get_all_sensor_states)
                real_hosts = await asyncio.to_thread(store.get_all_host_online)
                async with self:
                    if real_sensors != self.sensor_state:
                        self.sensor_state = real_sensors
                    if real_hosts != self.host_online:
                        self.host_online = real_hosts
                if not await aviso.espera(guardia, 3.0):
                    return
            except Exception as e:
                print(f"⚠️ Error en NodesState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 1):
                    return

    # ── Alta: nodos ──────────────────────────────────────────────────────
    @rx.event
    async def submit_add_node(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        ip = form_data.get("ip", "").strip()
        kind = form_data.get("kind", "esp32")
        user = form_data.get("user", "").strip()
        if not name or not ip:
            return
        store.add_node(name, ip, kind, user)
        # Todo nodo es también un equipo de la casa (misma IP) — así aparece
        # en Equipos sin tener que darlo de alta dos veces. Si es SSH, el
        # equipo hereda el usuario y ya tiene consola/acciones ahí mismo.
        if not store.find_host_by_ip(ip):
            nuevo = store.add_host(**store.host_fields(
                name=name, ip=ip, user=user if kind == "ssh" else "", icon="cpu",
            ))
            registry.sync_host(nuevo)
        self._reload()
        await self._log(logs.SENSORES, "NODO_CREADO", f"{name} · {ip} · {kind}")

    @rx.event
    async def delete_node(self, node_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.nodes, node_id)
        store.delete_node(node_id)
        self._reload()
        await self._log(logs.SENSORES, "NODO_ELIMINADO", nombre)

    @rx.event
    async def submit_edit_node(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        node_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        ip = form_data.get("ip", "").strip()
        kind = form_data.get("kind", "esp32")
        user = form_data.get("user", "").strip()
        if not node_id or not name or not ip:
            return
        anterior = self._nombre(self.nodes, node_id)
        store.update_node(node_id, name, ip, kind, user)
        self._reload()
        cambio = f"{anterior} -> {name}" if anterior != name else name
        await self._log(logs.SENSORES, "NODO_EDITADO", f"{cambio} · {ip} · {kind}")

    def _node_name(self, node_id: str) -> str:
        host = registry.gpio_hosts().get(node_id)
        if host:
            return host.name
        node = next((n for n in self.nodes if n["id"] == node_id), None)
        return node["name"] if node else "?"

    # ── Alta: sensores ───────────────────────────────────────────────────
    @rx.event
    async def submit_add_sensor(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        kind = form_data.get("kind", "generic")
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not name or not node_id or not pin:
            return
        item = store.add_sensor(name, kind, node_id, self._node_name(node_id), pin,
                                 show_on_floor, floor_icon)
        self._reload()
        self._subscribe_if_running(item["topic"], item["id"])
        await self._log(logs.SENSORES, "SENSOR_CREADO",
                        f"{name} · {kind} · {self._node_name(node_id)} pin {pin}")

    @rx.event
    async def delete_sensor(self, sensor_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.sensors, sensor_id)
        store.delete_sensor(sensor_id)
        self._reload()
        await self._log(logs.SENSORES, "SENSOR_ELIMINADO", nombre)

    @rx.event
    async def toggle_sensor_isolated(self, sensor_id: str):
        # Aislar un sensor es desarmar media casa sin tocar el botón de armar:
        # la alarma deja de vigilarlo. Pide el mismo permiso que armar.
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        nombre = self._nombre(self.sensors, sensor_id)
        actualizado = store.toggle_sensor_isolated(sensor_id)
        self._reload()
        aislado = bool(actualizado and actualizado.get("isolated"))
        await self._log(
            logs.SENSORES, "SENSOR_AISLADO" if aislado else "SENSOR_REINTEGRADO",
            f"{nombre} — {'la alarma deja de vigilarlo' if aislado else 'vuelve a vigilarse'}",
        )

    @rx.event
    async def asignar_camara(self, sensor_id: str, camara_id: str):
        """Dice qué cámara mira a un elemento, para el fotograma de la alarma.

        Pide AJUSTES y no ARMAR: esto no cambia lo que vigila la alarma ni
        cuándo suena, es configuración de la instalación. Aislar un sensor sí es
        ARMAR, porque ahí la alarma deja de mirarlo."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        real = "" if camara_id == SIN_CAMARA else camara_id
        nombre = self._nombre_elemento(sensor_id)
        if not store.set_sensor_camera(sensor_id, real):
            return
        camara = next((c["nombre"] for c in self.camaras_vigilancia
                       if c["id"] == camara_id), camara_id)
        self._reload()
        if real:
            await self._log(logs.SENSORES, "SENSOR_CAMARA_PUESTA",
                            f"{nombre} · la mira {camara}")
        else:
            await self._log(logs.SENSORES, "SENSOR_CAMARA_QUITADA",
                            f"{nombre} · ya no se guarda fotograma")

    def _nombre_elemento(self, sensor_id: str) -> str:
        return next((e["nombre"] for e in self.elementos_vigilados
                     if e["id"] == sensor_id), sensor_id)

    @rx.event
    async def submit_edit_sensor(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        sensor_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        kind = form_data.get("kind", "generic")
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not sensor_id or not name or not node_id or not pin:
            return
        old = next((s for s in self.sensors if s["id"] == sensor_id), None)
        item = store.update_sensor(sensor_id, name, kind, node_id, self._node_name(node_id), pin,
                                    show_on_floor, floor_icon)
        # Los grupos guardan copiado el nombre de sus miembros: hay que
        # propagarlo o el sensor sigue saliendo con el viejo en Grupos, y con ese
        # nombre viejo se avisa y se registra su apertura.
        groups_store.rename_member(sensor_id, name)
        self._reload()
        cambio = f"{old['name']} -> {name}" if old and old["name"] != name else name
        await self._log(logs.SENSORES, "SENSOR_EDITADO",
                        f"{cambio} · {kind} · {self._node_name(node_id)} pin {pin}")
        if item and old and old["topic"] != item["topic"]:
            bus = mqtt_bus.get_running_bus()
            if bus:
                bus.unsubscribe_dynamic(old["topic"])
                bus.subscribe_dynamic(item["topic"], sensor_id)

    # ── Alta: puertas / cerraduras ──────────────────────────────────────
    @rx.event
    async def submit_add_door(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        pulse_seconds = int(form_data.get("pulse_seconds") or 2)
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not name or not node_id or not pin:
            return
        item = store.add_door(name, node_id, self._node_name(node_id), pin, pulse_seconds,
                              show_on_floor, floor_icon)
        self._reload()
        self._subscribe_if_running(item["topic_state"], item["id"])
        await self._log(logs.PUERTAS, "PUERTA_CREADA",
                        f"{name} · {self._node_name(node_id)} pin {pin} · pulso {pulse_seconds}s")

    @rx.event
    async def delete_door(self, door_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.doors, door_id)
        _cancel_pulse(door_id)
        store.delete_door(door_id)
        self._reload()
        await self._log(logs.PUERTAS, "PUERTA_ELIMINADA", nombre)

    @rx.event
    async def submit_edit_door(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        door_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        pulse_seconds = int(form_data.get("pulse_seconds") or 2)
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not door_id or not name or not node_id or not pin:
            return
        old = next((d for d in self.doors if d["id"] == door_id), None)
        item = store.update_door(door_id, name, node_id, self._node_name(node_id), pin, pulse_seconds,
                                 show_on_floor, floor_icon)
        self._reload()
        cambio = f"{old['name']} -> {name}" if old and old["name"] != name else name
        await self._log(logs.PUERTAS, "PUERTA_EDITADA",
                        f"{cambio} · {self._node_name(node_id)} pin {pin} · pulso {pulse_seconds}s")
        if item and old and old["topic_state"] != item["topic_state"]:
            bus = mqtt_bus.get_running_bus()
            if bus:
                bus.unsubscribe_dynamic(old["topic_state"])
                bus.subscribe_dynamic(item["topic_state"], door_id)

    @rx.event(background=True)
    async def open_door(self, door_id: str):
        """Abrir (pulso): activa el relé durante door['pulse_seconds'] y lo
        vuelve a cerrar solo — cancelable desde cut_door_pulse/set_door_hold.
        El pulso en sí lo lleva operations.pulse_door, que es quien guarda la
        tarea en el registro compartido con el motor."""
        async with self:
            # Dentro del `async with` porque en un evento de fondo es donde se
            # puede tocar el estado — y consultar quién es esta sesión lo es.
            if (no := await permisos.denegar(self, permisos.PUERTAS)):
                return no
            door = next((d for d in self.doors if d["id"] == door_id), None)
            if door is None:
                return
            infra = await self.get_state(InfraState)
            infra.status = f"🔓 Abriendo {door['name']}..."
            self.pulsing_doors[door_id] = True
            await audit.registrar(
                self, logs.PUERTAS, "PUERTA_ABIERTA_MANDO",
                f"{door['name']} · pulso de {door.get('pulse_seconds', 2)}s",
                entidad=door_id,
            )

        async def _acabado(msg: str):
            async with self:
                infra = await self.get_state(InfraState)
                infra.status = msg
                self.pulsing_doors.pop(door_id, None)

        operations.pulse_door(door_id, on_finish=_acabado)

    @rx.event(background=True)
    async def cut_door_pulse(self, door_id: str):
        """Cortar pulso: interrumpe YA un "Abrir (pulso)" en marcha, sin
        esperar a que acabe su temporizador — el relé se fuerza a OFF."""
        async with self:
            if (no := await permisos.denegar(self, permisos.PUERTAS)):
                return no
        _cancel_pulse(door_id)
        async with self:
            self.pulsing_doors.pop(door_id, None)
            door = next((d for d in self.doors if d["id"] == door_id), None)
            if door is None:
                return
        try:
            await operations.send_door_state(door_id, False)
            msg = f"⏹️ Pulso de {door['name']} cortado"
        except operations.OperationError as e:
            msg = f"❌ {door['name']}: {e}"
        async with self:
            infra = await self.get_state(InfraState)
            infra.status = msg
            await self._log(logs.PUERTAS, "PUERTA_PULSO_CORTADO", door["name"])

    @rx.event(background=True)
    async def set_door_hold(self, door_id: str, state: bool):
        """Mantener abierto (state=True) / Mantener cerrado (state=False):
        fuerza el relé a ese estado y lo mantiene — cancela cualquier pulso
        en curso para que no lo pise el auto-cierre."""
        async with self:
            if (no := await permisos.denegar(self, permisos.PUERTAS)):
                return no
        _cancel_pulse(door_id)
        async with self:
            door = next((d for d in self.doors if d["id"] == door_id), None)
            if door is None:
                return
        try:
            await operations.send_door_state(door_id, state)
            msg = f"🔒 {door['name']} mantenida {'ABIERTA' if state else 'CERRADA'}"
        except operations.OperationError as e:
            msg = f"❌ {door['name']}: {e}"
        async with self:
            infra = await self.get_state(InfraState)
            infra.status = msg
            await self._log(
                logs.PUERTAS,
                "PUERTA_MANTENIDA_ABIERTA" if state else "PUERTA_MANTENIDA_CERRADA",
                door["name"],
            )

    # ── Alta: luces ──────────────────────────────────────────────────────
    @rx.var
    def teclas_de_mando(self) -> list[dict]:
        """Todas las teclas aprendidas de todos los mandos, para elegir con qué
        se enciende y con qué se apaga un accesorio.

        Van en UN solo desplegable con el valor compuesto "mando:tecla" (misma
        convención que el catálogo de widgets, más arriba) en vez de dos
        desplegables encadenados: dentro de un rx.form, un segundo select que
        dependa de lo elegido en el primero no se puede filtrar sin sacar el
        formulario entero al estado. Así el mando se deduce de la tecla.

        Solo las que ya tienen señal: ofrecer una tecla sin aprender sería un
        interruptor que no hace nada."""
        return [
            {"valor": f"{r['id']}:{b['id']}",
             "etiqueta": f"{r['name']} · {b['label']}"}
            for r in self.ir_remotes for b in r.get("buttons", []) if b.get("code")
        ]

    @rx.event
    async def submit_add_light(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        room_id = form_data.get("room_id", "")
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        # Una luz puede ser un relé o una tecla de un mando (la del ventilador de
        # techo, por ejemplo): cada forma pide unos datos distintos.
        kind = form_data.get("light_kind", store.LUZ_RELE)
        # Las teclas llegan como "mando:tecla" (ver teclas_de_mando): el mando
        # sale de ahi, y se exige que las dos sean del MISMO mando — encender con
        # uno y apagar con otro es siempre una equivocacion al elegir.
        remote_on, _, btn_on = form_data.get("btn_on", "").partition(":")
        remote_off, _, btn_off = form_data.get("btn_off", "").partition(":")
        remote_id = remote_on
        aspecto = form_data.get("aspecto", "luz")
        mando_modo = form_data.get("mando_modo", store.DOS_TECLAS)
        if not name:
            return
        if kind == store.LUZ_MANDO:
            if mando_modo == store.UNA_TECLA:
                # Una sola tecla para las dos cosas (la de encendido de la tele):
                # solo se pide esa, y la de apagar se ignora aunque venga puesta.
                if not remote_id or not btn_on:
                    self.status = "⚠️ Elige la tecla de encendido del mando."
                    return
                btn_off, remote_off = btn_on, remote_on
            elif not remote_id or not btn_on or not btn_off:
                self.status = ("⚠️ Un accesorio con dos teclas necesita las dos: "
                               "la de encender y la de apagar.")
                return
            if remote_on != remote_off:
                self.status = ("⚠️ Las dos teclas tienen que ser del mismo mando.")
                return
            node_id, pin = "", ""
        elif not node_id or not pin:
            return
        item = store.add_light(name, node_id, self._node_name(node_id), pin, room_id,
                               show_on_floor, floor_icon, kind=kind,
                               remote_id=remote_id, btn_on=btn_on, btn_off=btn_off,
                               aspecto=aspecto, mando_modo=mando_modo)
        self._reload()
        # Una luz de mando no tiene topic al que suscribirse (ver store._campos_luz).
        if item["topic_state"]:
            self._subscribe_if_running(item["topic_state"], item["id"])
        estancia = self._nombre(self.rooms, room_id) if room_id else "sin estancia"
        como = ("por mando" if kind == store.LUZ_MANDO
                else f"{self._node_name(node_id)} pin {pin}")
        await self._log(logs.LUCES, "LUZ_CREADA", f"{name} · {como} · {estancia}")

    @rx.event
    async def delete_light(self, light_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.lights, light_id)
        store.delete_light(light_id)
        self._reload()
        await self._log(logs.LUCES, "LUZ_ELIMINADA", nombre)

    @rx.event
    async def submit_edit_light(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        light_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        node_id = form_data.get("node_id", "")
        pin = form_data.get("pin", "").strip()
        room_id = form_data.get("room_id", "")
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        kind = form_data.get("light_kind", store.LUZ_RELE)
        # Las teclas llegan como "mando:tecla" (ver teclas_de_mando): el mando
        # sale de ahi, y se exige que las dos sean del MISMO mando — encender con
        # uno y apagar con otro es siempre una equivocacion al elegir.
        remote_on, _, btn_on = form_data.get("btn_on", "").partition(":")
        remote_off, _, btn_off = form_data.get("btn_off", "").partition(":")
        remote_id = remote_on
        aspecto = form_data.get("aspecto", "luz")
        mando_modo = form_data.get("mando_modo", store.DOS_TECLAS)
        if not light_id or not name:
            return
        if kind == store.LUZ_MANDO:
            if mando_modo == store.UNA_TECLA:
                # Una sola tecla para las dos cosas (la de encendido de la tele):
                # solo se pide esa, y la de apagar se ignora aunque venga puesta.
                if not remote_id or not btn_on:
                    self.status = "⚠️ Elige la tecla de encendido del mando."
                    return
                btn_off, remote_off = btn_on, remote_on
            elif not remote_id or not btn_on or not btn_off:
                self.status = ("⚠️ Un accesorio con dos teclas necesita las dos: "
                               "la de encender y la de apagar.")
                return
            if remote_on != remote_off:
                self.status = ("⚠️ Las dos teclas tienen que ser del mismo mando.")
                return
            node_id, pin = "", ""
        elif not node_id or not pin:
            return
        old = next((l for l in self.lights if l["id"] == light_id), None)
        item = store.update_light(light_id, name, node_id, self._node_name(node_id), pin, room_id,
                                  show_on_floor, floor_icon, kind=kind,
                                  remote_id=remote_id, btn_on=btn_on, btn_off=btn_off,
                               aspecto=aspecto, mando_modo=mando_modo)
        self._reload()
        cambio = f"{old['name']} -> {name}" if old and old["name"] != name else name
        estancia = self._nombre(self.rooms, room_id) if room_id else "sin estancia"
        movida = old and (old.get("room_id") or "") != (room_id or "")
        como = ("por mando" if kind == store.LUZ_MANDO
                else f"{self._node_name(node_id)} pin {pin}")
        detalle = f"{cambio} · {como} · {estancia}"
        await self._log(logs.LUCES, "LUZ_CAMBIADA_DE_ESTANCIA" if movida else "LUZ_EDITADA", detalle)
        if item and old and old["topic_state"] != item["topic_state"]:
            bus = mqtt_bus.get_running_bus()
            if bus:
                # Cualquiera de los dos puede estar vacío: al pasar una luz de
                # relé a mando pierde su topic, y al revés lo estrena.
                if old["topic_state"]:
                    bus.unsubscribe_dynamic(old["topic_state"])
                if item["topic_state"]:
                    bus.subscribe_dynamic(item["topic_state"], light_id)

    @rx.event(background=True)
    async def toggle_light(self, light_id: str):
        """Conmuta una luz de forma OPTIMISTA: se pinta el estado nuevo antes
        de mandar la orden, y se revierte si la orden falla.

        El orden importa: encender por SSH (conexión + raspi-gpio) puede tardar
        1-3s, y si se espera a que vuelva para repintar, el icono del plano
        parece colgado. Y hay que persistir en disco ANTES de tocar la Var, no
        solo la Var: sync_loop relee el JSON cada 0.5s y, si el disco todavía
        tuviera el valor viejo, desharía el cambio optimista al instante. Ese
        orden lo mantiene operations.set_light, que es donde vive ahora el
        envío y su reversión (lo comparte con el motor de automatizaciones);
        aquí queda solo lo que necesita la sesión, reinyectado por callbacks.

        El estado nuevo se calcula AQUÍ y se pasa explícito en vez de dejar que
        operations lo deduzca del disco: si no, un doble clic manda dos «lee el
        disco y dale la vuelta» que pueden leer el mismo valor y pedir lo mismo
        las dos veces."""
        async with self:
            if (no := await permisos.denegar(self, permisos.LUCES)):
                return no
            light = next((l for l in self.lights if l["id"] == light_id), None)
            if light is None:
                return
            nuevo_estado = not self.sensor_state.get(light_id, False)

        async def _pintar(nuevo: bool):
            async with self:
                self.sensor_state[light_id] = nuevo
                await audit.registrar(
                    self, logs.LUCES, "LUZ_ENCENDIDA" if nuevo else "LUZ_APAGADA",
                    light["name"], entidad=light_id,
                )

        async def _deshacer(nuevo: bool, e: Exception):
            async with self:
                self.sensor_state[light_id] = not nuevo
                infra = await self.get_state(InfraState)
                infra.status = f"❌ {light['name']}: {e}"
                # La orden no llegó, así que el encendido de arriba no pasó de
                # verdad: hay que dejarlo dicho o el registro miente.
                await self._log(logs.LUCES, "LUZ_ERROR", f"{light['name']}: {e}")

        try:
            await operations.set_light(light_id, nuevo_estado,
                                       on_applied=_pintar, on_failed=_deshacer)
        except operations.OperationError:
            # _deshacer ya lo ha pintado y registrado. El motor sí propaga el
            # fallo (lo apunta como error de la regla); la interfaz no tiene a
            # quién propagárselo.
            pass

    # ── Alta: cámaras extra ─────────────────────────────────────────────
    @rx.event
    async def submit_add_camera(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        url = form_data.get("url", "").strip()
        icon = form_data.get("icon", "video")
        kind = form_data.get("kind", "embed")
        if not name or not url:
            return
        store.add_camera(name, url, icon, kind)
        self._reload()
        await self._log(logs.CCTV, "CAMARA_CREADA", f"{name} · {kind} · {url}")

    @rx.event
    async def delete_camera(self, camera_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.cameras, camera_id)
        store.delete_camera(camera_id)
        self._reload()
        await self._log(logs.CCTV, "CAMARA_ELIMINADA", nombre)

    @rx.event
    async def submit_edit_camera(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        camera_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        url = form_data.get("url", "").strip()
        icon = form_data.get("icon", "video")
        kind = form_data.get("kind", "embed")
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not camera_id or not name or not url:
            return
        anterior = self._nombre(self.cameras, camera_id)
        store.update_camera(camera_id, name, url, icon, kind, show_on_floor, floor_icon)
        self._reload()
        cambio = f"{anterior} -> {name}" if anterior != name else name
        await self._log(logs.CCTV, "CAMARA_EDITADA", f"{cambio} · {kind} · {url}")

    # ── Mandos IR (Broadlink) ─────────────────────────────────────────────
    # El hub físico es uno solo (IP_BROADLINK/MAC_BROADLINK) — cada "mando" de
    # aquí es solo un nombre + una lista de botones, uno por accesorio real
    # (TV, ventilador, aire...). Aprender y disparar botones van por
    # domains/devices/ir_bus.py, 100% LAN, sin pasar por ninguna nube.
    @rx.event
    async def submit_add_ir_remote(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        icon = form_data.get("icon", "tv")
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        plantilla = form_data.get("plantilla", "vacio")
        if not name:
            return
        creado = store.add_ir_remote(name, icon, show_on_floor, floor_icon, plantilla)
        self._reload()
        n = len(creado.get("buttons", []))
        detalle = f"{name} · {n} botones de plantilla" if n else name
        await self._log(logs.SISTEMA, "MANDO_IR_CREADO", detalle)

    @rx.event
    async def delete_ir_remote(self, remote_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.ir_remotes, remote_id)
        store.delete_ir_remote(remote_id)
        self._reload()
        await self._log(logs.SISTEMA, "MANDO_IR_ELIMINADO", nombre)

    @rx.event
    async def submit_edit_ir_remote(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        remote_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        icon = form_data.get("icon", "tv")
        show_on_floor = bool(form_data.get("show_on_floor"))
        floor_icon = form_data.get("floor_icon", "")
        if not remote_id or not name:
            return
        old = next((r for r in self.ir_remotes if r["id"] == remote_id), None)
        store.update_ir_remote(remote_id, name, icon, show_on_floor, floor_icon)
        self._reload()
        cambio = f"{old['name']} -> {name}" if old and old["name"] != name else name
        await self._log(logs.SISTEMA, "MANDO_IR_EDITADO", cambio)

    @rx.event(background=True)
    async def submit_learn_ir_button(self, form_data: dict):
        """"Añadir botón" del mando virtual: en vez de un formulario que solo
        guarda texto, pone el hub en modo aprendizaje y espera a que acerques
        el mando real y pulses — el código que capture ES el botón, no hay
        paso de escribir nada a mano.

        signal="ir" (por defecto) es un único paso (acercar + pulsar).
        signal="rf" (433/315MHz — típico de ventiladores de techo) son DOS
        pasos con instrucciones que cambian a mitad de aprendizaje (mantener
        pulsado para encontrar la frecuencia, soltar y pulsar breve para
        capturar) — de ahí el callback on_status en vez de un único mensaje
        fijo como en IR."""
        remote_id = form_data.get("remote_id", "")
        label = form_data.get("label", "").strip()
        icon = form_data.get("icon", "circle") or "circle"
        signal = form_data.get("signal", "ir")
        if not remote_id or not label:
            return

        async def _status(texto: str):
            async with self:
                infra = await self.get_state(InfraState)
                infra.status = texto
                self.ir_status = texto

        async with self:
            remote = next((r for r in self.ir_remotes if r["id"] == remote_id), None)
            if remote is None:
                return
            self.ir_learning = f"{remote_id}:{label}"
        primer_mensaje = (
            f"📡 Acerca el mando real y pulsa \"{label}\" (15s)..." if signal == "ir"
            else f"📡 Mantén PULSADO \"{label}\" en el mando real (buscando frecuencia)..."
        )
        await _status(primer_mensaje)
        try:
            if signal == "rf":
                codigo = await ir_bus.learn_rf_button(on_status=_status)
            else:
                codigo = await ir_bus.learn_button(timeout=15.0)
            await asyncio.to_thread(store.add_ir_button, remote_id, label, icon, codigo)
            msg = f"✅ Botón \"{label}\" aprendido en {remote['name']}"
            aprendido = True
        except TimeoutError as e:
            msg = f"⌛ {e}"
            aprendido = False
        except Exception as e:
            msg = f"❌ Error aprendiendo \"{label}\": {e}"
            aprendido = False
        async with self:
            self._reload()
            infra = await self.get_state(InfraState)
            infra.status = msg
            self.ir_status = msg
            self.ir_learning = ""
            if aprendido:
                await self._log(logs.SISTEMA, "MANDO_IR_BOTON_APRENDIDO", f"{remote['name']} · {label}")

    @rx.event
    async def submit_edit_ir_button(self, form_data: dict):
        """Solo renombra/cambia el icono — recapturar la señal es borrar el
        botón y volver a aprenderlo, no hay edición del código a mano."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        remote_id = form_data.get("remote_id", "")
        button_id = form_data.get("button_id", "")
        label = form_data.get("label", "").strip()
        icon = form_data.get("icon", "circle") or "circle"
        if not remote_id or not button_id or not label:
            return
        store.update_ir_button(remote_id, button_id, label, icon)
        self._reload()

    @rx.event
    async def delete_ir_button(self, remote_id: str, button_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        remote = next((r for r in self.ir_remotes if r["id"] == remote_id), None)
        label = next(
            (b["label"] for b in (remote or {}).get("buttons", []) if b["id"] == button_id), button_id,
        )
        store.delete_ir_button(remote_id, button_id)
        # OJO: aquí NO se reajusta el cuerpo. Se probó y estaba mal: recortar
        # el mando recoloca TODAS las teclas para que quepan en el tamaño
        # nuevo, así que borrar una movía de sitio a las demás. Borrar un
        # botón solo borra ese botón; el hueco se queda y el resto no se
        # entera. Recoger el mando es una acción aparte y a propósito
        # ("Ajustar tamaño", ver fit_remote_body).
        self._reload()
        detalle = f"{remote['name']} · {label}" if remote else label
        await self._log(logs.SISTEMA, "MANDO_IR_BOTON_ELIMINADO", detalle)

    async def _enviar_boton_ir(self, remote_id: str, button_id: str) -> None:
        """El envío en sí — cuerpo compartido de send_ir_button y
        send_ir_button_combined (no lleva @rx.event: es un manejador de fondo
        llamando a otro manejador de fondo directamente, y ese cruce es mejor
        evitarlo — mismo criterio que _alta_equipo/_edicion_equipo/_baja_equipo
        más abajo en este archivo).

        Dispara un botón — por infrarrojos (Broadlink) o por red (webOS de la
        TV LG) según su `kind`. Los botones que vienen de plantilla y todavía
        no tienen señal no hacen nada: lo dicen y ya.

        El envío vive en operations.send_remote_button, que resuelve la tecla
        contra el ALMACÉN y no contra self.ir_remotes. No es un detalle: esa
        Var es la copia decorada que arma _reload() en cada sesión, así que una
        tecla aprendida en otra pestaña no se podía disparar desde esta hasta
        recargar la página."""
        etiqueta = ""
        fallo = ""
        try:
            etiqueta = await operations.send_remote_button(remote_id, button_id)
            msg = f"📡 {etiqueta}"
        except operations.NotConfigured as e:
            async with self:
                self.ir_status = f"⚠️ {e}"
            return
        except operations.EntityNotFound:
            return
        except operations.OperationError as e:
            msg = f"❌ {e}"
            # El error ya trae dentro "Mando · Tecla" (ver operations), que es
            # lo único que identifica la pulsación cuando el envío no llegó a
            # devolver etiqueta.
            fallo = str(e)
        async with self:
            infra = await self.get_state(InfraState)
            infra.status = msg
            self.ir_status = msg
            if etiqueta:
                await self._log(logs.SISTEMA, "MANDO_IR_BOTON_ENVIADO", etiqueta)
            elif fallo:
                # Un envío que falla TAMBIÉN se apunta. Sin esto, un mando que
                # ha dejado de funcionar no deja ni una línea en el histórico y
                # el fallo solo se ve en la barra de estado de quien lo pulsó:
                # es lo que hizo que un hub inalcanzable pasara horas sin que
                # nada lo delatara.
                await self._log(logs.SISTEMA, "MANDO_IR_BOTON_FALLIDO", fallo)

    @rx.event(background=True)
    async def send_ir_button(self, remote_id: str, button_id: str):
        await self._enviar_boton_ir(remote_id, button_id)

    @rx.event(background=True)
    async def send_ir_button_combined(self, combined: str):
        """Mismo envío, para cuando mando y tecla llegan JUNTOS en un único
        valor "mando:tecla" — es como los guarda el widget de acceso rápido
        del Resumen (target_id compuesto, ver _build_widget_catalog). Partir
        el valor aquí, en Python, y no en el propio botón: un split(":") sobre
        un Var del frontend es más frágil que hacerlo donde ya se hace en todo
        el resto de la app."""
        remote_id, _, button_id = combined.partition(":")
        await self._enviar_boton_ir(remote_id, button_id)

    @rx.event
    def set_remote_layout_editing(self, remote_id: str):
        self.remote_layout_editing = remote_id

    # ── Editor de un botón concreto ──────────────────────────────────────
    @rx.event
    def open_button_editor(self, remote_id: str, button_id: str):
        remote = next((r for r in self.ir_remotes if r["id"] == remote_id), None)
        boton = next((b for b in (remote or {}).get("buttons", []) if b["id"] == button_id), None)
        if boton is None:
            return
        self.editing_button_remote = remote_id
        self.editing_button_id = button_id
        self.editing_button_label = boton.get("label", "")
        self.editing_button_icon = boton.get("icon") or "circle"
        self.editing_button_kind = boton.get("kind") or "ir"
        # Para un botón webOS, `code` es el comando (HOME, netflix...) y sí se
        # edita a mano; para uno de infrarrojos es la señal capturada, que no
        # se toca desde aquí — se re-aprende.
        self.editing_button_code = boton.get("code", "") if (boton.get("kind") == "webos") else ""

    @rx.event
    def close_button_editor(self):
        self.editing_button_remote = ""
        self.editing_button_id = ""
        self.ir_status = ""

    @rx.event
    def set_editing_button_label(self, valor: str):
        self.editing_button_label = valor

    @rx.event
    def set_editing_button_icon(self, valor: str):
        self.editing_button_icon = valor

    @rx.event
    def set_editing_button_kind(self, valor: str):
        self.editing_button_kind = valor

    @rx.event
    def set_editing_button_code(self, valor: str):
        self.editing_button_code = valor

    @rx.event
    async def save_button_editor(self):
        """Guarda nombre/icono, y para los botones de red también qué comando
        webOS ejecutan. La señal infrarroja NO se toca aquí: se re-aprende con
        learn_into_button."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.editing_button_id:
            return
        etiqueta = self.editing_button_label.strip()
        if not etiqueta:
            return
        kind = self.editing_button_kind
        store.update_ir_button(
            self.editing_button_remote, self.editing_button_id,
            etiqueta, self.editing_button_icon,
            kind=kind,
            # Cambiar un botón a "red" con un comando, o dejarlo en infrarrojos
            # sin tocarle la señal ya aprendida.
            code=self.editing_button_code.strip() if kind == "webos" else None,
        )
        self._reload()
        self.close_button_editor()

    @rx.event(background=True)
    async def learn_into_button(self, signal: str = "ir"):
        """(Re)aprende la señal del botón que tiene abierto el editor — es lo
        que rellena los botones que vienen de una plantilla, y lo que permite
        recapturar uno que salió mal. Mismo motor que submit_learn_ir_button,
        pero grabando sobre un botón que ya existe en vez de creando uno."""
        async with self:
            remote_id, button_id = self.editing_button_remote, self.editing_button_id
            etiqueta = self.editing_button_label.strip() or "este botón"
            if not button_id:
                return
            self.ir_learning = f"{remote_id}:{button_id}"

        async def _status(texto: str):
            async with self:
                self.ir_status = texto

        await _status(
            f'📡 Acerca el mando y pulsa "{etiqueta}" (15s)...' if signal == "ir"
            else f'📡 Mantén PULSADO "{etiqueta}" en el mando (buscando frecuencia)...'
        )
        try:
            if signal == "rf":
                codigo = await ir_bus.learn_rf_button(on_status=_status)
            else:
                codigo = await ir_bus.learn_button(timeout=15.0)
            await asyncio.to_thread(store.set_ir_button_code, remote_id, button_id, codigo)
            msg = f'✅ Señal de "{etiqueta}" aprendida'
            aprendido = True
        except TimeoutError as e:
            msg = f"⌛ {e}"
            aprendido = False
        except Exception as e:
            msg = f'❌ Error aprendiendo "{etiqueta}": {e}'
            aprendido = False
        async with self:
            self._reload()
            self.ir_status = msg
            self.ir_learning = ""
            if aprendido:
                self.editing_button_kind = "ir"
                await self._log(logs.SISTEMA, "MANDO_IR_BOTON_APRENDIDO", etiqueta)

    @rx.event
    async def save_ir_button_positions(self, payload: str):
        """Guarda de golpe TODOS los botones movidos en la sesión de "Colocar
        botones" — lo dispara el botón "Guardar disposición" (ver
        REMOTE_COMMIT_SCRIPT en ir_remotes.py), exactamente igual que
        save_floor_positions con el plano de planta.

        De qué mando son los botones NO viaja como argumento: sale de
        `remote_layout_editing`, que es quien tiene el modo edición abierto.
        Pasarlo como argumento desde la vista era el motivo de que no se
        guardara nada: el id venía del rx.foreach de los mandos, y esa
        variable de bucle no existe en el contexto donde Reflex serializa el
        callback de un call_script, así que llegaba vacío y no cuadraba con
        ningún mando.

        Salir del modo edición se hace aquí, al final, y no como segundo
        evento del botón: encadenado en la vista podía ejecutarse ANTES de que
        el navegador devolviera las posiciones, y entonces esto ya no sabía de
        qué mando eran."""
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        remote_id = self.remote_layout_editing
        self.remote_layout_editing = ""
        if not payload or not remote_id:
            return
        try:
            pendientes = json.loads(payload)
        except (ValueError, TypeError):
            return
        if not isinstance(pendientes, dict) or not pendientes:
            return
        # Lo que manda el navegador son % del cuerpo TAL Y COMO SE PINTA, que
        # es un recorte del cuerpo real (ver _recorte). Hay que deshacer ese
        # recorte antes de guardar, o cada arrastre movería la tecla a un
        # sitio distinto del que la has soltado.
        remote = next((r for r in self.ir_remotes if r["id"] == remote_id), None)
        if remote is None:
            return
        ancho = int(remote.get("body_w") or 250)
        alto = int(remote.get("body_h") or 850)
        origen_x, origen_y, vista_w, vista_h = _recorte(remote, ancho, alto)

        updates = []
        for button_id, pos in pendientes.items():
            if not isinstance(pos, dict) or not pos.get("top") or not pos.get("left"):
                continue
            x = origen_x + _pct(pos["left"], vista_w)
            y = origen_y + _pct(pos["top"], vista_h)
            updates.append({
                "id": button_id,
                "left": f"{x / ancho * 100:.3f}%",
                "top": f"{y / alto * 100:.3f}%",
            })
        if not updates:
            return
        store.set_ir_button_positions_bulk(remote_id, updates)
        # Sin reajuste de cuerpo: si al guardar se recortase el mando, cada
        # tecla acabaría en un sitio distinto del que acabas de dejarla.
        self._reload()

    @rx.var
    def ir_remotes_on_floor(self) -> list[dict]:
        return self._en_plano(self.ir_remotes)

    # ── Posición en el plano de planta (arrastrar un marcador) ───────────
    @rx.event
    async def save_floor_positions(self, payload: str):
        """Guarda de golpe TODAS las posiciones movidas en la sesión de
        edición del plano — lo dispara el botón "Listo" (ver floor_plan.py).

        `payload` es el JSON que trae el navegador: {id: {top, left}}. Se
        escribe todo en una única operación atómica, así que o queda guardada
        la recolocación entera o no queda nada: se acabó el "a veces sí y a
        veces no" de guardar marcador por marcador según llegase cada suelta."""
        if not payload:
            return
        try:
            pendientes = json.loads(payload)
        except (ValueError, TypeError):
            return
        if not isinstance(pendientes, dict):
            return
        await self._persistir_posiciones(pendientes)

    @rx.event
    async def set_floor_pos(self, entity_id: str, pos: str):
        """Compatibilidad con clientes que aún tengan cargado el JavaScript
        anterior — sobre todo la PWA instalada en el móvil, que mantiene su
        propia caché y no se refresca con un recargado normal.

        Hasta hace poco cada suelta de un marcador guardaba por su cuenta con
        este evento; ahora se guarda todo junto al pulsar "Listo"
        (save_floor_positions). Sin este handler, un solo dispositivo
        desactualizado lanza una excepción en el backend CADA VEZ que alguien
        arrastra un icono, y llena el journal de trazas. Aquí se atiende con
        la misma lógica, así que además sigue funcionándole bien."""
        if not pos or "|" not in pos:
            return
        top, left = pos.split("|", 1)
        await self._persistir_posiciones({entity_id: {"top": top, "left": left}})

    async def _persistir_posiciones(self, pendientes: dict):
        """Escribe en disco un lote de posiciones {id: {top, left}} en UNA
        sola operación atómica, venga de donde venga."""
        if not pendientes:
            return

        # El catálogo ya sabe de qué colección viene cada id (ref = "col:id").
        coleccion_de = {}
        for e in self.floor_catalog:
            col, eid = e["ref"].split(":", 1)
            coleccion_de[eid] = col

        cambios, de_fabrica = [], []
        for eid, pos in pendientes.items():
            col = coleccion_de.get(eid)
            if not col or not isinstance(pos, dict):
                continue
            top, left = pos.get("top"), pos.get("left")
            if not top or not left:
                continue
            cambios.append({"collection": col, "id": eid, "top": top,
                            "left": left, "plano": self.plano_actual})
            if col in ("factory_sensors", "factory_cameras"):
                de_fabrica.append((eid, top, left))
        if not cambios:
            return

        store.set_floor_positions_bulk(cambios)
        # Los de fábrica no viven en ninguna colección reactiva: hay que
        # refrescarles a mano lo que se pinta (el disco ya está escrito).
        if de_fabrica:
            reg_state = await self.get_state(RegistryState)
            for eid, top, left in de_fabrica:
                reg_state._reflect_factory_floor_pos(eid, top, left)
        self._reload()

    # ── Qué plano se está mirando ────────────────────────────────────────
    @rx.event
    async def ver_plano(self, plano_id: str):
        """Cambia de plano. Los de fábrica no viven en ninguna colección
        reactiva, así que hay que reconstruirles a mano sus posiciones para el
        plano nuevo (ver RegistryState.cargar_plano)."""
        if not any(p["id"] == plano_id for p in self.planos):
            return
        self.plano_actual = plano_id
        reg_state = await self.get_state(RegistryState)
        reg_state.cargar_plano(plano_id)

    def _en_plano(self, items: list[dict]) -> list[dict]:
        """Los elementos colocados en el plano que se está mirando, con
        floor_top/floor_left ya puestos a la posición de ESE plano.

        Se sustituyen los dos campos en vez de añadir otros nuevos justo para
        que los marcadores no cambien: siguen leyendo floor_top como siempre y no
        se enteran de que ahora hay más de un plano."""
        plano = self.plano_actual
        salida = []
        for item in items:
            sitio = (item.get("posiciones") or {}).get(plano)
            if not sitio:
                continue
            salida.append({**item, "floor_top": sitio["top"],
                           "floor_left": sitio["left"]})
        return salida

    @rx.event
    async def subir_plano(self, files: list[rx.UploadFile]):
        """Sube una imagen y la da de alta como plano nuevo.

        El nombre del plano sale del nombre del fichero ("Planta alta.png" ->
        "Planta alta"): es lo que la persona acaba de escribir al guardarlo, así
        que es mejor que pedirle que lo escriba otra vez. Se puede renombrar."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not files:
            return rx.toast.error("No llegó ningún fichero.",
                                  position="top-center")
        for file in files:
            datos = await file.read()
            # En el log, para poder distinguir «no llegó» de «llegó y falló»: el
            # primer intento de subir un plano no dejaba ni rastro y no había
            # forma de saber en qué lado estaba el problema.
            print(f"🗺️ Plano recibido: {file.name} ({len(datos)} bytes)")
            try:
                imagen, ancho, alto = planos.guardar(file.name, datos)
            except ValueError as e:
                return rx.toast.error(str(e), position="top-center")
            nuevo = store.add_plano(Path(file.name).stem, imagen, ancho, alto)
            await self._log(logs.SISTEMA, "PLANO_CREADO",
                            f"{nuevo['nombre']} · {ancho}x{alto}")
        self._reload()
        return rx.toast.success("Plano añadido.", position="top-center")

    @rx.event
    def plano_rechazado(self):
        """El navegador ni ha intentado subirlo. Pasa cuando el fichero no casa
        con el filtro de tipos, y sin esto no se entera nadie: se vuelve a abrir
        el selector de ficheros y parece que la aplicación no responde."""
        return rx.toast.error(
            "Ese fichero no lo acepta el navegador. Tiene que ser una imagen "
            "PNG, JPG o WebP de menos de 12 MB.",
            position="top-center", duration=8000,
        )

    @rx.event
    async def renombrar_plano(self, plano_id: str, nombre: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        actualizado = store.rename_plano(plano_id, nombre)
        self._reload()
        if actualizado:
            await self._log(logs.SISTEMA, "PLANO_EDITADO", actualizado["nombre"])

    @rx.event
    async def marcar_plano_principal(self, plano_id: str):
        """El principal es el que se abre por defecto, y el que refleja el
        espejo floor_top que sigue usando la vista clásica."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not store.set_plano_principal(plano_id):
            return
        nombre = next((p["nombre"] for p in self.planos if p["id"] == plano_id),
                      plano_id)
        self._reload()
        await self._log(logs.SISTEMA, "PLANO_PRINCIPAL_CAMBIADO", nombre)

    @rx.event
    async def borrar_plano(self, plano_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = next((p["nombre"] for p in self.planos if p["id"] == plano_id),
                      plano_id)
        imagen = store.delete_plano(plano_id)
        if not imagen:
            return rx.toast.error(
                "No se puede quitar el único plano que queda.",
                position="top-center")
        # La imagen se borra DESPUÉS de que el plano ya no esté guardado: si se
        # borrara antes y fallara la escritura, quedaría un plano apuntando a una
        # imagen que no existe.
        planos.borrar(imagen)
        self._reload()
        await self._log(logs.SISTEMA, "PLANO_ELIMINADO", nombre)

    @rx.event
    async def duplicar_desde_plano(self, ref: str, origen: str):
        """Trae a ESTE plano un elemento que ya está colocado en otro, en el
        mismo sitio que ocupaba allí.

        Es el caso de «tengo un plano general y otro por habitaciones», o de un
        contacto magnético en una puerta que comparten dos estancias: el mismo
        elemento tiene que salir en los dos planos, y cada uno con su posición
        independiente a partir de ahí."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        coleccion, _, entity_id = ref.partition(":")
        if not store.duplicar_en_plano(coleccion, entity_id, origen,
                                       self.plano_actual):
            return rx.toast.error("Ese elemento ya no está en el otro plano.",
                                  position="top-center")
        nombre = self._nombre_elemento(entity_id)
        self._reload()
        await self._log(logs.SISTEMA, "PLANO_ELEMENTO_DUPLICADO",
                        f"{nombre} · traído de "
                        f"{self._nombres_plano.get(origen, origen)}")
        return rx.toast.success(f"«{nombre}» copiado aquí, en el mismo sitio.",
                                position="top-center")

    @rx.event
    async def duplicar_a_plano(self, ref: str, destino: str):
        """Pone en otro plano un elemento que ya está en el actual, en el mismo
        sitio. `ref` es "<colección>:<id>" (ver _build_floor_catalog)."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        coleccion, _, entity_id = ref.partition(":")
        if not store.duplicar_en_plano(coleccion, entity_id, self.plano_actual,
                                      destino):
            return rx.toast.error("Ese elemento no está en este plano.",
                                  position="top-center")
        nombre_destino = next((p["nombre"] for p in self.planos
                               if p["id"] == destino), destino)
        self._reload()
        await self._log(logs.SISTEMA, "PLANO_ELEMENTO_DUPLICADO",
                        f"{self._nombre_elemento(entity_id)} · a {nombre_destino}")
        return rx.toast.success(f"Copiado a «{nombre_destino}».",
                                position="top-center")

    @rx.var
    def otros_planos(self) -> list[dict]:
        """Los planos que NO se están mirando — a los que se puede copiar algo."""
        return [{"id": p["id"], "nombre": p["nombre"]}
                for p in self.planos if p["id"] != self.plano_actual]

    @rx.var
    def planos_ui(self) -> list[dict]:
        """Las pestañas de planos, con todo en str para el rx.foreach."""
        return [
            {"id": p["id"], "nombre": p["nombre"],
             "activo": p["id"] == self.plano_actual,
             "principal": "1" if p.get("principal") else "",
             "elementos": str(self._elementos_por_plano.get(p["id"], 0)),
             # Preformateado: concatenar el valor de una clave de dict dentro de
             # un rx.foreach revienta el frontend en esta versión de Reflex.
             "elementos_texto": (
                 f"{self._elementos_por_plano.get(p['id'], 0)} elemento(s)")}
            for p in self.planos
        ]

    @rx.var
    def plano_imagen_url(self) -> str:
        """La imagen del plano actual, servida por /api/plano (no es un
        estático: ver domains/nodes/planos.py)."""
        actual = next((p for p in self.planos if p["id"] == self.plano_actual), None)
        imagen = (actual or {}).get("imagen", "")
        return f"/api/plano/{imagen}" if imagen else ""

    @rx.var
    def plano_aspecto(self) -> str:
        """La proporción del plano, para que las posiciones en tanto por ciento
        caigan siempre en el mismo punto del dibujo. Sin medidas conocidas se
        usa la cuadrada, que es la que tenía el plano de siempre."""
        actual = next((p for p in self.planos if p["id"] == self.plano_actual), None)
        ancho, alto = (actual or {}).get("ancho", 0), (actual or {}).get("alto", 0)
        return f"{ancho} / {alto}" if ancho and alto else "1 / 1"

    @rx.var
    def hay_varios_planos(self) -> bool:
        return len(self.planos) > 1

    @rx.var
    def sensors_on_floor(self) -> list[dict]:
        return [
            {**s, "is_open": self.sensor_state.get(s["id"], False)}
            for s in self._en_plano(self.sensors)
        ]

    @rx.var
    def cameras_on_floor(self) -> list[dict]:
        return self._en_plano(self.cameras)

    @rx.var
    def doors_on_floor(self) -> list[dict]:
        return self._en_plano(self.doors)

    @rx.var
    def lights_on_floor(self) -> list[dict]:
        """Cada luz lleva su "is_on" ya resuelto: el marcador del plano se
        pinta encendido/apagado sin tener que cruzar sensor_state en el
        frontend (mismo criterio que sensors_on_floor)."""
        return [
            {**l, "is_on": self.sensor_state.get(l["id"], False)}
            for l in self._en_plano(self.lights)
        ]

    # ── Equipos (todos, sin distinción de origen) ────────────────────────
    # Alta y edición comparten el mismo juego de campos y la misma
    # normalización (store.host_fields): un equipo dado de alta hoy queda
    # exactamente igual de completo que los que ya venían de antes.
    @staticmethod
    def _campos_equipo(form_data: dict) -> dict:
        return store.host_fields(
            name=form_data.get("name", ""),
            ip=form_data.get("ip", ""),
            # "ssh_user" es como se llamaba el campo en el formulario viejo:
            # un navegador con el JavaScript anterior en caché lo sigue
            # mandando así (ver los alias del final de esta sección).
            user=form_data.get("user", form_data.get("ssh_user", "")),
            rdp_user=form_data.get("rdp_user", ""),
            # El desplegable no puede ofrecer "" como valor (un rx.select con
            # opción vacía no se puede seleccionar), así que "navegador" es el
            # centinela de "ninguno" y aquí se traduce al vacío que se guarda.
            rdp_launch_host=(
                "" if form_data.get("rdp_launch_host", _SIN_LANZADOR) == _SIN_LANZADOR
                else form_data["rdp_launch_host"]
            ),
            sistema=form_data.get("os", "linux"),
            mac=form_data.get("mac", ""),
            ping_retries=form_data.get("ping_retries", 1),
            icon=form_data.get("icon", "server"),
        )

    # Los tres siguientes DEVUELVEN lo que diga permisos.denegar para que el
    # manejador lo propague: son el único sitio por el que pasan los seis
    # puntos de entrada (los tres eventos y sus tres alias antiguos), así que
    # comprobar aquí cierra todos a la vez.
    async def _alta_equipo(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        campos = self._campos_equipo(form_data)
        if not campos["name"] or not campos["ip"]:
            return
        nuevo = store.add_host(**campos)
        # DEVICES se construye al importar el registry: sin esto el equipo
        # recién creado no existiría para el ping ni para la consola SSH hasta
        # el siguiente arranque.
        registry.sync_host(nuevo)
        # "También es nodo" (ESP32/Raspberry) — lo damos de alta a la vez en
        # Alarma sin que haga falta repetir nombre/IP dos veces.
        if form_data.get("es_nodo"):
            node_kind = form_data.get("node_kind", "esp32")
            store.add_node(campos["name"], campos["ip"], node_kind,
                           campos["user"] if node_kind == "ssh" else "")
        self._reload()
        await self._log(logs.EQUIPOS, "EQUIPO_CREADO",
                        f"{campos['name']} · {campos['ip']} · {campos['os']}")

    async def _edicion_equipo(self, form_data: dict):
        # Reapuntar un equipo cambia su IP y su destino SSH: solo AJUSTES.
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        host_id = form_data.get("entity_id", "")
        campos = self._campos_equipo(form_data)
        if not host_id or not campos["name"] or not campos["ip"]:
            return
        anterior = self._nombre(self.hosts, host_id)
        actualizado = store.update_host(host_id, **campos)
        if actualizado is not None:
            registry.sync_host(actualizado)
        self._reload()
        cambio = f"{anterior} -> {campos['name']}" if anterior != campos["name"] else campos["name"]
        await self._log(logs.EQUIPOS, "EQUIPO_EDITADO",
                        f"{cambio} · {campos['ip']} · {campos['os']}")

    async def _baja_equipo(self, host_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._nombre(self.hosts, host_id)
        store.delete_host(host_id)
        registry.forget_host(host_id)
        self._reload()
        await self._log(logs.EQUIPOS, "EQUIPO_ELIMINADO", nombre)

    @rx.event
    async def submit_add_host(self, form_data: dict):
        return await self._alta_equipo(form_data)

    @rx.event
    async def submit_edit_host(self, form_data: dict):
        return await self._edicion_equipo(form_data)

    @rx.event
    async def delete_host(self, host_id: str):
        return await self._baja_equipo(host_id)

    @rx.event
    async def move_host_up(self, host_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.move_host(host_id, -1)
        self._reload()

    @rx.event
    async def move_host_down(self, host_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.move_host(host_id, 1)
        self._reload()

    # ── Alias de los nombres anteriores a unificar los equipos ────────────
    # Un navegador (o la PWA del móvil) con el JavaScript viejo en caché sigue
    # mandando estos nombres de evento. Sin estos alias, Reflex responde con
    # KeyError, el evento muere sin contestar y el cliente se queda esperando
    # para siempre: eso es lo que se veía como "la UI se congela al añadir un
    # equipo". Recargando se arregla, pero un cliente desactualizado no debe
    # poder tumbar el backend, así que aquí se le atiende igual.
    @rx.event
    async def submit_add_custom_host(self, form_data: dict):
        return await self._alta_equipo(form_data)

    @rx.event
    async def submit_edit_custom_host(self, form_data: dict):
        return await self._edicion_equipo(form_data)

    @rx.event
    async def delete_custom_host(self, host_id: str):
        return await self._baja_equipo(host_id)

    # ── Widgets del Resumen (pestaña "Resumen" completamente configurable) ──
    # A qué apunta cada clase de widget y cómo se nombra vive en
    # referencias.WIDGET_TARGET / referencias.etiqueta_widget, junto a lo que
    # después mantiene esos nombres al día. Tenerlo en dos sitios era lo que
    # hacía que un widget se quedase con un nombre y el elemento con otro.

    @rx.event
    def refresh_widget_catalog(self, is_open: bool = True):
        """Relee el disco al ABRIR el diálogo de "Añadir widget".

        Dentro de una misma pestaña el catálogo ya se rehace en cada _reload()
        (o sea, en cada alta/baja/edición), así que esto es para lo que esa
        sesión no se entera: lo que se haya dado de alta o borrado desde otra
        pestaña, otro dispositivo o la vista clásica. Así el desplegable ofrece
        siempre lo que existe en ese instante, sin recargar la página. Lo llama
        on_open_change, que pasa si el diálogo queda abierto o cerrado — al
        cerrarlo no hay nada que releer.

        Rehace SOLO el catálogo, no el _reload() entero. Recargarlo todo
        reasignaba de golpe una docena de Vars que la portada está pintando
        (equipos, sensores, luces, el plano...), y ese repintado en el momento
        justo de abrir el desplegable contribuía a que se comportase de forma
        errática. Aquí lo único que puede haber cambiado es el catálogo."""
        if is_open:
            self.widget_catalog = _build_widget_catalog(store.read_all())
        else:
            self.widget_query = ""

    widget_query: str = ""

    @rx.event
    def set_widget_query(self, texto: str):
        self.widget_query = texto

    @rx.var
    def widget_catalog_filtrado(self) -> list[dict]:
        """El catálogo pasado por el buscador del selector. Filtrar aquí, en
        Python, y no en el frontend: comparar cadenas dentro de un rx.foreach
        obliga a condicionales anidados que no hay quien lea."""
        busca = self.widget_query.strip().lower()
        if not busca:
            return self.widget_catalog
        salida = []
        for seccion in self.widget_catalog:
            opciones = [o for o in seccion["options"]
                        if busca in o["label"].lower() or busca in seccion["label"].lower()]
            if opciones:
                salida.append({**seccion, "options": opciones})
        return salida

    @rx.event
    def add_widget_desde_selector(self, valor: str):
        """El selector devuelve el "<kind>:<target_id>" de siempre; se
        reutiliza el alta que ya existía en vez de duplicarla."""
        self.widget_picker_open = False
        return NodesState.submit_add_widget({"widget": valor})

    widget_picker_open: bool = False

    @rx.event
    def open_widget_picker(self):
        self.widget_query = ""
        self.widget_catalog = _build_widget_catalog(store.read_all())
        self.widget_picker_open = True

    @rx.event
    def close_widget_picker(self):
        self.widget_picker_open = False

    @rx.event
    def widget_picker_open_change(self, abierto: bool):
        """Escape y el clic fuera del diálogo llegan por aquí."""
        if not abierto:
            self.widget_picker_open = False

    @rx.event
    async def submit_add_widget(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        raw = form_data.get("widget", "")
        if ":" not in raw:
            return
        kind, target_id = raw.split(":", 1)
        # El nombre y el icono los resuelve referencias.py, que es el mismo
        # sitio que después los mantiene al día. Antes se calculaban aquí con
        # un if por familia, y ese era justo el motivo de que un widget se
        # quedase con el nombre del día que se añadió: nadie volvía a pasar por
        # este código al renombrar el elemento.
        label, icon = referencias.etiqueta_widget(kind, target_id)
        store.add_widget(kind, target_id, label, icon)
        self._reload()
        await self._log(logs.SISTEMA, "WIDGET_AÑADIDO", f"{kind} · {label or target_id}")

    @rx.event
    async def delete_widget(self, widget_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        widget = next((w for w in self.widgets if w["id"] == widget_id), None)
        store.delete_widget(widget_id)
        self._reload()
        await self._log(logs.SISTEMA, "WIDGET_QUITADO",
                        f"{widget['kind']} · {widget.get('label') or ''}" if widget else widget_id)

    @rx.event
    async def move_widget_left(self, widget_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.move_widget(widget_id, -1)
        self._reload()

    @rx.event
    async def move_widget_right(self, widget_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.move_widget(widget_id, 1)
        self._reload()
