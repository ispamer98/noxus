"""Operaciones comunes sobre entidades configurables.

La coleccion es parte de la identidad: evita borrar por accidente dos
elementos de dominios distintos que compartan un id.
"""
from ..nodes import store as nodes_store
from ..inventory import store as inventory_store
from ..automations import store as automations_store
from ..security import groups_store
from ..devices import alexa_catalog_store


_BORRADORES = {
    "nodes": nodes_store.delete_node,
    "sensors": nodes_store.delete_sensor,
    "factory_sensors": nodes_store.delete_factory_sensor,
    "doors": nodes_store.delete_door,
    "lights": nodes_store.delete_light,
    "cameras": nodes_store.delete_camera,
    "factory_cameras": nodes_store.delete_factory_camera,
    "hosts": nodes_store.delete_host,
    "ir_remotes": nodes_store.delete_ir_remote,
    "rooms": nodes_store.delete_room,
    "host_buttons": nodes_store.delete_host_button,
    "overview_widgets": nodes_store.delete_widget,
    "metricas_paneles": nodes_store.delete_panel,
    "planos": nodes_store.delete_plano,
    "comandos_voz": nodes_store.delete_comando_voz,
    "groups": groups_store.delete_group,
    "rules": automations_store.delete_rule,
    "folders": automations_store.delete_folder,
    "alexa_endpoints": alexa_catalog_store.borrar,
}


def delete(collection: str, entity_id: str) -> bool:
    """Borra una entidad gestionada y devuelve si la operación era conocida."""
    if collection == "inventory":
        inventory_store.borrar_suelto(entity_id)
        return True
    if collection == "ir_buttons":
        return nodes_store.delete_ir_button_by_id(entity_id)
    borrar = _BORRADORES.get(collection)
    if borrar is None:
        return False
    borrar(entity_id)
    return True
