"""
Registro declarativo de todos los objetos reales de la casa.

Para añadir hardware nuevo (un relé, un sensor, una persiana...) se añade una
entrada aquí — no hace falta tocar ningún State de Reflex.

Ejemplo: añadir un relé de garaje + su sensor de puerta:

    "rele_garaje": RelayEntity(id="rele_garaje", name="Relé Garaje",
                                gpio=GPIOSpec(host="pi_zero", pin="23")),
    "puerta_garaje": BinarySensorEntity(id="puerta_garaje", name="Puerta Garaje",
                                mqtt=MQTTSpec(topic="casa/pizero/garaje"),
                                kind="door", lock_relay="rele_garaje"),
"""
import dataclasses
import os
from . import overrides_store
from ..nodes import store as nodes_store
from .models import (
    Entity, HostEntity, RelayEntity, BinarySensorEntity, CameraEntity,
    GPIOSpec, MQTTSpec, SSHSpec, Accion,
)


# ── Equipos/sensores/cámaras ─────────────────────────────────────────────────
# Antes vivían aquí como literales Python (server, pc, raspberry, puerta_ppal,
# tamper1/2, cam_fija/ptz...); ahora se construyen leyendo las colecciones
# hosts/factory_sensors/factory_cameras de nodes/store.py (mismo fichero JSON
# — nodos_dinamicos.json — que usan luces y puertas añadidas desde la web),
# migradas una vez con scripts/migrate_static_entities.py.
# Esto es lo que las hace editables y BORRABLES de verdad: dejaron de ser
# literales de este archivo. El resto de esta función (hosts()/binary_sensors()
# /cameras()/GPIO_HOSTS...) no cambia — todo lo que llama a esas funciones
# sigue funcionando igual sin saber que la fuente cambió.
def _host_entity(h: dict) -> HostEntity:
    return HostEntity(
        id=h["id"], name=h["name"],
        ssh=SSHSpec(host=h.get("ip", ""), user=h.get("user", ""), os=h.get("os", "linux")),
        mac=h.get("mac"),
        ping_retries=h.get("ping_retries", 1),
        icon=h.get("icon"),
        acciones_extra=[
            Accion(nombre=a["nombre"], handler_name=a["handler_name"])
            for a in h.get("acciones_extra", [])
        ],
    )


def _build_hosts() -> dict[str, HostEntity]:
    return {h["id"]: _host_entity(h) for h in nodes_store.get_all_hosts()}


def sync_host(item: dict) -> None:
    """Mete en DEVICES un equipo recién dado de alta (o recién editado) SIN
    reiniciar. Hace falta porque DEVICES se construye una única vez al importar
    el módulo: sin esto, un equipo añadido desde la web no existía para el
    ping, ni para la consola SSH, ni para los relés, hasta el siguiente
    arranque — que era justo la diferencia de trato entre los equipos de
    siempre y los nuevos."""
    DEVICES[item["id"]] = _host_entity(item)


def forget_host(host_id: str) -> None:
    DEVICES.pop(host_id, None)


def _build_factory_sensors() -> dict[str, BinarySensorEntity]:
    return {
        s["id"]: BinarySensorEntity(
            id=s["id"], name=s["name"], kind=s.get("kind", "generic"),
            mqtt=MQTTSpec(topic=s["topic"]) if s.get("topic") else None,
            node=s.get("node_id") or None,
            floor_top=s.get("floor_top"), floor_left=s.get("floor_left"), floor_icon=s.get("floor_icon"),
            floor_subtle=s.get("floor_subtle", False), floor_color=s.get("floor_color"),
            floor_color_on=s.get("floor_color_on"),
        )
        for s in nodes_store.get_all_factory_sensors()
    }


