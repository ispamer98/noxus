"""
Grupos de armado (zonas): colecciones de sensores — de registry.py (estáticos:
puerta_ppal, tamper1, tamper2...) o dados de alta en caliente vía
domains/nodes (dinámicos) — que se pueden armar/desarmar de forma
independiente entre sí y del armado global del sistema (SecurityState).

Persistencia igual que logs.py/nodes/store.py: JSON plano con lock de
fichero. Los miembros se guardan denormalizados (id + nombre) para no tener
que cruzar listas reactivas distintas (registry estático vs. NodesState
dinámico) al pintar la UI.
"""
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

from ...core import bus

ARCHIVO = Path(os.getenv("GRUPOS_FILE", "grupos_armado.json"))


def _read() -> list[dict]:
    if not ARCHIVO.exists():
        return []
    try:
        with open(ARCHIVO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read().strip()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        groups = json.loads(content) if content else []
    except Exception:
        groups = []
    for g in groups:
        g.setdefault("is_principal", False)
    return groups


def _write(groups: list[dict]) -> None:
    with open(ARCHIVO, "a+" if ARCHIVO.exists() else "w+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            json.dump(groups, f, indent=2, ensure_ascii=False)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    bus.publicar(bus.ENTIDADES)


def read_all() -> list[dict]:
    return _read()


def escribir_todo(groups: list[dict]) -> None:
    """Reescribe la lista entera — la usa nodes/referencias.py al poner al día
    los nombres copiados de los miembros."""
    _write(groups)


def add_group(name: str) -> dict:
    groups = _read()
    group = {
        "id": f"grupo_{uuid.uuid4().hex[:8]}",
        "name": name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "armed": False,
        "is_principal": False,
        "members": [],  # [{"id": sensor_id, "name": sensor_name}]
    }
    groups.append(group)
    _write(groups)
    return group


# ── Grupo principal ────────────────────────────────────────────────────────
# El botón de "armado general" (de siempre) no es más que armar/desarmar el
# grupo marcado como principal. Solo puede haber uno; marcar otro desmarca el
# anterior. Ver ensure_principal_group() para la migración desde el sistema
# clásico (3 sensores fijos, sin grupos) la primera vez que se usa esto.
def set_principal(group_id: str) -> None:
    groups = _read()
    for g in groups:
        g["is_principal"] = (g["id"] == group_id)
    _write(groups)


def get_principal() -> dict | None:
    return next((g for g in _read() if g["is_principal"]), None)


def ensure_principal_group() -> dict:
    """Se llama en cada arranque de sesión (idempotente). Si ya hay un grupo
    principal, no hace nada. Si no hay NINGUNO, crea "Sistema" con los 3
    sensores clásicos (puerta_ppal, tamper1, tamper2) para no perder de la
    noche a la mañana la protección que ya tenías — a partir de ahí es un
    grupo normal: puedes vaciarlo, renombrarlo o cambiar qué grupo es el
    principal cuando quieras."""
    groups = _read()
    principal = next((g for g in groups if g["is_principal"]), None)
    if principal is not None:
        return principal

    if not groups:
        nuevo = {
            "id": f"grupo_{uuid.uuid4().hex[:8]}",
            "name": "Sistema",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "armed": False,
            "is_principal": True,
            "members": [
                {"id": "puerta_ppal", "name": "Puerta principal"},
                {"id": "tamper1", "name": "Tamper1"},
                {"id": "tamper2", "name": "Tamper2"},
            ],
        }
        groups.append(nuevo)
        _write(groups)
        return nuevo

    groups[0]["is_principal"] = True
    _write(groups)
    return groups[0]


def rename_group(group_id: str, name: str) -> None:
    groups = _read()
    for g in groups:
        if g["id"] == group_id:
            g["name"] = name
    _write(groups)


def delete_group(group_id: str) -> None:
    groups = [g for g in _read() if g["id"] != group_id]
    _write(groups)


def set_group_armed(group_id: str, armed: bool) -> None:
    groups = _read()
    for g in groups:
        if g["id"] == group_id:
            g["armed"] = armed
    _write(groups)


def add_member(group_id: str, sensor_id: str, sensor_name: str) -> None:
    groups = _read()
    for g in groups:
        if g["id"] == group_id and not any(m["id"] == sensor_id for m in g["members"]):
            g["members"].append({"id": sensor_id, "name": sensor_name})
    _write(groups)


def remove_member(group_id: str, sensor_id: str) -> None:
    groups = _read()
    for g in groups:
        if g["id"] == group_id:
            g["members"] = [m for m in g["members"] if m["id"] != sensor_id]
    _write(groups)


def rename_member(sensor_id: str, nuevo_nombre: str) -> list[str]:
    """Actualiza el nombre de un elemento en TODOS los grupos donde sea miembro.
    Devuelve los nombres de los grupos tocados.

    El nombre se guarda copiado dentro del grupo (no se resuelve al pintar) para
    que la lista de miembros no tenga que cruzar el catálogo entero con un Var
    reactivo. El precio es este: hay que propagar el renombrado a mano. Sin
    esto, un sensor renombrado seguía saliendo con su nombre viejo en el grupo
    para siempre — y ese nombre es el que se lee en la alerta y en el log, así
    que avisaba de una apertura con un nombre que ya no existía en ningún sitio.
    """
    groups = _read()
    tocados = []
    for g in groups:
        for m in g["members"]:
            if m["id"] == sensor_id and m.get("name") != nuevo_nombre:
                m["name"] = nuevo_nombre
                tocados.append(g["name"])
    if tocados:
        _write(groups)
    return tocados
