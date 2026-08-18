"""
Qué ha decidido el usuario sobre la simulación de presencia. Poco y en su
propio fichero, como el resto de los ajustes de la casa: si está encendida y
qué luces puede usar.

Las luces se guardan por id y en lista: importa poder decir «solo el salón y la
cocina». La del dormitorio suele ser justo la que no se quiere encender sola.
"""
import json
import os
from pathlib import Path

ARCHIVO = Path(os.getenv("PRESENCIA_FILE", "presencia.json"))

_VACIO = {"activada": False, "luces": []}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            return dict(_VACIO)
        datos = json.loads(ARCHIVO.read_text())
        return {
            "activada": bool(datos.get("activada", False)),
            "luces": [str(x) for x in datos.get("luces", [])],
        }
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e} — la simulación queda apagada.")
        return dict(_VACIO)


def escribir(datos: dict) -> None:
    """Atómico, como todo lo que se guarda de la casa: se escribe al lado y se
    reemplaza de golpe, para que un corte no deje el fichero a medias."""
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


def activada() -> bool:
    return leer()["activada"]


def poner_activada(valor: bool) -> None:
    datos = leer()
    datos["activada"] = bool(valor)
    escribir(datos)


def luces() -> list[str]:
    return leer()["luces"]


def poner_luces(ids: list[str]) -> None:
    datos = leer()
    datos["luces"] = [str(x) for x in ids]
    escribir(datos)