def _build_factory_cameras() -> dict[str, CameraEntity]:
    return {
        c["id"]: CameraEntity(
            id=c["id"], name=c["name"], stream_src=c["stream_src"],
            tuya_device_id=c.get("tuya_device_id"),
            has_ptz=c.get("has_ptz", False),
            icon=c.get("icon"),
            floor_top=c.get("floor_top"), floor_left=c.get("floor_left"), floor_icon=c.get("floor_icon"),
            floor_subtle=c.get("floor_subtle", False), floor_color=c.get("floor_color"),
            floor_color_on=c.get("floor_color_on"),
        )
        for c in nodes_store.get_all_factory_cameras()
    }


DEVICES: dict[str, Entity] = {
    **_build_hosts(),

    # ── Hosts de solo-estado sin UI propia (no gestionables desde ninguna
    # pestaña hoy — se quedan como literales, fuera de esta migración) ──────
    "cam_ptz_host": HostEntity(id="cam_ptz_host", name="Cámara PTZ", ssh=SSHSpec(host=os.getenv("IP_CAM_PTZ", ""), user="")),
    "cam_fija_host": HostEntity(id="cam_fija_host", name="Cámara Fija", ssh=SSHSpec(host=os.getenv("IP_CAM_FIJA", ""), user="")),

    # ── Relés ────────────────────────────────────────────────────────────
    "ventilador": RelayEntity(id="ventilador", name="Ventilador CPU", gpio=GPIOSpec(host="raspberry", pin="17")),

    **_build_factory_sensors(),
    **_build_factory_cameras(),
}


def hosts() -> dict[str, HostEntity]:
    return {k: v for k, v in DEVICES.items() if isinstance(v, HostEntity)}


def relays() -> dict[str, RelayEntity]:
    return {k: v for k, v in DEVICES.items() if isinstance(v, RelayEntity)}


def binary_sensors() -> dict[str, BinarySensorEntity]:
    return {k: v for k, v in DEVICES.items() if isinstance(v, BinarySensorEntity)}


def cameras() -> dict[str, CameraEntity]:
    return {k: v for k, v in DEVICES.items() if isinstance(v, CameraEntity)}


def _host_ids() -> set[str]:
    return {h["id"] for h in nodes_store.get_all_hosts()}


def _factory_sensor_ids() -> set[str]:
    return {s["id"] for s in nodes_store.get_all_factory_sensors()}


def _factory_camera_ids() -> set[str]:
    return {c["id"] for c in nodes_store.get_all_factory_cameras()}


def is_factory_sensor(entity_id: str) -> bool:
    return entity_id in _factory_sensor_ids()


def is_factory_camera(entity_id: str) -> bool:
    return entity_id in _factory_camera_ids()


def set_factory_floor_pos(entity_id: str, top: str, left: str) -> None:
    """Persiste la posición (%) de un sensor/cámara "de fábrica" en el plano
    de planta tras arrastrarlo — ver ui/views/device_list.py. También
    actualiza DEVICES en memoria (aunque lo que de verdad refresca la UI al
    instante es RegistryState.floor_pos, ver domains/nodes/state.py:
    set_floor_pos)."""
    if entity_id in _factory_sensor_ids():
        nodes_store.update_factory_sensor(entity_id, floor_top=top, floor_left=left)
    elif entity_id in _factory_camera_ids():
        nodes_store.update_factory_camera(entity_id, floor_top=top, floor_left=left)
    else:
        return
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {"floor_top": top, "floor_left": left})


def reflect_floor_pos(entity_id: str, top: str, left: str) -> None:
    """Refresca SOLO la copia en memoria de DEVICES. Lo usa el guardado en
    bloque del plano, que ya ha escrito en disco de una tacada (ver
    nodes/store.py:set_floor_positions_bulk) y solo necesita que lo que hay
    cargado en el proceso deje de estar desfasado."""
    entity = DEVICES.get(entity_id)
    if entity is not None and hasattr(entity, "floor_top"):
        DEVICES[entity_id] = _replace_entity(entity, {"floor_top": top, "floor_left": left})


def set_factory_floor_icon(entity_id: str, icon: str) -> None:
    """Cambia solo el icono del marcador, sin tocar su posición — a
    diferencia de apply_override(show_on_floor=...), que sí la recalcula."""
    if entity_id in _factory_sensor_ids():
        nodes_store.update_factory_sensor(entity_id, floor_icon=icon)
    elif entity_id in _factory_camera_ids():
        nodes_store.update_factory_camera(entity_id, floor_icon=icon)
    else:
        return
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {"floor_icon": icon})


