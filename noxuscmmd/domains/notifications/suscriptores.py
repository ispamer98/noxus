"""
La lista de dispositivos que reciben avisos (suscriptores.json).

Cada dispositivo se identifica por su `endpoint` —la dirección que le da su
navegador para recibir notificaciones— y lleva el nombre que le puso quien lo
vinculó. Ese nombre es el que sale en la barra superior y el que queda escrito
en cada línea del registro, así que es la identidad del aparato dentro del
panel, no un adorno.

Se saca a módulo aparte porque ya lo leen tres sitios (el envío de avisos, la
identidad de la sesión y la ventanita de gestión) y cada uno se lo abría por su
cuenta.
"""
import json
import os

ARCHIVO = "suscriptores.json"


def leer() -> list[dict]:
    try:
        if not os.path.exists(ARCHIVO):
            return []
        with open(ARCHIVO) as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e}")
        return []


def _escribir(subs: list[dict]) -> None:
    with open(ARCHIVO, "w") as f:
        json.dump(subs, f, indent=4, ensure_ascii=False)


def nombres() -> list[str]:
    return [s["nombre_usuario"] for s in leer() if s.get("nombre_usuario")]


def buscar(endpoint: str) -> dict | None:
    return next((s for s in leer() if s.get("endpoint") == endpoint), None)


def renombrar(endpoint: str, nombre: str) -> tuple[bool, str]:
    """(salió bien, motivo si no).

    No deja dos dispositivos con el mismo nombre: el nombre es lo que se ve en
    los registros y en la lista de destinatarios de un aviso, así que dos
    iguales harían imposible saber cuál hizo qué o a cuál se está escribiendo."""
    subs = leer()
    if any(s.get("nombre_usuario") == nombre and s.get("endpoint") != endpoint for s in subs):
        return False, f"Ya hay otro dispositivo llamado «{nombre}». Ponle uno distinto."
    for s in subs:
        if s.get("endpoint") == endpoint:
            s["nombre_usuario"] = nombre
            _escribir(subs)
            return True, ""
    return False, "Este dispositivo no aparece en la lista. Prueba a activarlo de nuevo."


def eliminar(endpoint: str) -> None:
    subs = leer()
    quedan = [s for s in subs if s.get("endpoint") != endpoint]
    if len(quedan) != len(subs):
        _escribir(quedan)
