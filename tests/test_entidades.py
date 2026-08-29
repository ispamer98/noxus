"""Contrato común y ciclo de vida de entidades configurables.

Solo toca la CasaDePruebas. No ejecuta automatizaciones ni manda MQTT, SSH,
infrarrojos o acciones de voz.
"""
from tests.comun import Caso

from noxuscmmd.domains.automations import store as automations_store
from noxuscmmd.domains.entities import service
from noxuscmmd.domains.inventory import catalogo
from noxuscmmd.domains.nodes import store as nodes_store
from noxuscmmd.domains.security import groups_store


def _contrato_y_borrado() -> Caso:
    c = Caso("Entidades globales e inventario")
    grupo = groups_store.add_group("Grupo de prueba")
    carpeta = automations_store.add_folder("Carpeta de prueba")
    regla = automations_store.add_rule(name="Regla de prueba", folder_id=carpeta["id"])
    mando = nodes_store.add_ir_remote("Mando de prueba")
    tecla = nodes_store.add_ir_button(mando["id"], "Tecla de prueba", "circle", "")
    boton = nodes_store.add_host_button("host_prueba", "Botón de prueba", "ssh_command", "true")
    widget = nodes_store.add_widget("action_view", "logs", "Registros", "scroll-text")
    panel = nodes_store.add_panel("Panel de prueba", "linea", "alarma")
    voz = nodes_store.add_comando_voz("frase de prueba", "action_logs")
    plano = nodes_store.add_plano("Plano de prueba", "prueba.png", 100, 100)

    try:
        tablas = catalogo.construir()
        filas = [fila for tabla in tablas.values() for fila in tabla]
        por_id = {fila["entity_id"]: fila for fila in filas}
        esperados = {
            grupo["id"]: "groups", carpeta["id"]: "folders", regla["id"]: "rules",
            mando["id"]: "ir_remotes", tecla["id"]: "ir_buttons",
            boton["id"]: "host_buttons", widget["id"]: "overview_widgets",
            panel["id"]: "metricas_paneles", voz["id"]: "comandos_voz",
            plano["id"]: "planos",
        }
        for entity_id, collection in esperados.items():
            fila = por_id.get(entity_id, {})
            c.revisar(f"{collection} entra en Inventario",
                      fila.get("entity_collection"), collection)
            c.cierto(f"{collection} tiene contrato común",
                     all(clave in fila for clave in (
                         "entity_id", "entity_name", "entity_family",
                         "entity_collection", "entity_capabilities",
                         "entity_can_delete")))

        borrados = (
            ("host_buttons", boton["id"]), ("ir_buttons", tecla["id"]),
            ("overview_widgets", widget["id"]), ("metricas_paneles", panel["id"]),
            ("comandos_voz", voz["id"]), ("rules", regla["id"]),
            ("folders", carpeta["id"]), ("groups", grupo["id"]),
            ("planos", plano["id"]),
        )
        for collection, entity_id in borrados:
            c.revisar(f"borrado central de {collection}",
                      service.delete(collection, entity_id), True)
        vivos = {fila["entity_id"] for tabla in catalogo.construir().values()
                 for fila in tabla}
        c.revisar("las bajas desaparecen del inventario",
                  any(entity_id in vivos for _, entity_id in borrados), False)
    finally:
        # Las bajas son idempotentes; este bloque deja la casa de pruebas limpia
        # también si falla una comprobación intermedia.
        for collection, entity_id in (
            ("host_buttons", boton["id"]), ("ir_buttons", tecla["id"]),
            ("overview_widgets", widget["id"]), ("metricas_paneles", panel["id"]),
            ("comandos_voz", voz["id"]), ("rules", regla["id"]),
            ("folders", carpeta["id"]), ("groups", grupo["id"]),
            ("planos", plano["id"]), ("ir_remotes", mando["id"]),
        ):
            service.delete(collection, entity_id)
    return c


def ejecutar() -> list[Caso]:
    return [_contrato_y_borrado()]