def set_factory_floor_color(entity_id: str, color: str) -> None:
    if entity_id in _factory_sensor_ids():
        nodes_store.set_floor_color("factory_sensors", entity_id, color)
    elif entity_id in _factory_camera_ids():
        nodes_store.set_floor_color("factory_cameras", entity_id, color)
    else:
        return
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {"floor_color": color or None})


def set_factory_floor_color_on(entity_id: str, color: str) -> None:
    """El color de cuando está activo, para las entidades de fábrica. Mismo
    camino que set_factory_floor_color: al almacén y a la copia en memoria."""
    if entity_id in _factory_sensor_ids():
        nodes_store.set_floor_color_on("factory_sensors", entity_id, color)
    elif entity_id in _factory_camera_ids():
        nodes_store.set_floor_color_on("factory_cameras", entity_id, color)
    else:
        return
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {"floor_color_on": color or None})


def toggle_factory_floor_subtle(entity_id: str) -> bool:
    """Alterna el modo discreto de un sensor/cámara "de fábrica" en el plano.
    Devuelve el estado resultante."""
    if entity_id in _factory_sensor_ids():
        actual = nodes_store.toggle_floor_subtle("factory_sensors", entity_id)
    elif entity_id in _factory_camera_ids():
        actual = nodes_store.toggle_floor_subtle("factory_cameras", entity_id)
    else:
        return False
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {"floor_subtle": actual})
    return actual


def delete_factory_entity(entity_id: str) -> None:
    """Borrado real (no ocultar) de un equipo/sensor/cámara "de fábrica" —
    igual que borrar cualquier equipo/sensor/cámara añadido desde la web.
    Solo se ve reflejado en pantalla tras reiniciar el servicio (las tarjetas
    de estas entidades se construyen una vez en Python, no vía rx.foreach),
    igual que cualquier otra edición estática — pero el dato ya está borrado
    de verdad de inmediato."""
    if entity_id in _host_ids():
        nodes_store.delete_host(entity_id)
    elif entity_id in _factory_sensor_ids():
        nodes_store.delete_factory_sensor(entity_id)
    elif entity_id in _factory_camera_ids():
        nodes_store.delete_factory_camera(entity_id)
    DEVICES.pop(entity_id, None)


def get_relay(relay_id: str) -> RelayEntity:
    entity = DEVICES[relay_id]
    if not isinstance(entity, RelayEntity):
        raise TypeError(f"{relay_id!r} no es un RelayEntity")
    return entity


# Hosts con GPIO físico accionable por SSH (raspi-gpio) — a diferencia del
# resto (PC, portátil, servidor, tablet...) que son equipos normales sin
# pines. Usado por domains/nodes para que la Raspberry/Pi Zero puedan
# elegirse como "nodo" al dar de alta un sensor/puerta/luz, igual que un
# ESP32 pero actuando por SSH en vez de por MQTT.
GPIO_HOSTS = ["raspberry", "pi_zero"]


def gpio_hosts() -> dict[str, HostEntity]:
    return {k: v for k, v in hosts().items() if k in GPIO_HOSTS}


# ── Ocultar/eliminar entidades estáticas ─────────────────────────────────────
# Las entidades "de fábrica" no se pueden borrar del código sin arriesgar
# romper el cableado real (SSH keepalive, topics MQTT, relés...), así que
# "eliminar" aquí es ocultar: desaparece de los listados de gestión (Equipos,
# Alarma, CCTV) y de los selectores para dar de alta cosas nuevas, pero el
# cableado de fondo (ping, MQTT, GPIO) sigue intacto por si algo más todavía
# la referencia (p.ej. un grupo que ya la tenía como miembro). Igual que
# cualquier otra edición estática, el cambio se guarda ya pero solo se ve en
# pantalla tras reiniciar el proceso.
def hidden_ids() -> set[str]:
    return overrides_store.get_hidden_ids()


