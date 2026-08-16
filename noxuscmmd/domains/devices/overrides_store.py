"""
Ediciones persistentes sobre las entidades ESTÁTICAS de registry.py (server,
pc, puerta_ppal, tamper1, cam_fija...). registry.py sigue siendo la fuente
de verdad "de fábrica" (env vars); esto es una capa fina por encima que se
aplica al importar el módulo y cada vez que se guarda una edición desde la
UI — así el proceso en marcha refleja el cambio al instante, aunque la
página ya estuviera compilada (ver registry.apply_override()).

A diferencia de domains/nodes (100% dinámico, sin restart), estas entidades
viven en árboles de componentes construidos una vez en Python al arrancar
Reflex — una edición aquí persiste correctamente pero solo se ve en pantalla
tras reiniciar el proceso (exactamente igual que si se editase el .env).
"""
import fcntl
import json
import os
from pathlib import Path

ARCHIVO = Path(os.getenv("REGISTRY_OVERRIDES_FILE", "registry_overrides.json"))


def _read() -> dict:
    if not ARCHIVO.exists():
        return {}
    try:
        with open(ARCHIVO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read().strip()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return json.loads(content) if content else {}
    except Exception:
        return {}


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


_HIDDEN_KEY = "_hidden"
_ISOLATED_KEY = "_isolated"


def get_overrides() -> dict[str, dict]:
    return {k: v for k, v in _read().items() if k not in (_HIDDEN_KEY, _ISOLATED_KEY)}


def set_override(entity_id: str, **fields) -> dict:
    data = _read()
    entry = data.setdefault(entity_id, {})
    entry.update({k: v for k, v in fields.items() if v not in (None, "")})
    _write(data)
    return entry


def drop_override(entity_id: str) -> None:
    """Borra la entrada de una entidad de este almacén. Lo usa
    registry._migrate_factory_overrides() con las que ya se guardan en
    nodos_dinamicos.json: dos sitios para el mismo campo significaba que el de
    aquí, al aplicarse el último, revertía en cada reinicio lo editado desde la
    web."""
    data = _read()
    if data.pop(entity_id, None) is not None:
        _write(data)


def get_hidden_ids() -> set[str]:
    return set(_read().get(_HIDDEN_KEY, []))


def hide_entity(entity_id: str) -> None:
    data = _read()
    hidden = set(data.get(_HIDDEN_KEY, []))
    hidden.add(entity_id)
    data[_HIDDEN_KEY] = sorted(hidden)
    _write(data)


def unhide_entity(entity_id: str) -> None:
    data = _read()
    hidden = set(data.get(_HIDDEN_KEY, []))
    hidden.discard(entity_id)
    data[_HIDDEN_KEY] = sorted(hidden)
    _write(data)


def get_isolated_ids() -> set[str]:
    return set(_read().get(_ISOLATED_KEY, []))


def isolate_entity(entity_id: str) -> None:
    data = _read()
    isolated = set(data.get(_ISOLATED_KEY, []))
    isolated.add(entity_id)
    data[_ISOLATED_KEY] = sorted(isolated)
    _write(data)


def unisolate_entity(entity_id: str) -> None:
    data = _read()
    isolated = set(data.get(_ISOLATED_KEY, []))
    isolated.discard(entity_id)
    data[_ISOLATED_KEY] = sorted(isolated)
    _write(data)
