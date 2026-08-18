"""Qué ha decidido el usuario sobre la detección de movimiento. Mismo patrón
que presencia_store: poco, en su fichero, y con escritura atómica."""
import json
import os
from pathlib import Path

ARCHIVO = Path(os.getenv("MOVIMIENTO_FILE", "movimiento.json"))

_VACIO = {"activada": False, "camaras": [], "umbral": 2.0, "solo_armado": True}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            return dict(_VACIO)
        d = json.loads(ARCHIVO.read_text())
        return {
            "activada": bool(d.get("activada", False)),
            "camaras": [str(x) for x in d.get("camaras", [])],
            "umbral": float(d.get("umbral", 2.0)),
            # Por defecto SOLO con la casa armada: mirar las cámaras del salón
            # mientras la familia está dentro no es vigilar, es otra cosa.
            "solo_armado": bool(d.get("solo_armado", True)),
        }
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e} — la detección queda apagada.")
        return dict(_VACIO)


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


def poner(clave: str, valor) -> None:
    datos = leer()
    datos[clave] = valor
    escribir(datos)
