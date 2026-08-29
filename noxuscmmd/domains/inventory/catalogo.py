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
from ..automations import store as automations_store
from ..security import groups_store
from ..devices import alexa_catalog_store, comandos
from . import red, store
from ..entities.catalog import common_fields

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
    ("accesorios", "Accesorios", "box"),
    ("estancias", "Estancias", "house"),
    ("grupos", "Grupos de alarma", "layers"),
    ("automatizaciones", "Automatizaciones", "workflow"),
    ("carpetas", "Carpetas de automatizaciones", "folder"),
    ("planos", "Planos", "map"),
    ("widgets", "Widgets del resumen", "layout-grid"),
    ("botones", "Botones y mandos", "square-mouse-pointer"),
    ("metricas", "Paneles de métricas", "chart-no-axes-combined"),
    ("voz", "Comandos de voz", "mic"),
    ("alexa", "Elementos publicados en Alexa", "audio-lines"),
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


def _fila_base(elemento_id: str, nombre: str, campos: dict,
               collection: str, item: dict, family: str, source: str = "managed") -> dict:
    fila = {
        "id": elemento_id,
        "nombre": _texto(nombre),
        "modelo": _texto(campos.get("modelo")),
        "ubicacion": _texto(campos.get("ubicacion")),
        "notas": (campos.get("notas") or "").strip(),
    }
    fila.update(common_fields(collection, item, family=family, source=source))
    return fila


