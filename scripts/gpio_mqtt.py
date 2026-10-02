"""
Salidas (relés) de un nodo Raspberry por MQTT — el mismo patrón que un ESP32.

El panel publica ON/OFF en  casa/<nodo>/<pin>/set  y aquí se pone el pin BCM en
HIGH/LOW con raspi-gpio; el nivel real del pin se devuelve RETENIDO en
casa/<nodo>/<pin>, que es donde el panel escucha el estado. Sustituye al
SSH + raspi-gpio que usaba el panel para cada orden.

Seguridad:
- Solo pines BCM 2..27, y NUNCA los de entrada de sensor_mqtt.py (PROTEGIDOS):
  convertir en salida el pin de la puerta dejaría a la alarma ciega.
- Al arrancar no toca ningún pin: solo cuando llega una orden.
- Las órdenes llegan sin retain (el panel no las retiene): reiniciar este
  servicio nunca repite una orden vieja.

Uso: gpio_mqtt.py [nodo]   (por defecto "raspberry"; en la Pi Zero, "pi_zero")
"""
import re
import subprocess
import sys

import paho.mqtt.client as mqtt

BROKER, PUERTO = "100.98.98.1", 1883
NODO = sys.argv[1] if len(sys.argv) > 1 else "raspberry"
PROTEGIDOS = {23, 27}  # entradas de sensor_mqtt.py (tamper PC, puerta)
ORDEN = re.compile(rf"^casa/{re.escape(NODO)}/(\d+)/set$")


def _credenciales():
    """Usuario y contraseña del broker, de un fichero 600 junto al script."""
    import os
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mqtt_cred")
    with open(ruta) as f:
        return NODO, f.read().strip()   # usuario del broker = slug del nodo


def _nivel(pin: int) -> bool:
    salida = subprocess.run(["raspi-gpio", "get", str(pin)], capture_output=True,
                            text=True, timeout=5).stdout
    return "level=1" in salida


def _poner(pin: int, encendido: bool) -> None:
    subprocess.run(["raspi-gpio", "set", str(pin), "op", "dh" if encendido else "dl"],
                   check=True, timeout=5)


def _al_conectar(cliente, *_args):
    cliente.subscribe(f"casa/{NODO}/+/set")
    print(f"Conectado: escuchando casa/{NODO}/+/set", flush=True)


def _al_mensaje(cliente, _datos, msg):
    m = ORDEN.match(msg.topic)
    if not m:
        return
    pin = int(m.group(1))
    orden = msg.payload.decode("utf-8", "replace").strip().upper()
    if pin in PROTEGIDOS or not 2 <= pin <= 27 or orden not in ("ON", "OFF", "1", "0"):
        print(f"Orden IGNORADA: {msg.topic} = {orden!r}", flush=True)
        return
    try:
        _poner(pin, orden in ("ON", "1"))
        estado = "ON" if _nivel(pin) else "OFF"
        cliente.publish(f"casa/{NODO}/{pin}", estado, retain=True)
        print(f"GPIO{pin} -> {estado}", flush=True)
    except Exception as e:  # noqa: BLE001 — que una orden rara no tumbe el servicio
        print(f"Error con GPIO{pin}: {e}", flush=True)


def _cliente() -> mqtt.Client:
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        return mqtt.Client()


cliente = _cliente()
cliente.username_pw_set(*_credenciales())
cliente.on_connect = _al_conectar
cliente.on_message = _al_mensaje
cliente.connect_async(BROKER, PUERTO, 60)
cliente.loop_forever(retry_first_connection=True)
