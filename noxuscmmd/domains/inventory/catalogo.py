"""Junta todo lo que hay en la casa en tablas por familia.

Cada familia lleva las columnas que de verdad comparten sus elementos, no un
molde común con huecos: un sensor tiene nodo y pin y no tiene IP; un equipo
tiene IP y MAC y no tiene pin. Una sola tabla para todo obligaría a dejar la
mitad de las celdas vacías en cada fila.

Los valores salen ya convertidos a texto. En esta versión de Reflex, componer
cadenas con el valor de una clave de un diccionario dentro de un rx.foreach
—sin pasarlo por .to(str)— revienta al compilar el frontend, así que la vista
recibe cadenas hechas y se limita a colocarlas.
"""
from ..nodes import store as nodes_store
from . import red, store

# (id, título, icono). El orden es el de la pantalla: primero lo que se avería
# y hay que localizar físicamente, y al final lo accesorio.
FAMILIAS = (
    ("equipos", "Equipos", "server"),
    ("nodos", "Nodos", "cpu"),
    ("sensores", "Sensores", "radar"),
    ("cerraderos", "Cerraderos y puertas", "door-open"),
    ("luces", "Luces", "lightbulb"),
    ("camaras", "Cámaras", "video"),
    ("mandos", "Mandos", "gamepad-2"),
    ("sueltos", "Otros equipos de red", "network"),
)

# Para el desplegable de "añadir elemento suelto".
FAMILIAS_SUELTAS = ("lectores", "red", "otros")
NOMBRES_SUELTAS = {
    "lectores": "Lector de tarjetas",
    "red": "Equipo de red (router, switch, repetidor)",
    "otros": "Otro",
}

_SIN_DATO = "—"


def _texto(valor) -> str:
    if valor is None:
        return _SIN_DATO
    texto = str(valor).strip()
    return texto or _SIN_DATO


def _manual(campos: dict, clave: str, descubierto: str = "") -> str:
    """Lo escrito a mano manda sobre lo descubierto.

    Al revés sería peor: la tabla ARP solo ve lo que ha hablado con el servidor
    hace un rato, así que un aparato apagado borraría el dato bueno cada vez
    que se apaga."""
    a_mano = (campos.get(clave) or "").strip()
    return a_mano or (descubierto or "").strip() or _SIN_DATO


def _estancias() -> dict[str, str]:
    return {r["id"]: r.get("name", "") for r in nodes_store.read_all().get("rooms", [])}


def _fila_base(elemento_id: str, nombre: str, campos: dict) -> dict:
    return {
        "id": elemento_id,
        "nombre": _texto(nombre),
        "modelo": _texto(campos.get("modelo")),
        "ubicacion": _texto(campos.get("ubicacion")),
        "notas": (campos.get("notas") or "").strip(),
    }


