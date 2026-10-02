"""Crea el mando IR «Humidificador» (sin señales) y su accesorio (2026-10-02).

La plantilla `humidificador` tiene las 6 teclas del mando físico real (ver
remote_templates.py). Los datos en vivo se crearon con 8 teclas genéricas y se
corrigieron en sitio a estas 6 (se conservó el botón de «Encender / Apagar»).

Idempotente: si ya hay un mando llamado «Humidificador», aborta sin tocar nada.
No envía nada por IR/MQTT/SSH: solo escribe en nodos_dinamicos.json.
"""
import json, sys
sys.path.insert(0, "/home/spamer/noxuscmmd")
from noxuscmmd.domains.nodes import store

HABITACION = "room_f167e139"
PLANO = "plano_1"

if any(r["name"] == "Humidificador" for r in store.read_all()["ir_remotes"]):
    sys.exit("Ya existe un mando «Humidificador»: no se crea nada.")

mando = store.add_ir_remote("Humidificador", "droplets", plantilla="humidificador")
tecla = next(b["id"] for b in mando["buttons"] if b["label"] == "Encender / Apagar")
luz = store.add_light(
    "Humidificador", "", "?", "", room_id=HABITACION, show_on_floor=False,
    floor_icon="droplets", kind=store.LUZ_MANDO, remote_id=mando["id"],
    btn_on=tecla, btn_off=tecla, aspecto="otro", mando_modo=store.UNA_TECLA)

store.set_floor_color("lights", luz["id"], "cian")
store.set_floor_color_on("lights", luz["id"], "verde")
# Posiciones iniciales (el usuario puede haberlas movido luego). Mando junto a los otros mandos (fila de arriba a la izquierda); accesorio
# sobre la cómoda, bajo la cama, sin pisar nada.
store.set_floor_position("ir_remotes", mando["id"], "7.8%", "22%", PLANO)
store.set_floor_position("lights", luz["id"], "90.5%", "52%", PLANO)

def _apply(data):
    for r in data["rooms"]:
        if r["id"] == HABITACION:
            for ref in (f"ir_remotes:{mando['id']}", f"lights:{luz['id']}"):
                if ref not in r["entidades"]:
                    r["entidades"].append(ref)
store._mutate(_apply)
print(json.dumps({"mando": mando["id"], "boton": tecla, "luz": luz["id"]}))
# El mando se ve discreto y cian en el plano, como el del ventilador.
store._update("ir_remotes", mando["id"], {"floor_subtle": True, "floor_color": "cian"})