def is_hidden(entity_id: str) -> bool:
    return entity_id in hidden_ids()


def hide(entity_id: str) -> None:
    overrides_store.hide_entity(entity_id)


def unhide(entity_id: str) -> None:
    overrides_store.unhide_entity(entity_id)


def visible_hosts() -> dict[str, HostEntity]:
    hidden = hidden_ids()
    return {k: v for k, v in hosts().items() if k not in hidden}


def visible_binary_sensors() -> dict[str, BinarySensorEntity]:
    hidden = hidden_ids()
    return {k: v for k, v in binary_sensors().items() if k not in hidden}


def visible_cameras() -> dict[str, CameraEntity]:
    hidden = hidden_ids()
    return {k: v for k, v in cameras().items() if k not in hidden}


# ── Aislar sensores ───────────────────────────────────────────────────────────
# Un sensor "aislado" sigue registrado y visible, pero la alarma lo trata como
# si no existiese: aunque esté en un grupo armado, no dispara alerta. A
# diferencia de ocultar, esto SÍ se aplica en caliente (GroupsState.watch_loop
# relee isolated_ids() del disco en cada vuelta) — solo el resaltado gris de
# la tarjeta de un sensor ESTÁTICO necesita reiniciar para verse, igual que
# cualquier otro cambio visual estático.
def isolated_ids() -> set[str]:
    factory_isolated = {
        s["id"] for s in nodes_store.get_all_factory_sensors() if s.get("isolated")
    }
    return overrides_store.get_isolated_ids() | factory_isolated


def is_isolated(entity_id: str) -> bool:
    return entity_id in isolated_ids()


def isolate(entity_id: str) -> None:
    if entity_id in _factory_sensor_ids():
        nodes_store.update_factory_sensor(entity_id, isolated=True)
    else:
        overrides_store.isolate_entity(entity_id)


def unisolate(entity_id: str) -> None:
    # Se limpia en LOS DOS almacenes a propósito: los sensores migrados
    # (tamper1/tamper2) pueden arrastrar todavía su marca de aislado en el
    # _isolated de registry_overrides.json, de antes de la migración. Si solo
    # se limpiase factory_sensors, isolated_ids() —que hace la unión de ambos—
    # seguiría diciendo "aislado", y toggle_isolated() volvería a entrar
    # siempre por la rama de reactivar: el sensor no se podría volver a aislar
    # nunca más.
    if entity_id in _factory_sensor_ids():
        nodes_store.update_factory_sensor(entity_id, isolated=False)
    overrides_store.unisolate_entity(entity_id)


# ── Edición en caliente desde la UI ──────────────────────────────────────────
# Los campos "de fábrica" vienen del .env; una edición desde la UI persiste
# aquí y se aplica sobre DEVICES al vuelo. registry.py sigue siendo el único
# sitio que sabe qué campo de cada tipo de entidad es editable y a qué
# atributo anidado corresponde (ssh.host, gpio.pin, mqtt.topic...).
EDITABLE_FIELDS = {
    HostEntity: {
        "name": "name", "mac": "mac", "host": "ssh.host", "user": "ssh.user",
        "os": "ssh.os", "ping_retries": "ping_retries", "icon": "icon",
    },
    BinarySensorEntity: {
        "name": "name", "topic": "mqtt.topic", "node": "node", "kind": "kind",
        "floor_top": "floor_top", "floor_left": "floor_left", "floor_icon": "floor_icon",
        "floor_subtle": "floor_subtle", "floor_color": "floor_color",
        "floor_color_on": "floor_color_on",
    },
    RelayEntity: {"name": "name", "host": "gpio.host", "pin": "gpio.pin"},
    CameraEntity: {
        "name": "name", "tuya_device_id": "tuya_device_id", "icon": "icon",
        "floor_top": "floor_top", "floor_left": "floor_left", "floor_icon": "floor_icon",
        "floor_subtle": "floor_subtle", "floor_color": "floor_color",
        "floor_color_on": "floor_color_on",
    },
}


