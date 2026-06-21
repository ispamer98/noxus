import asyncio
import paho.mqtt.client as mqtt
import time
from .shared_state import set_puerta_abierta

class MQTTClient:
    def __init__(self, broker, port, topic_puerta, state_instance=None):
        self.broker = broker
        self.port = port
        self.topic_puerta = topic_puerta
        self.state = state_instance  # Guardado por compatibilidad, no se usa para la UI
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.ultimo_estado = None
        self.ultimo_timestamp = 0

    def on_connect(self, client, userdata, flags, rc):
        print(f"✅ Conectado MQTT (código {rc})")
        client.subscribe(self.topic_puerta)

    def on_message(self, client, userdata, msg):
        if msg.topic == self.topic_puerta:
            ahora = time.time()
            payload = msg.payload.decode()
            abierta = (payload == "ON")
            
            # Filtro anti-rebote MQTT
            if abierta == self.ultimo_estado and (ahora - self.ultimo_timestamp) < 0.5:
                return
                
            self.ultimo_estado = abierta
            self.ultimo_timestamp = ahora
            print(f"📨 [{ahora:.3f}] MQTT recibido: {payload} -> abierta={abierta}")
            
            # 🟢 Escribe directo en la fuente de verdad (estado_seguridad.json)
            set_puerta_abierta(abierta)

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


# Fuente global de inicialización (Acepta state_instance de forma opcional)
_mqtt_client_instance = None

def get_mqtt_client(broker, port, topic, state_instance=None):
    global _mqtt_client_instance
    if _mqtt_client_instance is None:
        _mqtt_client_instance = MQTTClient(broker, port, topic, state_instance)
        _mqtt_client_instance.start()
    return _mqtt_client_instance