#!/usr/bin/env python3
import time

import paho.mqtt.client as mqtt
from gpiozero import Button

MQTT_BROKER = "100.98.98.1"
MQTT_PORT = 1883

# (nombre para el log, pin BCM, topic MQTT)
SENSORES = [
    ("Puerta",    27, "casa/raspberry/puerta"),
    ("Tamper PC", 23, "casa/raspberry/tamper_pc"),
]

BOUNCE = 0.3


def _credenciales():
    """Usuario y contraseña del broker, de un fichero 600 junto al script."""
    import os
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mqtt_cred")
    with open(ruta) as f:
        return "raspberry", f.read().strip()


def _nuevo_cliente() -> mqtt.Client:
    """paho-mqtt 2.x exige indicar la version de la API de callbacks;
    1.x ni conoce ese parametro. Asi vale en las dos."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        return mqtt.Client()


client = _nuevo_cliente()
client.username_pw_set(*_credenciales())
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

ultimo_estado = {}


def publicar(nombre, sensor, topic):
    # is_pressed es True con el pin en HIGH (pull_up=False). En reposo el
    # pull-up externo de 1k lo mantiene HIGH => contacto abierto.
    abierto = sensor.is_pressed
    payload = "ON" if abierto else "OFF"
    if ultimo_estado.get(topic) == payload:
        return
    ultimo_estado[topic] = payload
    client.publish(topic, payload, retain=True)
    print(f"{nombre}: {payload}", flush=True)


botones = []
for nombre, pin, topic in SENSORES:
    sensor = Button(pin, pull_up=False, bounce_time=BOUNCE)

    # Argumentos por defecto para capturar por valor: sin esto los dos
    # sensores compartirian las variables del bucle y publicarian lo mismo.
    def _cb(n=nombre, s=sensor, t=topic):
        publicar(n, s, t)

    sensor.when_pressed = _cb
    sensor.when_released = _cb
    botones.append(sensor)
    publicar(nombre, sensor, topic)   # estado inicial

print(f"Vigilando {len(botones)} sensores. Ctrl+C para salir.", flush=True)
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for s in botones:
        s.close()
    client.loop_stop()
    client.disconnect()