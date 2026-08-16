"""
Un único sitio que pone al día TODAS las copias del nombre de un elemento.

El problema que resuelve: media docena de sitios guardan el nombre (y a veces
el icono) de otro elemento copiado, no referenciado. Es a propósito —cruzar
listas reactivas de tres ficheros distintos al pintar cada fila sería un
disparate—, pero tiene el precio de siempre: en cuanto renombras algo, las
copias se quedan con el nombre viejo y acabas con dos o tres nombres para la
misma cosa según por dónde mires.

Dónde había copias:

  · nodos_dinamicos.json → sensores/puertas/luces guardan `node_name`.
  · nodos_dinamicos.json → cada widget del Resumen guarda `label` e `icon`.
  · grupos_armado.json   → cada miembro de un grupo guarda su `name`.
  · control_accesos.json → cada puerta de un nivel guarda su `name`, y cada
                           credencial guarda el `level_name`.

Y el mismo problema al borrar: la referencia se queda huérfana. Un widget
apuntando a una cámara borrada, un miembro de grupo que ya no existe (que era
justo lo que hacía salir nombres fantasma en el registro de armado).

sincronizar() repasa las cuatro y las deja como el original. Es idempotente y
solo escribe si algo estaba mal, así que se puede llamar después de cualquier
alta, baja o edición sin pensarlo — que es exactamente lo que hace
NodesState._reload().
"""
from . import store
from ..devices import registry
from ..security import groups_store
from ..access import store as access_store

# Qué tipo de cosa apunta cada clase de widget. Los que no están aquí no tienen
# target (contadores generales, "ir a una pestaña"...) y no hay nada que
# sincronizar en ellos.
WIDGET_TARGET = {
    "action_group": "group", "stat_group": "group",
    "action_camera": "camera",
    "action_door": "door", "stat_door": "door",
    "action_light": "light", "stat_light": "light",
    "stat_sensor": "factory_entity",
    "stat_sensor_dyn": "sensor",
    "stat_host": "host", "stat_custom_host": "host", "stat_host_temp": "host",
    "action_rdp": "host", "action_host_shutdown": "host", "action_host_wol": "host",
    "action_host_button": "host_button",
    "stat_automation": "automation",
    "action_view": "view",
    "action_ir_button": "ir_button",
}

VISTAS = {
    "overview": "Resumen", "alarm": "Alarma", "groups": "Grupos", "floor_plan": "Plano",
    "video_wall": "Mural",
    "cctv": "CCTV", "access": "Accesos", "lights": "Luces", "equipment": "Equipos",
    "logs": "Registros",
    "ir_remotes": "Mandos", "automations": "Automatizaciones",
    # "settings_hub" no es una pantalla con contenido propio (ver
    # ui/dashboard/views/settings_hub.py): es el punto de entrada a las cinco
    # de arriba. Se puede referenciar igual desde un widget "Ir a Ajustes".
    "settings_hub": "Ajustes",
}

# Icono de cada tipo de widget. Solo dos lo sacan del propio elemento (las
# cámaras y los equipos); el resto es fijo por familia.
_ICONO_FIJO = {
    "door": "door-open", "light": "lightbulb", "group": "layers",
    "sensor": "radar", "factory_entity": "activity", "view": "layout-grid",
    "host_button": "square-mouse-pointer", "automation": "workflow",
}


