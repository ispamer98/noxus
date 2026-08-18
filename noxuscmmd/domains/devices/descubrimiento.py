"""
Modo instalador: oír lo que la casa publica por MQTT y convertirlo en un
sensor, una luz o una puerta sin escribir un topic a mano.

El problema que resuelve: dar de alta algo nuevo obligaba a saber de antemono el
nombre del nodo y el de la señal, escribirlos igual que los tiene el firmware, y
descubrir el fallo de tipografía más tarde —cuando el sensor no se movía en la
pantalla y no había forma de saber si la culpa era del cable, del ESP32 o de una
letra—. Aquí se hace al revés: se escucha, se enseña lo que de verdad está
llegando, y se da de alta lo que el instalador reconozca.

Cómo funciona: mientras la pantalla está abierta se suscribe el bus a `casa/#`
(ver mqtt_bus.escuchar_todo) y se apunta cada topic con su último valor. Al
salir se deja de escuchar: tener al broker mandando toda la casa a este proceso
solo tiene sentido con alguien delante.

El convenio de topics es el de nodes/store: `casa/<nodo>/<señal>` para lo que
publica un aparato y `casa/<nodo>/<señal>/set` para lo que se le ordena. De ahí
salen el nodo y la señal de cada hallazgo, y con la señal se propone el tipo
—una llamada `pir_salon` casi siempre es un detector—. Es una PROPUESTA: la
decide quien está instalando, no esto.
"""
import time

from . import mqtt_bus
from ..nodes import store as nodes_store

# Cuántos topics distintos se guardan como mucho. Es una red de seguridad: un
# firmware con un bucle publicando en topics con nombre aleatorio no puede
# llenar la memoria del panel.
TOPE = 300

# Qué se propone según lo que diga el nombre de la señal. Se mira por orden y se
# queda con el primero que encaje, así que lo más específico va antes.
_PISTAS = (
    (("puerta", "door", "porton", "porton", "garaje", "cerradura", "lock"), "puerta", "door"),
    (("luz", "light", "lampara", "lamp", "bombilla", "foco"), "luz", ""),
    (("pir", "mov", "motion", "presencia", "radar"), "sensor", "pir"),
    (("tamper", "sabotaje"), "sensor", "tamper"),
    (("magnet", "ventana", "window", "contacto", "reed"), "sensor", "door"),
    (("humo", "smoke", "gas", "agua", "water", "inund"), "sensor", "pir"),
)

_vistos: dict[str, dict] = {}
_escuchando = False
_desde = 0.0


def _apuntar(topic: str, payload: str) -> None:
    """Oyente del bus. Corre en el hilo de paho: solo toca el diccionario."""
    ficha = _vistos.get(topic)
    ahora = time.time()
    if ficha is None:
        if len(_vistos) >= TOPE:
            return
        _vistos[topic] = {"payload": payload, "veces": 1,
                          "primera": ahora, "ultima": ahora}
        return
    ficha["payload"] = payload
    ficha["veces"] += 1
    ficha["ultima"] = ahora


def arrancar() -> str:
    """Empieza a escuchar. Devuelve "" si todo bien, o el motivo si no puede."""
    global _escuchando, _desde
    bus = mqtt_bus.get_running_bus()
    if bus is None:
        return ("El bus MQTT todavía no está en marcha — abre la pestaña de "
                "Alarma una vez y vuelve a intentarlo.")
    if _escuchando:
        return ""
    _vistos.clear()
    _desde = time.time()
    bus.escuchar_todo(_apuntar)
    _escuchando = True
    return ""


def parar() -> None:
    global _escuchando
    bus = mqtt_bus.get_running_bus()
    if bus is not None:
        bus.dejar_de_escuchar_todo()
    _escuchando = False


def escuchando() -> bool:
    return _escuchando


def segundos_escuchando() -> int:
    return int(time.time() - _desde) if _desde else 0


def olvidar() -> None:
    """Vacía lo oído sin dejar de escuchar — para empezar de cero después de
    mover un sensor y ver solo lo que se mueva a partir de ahora."""
    _vistos.clear()


def _topics_conocidos() -> dict[str, str]:
    """Topic -> nombre de lo que ya está dado de alta con ese topic.

    Se miran las cuatro colecciones que llevan topic: los sensores de fábrica
    (la puerta y los tampers), los añadidos desde la web, y las puertas y luces
    —que tienen dos, el de la orden y el del estado real—.
    """
    datos = nodes_store.read_all()
    conocidos: dict[str, str] = {}
    for coleccion in ("factory_sensors", "sensors"):
        for item in datos.get(coleccion, []):
            if item.get("topic"):
                conocidos[item["topic"]] = item.get("name", "")
    for coleccion in ("doors", "lights"):
        for item in datos.get(coleccion, []):
            for clave in ("topic_cmd", "topic_state"):
                if item.get(clave):
                    conocidos[item[clave]] = item.get("name", "")
    return conocidos


def partir(topic: str) -> tuple[str, str, bool]:
    """`casa/nodo_garaje/pir1/set` -> ("nodo_garaje", "pir1", True).

    El booleano dice si el topic es de ORDEN (acaba en /set), o sea algo que el
    panel publica y no un aparato informando. Esos no se ofrecen para dar de
    alta: darían de alta el eco de una orden nuestra.
    """
    partes = [p for p in topic.split("/") if p]
    if partes and partes[0] == "casa":
        partes = partes[1:]
    es_orden = len(partes) > 1 and partes[-1] == "set"
    if es_orden:
        partes = partes[:-1]
    if not partes:
        return "", "", es_orden
    if len(partes) == 1:
        return "", partes[0], es_orden
    return partes[0], "/".join(partes[1:]), es_orden


def proponer(senal: str) -> tuple[str, str]:
    """(tipo, clase) sugeridos para una señal. ("sensor", "pir") por defecto:
    es lo más común y lo menos peligroso de equivocarse — un sensor mira, no
    acciona nada."""
    minus = senal.lower()
    for palabras, tipo, clase in _PISTAS:
        if any(p in minus for p in palabras):
            return tipo, clase
    return "sensor", "pir"


def hallazgos() -> list[dict]:
    """Lo oído, listo para pintar: lo desconocido primero y, dentro de eso, lo
    que se acaba de mover antes que lo que lleva rato callado. Ese orden es el
    que hace que «abre la ventana y mira arriba» funcione."""
    conocidos = _topics_conocidos()
    salida = []
    for topic, ficha in _vistos.items():
        nodo, senal, es_orden = partir(topic)
        tipo, clase = proponer(senal)
        nombre_conocido = conocidos.get(topic, "")
        salida.append({
            "topic": topic,
            "payload": ficha["payload"][:40],
            "veces": ficha["veces"],
            "hace": int(time.time() - ficha["ultima"]),
            "nodo": nodo,
            "senal": senal,
            "es_orden": es_orden,
            "tipo": tipo,
            "clase": clase,
            "conocido": bool(nombre_conocido),
            "nombre_conocido": nombre_conocido,
            "binario": ficha["payload"].strip().upper() in ("ON", "OFF", "1", "0",
                                                            "TRUE", "FALSE"),
        })
    salida.sort(key=lambda h: (h["conocido"], h["es_orden"], h["hace"]))
    return salida


def nuevos() -> int:
    return sum(1 for h in hallazgos() if not h["conocido"] and not h["es_orden"])
