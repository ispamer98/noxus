#!/usr/bin/env python3
"""
Publicador MQTT de los sensores todo/nada cableados a la Raspberry.

Sustituye al script de un solo sensor que había antes: lleva la puerta y el
tamper del PC en UN solo proceso (una conexión MQTT, un servicio systemd). Para
añadir otro sensor basta con una línea más en SENSORES — no hay que duplicar
nada ni levantar otro servicio.

Convenio de payload (el mismo que ya usa el panel, ver domains/devices/
mqtt_bus.py: `is_on = (payload == "ON")`):
    "ON"  -> contacto ABIERTO   (puerta abierta / caja del PC abierta = alarma)
    "OFF" -> contacto CERRADO   (todo en su sitio)

Cableado admitido (los dos montajes dejan el pin HIGH con el contacto abierto
y LOW al cerrarse, que es lo que espera este script):

  a) pull-up EXTERNO: resistencia de 1 kΩ entre el GPIO y 3.3V, contacto
     (reed / microswitch) entre el GPIO y GND    -> pull_up=False
  b) pull-up INTERNO: solo el contacto entre el GPIO y GND, sin resistencia
     -> pull_up=True

OJO: en gpiozero `pull_up=False` NO es "sin pull", es "pull-DOWN interno". Si
lo pones en un pin sin la resistencia externa del montaje (a), el pull-down
clava el pin a LOW para siempre y el sensor no cambia nunca de estado. Ante la
duda, `pull_up=True` es la opción segura: funciona en los dos montajes, porque
el pull-up interno (~50 kΩ) suma con el externo en vez de pelearse con él.

Los relés (luces, ventilador) NO se controlan desde aquí: el panel los mueve
por SSH con `raspi-gpio set <pin> op dh|dl` (ver domains/devices/gpio_bus.py).
Este script solo publica sensores.
"""
import time

import paho.mqtt.client as mqtt
from gpiozero import Button

MQTT_BROKER = "100.98.98.1"
MQTT_PORT = 1883

# (nombre para el log, pin BCM, topic MQTT, pull_up)
# El pull va por sensor, no global: no todos los pines tienen la resistencia
# externa de 1 kΩ. Ver el cableado en el docstring de arriba.
SENSORES = [
    ("Puerta",    27, "casa/raspberry/puerta",    False),  # reed, con 1 kΩ a 3.3V
    ("Tamper PC", 23, "casa/raspberry/tamper_pc", True),   # sin resistencia externa
]

# Anti-rebote: 0.3s va bien tanto para un reed de puerta como para el
# microswitch de una caja de PC.
BOUNCE = 0.3


def _nuevo_cliente() -> mqtt.Client:
    """paho-mqtt 2.x exige indicar la versión de la API de callbacks; 1.x ni
    conoce ese parámetro. Así el script vale en las dos sin tocar nada."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        return mqtt.Client()


client = _nuevo_cliente()
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

ultimo_estado: dict[str, str] = {}


def publicar(nombre: str, sensor: Button, topic: str) -> None:
    # is_pressed va referido al estado ACTIVO del pin, que gpiozero invierte
    # según el pull: HIGH con pull_up=False, LOW con pull_up=True. Aquí lo que
    # importa es el nivel real, porque en los dos montajes el contacto ABIERTO
    # deja el pin en HIGH => con pull-up interno hay que negar.
    abierto = not sensor.is_pressed if sensor.pull_up else sensor.is_pressed
    payload = "ON" if abierto else "OFF"
    if ultimo_estado.get(topic) == payload:
        return  # descartado: repetido, no se molesta al broker ni al panel
    ultimo_estado[topic] = payload
    # retain=True para que el panel conozca el estado nada más arrancar,
    # sin esperar a que el sensor cambie.
    client.publish(topic, payload, retain=True)
    print(f"{nombre}: {payload}", flush=True)


botones = []
for nombre, pin, topic, pull_up in SENSORES:
    sensor = Button(pin, pull_up=pull_up, bounce_time=BOUNCE)

    # El lambda captura por valor (argumentos por defecto): sin esto, los dos
    # sensores compartirían las variables del bucle y publicarían lo mismo.
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
