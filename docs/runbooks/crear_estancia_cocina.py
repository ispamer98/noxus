"""Crea la cocina de PRUEBA (2026-09-29): plano, estancia, luces, puerta. Todo simulado."""
import json, pathlib, sys
sys.path.insert(0, "/home/spamer/noxuscmmd")
from noxuscmmd.domains.nodes import store, planos

NODO = next(n for n in store.read_all()["nodes"] if n["name"] == "ESP32 Cocina")
img = pathlib.Path.home() / "planos-generados/cocina.jpg"
nombre, ancho, alto = planos.guardar("cocina.jpg", img.read_bytes())
plano = store.add_plano("cocina", nombre, ancho, alto)
sala = store.add_room("Cocina")
creados = {"plano": plano["id"], "imagen": nombre, "estancia": sala["id"], "nodo": NODO["id"], "refs": []}

def colocar(col, item, top, left):
    store.set_floor_position(col, item["id"], f"{top}%", f"{left}%", plano["id"])
    creados["refs"].append(f"{col}:{item['id']}")

LUCES = [  # nombre, pin, icono, top, left
    ("Luz principal cocina", "k1", "lightbulb", 50, 58),
    ("Tira LED fregadero", "k2", "lamp-wall-down", 27, 50),
    ("Tira LED cafetera y microondas", "k3", "lamp-wall-down", 34, 22),
    ("Foco techo zona cocinar", "k4", "lamp-ceiling", 40, 36),
    ("Foco techo mesa de cocina", "k5", "lamp-ceiling", 70, 48),
]
for n, pin, ic, t, l in LUCES:
    luz = store.add_light(n, NODO["id"], NODO["name"], pin, floor_icon=ic)  # sin show_on_floor: pondría la luz también en el plano principal
    colocar("lights", luz, t, l)

mag = store.add_sensor("Magnético Puerta cocina", "door", NODO["id"], NODO["name"], "mk6")
cerr = store.add_door("Puerta cocina", NODO["id"], NODO["name"], "k6")
puerta = store.add_puerta("Puerta cocina", cerr["id"], mag["id"])
colocar("puertas", puerta, 91, 27)
creados["refs"] += [f"doors:{cerr['id']}", f"sensors:{mag['id']}"]

ids_sim = {x.split(":")[1] for x in creados["refs"]}
def _apply(data):
    for col in ("lights", "doors"):
        for it in data[col]:
            if it["id"] in ids_sim:
                it["simulado"] = True
    for r in data["rooms"]:
        if r["id"] == sala["id"]:
            r["entidades"] = list(creados["refs"])
            r["equipos_vista"] = [f"nodes:{NODO['id']}"]
store._mutate(_apply)
print(json.dumps(creados, ensure_ascii=False))
