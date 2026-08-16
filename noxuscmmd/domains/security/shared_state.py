"""
shared_state.py — El ARMADO GENERAL, compartido entre todos los procesos y
clientes. Persiste en JSON para que todos los workers Reflex lean lo mismo.

Esto es TODO lo que queda en estado_seguridad.json. El abierto/cerrado de los
sensores ya no vive aquí: vive en sensor_states de nodos_dinamicos.json, igual
que el de todos los demás elementos (ver ../nodes/store.py y
../nodes/sensor_events.py). Antes este archivo tenía un par getter/setter
escrito a mano por sensor —get_puerta_abierta, get_tamper1_abierto...— y un
sensor que no tuviera el suyo no guardaba su estado en ninguna parte.

sistema_armado se mantiene aquí porque es lo que lee la vista clásica; su
espejo es el grupo marcado is_principal en grupos_armado.json, sincronizado en
ambas direcciones (ver groups_state.toggle_group_armed).
"""
import json
import os
import shutil
import threading
import time
from pathlib import Path

from ..nodes import store as nodes_store

ESTADO_FILE = Path(os.getenv("ESTADO_FILE", "estado_seguridad.json"))
_lock = threading.Lock()

_DEFAULTS = {
    "sistema_armado": False,
}

# Claves que este archivo tuvo alguna vez y ya no le pertenecen. Las tres de
# estado se llevan a sensor_states; el resto son restos de versiones anteriores
# que nadie leía ni escribía desde hace tiempo (tamper_1_activado,
# tamper1_armado, notificacion_tamper1_enviada, notificacion_enviada...).
_LEGADO_A_SENSOR = {
    "puerta_abierta": "puerta_ppal",
    "tamper1_abierto": "tamper1",
    "tamper2_abierto": "tamper2",
}


def _read() -> dict:
    try:
        with _lock:
            if ESTADO_FILE.exists():
                data = json.loads(ESTADO_FILE.read_text())
                for k, v in _DEFAULTS.items():
                    data.setdefault(k, v)
                return data
    except Exception:
        pass
    return dict(_DEFAULTS)


def _write(data: dict):
    with _lock:
        # Solo las claves que siguen siendo de este archivo: cualquier resto de
        # versiones anteriores desaparece en la primera escritura.
        limpio = {k: data.get(k, v) for k, v in _DEFAULTS.items()}
        ESTADO_FILE.write_text(json.dumps(limpio, indent=2))


# ── Migración única del estado de sensores ────────────────────────────────────
def _migrar_estado_legado() -> None:
    """Se lleva puerta_abierta/tamper1_abierto/tamper2_abierto a sensor_states y
    reescribe el archivo con solo lo que sigue siendo suyo.

    Se ejecuta al importar y es idempotente: en cuanto el archivo queda limpio,
    la primera comprobación sale sin tocar nada. Un valor que ya exista en
    sensor_states NO se pisa — manda el destino, que es el que está en uso.

    Corre en el import a propósito, sin script que haya que lanzar a mano: es la
    misma idea que _apply_stored_overrides() en devices/registry.py.
    """
    if not ESTADO_FILE.exists():
        return
    try:
        crudo = json.loads(ESTADO_FILE.read_text())
    except Exception:
        return
    if not isinstance(crudo, dict):
        return

    sobrantes = set(crudo) - set(_DEFAULTS)
    if not sobrantes:
        return

    # Copia de seguridad antes de reescribir: es el fichero del sistema de
    # alarma, y esta migración solo pasa una vez.
    try:
        shutil.copy2(ESTADO_FILE, f"{ESTADO_FILE}.bak.{time.strftime('%Y%m%d%H%M%S')}")
    except Exception as e:
        print(f"⚠️ No se pudo respaldar {ESTADO_FILE}: {e}")

    ya_guardados = nodes_store.get_all_sensor_states()
    movidos = []
    for clave, sensor_id in _LEGADO_A_SENSOR.items():
        if clave in crudo and sensor_id not in ya_guardados:
            nodes_store.set_sensor_state(sensor_id, bool(crudo[clave]))
            movidos.append(f"{sensor_id}={bool(crudo[clave])}")

    _write(crudo)
    print(
        f"✅ estado_seguridad.json migrado: {len(sobrantes)} claves fuera"
        + (f", estado movido a sensor_states ({', '.join(movidos)})" if movidos else "")
    )


# ── Sistema armado ─────────────────────────────────────────────────────────
def get_sistema_armado() -> bool:
    return _read().get("sistema_armado", False)


def set_sistema_armado(value: bool):
    data = _read()
    data["sistema_armado"] = value
    _write(data)


def toggle_sistema_armado() -> bool:
    data = _read()
    nuevo = not data.get("sistema_armado", False)
    data["sistema_armado"] = nuevo
    _write(data)
    return nuevo


_migrar_estado_legado()