def _catalogo() -> dict[str, dict]:
    """id -> {"name", "icon"} de todo lo que se puede referenciar."""
    datos = store.read_all()
    catalogo: dict[str, dict] = {}

    # Entidades literales del registry (cámaras fijas, relés...) primero, para
    # que las del almacén las pisen si comparten id.
    for eid, entidad in registry.DEVICES.items():
        catalogo[eid] = {"name": entidad.name, "icon": getattr(entidad, "icon", None) or ""}

    for coleccion in ("hosts", "nodes", "sensors", "factory_sensors", "doors",
                      "lights", "cameras", "factory_cameras", "rooms", "host_buttons"):
        for item in datos[coleccion]:
            # Los botones de equipo guardan su texto en "label", no en "name"
            # — es el único de la lista, de ahí el fallback.
            catalogo[item["id"]] = {
                "name": item.get("name") or item.get("label") or "",
                "icon": item.get("icon") or item.get("floor_icon") or "",
            }
    for grupo in groups_store.read_all():
        catalogo[grupo["id"]] = {"name": grupo["name"], "icon": "layers"}
    for nivel in access_store.read_all()["levels"]:
        catalogo[nivel["id"]] = {"name": nivel["name"], "icon": "key-round"}

    # Las teclas de los mandos se indexan por su id COMPUESTO ("mando:tecla"),
    # tal cual lo guarda el widget — un id de por sí nunca lleva ":", así que
    # no hay riesgo de que choque con ninguno de los de arriba. El icono es el
    # del MANDO (TV, ventilador...), no uno fijo por familia: cada aparato es
    # el suyo, y antes de esto todas las teclas salían con un icono de
    # televisor aunque el mando fuera de un ventilador.
    for remoto in datos["ir_remotes"]:
        for boton in remoto.get("buttons", []):
            catalogo[f"{remoto['id']}:{boton['id']}"] = {
                "name": f"{remoto['name']} · {boton['label']}",
                "icon": remoto.get("icon") or "tv",
            }

    # Import perezoso, no arriba del módulo: nodes/ no depende de
    # automations/ (es al revés). Solo hace falta esto para que un widget
    # "Estado de una automatización" se mantenga al día con su nombre.
    from ..automations import store as auto_store
    try:
        for regla in auto_store.read_all():
            catalogo[regla["id"]] = {"name": regla["name"], "icon": regla.get("icon") or "workflow"}
    except auto_store.ArchivoCorrupto:
        pass
    return catalogo


def etiqueta_widget(kind: str, target_id: str, catalogo: dict | None = None) -> tuple[str, str]:
    """(etiqueta, icono) que le toca a un widget AHORA MISMO.

    La usan tanto el alta de un widget como la sincronización, y ese es el
    punto: si el alta calculase la etiqueta por su cuenta y la sincronización
    por la suya, tarde o temprano dejarían de coincidir y un widget cambiaría
    de nombre solo al recargar."""
    tipo = WIDGET_TARGET.get(kind)
    if tipo is None:
        return "", ""
    if tipo == "view":
        return VISTAS.get(target_id, target_id), "layout-grid"

    entrada = (catalogo if catalogo is not None else _catalogo()).get(target_id)
    if entrada is None:
        return "", ""
    if kind == "action_rdp":
        return entrada["name"], "monitor-play"
    if tipo == "host":
        return entrada["name"], entrada["icon"] or "server"
    if tipo == "camera":
        return entrada["name"], entrada["icon"] or "video"
    if tipo == "ir_button":
        return entrada["name"], entrada["icon"] or "tv"
    return entrada["name"], _ICONO_FIJO.get(tipo, "activity")


def _existe(target_id: str, kind: str, catalogo: dict) -> bool:
    """Un widget sin target (un contador general) siempre "existe"; uno de
    pestaña vale si la pestaña sigue estando."""
    tipo = WIDGET_TARGET.get(kind)
    if tipo is None:
        return True
    if tipo == "view":
        return target_id in VISTAS
    return target_id in catalogo


def _sincronizar_nodos(catalogo: dict) -> bool:
    """node_name de sensores/puertas/luces + etiquetas de los widgets."""
    cambios = False

    def _aplicar(datos):
        nonlocal cambios
        for coleccion in ("sensors", "doors", "lights"):
            for item in datos[coleccion]:
                nodo = catalogo.get(item.get("node_id", ""))
                if nodo and item.get("node_name") != nodo["name"]:
                    item["node_name"] = nodo["name"]
                    cambios = True

        vivos = []
        for widget in datos["overview_widgets"]:
            if not _existe(widget.get("target_id", ""), widget.get("kind", ""), catalogo):
                cambios = True  # apuntaba a algo que ya no está: se cae
                continue
            etiqueta, icono = etiqueta_widget(
                widget.get("kind", ""), widget.get("target_id", ""), catalogo
            )
            if etiqueta and (widget.get("label") != etiqueta or widget.get("icon") != icono):
                widget["label"], widget["icon"] = etiqueta, icono
                cambios = True
            vivos.append(widget)
        datos["overview_widgets"] = vivos

    store.mutar(_aplicar)
    return cambios