def _replace_entity(entity: Entity, fields: dict) -> Entity:
    mapping = EDITABLE_FIELDS.get(type(entity), {})
    top_updates: dict = {}
    nested_updates: dict[str, dict] = {}
    for field_name, value in fields.items():
        target = mapping.get(field_name)
        if target is None:
            continue
        if "." in target:
            attr, sub = target.split(".", 1)
            nested_updates.setdefault(attr, {})[sub] = value
        else:
            top_updates[target] = value
    for attr, sub_updates in nested_updates.items():
        current = getattr(entity, attr)
        top_updates[attr] = dataclasses.replace(current, **sub_updates)
    return dataclasses.replace(entity, **top_updates) if top_updates else entity


def _apply_stored_overrides() -> None:
    for entity_id, fields in overrides_store.get_overrides().items():
        if entity_id in DEVICES:
            DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], fields)


def _migrate_factory_overrides() -> None:
    """Se lleva a nodos_dinamicos.json las entradas de registry_overrides.json
    que apuntan a una entidad ya migrada, y las borra de allí.

    Esto arregla un renombrado que revertía solo. Desde la migración de las
    entidades "de fábrica", editar puerta_ppal/tamper2/iphone... desde la web
    escribe en el store (ver apply_override), pero las entradas viejas seguían
    en registry_overrides.json y _apply_stored_overrides() las aplica DESPUÉS de
    construir DEVICES desde el store: el valor viejo ganaba en cada arranque. Se
    veía como "le cambio el nombre, se guarda, y al reiniciar vuelve el de
    antes". Con tamper2 se notaba a simple vista: el store decía "Tamper2" y el
    override "Tamper pc".

    Manda el valor del override, no el del store, porque el del override es el
    que se está viendo en pantalla ahora mismo — así la migración no cambia nada
    visualmente, solo deja UN sitio donde mirar. Corre antes de
    _apply_stored_overrides() y es idempotente: tras la primera vez ya no queda
    ninguna entrada que migrar.
    """
    factory_ids = _host_ids() | _factory_sensor_ids() | _factory_camera_ids()
    for entity_id, fields in overrides_store.get_overrides().items():
        if entity_id not in factory_ids:
            continue
        if entity_id in _host_ids():
            _save_host_edit(entity_id, fields)
        elif entity_id in _factory_sensor_ids():
            _save_factory_sensor_edit(entity_id, fields)
        else:
            _save_factory_camera_edit(entity_id, fields)
        # DEVICES se construyó arriba con los valores del store, todavía sin
        # estos campos: se aplican igual que habría hecho
        # _apply_stored_overrides(), para que el proceso en marcha no cambie.
        if entity_id in DEVICES:
            DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], fields)
        overrides_store.drop_override(entity_id)
        print(f"✅ {entity_id}: override migrado a nodos_dinamicos.json ({', '.join(fields)})")


def _save_host_edit(entity_id: str, fields: dict) -> None:
    """Los nombres que trae el formulario ("host" para la IP) no son los del
    almacén ("ip"); aquí se traducen. Todo lo que sea texto se recorta: un
    usuario SSH que en realidad es un espacio hacía que el equipo se
    considerase accionable por SSH sin serlo."""
    traduccion = {"name": "name", "host": "ip", "user": "user", "os": "os", "icon": "icon"}
    store_fields = {
        destino: (fields[origen] or "").strip()
        for origen, destino in traduccion.items() if origen in fields
    }
    if "mac" in fields:
        store_fields["mac"] = (fields["mac"] or "").strip() or None
    if "icon" in store_fields:
        store_fields["icon"] = store_fields["icon"] or None
    if "os" in store_fields and store_fields["os"] not in nodes_store.SISTEMAS:
        store_fields["os"] = "linux"
    if "ping_retries" in fields:
        try:
            store_fields["ping_retries"] = max(1, int(fields["ping_retries"] or 1))
        except (TypeError, ValueError):
            store_fields["ping_retries"] = 1
    nodes_store.update_host(entity_id, **store_fields)


