"""
Qué pasa cuando un sensor binario cambia de estado. UN SOLO camino para todos,
vengan de donde vengan: los "de fábrica" (puerta_ppal, tamper1, tamper2) y los
dados de alta desde la web pasan por aquí exactamente igual.

Antes había dos caminos distintos y esa era la causa del clásico "unos van y
otros no":

  - Los de fábrica guardaban su abierto/cerrado en estado_seguridad.json a
    través de un par getter/setter escrito A MANO por sensor
    (_SENSOR_ACCESSORS en ../security/state.py). Añadir un sensor de fábrica
    nuevo obligaba a escribir ese par a mano, y si no estaba en el diccionario
    su estado simplemente no se guardaba en ningún sitio.
  - Su log, además, no salía del callback de MQTT sino del sync_loop de
    SecurityState, que es POR SESIÓN: con dos pestañas abiertas cada una
    llevaba su propio "último estado" y el mismo evento se registraba dos
    veces.
  - Los dados de alta desde la web guardaban en sensor_states de
    nodos_dinamicos.json y sí registraban el log en su propio callback.

Ahora el estado de TODOS vive en sensor_states y el log sale de aquí, que corre
una sola vez por proceso (hilo de paho-mqtt). Un sensor nuevo no necesita nada:
basta que el MQTTBus le tenga el topic mapeado.
"""
from . import store
from ..security import logs

# Colecciones donde buscar el elemento para nombrarlo en el log. Las luces no
# están a propósito: encender una luz no es un evento de seguridad y llenaría el
# historial.
_COLECCIONES = ("factory_sensors", "sensors", "doors")

def _categoria(coleccion: str) -> str:
    """En qué familia del registro entra un cambio de estado.

    "Puertas" es el reflejo del CONTROL DE ACCESOS: lo que el sistema manda
    abrir (un cerradero, un relé de la colección doors). Un contacto magnético
    no pinta nada ahí aunque esté en una puerta: él no abre nada, solo cuenta si
    está abierta, y eso es cosa de la alarma. Por eso un magnético que se abre
    ya no aparece en Puertas — aparece en Alarma, que es quien lo vigila.

    Antes se decidía con `coleccion == "doors" or item["kind"] == "door"`, y ese
    segundo trozo era justo el que colaba los magnéticos en Puertas."""
    return logs.PUERTAS if coleccion == "doors" else logs.ALARMA


def on_binary_sensor(entity_id: str, is_on: bool) -> None:
    """Callback síncrono desde el hilo de paho-mqtt: persiste el estado y, si de
    verdad ha cambiado, lo deja en el registro de eventos. Pintarlo es cosa del
    sync_loop de cada sesión, que relee sensor_states del disco.

    El log se escribe AQUÍ y no en GroupsState.watch_loop a propósito: allí solo
    se miran los grupos ARMADOS, así que un sensor sin grupo (o con su grupo
    desarmado) no dejaba rastro ninguno. Y se registra con el nombre del propio
    elemento y una acción genérica, para que en el historial se lea igual venga
    de donde venga.
    """
    anterior = store.get_sensor_state(entity_id)
    store.set_sensor_state(entity_id, is_on)
    if anterior == is_on:
        return

    datos = store.read_all()
    for coleccion in _COLECCIONES:
        item = next((x for x in datos[coleccion] if x["id"] == entity_id), None)
        if item is None:
            continue
        # El detalle es SOLO el nombre. El abierto/cerrado ya lo dice la acción
        # (y el icono y el color del listado), así que meterlo también en el
        # texto era leer "Puerta abierta — Puerta ABIERTA" en cada fila.
        # El autor es "sistema": esto no lo pulsa nadie, lo cuenta el sensor.
        logs.registrar(
            _categoria(coleccion),
            "ELEMENTO_ABIERTO" if is_on else "ELEMENTO_CERRADO",
            "sistema", item["name"], entidad=entity_id,
        )
        return
