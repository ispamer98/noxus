"""
Alta de hardware en caliente, desde la propia web — nodos ESP32, sus
sensores/relés, puertas, luces, cámaras extra y equipos a monitorizar por
IP. Mismo patrón de persistencia que logs.py/shared_state.py (JSON plano con
lock de fichero), pero aquí es CRUD genérico en vez de campos fijos, porque
el conjunto de entidades lo decide el usuario en tiempo de ejecución, no el
código.

Convenio de topics MQTT (mismo estilo que devices/registry.py: casa/<host>/<sensor>,
ej. casa/raspberry/puerta, casa/pizero/tamper1):
  - Un sensor (magnético/PIR) publica su estado en   casa/{nombre-del-nodo}/{señal}
  - Una puerta/luz se ordena publicando ON/OFF en    casa/{nombre-del-nodo}/{señal}/set
El "nombre-del-nodo" es el nombre del nodo tal cual se le puso al darlo de
alta, pasado a slug (minúsculas, sin espacios/acentos) — NO su id interno —
así el ESP32 solo necesita saber su propio nombre y el nombre de cada señal
que publica/escucha, exactamente igual que ya hacen la Raspberry/Pi Zero.
"""
import fcntl
import json
import os
import re
import time
import unicodedata
import uuid
from pathlib import Path

ARCHIVO = Path(os.getenv("NODOS_FILE", "nodos_dinamicos.json"))

_COLLECTIONS = (
    "nodes", "sensors", "doors", "lights", "cameras", "hosts", "host_buttons", "rooms",
    "factory_sensors", "factory_cameras", "overview_widgets", "ir_remotes",
)

# Sistemas operativos que sabe manejar ssh_bus (apagar/reiniciar cambian de
# comando según cuál sea) — cualquier otro valor se trata como linux.
SISTEMAS = ("linux", "windows")