def _save_factory_sensor_edit(entity_id: str, fields: dict) -> dict:
    store_fields = {}
    if "name" in fields:
        store_fields["name"] = fields["name"]
    if "topic" in fields:
        store_fields["topic"] = fields["topic"]
    if "kind" in fields:
        store_fields["kind"] = fields["kind"]
    if "node" in fields:
        new_node_id = fields["node"]
        store_fields["node_id"] = new_node_id
        new_node = DEVICES.get(new_node_id)
        store_fields["node_name"] = new_node.name if new_node else ""
    if "show_on_floor" in fields or "floor_icon" in fields:
        current = next((s for s in nodes_store.get_all_factory_sensors() if s["id"] == entity_id), None)
        store_fields.update(nodes_store.floor_fields(
            bool(fields.get("show_on_floor")), fields.get("floor_icon", ""), current,
        ))
    nodes_store.update_factory_sensor(entity_id, **store_fields)
    return store_fields


def _save_factory_camera_edit(entity_id: str, fields: dict) -> dict:
    store_fields = {}
    if "name" in fields:
        store_fields["name"] = fields["name"]
    if "tuya_device_id" in fields:
        store_fields["tuya_device_id"] = fields["tuya_device_id"] or None
    if "icon" in fields:
        store_fields["icon"] = fields["icon"] or None
    if "show_on_floor" in fields or "floor_icon" in fields:
        current = next((c for c in nodes_store.get_all_factory_cameras() if c["id"] == entity_id), None)
        store_fields.update(nodes_store.floor_fields(
            bool(fields.get("show_on_floor")), fields.get("floor_icon", ""), current,
        ))
    nodes_store.update_factory_camera(entity_id, **store_fields)
    return store_fields


def apply_override(entity_id: str, **fields) -> dict:
    """Guarda la edición y la aplica al proceso en marcha inmediatamente.
    Para las entidades "de fábrica" (ver domains/nodes/store.py factory_*), se
    persiste en su registro dinámico — mismo formulario de siempre, solo
    cambia dónde se guarda. Para el resto (cam_ptz_host, cam_fija_host,
    ventilador), sigue en registry_overrides.json como siempre.
    Ojo: los componentes ya compilados (nombres/textos fijos en las vistas)
    no se refrescan solos — hace falta reiniciar para VER el cambio, aunque
    ya haya quedado guardado y DEVICES ya lo tenga (name/isolated/floor_* son
    la excepción: tienen su propia Var reactiva — ver registry_state.py — y
    se reflejan al instante sin reiniciar).
    Devuelve los campos "de fábrica" realmente calculados/persistidos (por
    ejemplo floor_top/floor_left resueltos a partir de show_on_floor), para
    que quien llame pueda espejarlos en una Var reactiva sin recalcularlos."""
    stored: dict = {}
    if entity_id in _host_ids():
        # Los equipos se reconstruyen desde el almacén en vez de parchear la
        # entidad con lo que venía en el formulario: así DEVICES queda con los
        # valores YA normalizados (reintentos como número y no como el texto
        # del input, usuario sin espacios) en lugar de con el texto crudo.
        _save_host_edit(entity_id, fields)
        actualizado = nodes_store.find_host_by_id(entity_id)
        if actualizado is not None:
            DEVICES[entity_id] = _host_entity(actualizado)
        return stored
    if entity_id in _factory_sensor_ids():
        stored = _save_factory_sensor_edit(entity_id, fields)
    elif entity_id in _factory_camera_ids():
        stored = _save_factory_camera_edit(entity_id, fields)
    else:
        overrides_store.set_override(entity_id, **fields)
    if entity_id in DEVICES:
        DEVICES[entity_id] = _replace_entity(DEVICES[entity_id], {**fields, **stored})
    return stored


# El orden importa: la migración tiene que vaciar los overrides duplicados
# ANTES de que se apliquen, o volverían a pisar al store un arranque más.
_migrate_factory_overrides()
_apply_stored_overrides()
