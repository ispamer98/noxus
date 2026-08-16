"""
Migración única: copia los 12 elementos "de fábrica" (puerta_ppal, tamper1,
tamper2, cam_fija, cam_ptz, server, pc, portatil, raspberry, pi_zero, tablet,
iphone) desde devices/registry.py (Python + .env + registry_overrides.json)
a las colecciones hosts/factory_sensors/factory_cameras de
nodos_dinamicos.json (ver domains/nodes/store.py).

Se ejecuta A MANO, UNA SOLA VEZ:

    cd /home/spamer/noxuscmmd
    ./.venv/bin/python scripts/migrate_static_entities.py

Es idempotente (no duplica si se ejecuta más de una vez — get_all_factory_*
+ _add_with_id ya comprueban el id). Lee los valores EFECTIVOS actuales
(importar registry.py ya aplica registry_overrides.json vía
_apply_stored_overrides()), no los valores "de fábrica" del .env — así se
conservan los nombres/IPs/aislados ya editados desde la UI.

No lo importa la app en ningún sitio — es una herramienta de migración, no
código de arranque.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# En producción (systemd, EnvironmentFile=.env) las variables ya están en el
# entorno del proceso; ejecutando este script a mano desde una shell normal
# no lo están — cargamos .env explícitamente para que los os.getenv(...) de
# registry.py salgan con las IPs/usuarios reales, no vacíos.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from noxuscmmd.domains.devices import registry
from noxuscmmd.domains.nodes import store

_HOST_IDS = ["server", "pc", "portatil", "raspberry", "pi_zero", "tablet", "iphone"]
_SENSOR_IDS = ["puerta_ppal", "tamper1", "tamper2"]
_CAMERA_IDS = ["cam_fija", "cam_ptz"]


def _migrate_hosts() -> list[str]:
    log = []
    for hid in _HOST_IDS:
        host = registry.DEVICES[hid]
        item = {
            "id": hid,
            "name": host.name,
            "ip": host.ssh.host or "",
            "user": host.ssh.user or "",
            "os": host.ssh.os,
            "mac": host.mac,
            "ping_retries": host.ping_retries,
            "icon": host.icon,
            "acciones_extra": [
                {"nombre": a.nombre, "handler_name": a.handler_name}
                for a in host.acciones_extra
            ],
        }
        store.add_host_with_id(item)
        log.append(f"  host {hid!r}: name={item['name']!r} ip={item['ip']!r} user={item['user']!r} "
                    f"mac={item['mac']!r} acciones_extra={[a['handler_name'] for a in item['acciones_extra']]}")
    return log


def _migrate_sensors() -> list[str]:
    log = []
    for sid in _SENSOR_IDS:
        sensor = registry.DEVICES[sid]
        topic = sensor.mqtt.topic if sensor.mqtt else ""
        item = {
            "id": sid,
            "name": sensor.name,
            "kind": sensor.kind,
            "node_id": sensor.node,
            "node_name": registry.DEVICES[sensor.node].name if sensor.node else "",
            "topic": topic,
            "isolated": registry.is_isolated(sid),
        }
        store.add_factory_sensor(item)
        log.append(f"  sensor {sid!r}: name={item['name']!r} topic={item['topic']!r} "
                    f"node_id={item['node_id']!r} isolated={item['isolated']}")
    return log


def _migrate_cameras() -> list[str]:
    log = []
    for cid in _CAMERA_IDS:
        cam = registry.DEVICES[cid]
        item = {
            "id": cid,
            "name": cam.name,
            "stream_src": cam.stream_src,
            "tuya_device_id": cam.tuya_device_id,
            "has_ptz": cam.has_ptz,
            "icon": cam.icon,
        }
        store.add_factory_camera(item)
        log.append(f"  camera {cid!r}: name={item['name']!r} stream_src={item['stream_src']!r} "
                    f"has_ptz={item['has_ptz']} tuya_device_id={'<set>' if item['tuya_device_id'] else '<vacío>'}")
    return log


def main():
    print("== Migrando equipos ==")
    for line in _migrate_hosts():
        print(line)

    print("\n== Migrando sensores ==")
    for line in _migrate_sensors():
        print(line)
    # Comprobación explícita pedida en el plan: los topics de tamper1/tamper2
    # deben quedar EXACTOS (sin guion bajo), no recalculados con slugify.
    sensors = {s["id"]: s for s in store.get_all_factory_sensors()}
    expected_topics = {
        "puerta_ppal": "casa/raspberry/puerta",
        "tamper1": "casa/pizero/tamper1",
        "tamper2": "casa/pizero/tamper2",
    }
    for sid, expected in expected_topics.items():
        actual = sensors.get(sid, {}).get("topic")
        marker = "OK" if actual == expected else "‼️ MISMATCH"
        print(f"  [{marker}] {sid}: esperado={expected!r} obtenido={actual!r}")

    print("\n== Migrando cámaras ==")
    for line in _migrate_cameras():
        print(line)

    print("\n== Resumen ==")
    print(f"  hosts:           {len(store.get_all_hosts())} (esperado >= {len(_HOST_IDS)})")
    print(f"  factory_sensors: {len(store.get_all_factory_sensors())} (esperado {len(_SENSOR_IDS)})")
    print(f"  factory_cameras: {len(store.get_all_factory_cameras())} (esperado {len(_CAMERA_IDS)})")
    print("\nRevisa el resumen de arriba a mano antes de seguir con la Fase 2 del plan.")


if __name__ == "__main__":
    main()
