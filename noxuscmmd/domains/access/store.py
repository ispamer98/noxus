"""
Control de accesos: tarjetas/tags (credenciales) y niveles de acceso — misma
idea que cualquier app de control de accesos comercial. Un nivel agrupa
puertas (como un grupo de armado agrupa sensores); una credencial (tarjeta o
tag) identifica a una persona y pertenece a un nivel, que es lo que decide
qué puertas puede abrir.

Persistencia igual que groups_store.py/nodes/store.py: JSON plano con lock de
fichero. Las puertas dentro de un nivel se guardan denormalizadas (id +
nombre), igual que los miembros de un grupo, para no tener que cruzar con la
lista reactiva de NodesState.doors al pintar la UI.

Preparado para cuando haya un lector RFID/NFC real (ESP32 publicando el tag
leído por MQTT, mismo convenio casa/<nodo>/<señal> que el resto): ese día,
el flujo sería leer el tag -> find_credential_by_tag() -> comprobar si su
nivel concede la puerta -> NodesState.open_door(). Por ahora esto es solo la
gestión (alta/edición/borrado) de tarjetas y niveles.
"""
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

ARCHIVO = Path(os.getenv("ACCESS_CONTROL_FILE", "control_accesos.json"))


def _read() -> dict:
    if not ARCHIVO.exists():
        return {"levels": [], "credentials": []}
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
    data.setdefault("levels", [])
    data.setdefault("credentials", [])
    return data


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


def escribir_todo(data: dict) -> None:
    """Reescribe el fichero entero — la usa nodes/referencias.py al poner al
    día los nombres de puertas y niveles copiados aquí."""
    _write(data)



# ── Niveles de acceso ─────────────────────────────────────────────────────────
def add_level(name: str) -> dict:
    data = _read()
    level = {
        "id": f"nivel_{uuid.uuid4().hex[:8]}",
        "name": name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "doors": [],  # [{"id": door_id, "name": door_name}]
    }
    data["levels"].append(level)
    _write(data)
    return level


def update_level(level_id: str, name: str) -> dict | None:
    data = _read()
    updated = None
    for lv in data["levels"]:
        if lv["id"] == level_id:
            lv["name"] = name
            updated = lv
    if updated:
        for cred in data["credentials"]:
            if cred["level_id"] == level_id:
                cred["level_name"] = name
    _write(data)
    return updated


def delete_level(level_id: str) -> None:
    data = _read()
    data["levels"] = [lv for lv in data["levels"] if lv["id"] != level_id]
    # Las credenciales que apuntaban a este nivel se quedan "sin nivel" en vez
    # de referenciar un id fantasma.
    for cred in data["credentials"]:
        if cred["level_id"] == level_id:
            cred["level_id"] = ""
            cred["level_name"] = ""
    _write(data)


def add_door_to_level(level_id: str, door_id: str, door_name: str) -> None:
    data = _read()
    for lv in data["levels"]:
        if lv["id"] == level_id and not any(d["id"] == door_id for d in lv["doors"]):
            lv["doors"].append({"id": door_id, "name": door_name})
    _write(data)


def remove_door_from_level(level_id: str, door_id: str) -> None:
    data = _read()
    for lv in data["levels"]:
        if lv["id"] == level_id:
            lv["doors"] = [d for d in lv["doors"] if d["id"] != door_id]
    _write(data)


def get_level(level_id: str) -> dict | None:
    return next((lv for lv in _read()["levels"] if lv["id"] == level_id), None)


# ── Credenciales (tarjetas / tags) ────────────────────────────────────────────
def add_credential(holder_name: str, tag_id: str, level_id: str, level_name: str) -> dict:
    data = _read()
    cred = {
        "id": f"cred_{uuid.uuid4().hex[:8]}",
        "holder_name": holder_name,
        "tag_id": tag_id,
        "level_id": level_id,
        "level_name": level_name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["credentials"].append(cred)
    _write(data)
    return cred


def delete_credential(cred_id: str) -> None:
    data = _read()
    data["credentials"] = [c for c in data["credentials"] if c["id"] != cred_id]
    _write(data)


def update_credential(cred_id: str, holder_name: str, tag_id: str, level_id: str, level_name: str) -> dict | None:
    data = _read()
    updated = None
    for c in data["credentials"]:
        if c["id"] == cred_id:
            c.update({
                "holder_name": holder_name, "tag_id": tag_id,
                "level_id": level_id, "level_name": level_name,
            })
            updated = c
    _write(data)
    return updated


def find_credential_by_tag(tag_id: str) -> dict | None:
    return next((c for c in _read()["credentials"] if c["tag_id"] == tag_id), None)


def level_grants_door(level_id: str, door_id: str) -> bool:
    level = get_level(level_id)
    if not level:
        return False
    return any(d["id"] == door_id for d in level["doors"])