def _sincronizar_grupos(catalogo: dict) -> bool:
    grupos = groups_store.read_all()
    cambios = False
    for grupo in grupos:
        vivos = []
        for miembro in grupo.get("members", []):
            entrada = catalogo.get(miembro["id"])
            if entrada is None:
                cambios = True  # el sensor ya no existe
                continue
            if miembro.get("name") != entrada["name"]:
                miembro["name"] = entrada["name"]
                cambios = True
            vivos.append(miembro)
        if len(vivos) != len(grupo.get("members", [])):
            grupo["members"] = vivos
    if cambios:
        groups_store.escribir_todo(grupos)
    return cambios


def _sincronizar_accesos(catalogo: dict) -> bool:
    datos = access_store.read_all()
    cambios = False
    for nivel in datos["levels"]:
        vivas = []
        for puerta in nivel.get("doors", []):
            entrada = catalogo.get(puerta["id"])
            if entrada is None:
                cambios = True  # la puerta ya no existe
                continue
            if puerta.get("name") != entrada["name"]:
                puerta["name"] = entrada["name"]
                cambios = True
            vivas.append(puerta)
        if len(vivas) != len(nivel.get("doors", [])):
            nivel["doors"] = vivas

    niveles = {n["id"]: n["name"] for n in datos["levels"]}
    for credencial in datos["credentials"]:
        nombre = niveles.get(credencial.get("level_id", ""), "")
        if not nombre and credencial.get("level_id"):
            credencial["level_id"] = ""  # el nivel se borró
            cambios = True
        if credencial.get("level_name", "") != nombre:
            credencial["level_name"] = nombre
            cambios = True
    if cambios:
        access_store.escribir_todo(datos)
    return cambios


def _revisar_automatizaciones() -> bool:
    """Marca las reglas que apuntan a algo que ya no existe.

    Política DISTINTA a la de los widgets y los miembros de grupo, y a
    propósito: aquellos se BORRAN cuando su objetivo desaparece, pero una regla
    no. Un widget se vuelve a poner en dos clics; una automatización con sus
    disparadores, sus condiciones y su secuencia de acciones es trabajo de
    verdad, y tirarla porque alguien renombró un nodo sería inaceptable. Se
    desactiva, se explica por qué, y que decida el usuario si la arregla o la
    borra.

    Tampoco se reactiva sola cuando el objetivo vuelve: reactivar una regla que
    acciona relés sin que nadie lo pida es justo lo que no debe pasar."""
    # Import aquí dentro y no arriba: automatizaciones consume los dominios de
    # dispositivo, así que su catálogo llega hasta este mismo paquete.
    from ..automations import catalog as auto_catalog
    from ..automations import store as auto_store

    try:
        reglas = auto_store.read_all()
    except auto_store.ArchivoCorrupto:
        return False
    if not reglas:
        return False

    validas = set(auto_catalog.labels())
    cambios = False
    for regla in reglas:
        objetivos = [p["target"] for p in regla["triggers"] + regla["conditions"]]
        objetivos += [a["target"] for a in regla["actions"]]
        rotos = [o for o in objetivos if o and o not in validas]
        if not rotos:
            continue
        motivo = f"apunta a algo que ya no existe ({len(rotos)}: {rotos[0]})"
        if regla["enabled"] or regla["disabled_reason"] != motivo:
            auto_store.set_enabled(regla["id"], False, motivo)
            cambios = True
    return cambios


def sincronizar() -> bool:
    """Deja todas las copias como el original. True si hubo que tocar algo."""
    catalogo = _catalogo()
    # Sin cortocircuito (nada de `or`): todas tienen que ejecutarse aunque
    # la primera ya haya encontrado algo que corregir.
    resultados = [
        _sincronizar_nodos(catalogo),
        _sincronizar_grupos(catalogo),
        _sincronizar_accesos(catalogo),
        _revisar_automatizaciones(),
    ]
    return any(resultados)
