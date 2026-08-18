#!/usr/bin/env python
"""Rescate de permisos desde la consola, sin pasar por el panel.

Existe por un caso concreto: si el bloqueo está en vigor y ningún dispositivo
tiene rol de administrador —porque la suscripción push cambió, porque se borró
el fichero, porque se estrenó esto un mal día— NO hay forma de arreglarlo desde
la interfaz, porque la pantalla que lo arregla es justo la que pide ser
administrador. Esto es esa puerta de servicio.

    .venv/bin/python scripts/acceso.py listar
    .venv/bin/python scripts/acceso.py rol <nombre-o-id> admin
    .venv/bin/python scripts/acceso.py estricto off
    .venv/bin/python scripts/acceso.py admin-a-todos      # último recurso

Se ejecuta en el servidor, así que quien puede usarlo ya tiene acceso a la
máquina; no añade ningún camino nuevo para entrar desde fuera.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noxuscmmd.domains.auth import store  # noqa: E402


def _fecha(marca):
    if not marca:
        return "nunca"
    from datetime import datetime
    return datetime.fromtimestamp(marca).strftime("%d/%m/%Y %H:%M")


def listar():
    print(f"Bloqueo de permisos: {'EN VIGOR' if store.estricto() else 'en rodaje (no impide nada)'}")
    dispositivos = store.todos()
    if not dispositivos:
        print("\nNo hay ningún dispositivo dado de alta todavía.")
        return
    print(f"\n{'ROL':<10} {'NOMBRE':<22} {'VISTO':<18} ID")
    print("-" * 78)
    for d in dispositivos:
        rol = store.rol_de(d["id"])
        marca = "*" if rol != d.get("rol") else " "
        print(f"{rol:<9}{marca} {d.get('nombre') or '(sin nombre)':<22} "
              f"{_fecha(d.get('visto')):<18} {d['id']}")
    if any(store.rol_de(d["id"]) != d.get("rol") for d in dispositivos):
        print("\n* el rol guardado ya no vale: se le pasó la caducidad")
    admins = [d for d in dispositivos if store.rol_de(d["id"]) == store.ADMIN]
    if not admins:
        print("\n⚠️  NO hay ningún administrador. Si el bloqueo está en vigor, "
              "nadie puede tocar la configuración desde el panel.")


def _buscar(clave: str):
    if store.dispositivo(clave):
        return clave
    id_d, _ = store.por_nombre(clave)
    return id_d


def poner_rol(clave: str, rol: str):
    if rol not in store.ROLES:
        print(f"Rol desconocido: {rol}. Son: {', '.join(store.ROLES)}")
        return 1
    id_d = _buscar(clave)
    if not id_d:
        print(f"No encuentro ningún dispositivo que sea «{clave}».")
        print("Mira los que hay con:  .venv/bin/python scripts/acceso.py listar")
        return 1
    # La caducidad se quita al cambiar de rol a mano: si alguien sube a un
    # invitado a familia, no tendría sentido que siguiera cayéndose la hora.
    store.actualizar(id_d, rol=rol, caduca=None)
    d = store.dispositivo(id_d)
    print(f"«{d.get('nombre') or id_d}» pasa a {store.NOMBRES_DE_ROL[rol]}.")
    return 0


def estricto(valor: str):
    encender = valor.lower() in ("on", "si", "sí", "true", "1")
    store.poner_estricto(encender)
    if encender:
        admins = [d for d in store.todos() if store.rol_de(d["id"]) == store.ADMIN]
        print("Bloqueo EN VIGOR." if admins else
              "Bloqueo EN VIGOR, pero ¡ojo!: no hay ningún administrador.")
    else:
        print("Bloqueo en rodaje: se apunta quién haría qué, pero no se impide nada.")
    return 0


def admin_a_todos():
    """Último recurso: deja a todos los dispositivos conocidos como
    administradores. Para salir del paso, no para quedarse así."""
    dispositivos = store.todos()
    if not dispositivos:
        print("No hay dispositivos que promover.")
        return 1
    for d in dispositivos:
        store.actualizar(d["id"], rol=store.ADMIN, caduca=None)
    print(f"{len(dispositivos)} dispositivos son ahora administradores.")
    print("Repasa la lista y baja los que no deban serlo.")
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "ayuda"):
        print(__doc__)
        return 0
    orden = args[0]
    if orden == "listar":
        listar()
        return 0
    if orden == "rol" and len(args) == 3:
        return poner_rol(args[1], args[2])
    if orden == "estricto" and len(args) == 2:
        return estricto(args[1])
    if orden == "admin-a-todos":
        return admin_a_todos()
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
