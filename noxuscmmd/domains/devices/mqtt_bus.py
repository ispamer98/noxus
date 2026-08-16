"""
Cliente MQTT genérico: se suscribe a los topics de TODOS los BinarySensorEntity
del registry (hoy puerta/tamper1/tamper2) y despacha a un callback único por
id de entidad. Añadir un sensor MQTT nuevo (ej. lector de tarjetas) es añadirlo
al registry — esta clase no cambia.

Además soporta un segundo callback "dinámico" (domains/nodes) para sensores
dados de alta en caliente desde la web sobre nodos ESP32 — igual de genérico,
pero registrado en tiempo de ejecución en vez de en registry.py, y también
permite publicar comandos (abrir puerta, encender luz) hacia esos nodos.
"""
import time
import paho.mqtt.client as mqtt
from typing import Callable
from . import registry

OnBinarySensor = Callable[[str, bool], None]


class MQTTBus:
    def __init__(self, broker: str, port: int, on_binary_sensor: OnBinarySensor):
        self._on_binary_sensor = on_binary_sensor
        self._topic_to_entity = {
            e.mqtt.topic: e.id for e in registry.binary_sensors().values() if e.mqtt
        }
        self._dynamic_topic_to_entity: dict[str, str] = {}
        self._dynamic_callback: OnBinarySensor | None = None
        self._ultimo_estado: dict[str, str] = {}
        self._ultimo_timestamp = 0.0

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.broker = broker
        self.port = port

    def _on_connect(self, client, userdata, flags, rc):
        print(f"✅ Conectado MQTT (código {rc})")
        for topic in self._topic_to_entity:
            client.subscribe(topic)
        for topic in self._dynamic_topic_to_entity:
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        ahora = time.time()
        payload = msg.payload.decode()

        entity_id = self._topic_to_entity.get(msg.topic)
        callback = self._on_binary_sensor
        if entity_id is None:
            entity_id = self._dynamic_topic_to_entity.get(msg.topic)
            callback = self._dynamic_callback
        if entity_id is None or callback is None:
            return

        if payload == self._ultimo_estado.get(entity_id) and (ahora - self._ultimo_timestamp) < 0.5:
            return
        self._ultimo_estado[entity_id] = payload
        self._ultimo_timestamp = ahora

        is_on = (payload == "ON")
        print(f"📨 [{ahora:.3f}] MQTT {entity_id}: {payload} -> on={is_on}")
        callback(entity_id, is_on)

    def set_dynamic_callback(self, callback: OnBinarySensor) -> None:
        self._dynamic_callback = callback

    def subscribe_dynamic(self, topic: str, entity_id: str) -> None:
        self._dynamic_topic_to_entity[topic] = entity_id
        self.client.subscribe(topic)

    def unsubscribe_dynamic(self, topic: str) -> None:
        self._dynamic_topic_to_entity.pop(topic, None)
        self.client.unsubscribe(topic)

    def publish(self, topic: str, payload: str) -> None:
        self.client.publish(topic, payload)

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


_instance: MQTTBus | None = None


def get_mqtt_bus(broker: str, port: int, on_binary_sensor: OnBinarySensor) -> MQTTBus:
    global _instance
    if _instance is None:
        _instance = MQTTBus(broker, port, on_binary_sensor)
        _instance.start()
    return _instance


def get_running_bus() -> MQTTBus | None:
    """None si SecurityState.on_load todavía no ha arrancado el bus (arranca
    él porque es quien conoce los sensores estáticos del registry)."""
    return _instance
