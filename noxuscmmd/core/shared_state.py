"""
shared_state.py — Fuente de verdad compartida entre todos los procesos y clientes.

Persiste en JSON para que:
- Todos los workers Reflex lean el mismo estado.
- Al abrir la app, muestra el estado correcto desde el primer frame.
- Cualquier cambio desde cualquier dispositivo se propaga a todos en ≤1.5 s.
"""

import json
import os
import threading
from pathlib import Path

ESTADO_FILE = Path(os.getenv("ESTADO_FILE", "estado_seguridad.json"))
_lock = threading.Lock()

_DEFAULTS = {
    "sistema_armado": False,
    "puerta_abierta": False,
    "notificacion_enviada": False,
}


def _read() -> dict:
    try:
        with _lock:
            if ESTADO_FILE.exists():
                data = json.loads(ESTADO_FILE.read_text())
                # Rellenar claves que pudieran faltar en archivos antiguos
                for k, v in _DEFAULTS.items():
                    data.setdefault(k, v)
                return data
    except Exception:
        pass
    return dict(_DEFAULTS)


def _write(data: dict):
    with _lock:
        ESTADO_FILE.write_text(json.dumps(data, indent=2))


# ── Sistema armado ─────────────────────────────────────────────────────────

def get_sistema_armado() -> bool:
    return _read().get("sistema_armado", False)

def set_sistema_armado(value: bool):
    data = _read()
    data["sistema_armado"] = value
    if not value:
        data["notificacion_enviada"] = False
    _write(data)

def toggle_sistema_armado() -> bool:
    data  = _read()
    nuevo = not data.get("sistema_armado", False)
    data["sistema_armado"] = nuevo
    if not nuevo:
        data["notificacion_enviada"] = False
    _write(data)
    return nuevo

# ── Puerta ─────────────────────────────────────────────────────────────────

def get_puerta_abierta() -> bool:
    return _read().get("puerta_abierta", False)

def set_puerta_abierta(value: bool):
    data = _read()
    if data.get("puerta_abierta") != value:   # solo escribir si cambió
        data["puerta_abierta"] = value
        _write(data)

# ── Notificación ───────────────────────────────────────────────────────────

def get_notificacion_enviada() -> bool:
    return _read().get("notificacion_enviada", False)

def set_notificacion_enviada(value: bool):
    data = _read()
    if data.get("notificacion_enviada") != value:
        data["notificacion_enviada"] = value
        _write(data)