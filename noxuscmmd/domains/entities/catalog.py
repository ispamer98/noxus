"""Forma comun de cualquier elemento que conoce NoxusCmmd.

Los stores especializados conservan los campos propios del hardware; este
modulo define la envoltura comun para que las vistas no distingan entre
registry, alta web o coleccion de configuracion.
"""
from __future__ import annotations

from collections.abc import Mapping


_FAMILIA = {
    "hosts": "equipos", "nodes": "nodos", "sensors": "sensores",
    "factory_sensors": "sensores", "doors": "puertas", "lights": "luces",
    "cameras": "camaras", "factory_cameras": "camaras", "ir_remotes": "mandos",
    "rooms": "estancias", "planos": "planos", "overview_widgets": "widgets",
    "host_buttons": "botones", "ir_buttons": "botones",
    "metricas_paneles": "metricas", "comandos_voz": "voz",
    "alexa_endpoints": "alexa",
    "groups": "grupos", "rules": "automatizaciones", "folders": "carpetas",
}

_ICONO = {
    "equipos": "server", "nodos": "cpu", "sensores": "radar",
    "puertas": "door-closed", "luces": "lightbulb", "camaras": "video",
    "mandos": "gamepad-2", "estancias": "house", "planos": "map",
    "grupos": "layers", "automatizaciones": "workflow", "widgets": "layout-grid",
    "botones": "square-mouse-pointer", "metricas": "chart-no-axes-combined",
    "voz": "mic", "alexa": "audio-lines", "carpetas": "folder",
}


def _floor(item: Mapping) -> dict[str, object]:
    return {
        "top": item.get("floor_top") or "",
        "left": item.get("floor_left") or "",
        "icon": item.get("floor_icon") or "",
        "subtle": "1" if item.get("floor_subtle") else "",
        "color": item.get("floor_color") or "",
        "color_on": item.get("floor_color_on") or "",
        "positions": item.get("posiciones") or {},
    }


def common_fields(collection: str, item: Mapping, *, family: str | None = None,
                  source: str | None = None, physical: bool | None = None,
                  parent_id: str = "", can_delete: bool = True) -> dict:
    """Contrato comun de identidad, presentacion y ciclo de vida."""
    familia = family or _FAMILIA.get(collection, collection)
    origen = source or ("registry" if collection.startswith("factory_") else "managed")
    if physical is None:
        physical = familia not in {
            "planos", "grupos", "automatizaciones", "widgets", "metricas", "voz",
            "alexa",
        }
    nombre = str(item.get("name") or item.get("nombre") or item.get("title")
                 or item.get("label") or item.get("frase") or item.get("id") or "")
    tipo = str(item.get("kind") or item.get("type") or item.get("forma")
               or familia.rstrip("s"))
    icon = str(item.get("icon") or item.get("floor_icon")
               or _ICONO.get(familia, "box"))
    capabilities = ["edit", "inventory"]
    if item.get("floor_top") or item.get("floor_left") or item.get("posiciones"):
        capabilities.append("floor")
    if collection in {
        "hosts", "nodes", "sensors", "doors", "lights", "cameras",
        "factory_sensors", "factory_cameras", "ir_remotes",
    }:
        capabilities.append("control")
    if collection in {"sensors", "factory_sensors", "doors", "lights", "hosts"}:
        capabilities.append("automation")
    return {
        "entity_id": str(item.get("id") or ""),
        "entity_name": nombre,
        "entity_family": familia,
        "entity_type": tipo,
        "entity_collection": collection,
        "entity_source": origen,
        "entity_parent_id": parent_id or str(
            item.get("node_id") or item.get("room_id") or ""
        ),
        "entity_physical": bool(physical),
        "entity_icon": icon,
        "entity_floor": _floor(item),
        "entity_capabilities": capabilities,
        "entity_can_edit": True,
        "entity_can_delete": bool(can_delete),
        "entity_inventory_family": familia,
    }


def all_entities(data: Mapping, *, groups: list[Mapping] | None = None,
                 rules: list[Mapping] | None = None,
                 folders: list[Mapping] | None = None,
                 alexa_endpoints: list[Mapping] | None = None) -> list[dict]:
    """Aplana un snapshot de stores en un catalogo comun, sin escribir nada."""
    result: list[dict] = []
    for collection, items in data.items():
        if collection not in _FAMILIA or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping) or not item.get("id"):
                continue
            family = _FAMILIA[collection]
            if collection == "lights" and item.get("kind") not in (
                None, "relay", "light"
            ):
                family = "accesorios"
            result.append(common_fields(collection, item, family=family))
    for collection, items, family in (
        ("groups", groups or [], "grupos"),
        ("rules", rules or [], "automatizaciones"),
        ("folders", folders or [], "carpetas"),
        ("alexa_endpoints", alexa_endpoints or [], "alexa"),
    ):
        for item in items:
            if isinstance(item, Mapping) and item.get("id"):
                result.append(common_fields(
                    collection, item, family=family, physical=False
                ))
    return result