# La ficha de un equipo, campo a campo y en este orden. TODOS los equipos se
# reescriben con exactamente estas claves (ver _normalizar_equipos): el que
# venía de fábrica y el que se añadió hace un minuto son el mismo objeto, con
# la misma forma, y así se ven también al abrir nodos_dinamicos.json a mano.
# "acciones_extra" va al final porque es la única lista, y suele estar vacía.
CLAVES_EQUIPO = (
    "id", "created_at", "name", "ip", "user", "rdp_user", "rdp_launch_host",
    "os", "mac", "ping_retries", "icon", "order", "acciones_extra",
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _migrar_equipos(data: dict) -> None:
    """factory_hosts + custom_hosts -> hosts (UNA sola colección).

    Antes había dos clases de equipo con campos distintos: los "de fábrica"
    (server, pc, raspberry, iphone...) con usuario/os/mac/reintentos, y los
    añadidos desde la web, que solo tenían nombre/ip/icono/ssh_user. Eso hacía
    que la misma pantalla ofreciese formularios distintos según de dónde
    viniera el equipo, y que los de fábrica se pintasen desde Python (había que
    reiniciar para ver una edición) mientras los otros eran reactivos.

    Ahora todos son la misma cosa. La fusión conserva los ids literales
    (raspberry, pi_zero... están referenciados por id en grupos_armado.json,
    en los niveles de acceso y en el node_id de cada sensor) y renombra
    ssh_user -> user, que era el mismo dato con dos nombres. Es idempotente:
    tras la primera lectura ya no quedan las claves viejas que migrar."""
    if "factory_hosts" not in data and "custom_hosts" not in data:
        return
    fusion = list(data.get("hosts", []))
    vistos = {h.get("id") for h in fusion}
    for host in data.pop("factory_hosts", []) + data.pop("custom_hosts", []):
        if host.get("id") in vistos:
            continue
        vistos.add(host.get("id"))
        if "ssh_user" in host:
            host["user"] = host.pop("ssh_user")
        fusion.append(host)
    data["hosts"] = fusion


def _normalizar_equipos(data: dict) -> None:
    """Deja TODOS los equipos con exactamente las mismas claves, en el mismo
    orden y con los mismos tipos — da igual de dónde vinieran. Se ejecuta en
    cada lectura y dentro de cada escritura, así que no hay forma de que un
    equipo acabe con una forma distinta de la de sus vecinos.

    Aquí es también donde el usuario SSH se recorta: " " no es un usuario,
    es un campo vacío con un espacio dentro. Sin esto bool(" ") vale True y el
    equipo se anunciaba como accionable por SSH — con la bandera puesta y
    fallando cualquier conexión, porque detrás no había ningún usuario."""
    normalizados = []
    for i, host in enumerate(data["hosts"]):
        limpio = {
            "id": host.get("id", ""),
            "created_at": host.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": (host.get("name") or "").strip(),
            "ip": (host.get("ip") or "").strip(),
            "user": (host.get("user") or "").strip(),
            "rdp_user": (host.get("rdp_user") or "").strip(),
            "rdp_launch_host": (host.get("rdp_launch_host") or "").strip(),
            "os": host["os"] if host.get("os") in SISTEMAS else "linux",
            "mac": (host.get("mac") or "").strip() or None,
            "ping_retries": _entero(host.get("ping_retries"), por_defecto=1, minimo=1),
            "icon": host.get("icon") or "server",
            # El orden lo fija el usuario desde la pestaña Equipos; si falta
            # (fichero de antes de que se pudiera ordenar) se toma el orden
            # actual del fichero, que es justo como se venían pintando.
            "order": _entero(host.get("order"), por_defecto=i, minimo=0),
            "acciones_extra": host.get("acciones_extra") or [],
        }
        normalizados.append(limpio)
    normalizados.sort(key=lambda h: h["order"])
    # Se reasigna 0..N-1 para que el orden guardado no acumule huecos ni
    # empates al borrar equipos o al moverlos muchas veces.
    for posicion, host in enumerate(normalizados):
        host["order"] = posicion
    data["hosts"] = normalizados


def _entero(valor, por_defecto: int, minimo: int) -> int:
    try:
        return max(minimo, int(valor))
    except (TypeError, ValueError):
        return por_defecto


def _apply_defaults(data: dict) -> dict:
    """Rellena colecciones y campos que puedan faltar (ficheros de versiones
    anteriores del programa). Se aplica tanto al leer como dentro de _mutate,
    para que ambos caminos vean siempre la misma forma."""
    _migrar_equipos(data)
    for k in _COLLECTIONS:
        data.setdefault(k, [])
    data.setdefault("sensor_states", {})
    data.setdefault("host_online", {})
    vw = data.get("video_wall")
    if not isinstance(vw, dict):
        vw = {}
        data["video_wall"] = vw
    vw.setdefault("layout", "4")
    if not isinstance(vw.get("slots"), dict):
        vw["slots"] = {}
    for node in data["nodes"]:
        node.setdefault("kind", "esp32")
        node.setdefault("user", "")
    for cam in data["cameras"]:
        cam.setdefault("kind", "embed")
    for sensor in data["sensors"]:
        sensor.setdefault("isolated", False)
        sensor.setdefault("floor_top", None)
        sensor.setdefault("floor_left", None)
        sensor.setdefault("floor_icon", None)
        sensor.setdefault("floor_subtle", False)
        sensor.setdefault("floor_color", None)
    for door in data["doors"]:
        door.setdefault("pulse_seconds", 2)
        door.setdefault("floor_top", None)
        door.setdefault("floor_left", None)
        door.setdefault("floor_icon", None)
        door.setdefault("floor_subtle", False)
        door.setdefault("floor_color", None)
    for light in data["lights"]:
        light.setdefault("room_id", "")
        light.setdefault("floor_top", None)
        light.setdefault("floor_left", None)
        light.setdefault("floor_icon", None)
        light.setdefault("floor_subtle", False)
        light.setdefault("floor_color", None)
    # Una luz que apunte a una estancia que ya no existe pasa a "sin estancia".
    # delete_room ya lo deja así, pero esto recupera además las que quedaron
    # huérfanas antes (y las que pueda dejar cualquier edición a mano del
    # fichero): con un room_id fantasma la luz no salía ni en su estancia ni en
    # "sin estancia", así que parecía borrada aunque siguiera aquí.
    ids_estancias = {r.get("id") for r in data["rooms"]}
    for light in data["lights"]:
        if light["room_id"] and light["room_id"] not in ids_estancias:
            light["room_id"] = ""
    for cam in data["cameras"]:
        cam.setdefault("floor_top", None)
        cam.setdefault("floor_left", None)
        cam.setdefault("floor_icon", None)
        cam.setdefault("floor_subtle", False)
        cam.setdefault("floor_color", None)
    _normalizar_equipos(data)
    for sensor in data["factory_sensors"]:
        sensor.setdefault("isolated", False)
        sensor.setdefault("floor_top", None)
        sensor.setdefault("floor_left", None)
        sensor.setdefault("floor_icon", None)
        sensor.setdefault("floor_subtle", False)
        sensor.setdefault("floor_color", None)
    for cam in data["factory_cameras"]:
        cam.setdefault("tuya_device_id", None)
        cam.setdefault("has_ptz", False)
        cam.setdefault("icon", None)
        cam.setdefault("floor_top", None)
        cam.setdefault("floor_left", None)
        cam.setdefault("floor_icon", None)
        cam.setdefault("floor_subtle", False)
        cam.setdefault("floor_color", None)
    for remote in data["ir_remotes"]:
        remote.setdefault("icon", "tv")
        remote.setdefault("buttons", [])
        remote.setdefault("groups", [])
        # Mandos de antes de que el cuerpo fuera configurable: los que se
        # montaron a mano usaban el vertical, que es el que se les queda.
        remote.setdefault("body_w", 250)
        remote.setdefault("body_h", 850)
        remote.setdefault("floor_top", None)
        remote.setdefault("floor_left", None)
        remote.setdefault("floor_icon", None)
        remote.setdefault("floor_subtle", False)
        remote.setdefault("floor_color", None)
        for boton in remote["buttons"]:
            # Botones de antes de que existieran las plantillas: todos eran
            # infrarrojos y todos tenían señal, así que ese es el valor que les
            # corresponde.
            boton.setdefault("kind", "ir")
            boton.setdefault("code", "")
            # Rótulo impreso en la tecla (los números) y tinte de color (las
            # cuatro teclas de color de la TV) — ver remote_templates.py.
            boton.setdefault("text", "")
            boton.setdefault("color", "")
            # Tamaño del icono dentro de la tecla: los pares "más/menos" del
            # mando (los dos soles de la luz, las dos aspas de la velocidad)
            # solo se distinguen por eso.
            boton.setdefault("icon_size", "46%")
        _asegurar_posiciones(remote)
    return data


def _read() -> dict:
    if not ARCHIVO.exists():
        return _apply_defaults({})
    try:
        with open(ARCHIVO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read().strip()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        data = json.loads(content) if content else {}
    except Exception:
        data = {}
    return _apply_defaults(data)


def _mutate(mutator):
    """Ciclo leer-modificar-escribir ATÓMICO: el cerrojo exclusivo se mantiene
    durante TODO el ciclo, no solo durante la lectura y luego durante la
    escritura por separado.

    Sin esto se pierden escrituras, y de forma intermitente: como cada
    operación reescribe el fichero ENTERO, si entre el _read() y el _write()
    de una (p.ej. guardar la posición de un icono del plano) se cuela otra
    (set_sensor_state, que dispara con cada mensaje MQTT, o
    set_host_online_bulk cada 10s), la que escribe última machaca los cambios
    de la otra. Medido antes de este arreglo: 8 de 60 posiciones perdidas con
    un escritor concurrente."""
    with open(ARCHIVO, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read().strip()
            try:
                data = json.loads(content) if content else {}
            except Exception:
                data = {}
            _apply_defaults(data)
            result = mutator(data)
            # Otra vez DESPUÉS de mutar: lo que acabe de tocar el mutador (un
            # equipo recién añadido, un `order` intercambiado) queda con la
            # forma canónica ya en esta misma escritura, no en la siguiente.
            # Es idempotente, así que pasarlo dos veces no cambia nada más.
            _apply_defaults(data)
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return result


def _write(data: dict) -> None:
    with open(ARCHIVO, "a+" if ARCHIVO.exists() else "w+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_all() -> dict:
    return _read()


def slugify(texto: str) -> str:
    """"Nodo Garaje" -> "nodo_garaje" — mismo estilo que los slugs ya usados a
    mano en registry.py (raspberry, pizero)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_") or "nodo"


def sensor_topic(node_name: str, pin: str) -> str:
    return f"casa/{slugify(node_name)}/{pin}"


def command_topic(node_name: str, pin: str) -> str:
    return f"casa/{slugify(node_name)}/{pin}/set"


def _add(collection: str, prefix: str, item: dict) -> dict:
    nuevo = {"id": _new_id(prefix), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"), **item}

    def _apply(data):
        data[collection].append(nuevo)
        return nuevo

    return _mutate(_apply)


def _add_with_id(collection: str, item: dict) -> dict:
    """Igual que _add pero conservando el id tal cual viene en `item` — solo
    para la migración de entidades "de fábrica" (puerta_ppal, tamper1,
    raspberry...), que deben mantener su id literal de siempre porque ya
    están referenciadas por ese id en grupos_armado.json y en niveles de
    acceso. No usar para altas normales desde la UI (esas sí generan un id
    nuevo con _add)."""
    def _apply(data):
        existente = next((x for x in data[collection] if x.get("id") == item["id"]), None)
        if existente is not None:
            return existente
        nuevo = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"), **item}
        data[collection].append(nuevo)
        return nuevo

    return _mutate(_apply)


def _delete(collection: str, item_id: str) -> None:
    def _apply(data):
        data[collection] = [x for x in data[collection] if x.get("id") != item_id]

    _mutate(_apply)


def _update(collection: str, item_id: str, fields: dict) -> dict | None:
    def _apply(data):
        updated = None
        for item in data[collection]:
            if item["id"] == item_id:
                item.update(fields)
                updated = item
        return updated

    return _mutate(_apply)


# ── Nodos ────────────────────────────────────────────────────────────────────
# kind="esp32" (por defecto): se actúa/lee por MQTT, como cualquier ESP32.
# kind="ssh": es un equipo tipo Raspberry más — se actúa por SSH+raspi-gpio
# igual que la Raspberry/Pi Zero fijas del registry, pero dado de alta desde
# la web en vez de hardcodeado. `user` solo se usa cuando kind="ssh".
def add_node(name: str, ip: str, kind: str = "esp32", user: str = "") -> dict:
    return _add("nodes", "node", {"name": name, "ip": ip, "kind": kind, "user": user})


def delete_node(node_id: str) -> None:
    _delete("nodes", node_id)


def update_node(node_id: str, name: str, ip: str, kind: str = "esp32", user: str = "") -> dict | None:
    return _update("nodes", node_id, {"name": name, "ip": ip, "kind": kind, "user": user})


# ── Posición en el plano de planta (room.png) ────────────────────────────────
# Cualquier sensor o cámara (de fábrica o añadido desde la web) puede
# mostrarse en el plano — floor_top/floor_left en None significa "no se
# muestra". floor_fields() traduce el toggle "mostrar en el plano" + icono
# elegido del formulario de edición a los campos de storage; el arrastre en
# el propio plano usa set_floor_position() directamente (ver device_list.py).
_FLOOR_DEFAULT_POS = {"floor_top": "50%", "floor_left": "50%"}


def floor_fields(show_on_floor: bool, floor_icon: str, current: dict | None) -> dict:
    if not show_on_floor:
        return {"floor_top": None, "floor_left": None, "floor_icon": floor_icon or None}
    fields = {"floor_icon": floor_icon or None}
    if not current or not current.get("floor_top"):
        fields.update(_FLOOR_DEFAULT_POS)
    return fields


def set_floor_position(collection: str, entity_id: str, top: str, left: str) -> dict | None:
    """Persiste la posición (%) de un marcador tras arrastrarlo — genérico
    para cualquier colección con floor_top/floor_left."""
    return _update(collection, entity_id, {"floor_top": top, "floor_left": left})


def set_floor_positions_bulk(updates: list[dict]) -> None:
    """Guarda de una sola vez la posición de VARIOS marcadores — es lo que usa
    el botón "Listo" del editor del plano, que se trae toda la sesión de
    recolocar iconos junta. Al ir en un único _mutate, o se guardan todas o no
    se guarda ninguna: no puede quedar media recolocación a medias.

    Cada entrada: {"collection": ..., "id": ..., "top": ..., "left": ...}."""
    def _apply(data):
        por_coleccion: dict[str, dict] = {}
        for u in updates:
            por_coleccion.setdefault(u["collection"], {})[u["id"]] = u
        for collection, pendientes in por_coleccion.items():
            for item in data.get(collection, []):
                u = pendientes.get(item.get("id"))
                if u:
                    item["floor_top"] = u["top"]
                    item["floor_left"] = u["left"]

    _mutate(_apply)


def clear_floor_position(collection: str, entity_id: str) -> dict | None:
    """Quita el elemento del plano (deja de pintarse) sin tocar nada más de
    su configuración — floor_top a None es lo que significa "no se muestra"."""
    return _update(collection, entity_id, {"floor_top": None, "floor_left": None})


def set_floor_icon(collection: str, entity_id: str, icon: str) -> dict | None:
    return _update(collection, entity_id, {"floor_icon": icon or None})


def set_floor_color(collection: str, entity_id: str, color: str) -> dict | None:
    """Color EN REPOSO del marcador. El estado activo (abierto/alarma) sigue
    mandando siempre en rojo, así que cambiar esto no oculta nunca una
    alerta — solo decide de qué color se ve cuando todo está en orden."""
    return _update(collection, entity_id, {"floor_color": color or None})


def toggle_floor_subtle(collection: str, entity_id: str) -> bool:
    """Alterna el modo "discreto" de un marcador: se pinta pequeño y atenuado,
    para elementos que interesa tener localizados pero que no deben robar
    atención (un tamper, por ejemplo). Devuelve el estado resultante."""
    def _apply(data):
        for item in data.get(collection, []):
            if item.get("id") == entity_id:
                item["floor_subtle"] = not item.get("floor_subtle", False)
                return item["floor_subtle"]
        return False

    return _mutate(_apply)


# ── Sensores (magnético / PIR / tamper) ──────────────────────────────────────
# node_name se guarda duplicado (además de node_id) para poder pintar "Nodo:
# X" en la UI sin tener que cruzar listas con un Var reactivo — si el nodo se
# renombra más tarde, las entidades ya creadas se quedan con el nombre viejo.
def add_sensor(name: str, kind: str, node_id: str, node_name: str, pin: str,
               show_on_floor: bool = False, floor_icon: str = "") -> dict:
    item = {
        "name": name, "kind": kind, "node_id": node_id, "node_name": node_name,
        "pin": pin, "topic": sensor_topic(node_name, pin),
        "isolated": False,
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("sensors", "sensor", item)


def delete_sensor(sensor_id: str) -> None:
    _delete("sensors", sensor_id)


def update_sensor(sensor_id: str, name: str, kind: str, node_id: str, node_name: str, pin: str,
                   show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((s for s in _read()["sensors"] if s["id"] == sensor_id), None)
    return _update("sensors", sensor_id, {
        "name": name, "kind": kind, "node_id": node_id, "node_name": node_name,
        "pin": pin, "topic": sensor_topic(node_name, pin),
        **floor_fields(show_on_floor, floor_icon, current),
    })


def toggle_sensor_isolated(sensor_id: str) -> dict | None:
    def _apply(data):
        updated = None
        for s in data["sensors"]:
            if s["id"] == sensor_id:
                s["isolated"] = not s.get("isolated", False)
                updated = s
        return updated

    return _mutate(_apply)


# ── Puertas / cerraduras ─────────────────────────────────────────────────────
# topic_state es opcional de usar por el firmware (confirmación de estado real
# del relé); topic_cmd es donde el sistema publica ON/OFF para actuar.
# pulse_seconds: duración del pulso de "Abrir" antes de cerrarse solo — definible
# por puerta (2, 3, 4, 5s...) en vez de fijo en el código.
def add_door(name: str, node_id: str, node_name: str, pin: str, pulse_seconds: int = 2,
             show_on_floor: bool = False, floor_icon: str = "") -> dict:
    item = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "pulse_seconds": pulse_seconds,
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("doors", "door", item)


def delete_door(door_id: str) -> None:
    _delete("doors", door_id)


def update_door(door_id: str, name: str, node_id: str, node_name: str, pin: str, pulse_seconds: int = 2,
                show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((d for d in _read()["doors"] if d["id"] == door_id), None)
    return _update("doors", door_id, {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "pulse_seconds": pulse_seconds,
        **floor_fields(show_on_floor, floor_icon, current),
    })


# ── Luces ─────────────────────────────────────────────────────────────────────
# room_id agrupa las luces por estancia (ver add_room/list_rooms más abajo) —
# opcional, "" significa "sin estancia asignada".
def add_light(name: str, node_id: str, node_name: str, pin: str, room_id: str = "",
              show_on_floor: bool = False, floor_icon: str = "") -> dict:
    item = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "room_id": room_id,
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("lights", "light", item)


def delete_light(light_id: str) -> None:
    _delete("lights", light_id)


def update_light(light_id: str, name: str, node_id: str, node_name: str, pin: str, room_id: str = "",
                 show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((l for l in _read()["lights"] if l["id"] == light_id), None)
    return _update("lights", light_id, {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "room_id": room_id,
        **floor_fields(show_on_floor, floor_icon, current),
    })


# ── Estancias (agrupación de luces) ──────────────────────────────────────────
def list_rooms() -> list[dict]:
    return _read()["rooms"]


def add_room(name: str) -> dict:
    return _add("rooms", "room", {"name": name})


def delete_room(room_id: str) -> None:
    """Borrar una estancia NO borra sus luces: se quedan sin estancia y pasan
    al bloque "SIN ESTANCIA" de la pestaña Luces.

    El barrido del room_id va en la MISMA mutación que la baja de la estancia
    (un solo _mutate) para que no pueda quedar a medias. Sin él, las luces
    seguían apuntando a una estancia que ya no existía: no se borraban del
    fichero, pero tampoco se pintaban en ningún sitio —ni en su estancia, que
    ya no estaba, ni en "sin estancia", porque su room_id no estaba vacío—,
    así que desaparecían de la vista sin haberse borrado."""
    def _apply(data):
        data["rooms"] = [r for r in data["rooms"] if r.get("id") != room_id]
        for light in data["lights"]:
            if light.get("room_id") == room_id:
                light["room_id"] = ""

    _mutate(_apply)


# ── Cámaras extra (URL directa, sin go2rtc/Tuya) ─────────────────────────────
def add_camera(name: str, url: str, icon: str, kind: str = "embed") -> dict:
    return _add("cameras", "cam", {"name": name, "url": url, "icon": icon, "kind": kind})


def delete_camera(camera_id: str) -> None:
    _delete("cameras", camera_id)


def update_camera(camera_id: str, name: str, url: str, icon: str, kind: str = "embed",
                   show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((c for c in _read()["cameras"] if c["id"] == camera_id), None)
    return _update("cameras", camera_id, {
        "name": name, "url": url, "icon": icon, "kind": kind,
        **floor_fields(show_on_floor, floor_icon, current),
    })


# ── Equipos (TODOS: los de siempre y los añadidos desde la web) ──────────────
# Una sola colección y un solo juego de campos, para que la pestaña Equipos
# pueda tratarlos a todos igual — mismo formulario de alta que de edición, y
# lo mismo para un equipo de hace un año que para uno dado de alta hace un
# minuto. user="" significa "solo ping, sin consola ni acciones SSH".
def host_fields(name: str, ip: str, user: str = "", sistema: str = "linux",
                mac: str = "", ping_retries: str | int = 1, icon: str = "server",
                rdp_user: str = "", rdp_launch_host: str = "") -> dict:
    """Normaliza en un único sitio lo que llega de CUALQUIER formulario de
    equipo. Que el alta y la edición pasen las dos por aquí es lo que impide
    que se cuele un usuario con espacios (" " no es un usuario) o unos
    reintentos de ping en 0, que dejaría al equipo sin comprobar nunca."""
    try:
        reintentos = max(1, int(ping_retries or 1))
    except (TypeError, ValueError):
        reintentos = 1
    return {
        "name": name.strip(),
        "ip": ip.strip(),
        "user": user.strip(),
        # Cuenta con la que entra el escritorio remoto. Es OTRA cosa que el
        # usuario SSH: en el PC de casa el SSH va con "ruben" y el RDP puede
        # ser la sesión de otra persona.
        "rdp_user": rdp_user.strip(),
        # Desde QUÉ equipo se abre la sesión remota. Vacío = desde el navegador
        # de quien pulsa (se le pasa la dirección al sistema o se le baja el
        # .rdp). Con un id de equipo puesto, el servidor entra por SSH a ESE
        # equipo y abre allí el cliente — ver domains/nodes/rdp.py.
        "rdp_launch_host": rdp_launch_host.strip(),
        "os": sistema if sistema in SISTEMAS else "linux",
        "mac": (mac or "").strip() or None,
        "ping_retries": reintentos,
        "icon": icon or "server",
    }


def mutar(mutator):
    """Ciclo leer-modificar-escribir atómico, para quien necesite tocar varias
    colecciones de una vez (ver nodes/referencias.py). Es _mutate con nombre
    público: el ciclo con cerrojo no debe reimplementarse fuera."""
    return _mutate(mutator)


def get_all_hosts() -> list[dict]:
    return _read()["hosts"]


def add_host(**campos) -> dict:
    """El equipo nuevo entra al FINAL de la lista (order = cuántos había), no
    al principio: quien acaba de darlo de alta espera verlo aparecer abajo,
    no colado entre los que ya tenía ordenados a su gusto."""
    nuevo_id = _new_id("host")

    def _apply(data):
        data["hosts"].append({
            "id": nuevo_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "order": len(data["hosts"]),
            "acciones_extra": [],
            **campos,
        })
        # Se devuelve buscándolo DESPUÉS de que _mutate lo normalice, para que
        # quien llame reciba la ficha con la forma definitiva y no la cruda.
        return lambda: next(h for h in data["hosts"] if h["id"] == nuevo_id)

    return _mutate(_apply)()


def move_host(host_id: str, direction: int) -> None:
    """direction: -1 sube el equipo una posición, +1 lo baja. Intercambia el
    `order` con el vecino, igual que move_widget en el Resumen."""
    def _apply(data):
        items = data["hosts"]  # ya vienen ordenados por _normalizar_equipos
        idx = next((i for i, h in enumerate(items) if h["id"] == host_id), None)
        if idx is None:
            return
        destino = idx + direction
        if not (0 <= destino < len(items)):
            return
        items[idx]["order"], items[destino]["order"] = items[destino]["order"], items[idx]["order"]

    _mutate(_apply)


def add_host_with_id(item: dict) -> dict:
    """Alta conservando el id indicado — solo para la migración de los equipos
    que ya venían con id literal (raspberry, pi_zero, iphone...)."""
    return _add_with_id("hosts", item)


def update_host(host_id: str, **campos) -> dict | None:
    return _update("hosts", host_id, campos)


def delete_host(host_id: str) -> None:
    """Al borrar un equipo hay que llevarse también su último estado de ping.
    Si no, la entrada se queda huérfana en host_online para siempre con el
    valor que tuviera al borrarlo — y si era True, el contador "Equipos en
    línea" del Resumen sigue sumándola aunque el equipo ya no exista."""
    _delete("hosts", host_id)

    def _apply(data):
        data["host_online"].pop(host_id, None)

    _mutate(_apply)


def find_host_by_ip(ip: str) -> dict | None:
    return next((h for h in _read()["hosts"] if h["ip"] == ip), None)


def find_host_by_id(host_id: str) -> dict | None:
    return next((h for h in _read()["hosts"] if h["id"] == host_id), None)


# ── Estado en vivo de sensores/puertas/luces dinámicos (vía MQTT) ───────────
# Guardado aparte de nodes/sensors/... para no reescribir toda la config en
# cada evento MQTT; misma fuente de verdad compartida entre workers que usa
# shared_state.py para el sistema de alarma clásico.
def get_sensor_state(entity_id: str) -> bool:
    return _read().get("sensor_states", {}).get(entity_id, False)


def set_sensor_state(entity_id: str, value: bool) -> None:
    def _apply(data):
        data["sensor_states"][entity_id] = value

    _mutate(_apply)


def get_all_sensor_states() -> dict:
    return _read().get("sensor_states", {})


# ── Estado en vivo de ping de equipos extra ──────────────────────────────────
# Igual que sensor_states: el bucle que hace ping corre una sola vez por
# proceso, pero cada sesión/pestaña necesita poder leerlo, así que se persiste
# aquí en vez de guardarse solo en el `self` de la sesión que hizo el ping.
def set_host_online_bulk(updates: dict) -> None:
    """`updates` trae SIEMPRE todos los equipos de la vuelta de ping, así que
    se reemplaza el diccionario entero en vez de fusionarlo: así cualquier
    entrada huérfana (equipo borrado en una versión anterior, que no limpiaba
    host_online) se cae sola en el primer ping tras arrancar."""
    def _apply(data):
        data["host_online"] = dict(updates)

    _mutate(_apply)


def get_all_host_online() -> dict:
    return _read().get("host_online", {})


# ── Botones de acción personalizados por host ────────────────────────────────
# Mismo mecanismo para CUALQUIER host (fijo del registry o extra dado de alta
# en Equipos) — se guardan aparte, referenciados solo por host_id (un string),
# así que aplican igual sin importar de dónde viene el host.
# kind: "ssh_command" (ejecuta y muestra la salida) | "pin_write" (pone un pin
# a on/off) | "pin_read" (lee el estado de un pin y muestra la salida cruda).
def list_host_buttons(host_id: str) -> list[dict]:
    return [b for b in _read()["host_buttons"] if b["host_id"] == host_id]


def add_host_button(host_id: str, label: str, kind: str, value: str) -> dict:
    return _add("host_buttons", "btn", {"host_id": host_id, "label": label, "kind": kind, "value": value})


def delete_host_button(button_id: str) -> None:
    _delete("host_buttons", button_id)


# ── Sensores/cámaras "de fábrica" ─────────────────────────────────────────────
# Lo que antes vivía como literales Python en devices/registry.py (puerta
# principal, tampers, cámara fija/PTZ...) — misma forma CRUD que todo lo demás
# en este fichero, así son editables/borrables de verdad. Colecciones separadas
# (no dentro de sensors/cameras) para no duplicar tarjetas ni pisar el estado
# en vivo de los sensores, que sigue viniendo de shared_state.py — ver
# domains/devices/registry.py, que es quien construye las entidades reales a
# partir de estas colecciones. Los EQUIPOS ya no están aquí: viven todos
# juntos en la colección "hosts" (ver _migrar_equipos).
def get_all_factory_sensors() -> list[dict]:
    return _read()["factory_sensors"]


def add_factory_sensor(item: dict) -> dict:
    """Solo para la migración inicial — conserva el id indicado en `item`.
    `topic` va literal (no se deriva con sensor_topic()/slugify): estos
    sensores ya tienen un topic real desplegado en hardware físico."""
    return _add_with_id("factory_sensors", item)


def update_factory_sensor(sensor_id: str, **fields) -> dict | None:
    return _update("factory_sensors", sensor_id, fields)


def delete_factory_sensor(sensor_id: str) -> None:
    _delete("factory_sensors", sensor_id)


def toggle_factory_sensor_isolated(sensor_id: str) -> dict | None:
    def _apply(data):
        updated = None
        for s in data["factory_sensors"]:
            if s["id"] == sensor_id:
                s["isolated"] = not s.get("isolated", False)
                updated = s
        return updated

    return _mutate(_apply)


# ── Mural de vídeo ───────────────────────────────────────────────────────────
# Una sola rejilla persistente (no varias vistas guardadas): un reparto
# elegido + qué cámara va en cada hueco. (id, etiqueta, columnas, filas) —
# repartos cuadrados o rectangulares de verdad, no el "1 grande + 5 pequeñas"
# de un NVR profesional, que exigiría celdas de tamaños distintos.
VIDEO_WALL_LAYOUTS = (
    ("1", "1", 1, 1),
    ("2h", "2 · lado a lado", 2, 1),
    ("2v", "2 · apiladas", 1, 2),
    ("4", "4", 2, 2),
    ("6", "6", 3, 2),
    ("8", "8", 4, 2),
    ("9", "9", 3, 3),
    ("16", "16", 4, 4),
)
_VIDEO_WALL_LAYOUT_IDS = {l[0] for l in VIDEO_WALL_LAYOUTS}


def get_video_wall() -> dict:
    return _read()["video_wall"]


def set_video_wall_layout(layout: str) -> None:
    if layout not in _VIDEO_WALL_LAYOUT_IDS:
        return

    def _apply(data):
        vw = data["video_wall"]
        vw["layout"] = layout
        total = next(c * r for lid, _, c, r in VIDEO_WALL_LAYOUTS if lid == layout)
        # Al reducir el reparto, los huecos que ya no caben se sueltan: una
        # cámara "colocada" en el hueco 12 de un mural que pasa a tener 4
        # quedaría asignada pero invisible e inalcanzable para siempre.
        vw["slots"] = {k: v for k, v in vw["slots"].items() if int(k) < total}

    _mutate(_apply)


def set_video_wall_slot(slot: str, camera_id: str) -> None:
    def _apply(data):
        slots = data["video_wall"]["slots"]
        # Una cámara solo puede estar en UN hueco: si ya estaba en otro, se
        # retira de allí antes de ponerla en el nuevo, para no verla repetida.
        for k in [k for k, v in slots.items() if v == camera_id]:
            del slots[k]
        slots[slot] = camera_id

    _mutate(_apply)


def clear_video_wall_slot(slot: str) -> None:
    def _apply(data):
        data["video_wall"]["slots"].pop(slot, None)

    _mutate(_apply)


def clear_video_wall() -> None:
    def _apply(data):
        data["video_wall"]["slots"] = {}

    _mutate(_apply)


def get_all_factory_cameras() -> list[dict]:
    return _read()["factory_cameras"]


def add_factory_camera(item: dict) -> dict:
    """Solo para la migración inicial — conserva el id indicado en `item`."""
    return _add_with_id("factory_cameras", item)


def update_factory_camera(camera_id: str, **fields) -> dict | None:
    return _update("factory_cameras", camera_id, fields)


def delete_factory_camera(camera_id: str) -> None:
    _delete("factory_cameras", camera_id)


# ── Mandos IR (Broadlink) ─────────────────────────────────────────────────────
# Un "mando" es solo un nombre + una lista de botones — el hub físico es uno
# solo (IP_BROADLINK/MAC_BROADLINK, ver domains/devices/ir_bus.py), así que
# aquí no se guarda ninguna referencia a él. Cada botón lleva su propio código
# aprendido (hex) — aprenderlo es domains/devices/ir_bus.learn_button(),
# dispararlo es ir_bus.send_button(código).
#
# pos_top/pos_left son la posición (%) del botón DENTRO del cuerpo del mando
# virtual (ver ui/dashboard/views/ir_remotes.py) — igual que floor_top/
# floor_left posicionan un icono sobre el plano de planta, solo que aquí el
# "plano" es la silueta del mando.
#
# La posición de un botón NO puede depender nunca de su sitio en la lista.
# Antes se calculaba con una rejilla a partir del índice, y eso hacía que al
# borrar un botón se corrieran los índices de los demás y saltaran de columna
# — el mando entero se reorganizaba solo. Ahora un botón sin posición recibe
# un hueco libre calculado contra los botones YA colocados (no contra su
# índice), se le guarda, y a partir de ahí no se vuelve a mover nunca salvo
# que lo arrastres tú.
def _asegurar_posiciones(remote: dict) -> None:
    ancho = int(remote.get("body_w") or 300)
    alto = int(remote.get("body_h") or 820)
    ocupados = [
        (_porcentaje(b.get("pos_left"), ancho), _porcentaje(b.get("pos_top"), alto))
        for b in remote["buttons"]
        if b.get("pos_top") and b.get("pos_left")
    ]
    for boton in remote["buttons"]:
        if boton.get("pos_top") and boton.get("pos_left"):
            continue
        x, y = _primer_hueco(ocupados, ancho, alto)
        boton["pos_left"] = f"{x / ancho * 100:.2f}%"
        boton["pos_top"] = f"{y / alto * 100:.2f}%"
        ocupados.append((x, y))


def _primer_hueco(ocupados: list[tuple[float, float]], ancho: int, alto: int) -> tuple[float, float]:
    """Primer punto del cuerpo (px) donde cabe una tecla sin pisar a las que ya
    están, barriendo en rejilla de arriba abajo. Si no queda sitio, el centro."""
    paso = _TECLA_PX + 12
    margen = _TECLA_PX / 2 + 6
    y = margen
    while y <= alto - margen:
        x = margen
        while x <= ancho - margen:
            if all(abs(x - ox) >= _TECLA_PX or abs(y - oy) >= _TECLA_PX for ox, oy in ocupados):
                return x, y
            x += paso
        y += paso
    return ancho / 2, alto / 2


def get_all_ir_remotes() -> list[dict]:
    return _read()["ir_remotes"]


def add_ir_remote(name: str, icon: str = "tv",
                   show_on_floor: bool = False, floor_icon: str = "",
                   plantilla: str = "vacio") -> dict:
    """`plantilla` rellena el mando de entrada con TODOS los botones de un
    mando físico real, ya colocados pero sin señal aprendida — ver
    ../devices/remote_templates.py. "vacio" lo deja como estaba: sin botones."""
    from ..devices import remote_templates

    botones = [
        {"id": _new_id("btn"), **b} for b in remote_templates.botones(plantilla)
    ]
    # Las placas de la plantilla dicen a qué teclas agrupan por su NOMBRE
    # (los ids se generan aquí); se traducen a ids, que es lo que aguanta un
    # renombrado posterior.
    id_por_nombre = {b["label"]: b["id"] for b in botones}
    grupos = []
    for grupo in remote_templates.grupos(plantilla):
        miembros = [id_por_nombre[n] for n in grupo["members"] if n in id_por_nombre]
        if miembros:
            grupos.append({**grupo, "members": miembros})
    # La forma del cuerpo viaja con el mando, no con la plantilla: el de la TV
    # es alto y estrecho y el del ventilador apaisado, y las posiciones de sus
    # botones están en % sobre SU cuerpo. Guardarla aquí es lo que permite
    # que cada mando se pinte con su propia proporción.
    ancho, alto = remote_templates.cuerpo(plantilla)
    item = {
        "name": name, "icon": icon or "tv", "buttons": botones,
        # Placas decorativas del mando real (balancín, rueda, tira de colores,
        # pad de la luz...). No se pulsan: son lo que hace que se reconozca
        # como el mando de verdad y no como círculos sueltos.
        "groups": grupos,
        "body_w": ancho, "body_h": alto,
        # En el plano se ve el MISMO icono que tiene el mando: un mando no
        # necesita dos identidades distintas, y tener que elegir el icono dos
        # veces solo servía para que acabaran descuadrados.
        **floor_fields(show_on_floor, icon or "tv", None),
    }
    return _add("ir_remotes", "ir", item)


def delete_ir_remote(remote_id: str) -> None:
    _delete("ir_remotes", remote_id)


def update_ir_remote(remote_id: str, name: str, icon: str,
                      show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((r for r in _read()["ir_remotes"] if r["id"] == remote_id), None)
    return _update("ir_remotes", remote_id, {
        "name": name, "icon": icon or "tv",
        # El icono del plano sigue al del mando: cambiarle el icono al mando
        # lo cambia también donde se ve en la casa, sin tener que acordarse.
        **floor_fields(show_on_floor, icon or "tv", current),
    })


def _hueco_libre(remote: dict) -> tuple[str, str]:
    """(pos_top, pos_left) del primer sitio libre del cuerpo.

    Se busca DENTRO del cuerpo actual en vez de agrandarlo: cambiar el tamaño
    del mando obliga a recalcular el % de todas las teclas, y eso movería de
    sitio a las que ya estaban colocadas. Añadir un botón no puede tocar a los
    demás."""
    ancho = int(remote.get("body_w") or 300)
    alto = int(remote.get("body_h") or 820)
    ocupados = [
        (_porcentaje(b.get("pos_left"), ancho), _porcentaje(b.get("pos_top"), alto))
        for b in remote["buttons"]
    ]
    x, y = _primer_hueco(ocupados, ancho, alto)
    return f"{y / alto * 100:.2f}%", f"{x / ancho * 100:.2f}%"


def add_ir_button(remote_id: str, label: str, icon: str, code: str) -> dict | None:
    """Añade un botón ya aprendido (código en hex) al mando indicado, en el
    primer hueco libre del cuerpo — ver _hueco_libre."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] == remote_id:
                pos_top, pos_left = _hueco_libre(remote)
                boton = {
                    "id": _new_id("btn"), "label": label, "icon": icon or "circle", "code": code,
                    "kind": "ir", "text": "", "color": "", "icon_size": "46%",
                    "pos_top": pos_top, "pos_left": pos_left,
                }
                remote["buttons"].append(boton)
                return boton
        return None

    return _mutate(_apply)


def set_ir_button_position(remote_id: str, button_id: str, top: str, left: str) -> dict | None:
    """Persiste la posición (%) de un botón tras arrastrarlo dentro del mando
    virtual — un botón suelto, ver set_ir_button_positions_bulk para varios
    de una vez (lo que usa "Guardar disposición")."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["pos_top"] = top
                    boton["pos_left"] = left
                    return boton
        return None

    return _mutate(_apply)


# Lado de una tecla, para buscar huecos libres donde colocar un botón nuevo.
# El recorte del cuerpo y el tamaño con que se PINTA cada tecla se calculan
# aparte, al montar la vista (ver _remote_para_ui en state.py): aquí solo se
# guardan coordenadas.
_TECLA_PX = 44


def _porcentaje(valor: str, total: float) -> float:
    try:
        return float(str(valor).rstrip("%")) / 100 * total
    except (TypeError, ValueError):
        return 0.0


def set_ir_button_positions_bulk(remote_id: str, updates: list[dict]) -> None:
    """Guarda de una sola vez la posición de VARIOS botones tras una sesión de
    recolocación — mismo motivo que set_floor_positions_bulk: o se guarda toda
    la disposición nueva o no se guarda ninguna.

    Cada entrada de `updates`: {"id": ..., "top": ..., "left": ...}."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            pendientes = {u["id"]: u for u in updates}
            for boton in remote["buttons"]:
                u = pendientes.get(boton["id"])
                if u and u.get("top") and u.get("left"):
                    boton["pos_top"] = u["top"]
                    boton["pos_left"] = u["left"]

    _mutate(_apply)


def update_ir_button(remote_id: str, button_id: str, label: str, icon: str,
                      kind: str | None = None, code: str | None = None) -> dict | None:
    """Nombre/icono de un botón, y opcionalmente por dónde se manda (`kind`:
    "ir" o "webos") y su comando webOS (`code`). La señal INFRARROJA no se
    edita a mano nunca: se (re)aprende con set_ir_button_code."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["label"] = label
                    boton["icon"] = icon or "circle"
                    if kind is not None:
                        boton["kind"] = kind
                    if code is not None:
                        boton["code"] = code
                    return boton
        return None

    return _mutate(_apply)


def set_ir_button_code(remote_id: str, button_id: str, code: str) -> dict | None:
    """Graba en un botón YA EXISTENTE la señal recién aprendida — es lo que
    convierte un botón de plantilla (sin señal) en uno funcional, y también lo
    que permite re-aprender uno que se capturó mal."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["code"] = code
                    boton["kind"] = "ir"
                    return boton
        return None

    return _mutate(_apply)


def delete_ir_button(remote_id: str, button_id: str) -> None:
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] == remote_id:
                remote["buttons"] = [b for b in remote["buttons"] if b["id"] != button_id]

    _mutate(_apply)


# ── Widgets del Resumen ("Centro de Control") ────────────────────────────────
# La pestaña Resumen es completamente configurable: el usuario elige qué
# widgets ver (contadores o accesos rápidos) y en qué orden. label/icon se
# guardan denormalizados en el propio widget (igual que node_name en
# sensores/luces) para no depender de cruzar listas con una Var reactiva al
# pintar — si el grupo/cámara/luz/puerta referenciado se renombra después, el
# widget se queda con el nombre de cuando se añadió, hasta que se borre y
# vuelva a añadir.
def get_all_widgets() -> list[dict]:
    return sorted(_read()["overview_widgets"], key=lambda w: w.get("order", 0))


def add_widget(kind: str, target_id: str, label: str, icon: str) -> dict:
    def _apply(data):
        item = {
            "id": _new_id("widget"), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind, "target_id": target_id, "label": label, "icon": icon,
            "order": len(data["overview_widgets"]),
        }
        data["overview_widgets"].append(item)
        return item

    return _mutate(_apply)


def delete_widget(widget_id: str) -> None:
    def _apply(data):
        data["overview_widgets"] = [w for w in data["overview_widgets"] if w["id"] != widget_id]
        for i, w in enumerate(sorted(data["overview_widgets"], key=lambda w: w.get("order", 0))):
            w["order"] = i

    _mutate(_apply)


# A qué grupo visual pertenece cada acceso rápido — Alarma, Luces, Puertas...
# Es lo que permite pintarlos agrupados por familia en el Resumen (en vez de
# una única lista donde una puerta, una luz y una cámara van intercaladas sin
# ningún orden) Y es lo que usa move_widget para saber con qué vecino
# intercambiar un widget al moverlo: si no se supiera la familia, "mover" un
# acceso de Puertas podría intercambiarlo con uno de Luces que esté al lado en
# el orden global, y como cada familia se pinta en su propia sección, el botón
# parecería no hacer nada.
# (id, etiqueta, icono) — orden en el que se pintan las secciones de accesos
# rápidos del Resumen. "otros" va el último a propósito: es el cajón de sastre
# (ir a una pestaña, ver registros, enviar un aviso), lo menos "acción física
# sobre la casa" de todas.
ACTION_FAMILIES = (
    ("alarma", "Alarma y grupos", "shield"),
    ("luces", "Luces", "lightbulb"),
    ("puertas", "Puertas", "door-open"),
    ("camaras", "Cámaras", "video"),
    ("mandos", "Mandos", "gamepad-2"),
    ("equipos", "Equipos", "server"),
    ("otros", "Otros", "layout-grid"),
)

FAMILIA_ACCION = {
    "action_arm": "alarma", "action_group": "alarma",
    "action_light": "luces",
    "action_door": "puertas",
    "action_camera": "camaras",
    "action_ir_button": "mandos",
    "action_rdp": "equipos", "action_host_button": "equipos",
    "action_host_shutdown": "equipos", "action_host_wol": "equipos",
    "action_view": "otros", "action_logs": "otros", "action_notify": "otros",
}


def familia_de(kind: str) -> str:
    """Familia de un widget cualquiera. Los contadores ("stat_*") siguen
    siendo UNA sola familia — no se pintan agrupados por sub-tipo, así que
    basta con que no se mezclen con los accesos rápidos."""
    if kind.startswith("stat_"):
        return "stat"
    return FAMILIA_ACCION.get(kind, "otros")


def move_widget(widget_id: str, direction: int) -> None:
    """direction: -1 mueve a la izquierda/arriba, +1 a la derecha/abajo.

    El intercambio es con el vecino de su MISMA familia (ver familia_de), no
    con el vecino del orden global: cada familia se pinta en su propio
    contenedor del Resumen, así que intercambiar con algo de otra familia no
    movería nada en pantalla y el botón parecería estropeado."""
    def _apply(data):
        items = sorted(data["overview_widgets"], key=lambda w: w.get("order", 0))
        target = next((w for w in items if w["id"] == widget_id), None)
        if target is None:
            return
        family = familia_de(target["kind"])
        same_family = [w for w in items if familia_de(w["kind"]) == family]
        idx = same_family.index(target)
        new_idx = idx + direction
        if not (0 <= new_idx < len(same_family)):
            return
        neighbour = same_family[new_idx]
        target["order"], neighbour["order"] = neighbour["order"], target["order"]

    _mutate(_apply)