def construir() -> dict[str, list[dict]]:
    """Todas las familias con sus filas, listas para pintar."""
    datos = nodes_store.read_all()
    manual = store.leer()["campos"]
    arp = red.tabla_arp()
    estancias = _estancias()
    online = datos.get("host_online", {}) or {}

    tablas: dict[str, list[dict]] = {f[0]: [] for f in FAMILIAS}

    # ── Equipos ──────────────────────────────────────────────────────────
    for h in datos.get("hosts", []):
        campos = manual.get(h["id"], {})
        ip_ficha = (h.get("ip") or "").strip()
        nodo = red.emparejar(h.get("name", ""), ip_ficha)
        ip_lan = nodo["ip_lan"] if nodo else ""
        ip_ts = nodo["ip_tailscale"] if nodo else ""
        # Si la ficha ya lleva una IP de Tailscale, esa es la buena aunque el
        # nodo esté apagado y no se haya podido emparejar.
        if not ip_ts and red.es_de_tailscale(ip_ficha):
            ip_ts = ip_ficha
        if not ip_lan and ip_ficha and not red.es_de_tailscale(ip_ficha):
            ip_lan = ip_ficha

        fila = _fila_base(h["id"], h.get("name", ""), campos)
        fila.update({
            "ip_local": _manual(campos, "ip_manual", ip_lan),
            "ip_tailscale": _texto(ip_ts),
            "mac": _manual(
                campos, "mac_manual",
                arp.get(ip_lan, "") or h.get("mac", "")
                or (red.mac_propia() if (nodo and nodo.get("propio")) else "")),
            # El sistema operativo lo dice Tailscale, que lo sabe de verdad: el
            # campo `os` de la ficha está puesto a "linux" en todos los equipos
            # de esta instalación, iPhones incluidos, y se usa para otras cosas
            # (SSH) — corregirlo allí no toca al inventario.
            "so": _texto((nodo["so"] if nodo else "") or h.get("os", "")),
            "en_linea": "sí" if online.get(h["id"]) else "no",
        })
        tablas["equipos"].append(fila)

    # ── Nodos (las placas que llevan sensores, relés y luces) ────────────
    for n in datos.get("nodes", []):
        campos = manual.get(n["id"], {})
        ip = (n.get("ip") or "").strip()
        fila = _fila_base(n["id"], n.get("name", ""), campos)
        fila.update({
            "ip_local": _manual(campos, "ip_manual", ip),
            "mac": _manual(campos, "mac_manual", arp.get(ip, "")),
            "tipo": _texto(n.get("kind")),
        })
        tablas["nodos"].append(fila)

    # ── Sensores (los de alta a mano y los de fábrica) ───────────────────
    for s in datos.get("sensors", []) + datos.get("factory_sensors", []):
        campos = manual.get(s["id"], {})
        fila = _fila_base(s["id"], s.get("name", ""), campos)
        fila.update({
            "tipo": _texto(s.get("kind")),
            "nodo": _texto(s.get("node_name") or s.get("node_id")),
            "pin": _texto(s.get("pin")),
            "vigilado": "no" if s.get("isolated") else "sí",
        })
        tablas["sensores"].append(fila)

    # ── Cerraderos ───────────────────────────────────────────────────────
    for d in datos.get("doors", []):
        campos = manual.get(d["id"], {})
        fila = _fila_base(d["id"], d.get("name", ""), campos)
        fila.update({
            "nodo": _texto(d.get("node_name") or d.get("node_id")),
            "pin": _texto(d.get("pin")),
            "pulso": _texto(f"{d.get('pulse_seconds', 2)} s"),
        })
        tablas["cerraderos"].append(fila)

    # ── Luces ────────────────────────────────────────────────────────────
    for l in datos.get("lights", []):
        campos = manual.get(l["id"], {})
        fila = _fila_base(l["id"], l.get("name", ""), campos)
        # La estancia ya la sabe el panel: se usa como ubicación cuando no se
        # ha escrito otra a mano, para no pedir dos veces el mismo dato.
        if fila["ubicacion"] == _SIN_DATO:
            fila["ubicacion"] = _texto(estancias.get(l.get("room_id", "")))
        fila.update({
            "nodo": _texto(l.get("node_name") or l.get("node_id")),
            "pin": _texto(l.get("pin")),
            "gobierno": "por relé" if l.get("pin") else "por orden",
        })
        tablas["luces"].append(fila)

    # ── Cámaras ──────────────────────────────────────────────────────────
    for c in datos.get("cameras", []) + datos.get("factory_cameras", []):
        campos = manual.get(c["id"], {})
        fila = _fila_base(c["id"], c.get("name", ""), campos)
        origen = (c.get("stream_src") or "").strip()
        fila.update({
            "origen": _texto(origen or ("Tuya" if c.get("tuya_device_id") else "")),
            "ptz": "sí" if c.get("has_ptz") else "no",
        })
        tablas["camaras"].append(fila)

    # ── Mandos ───────────────────────────────────────────────────────────
    for m in datos.get("ir_remotes", []):
        campos = manual.get(m["id"], {})
        fila = _fila_base(m["id"], m.get("name", ""), campos)
        fila.update({"botones": _texto(len(m.get("buttons", []) or []))})
        tablas["mandos"].append(fila)

    # ── Sueltos ──────────────────────────────────────────────────────────
    for f in store.sueltos():
        fila = _fila_base(f["id"], f.get("nombre", ""), f)
        fila.update({
            "familia": _texto(NOMBRES_SUELTAS.get(f.get("familia", ""), f.get("familia"))),
            "ip_local": _texto(f.get("ip_manual")),
            "mac": _texto(f.get("mac_manual")),
        })
        tablas["sueltos"].append(fila)

    for filas in tablas.values():
        filas.sort(key=lambda f: f["nombre"].lower())
    return tablas


def ids_vivos() -> set[str]:
    """Los ids que existen ahora mismo, para poder limpiar los huérfanos."""
    datos = nodes_store.read_all()
    vivos = set()
    for clave in ("hosts", "nodes", "sensors", "factory_sensors", "doors",
                  "lights", "cameras", "factory_cameras", "ir_remotes"):
        for item in datos.get(clave, []) or []:
            vivos.add(item.get("id", ""))
    return vivos


def sin_documentar(tablas: dict[str, list[dict]]) -> int:
    """Cuántos elementos no tienen ni modelo ni ubicación.

    Es el número que dice si el inventario sirve para algo: uno con la mitad
    de las fichas en blanco no ayuda a encontrar nada el día de la avería."""
    total = 0
    for filas in tablas.values():
        for f in filas:
            if f["modelo"] == _SIN_DATO and f["ubicacion"] == _SIN_DATO:
                total += 1
    return total