def _fila_config(item: dict, collection: str, family: str, manual: dict,
                 *, nombre: str = "", parent_id: str = "") -> dict:
    """Fila para configuración sin hardware: conserva el mismo contrato.

    Estas entidades también tienen identidad, ficha y borrado. Solo cambian
    las columnas que inventario enseña, no la forma con la que se manejan.
    """
    entity_id = str(item.get("id") or "")
    campos = manual.get(entity_id, {})
    fila = _fila_base(entity_id, nombre or item.get("name") or item.get("nombre")
                      or item.get("label") or item.get("frase") or item.get("title")
                      or entity_id, campos, collection, item, family)
    fila.update(common_fields(collection, item, family=family, physical=False,
                              parent_id=parent_id))
    return fila


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

        fila = _fila_base(h["id"], h.get("name", ""), campos, "hosts", h, "equipos")
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

    # Las estancias tambien son entidades globales documentables.
    for room in datos.get("rooms", []):
        campos = manual.get(room["id"], {})
        fila = _fila_base(room["id"], room.get("name", ""), campos,
                          "rooms", room, "estancias")
        fila.update({"tipo": _texto(room.get("kind"))})
        tablas["estancias"].append(fila)

    # ── Nodos (las placas que llevan sensores, relés y luces) ────────────
    for n in datos.get("nodes", []):
        campos = manual.get(n["id"], {})
        ip = (n.get("ip") or "").strip()
        fila = _fila_base(n["id"], n.get("name", ""), campos, "nodes", n, "nodos")
        fila.update({
            "ip_local": _manual(campos, "ip_manual", ip),
            "mac": _manual(campos, "mac_manual", arp.get(ip, "")),
            "tipo": _texto(n.get("kind")),
        })
        tablas["nodos"].append(fila)

    # ── Sensores (los de alta a mano y los de fábrica) ───────────────────
    for collection in ("sensors", "factory_sensors"):
        for s in datos.get(collection, []):
            campos = manual.get(s["id"], {})
            fila = _fila_base(s["id"], s.get("name", ""), campos, collection, s,
                              "sensores")
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
        fila = _fila_base(d["id"], d.get("name", ""), campos, "doors", d, "cerraderos")
        fila.update({
            "nodo": _texto(d.get("node_name") or d.get("node_id")),
            "pin": _texto(d.get("pin")),
            "pulso": _texto(f"{d.get('pulse_seconds', 2)} s"),
        })
        tablas["cerraderos"].append(fila)

    # ── Luces ────────────────────────────────────────────────────────────
    for l in datos.get("lights", []):
        campos = manual.get(l["id"], {})
        fila = _fila_base(l["id"], l.get("name", ""), campos, "lights", l, "luces")
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
        if not nodes_store.es_luz(l):
            accesorio = dict(fila)
            accesorio["entity_family"] = "accesorios"
            accesorio["entity_inventory_family"] = "accesorios"
            tablas["accesorios"].append(accesorio)

    # ── Cámaras ──────────────────────────────────────────────────────────
    for collection in ("cameras", "factory_cameras"):
        for c in datos.get(collection, []):
            campos = manual.get(c["id"], {})
            fila = _fila_base(c["id"], c.get("name", ""), campos, collection, c,
                              "camaras")
            origen = (c.get("stream_src") or "").strip()
            fila.update({
                "origen": _texto(origen or ("Tuya" if c.get("tuya_device_id") else "")),
                "ptz": "sí" if c.get("has_ptz") else "no",
            })
            tablas["camaras"].append(fila)

    # ── Mandos ───────────────────────────────────────────────────────────
    for m in datos.get("ir_remotes", []):
        campos = manual.get(m["id"], {})
        fila = _fila_base(m["id"], m.get("name", ""), campos, "ir_remotes", m, "mandos")
        fila.update({"botones": _texto(len(m.get("buttons", []) or []))})
        tablas["mandos"].append(fila)

    # ── Configuración global ─────────────────────────────────────────────
    # Las colecciones viven en stores distintos por razones operativas, pero
    # en Inventario se tratan exactamente como el resto: misma identidad,
    # ficha documental y baja centralizada con confirmación.
    grupos = groups_store.read_all()
    for grupo in grupos:
        fila = _fila_config(grupo, "groups", "grupos", manual)
        fila.update({
            "miembros": _texto(len(grupo.get("members", []))),
            "principal": "sí" if grupo.get("is_principal") else "no",
            "armado": "sí" if grupo.get("armed") else "no",
        })
        tablas["grupos"].append(fila)

    reglas = automations_store.read_all()
    for regla in reglas:
        fila = _fila_config(regla, "rules", "automatizaciones", manual)
        fila.update({
            "activa": "sí" if regla.get("enabled") else "no",
            "disparadores": _texto(len(regla.get("triggers", []))),
            "acciones": _texto(len(regla.get("actions", []))),
        })
        tablas["automatizaciones"].append(fila)

    for carpeta in automations_store.list_folders():
        fila = _fila_config(carpeta, "folders", "carpetas", manual)
        fila["reglas"] = _texto(sum(1 for r in reglas
                                    if r.get("folder_id") == carpeta["id"]))
        tablas["carpetas"].append(fila)

    for plano in datos.get("planos", []):
        fila = _fila_config(plano, "planos", "planos", manual)
        fila.update({
            "medidas": _texto(f"{plano.get('ancho', 0)} × {plano.get('alto', 0)}"),
            "principal": "sí" if plano.get("principal") else "no",
            "iconos": _texto(len(nodes_store.elementos_de_plano(plano["id"]))),
        })
        tablas["planos"].append(fila)

    for widget in datos.get("overview_widgets", []):
        fila = _fila_config(widget, "overview_widgets", "widgets", manual)
        fila.update({"tipo": _texto(widget.get("kind")),
                     "destino": _texto(widget.get("target_id"))})
        tablas["widgets"].append(fila)

    for boton in datos.get("host_buttons", []):
        fila = _fila_config(boton, "host_buttons", "botones", manual,
                            nombre=boton.get("label", ""),
                            parent_id=boton.get("host_id", ""))
        fila.update({"tipo": _texto(boton.get("kind")),
                     "padre": _texto(boton.get("host_id"))})
        tablas["botones"].append(fila)
    for mando in datos.get("ir_remotes", []):
        for boton in mando.get("buttons", []):
            fila = _fila_config(boton, "ir_buttons", "botones", manual,
                                nombre=boton.get("label", ""), parent_id=mando["id"])
            fila.update({"tipo": _texto(boton.get("kind")),
                         "padre": _texto(mando.get("name"))})
            tablas["botones"].append(fila)

    for panel in datos.get("metricas_paneles", []):
        fila = _fila_config(panel, "metricas_paneles", "metricas", manual)
        fila.update({"forma": _texto(panel.get("forma")),
                     "medida": _texto(panel.get("medida")),
                     "dias": _texto(panel.get("dias"))})
        tablas["metricas"].append(fila)

    for comando in datos.get("comandos_voz", []):
        fila = _fila_config(comando, "comandos_voz", "voz", manual,
                            nombre=comando.get("frase", ""))
        fila.update({"comando": _texto(comando.get("comando"))})
        tablas["voz"].append(fila)

    etiquetas_comandos = {item["id"]: item["etiqueta"]
                          for item in comandos.comandos()}
    try:
        elementos_alexa = alexa_catalog_store.listar()
    except alexa_catalog_store.ArchivoCorrupto as error:
        print(f"⚠️ Inventario: catálogo Alexa no disponible: {error}")
        elementos_alexa = []
    for elemento in elementos_alexa:
        fila = _fila_config(elemento, "alexa_endpoints", "alexa", manual)
        if elemento.get("behavior") == "action":
            comando = etiquetas_comandos.get(
                elemento.get("command"), "⚠ acción inexistente")
            comportamiento = "acción"
            frase = f"Alexa, enciende {elemento.get('name', '')}"
        else:
            comando = "ON: " + etiquetas_comandos.get(
                elemento.get("on_command"), "⚠ inexistente")
            comando += " · OFF: " + etiquetas_comandos.get(
                elemento.get("off_command"), "⚠ inexistente")
            comportamiento = "encender / apagar"
            frase = f"Alexa, enciende/apaga {elemento.get('name', '')}"
        fila.update({"comportamiento": comportamiento,
                     "accion": comando, "frase_alexa": frase})
        tablas["alexa"].append(fila)

    # ── Sueltos ──────────────────────────────────────────────────────────
    for f in store.sueltos():
        fila = _fila_base(f["id"], f.get("nombre", ""), f, "inventory", f, "sueltos", "manual")
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
                  "lights", "cameras", "factory_cameras", "ir_remotes",
                  "host_buttons", "overview_widgets", "metricas_paneles",
                  "planos", "comandos_voz"):
        for item in datos.get(clave, []) or []:
            vivos.add(item.get("id", ""))
    for remote in datos.get("ir_remotes", []) or []:
        vivos.update(b.get("id", "") for b in remote.get("buttons", []))
    vivos.update(g.get("id", "") for g in groups_store.read_all())
    try:
        vivos.update(r.get("id", "") for r in automations_store.read_all())
        vivos.update(c.get("id", "") for c in automations_store.list_folders())
    except automations_store.ArchivoCorrupto:
        # Un inventario no puede declarar huérfanas las fichas de reglas si el
        # archivo está dañado: la reparación debe conservar toda la evidencia.
        pass
    try:
        vivos.update(item.get("id", "") for item in alexa_catalog_store.listar())
    except alexa_catalog_store.ArchivoCorrupto:
        # No limpiar documentación mientras no se pueda demostrar qué ids
        # faltan. Un catálogo dañado no equivale a un catálogo vacío.
        vivos.update(store.leer().get("campos", {}).keys())
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
