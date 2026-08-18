"""
Modo instalador: partir el topic, proponer el tipo, marcar lo ya dado de alta y
—lo importante— la salvaguarda que evita dar de alta algo que nunca funcionaría.

No se conecta a MQTT: se alimenta el oyente a mano, que es exactamente lo que
hace el bus cuando llega un mensaje.
"""
from tests.comun import Caso

from noxuscmmd.domains.devices import descubrimiento as d
from noxuscmmd.domains.devices.instalador_state import InstaladorState
from noxuscmmd.domains.nodes import store as nodes_store


def _descubrimiento() -> Caso:
    c = Caso("Descubrimiento por MQTT")
    c.revisar("estado normal", d.partir("casa/nodo_garaje/pir1"),
              ("nodo_garaje", "pir1", False))
    c.revisar("orden del panel (/set)", d.partir("casa/nodo_garaje/luz1/set"),
              ("nodo_garaje", "luz1", True))
    c.revisar("señal con barras", d.partir("casa/nodo/a/b"), ("nodo", "a/b", False))

    c.revisar("pir_salon es detector", d.proponer("pir_salon"), ("sensor", "pir"))
    c.revisar("puerta_calle es puerta", d.proponer("puerta_calle"), ("puerta", "door"))
    c.revisar("luz_cocina es luz", d.proponer("luz_cocina"), ("luz", ""))
    c.revisar("tamper1 es sabotaje", d.proponer("tamper1"), ("sensor", "tamper"))
    # Lo desconocido cae en sensor: es lo que menos daño hace si se acierta mal,
    # porque un sensor mira y no acciona nada.
    c.revisar("lo desconocido cae en sensor", d.proponer("zzzz"), ("sensor", "pir"))

    d._vistos.clear()
    d._apuntar("casa/nodo_test/pir_nuevo", "ON")
    d._apuntar("casa/nodo_test/pir_nuevo", "OFF")
    d._apuntar("casa/nodo_test/luz_nueva/set", "ON")
    datos = nodes_store.read_all()
    ya = next((s["topic"] for col in ("factory_sensors", "sensors")
               for s in datos.get(col, []) if s.get("topic")), "")
    if ya:
        d._apuntar(ya, "ON")

    por_topic = {h["topic"]: h for h in d.hallazgos()}
    nuevo = por_topic["casa/nodo_test/pir_nuevo"]
    c.revisar("cuenta los mensajes repetidos", nuevo["veces"], 2)
    c.revisar("se queda con el último valor", nuevo["payload"], "OFF")
    c.revisar("lo nuevo no está dado de alta", nuevo["conocido"], False)
    c.revisar("reconoce una orden del panel",
              por_topic["casa/nodo_test/luz_nueva/set"]["es_orden"], True)
    if ya:
        c.revisar(f"marca lo ya dado de alta ({ya})", por_topic[ya]["conocido"], True)
    c.revisar("solo cuenta como nuevo lo que se puede dar de alta", d.nuevos(), 1)

    d._vistos.clear()
    for i in range(d.TOPE + 25):
        d._apuntar(f"casa/x/{i}", "ON")
    c.revisar("respeta el tope de topics guardados", len(d._vistos), d.TOPE)
    return c


def _salvaguarda() -> Caso:
    c = Caso("Salvaguarda del topic")
    # El alta RECALCULA el topic a partir del nombre del nodo. Si lo que saldría
    # no es lo que se oyó, el aparato se daría de alta y no se movería nunca:
    # eso es lo que esto impide.
    s = InstaladorState(_reflex_internal_init=True)

    def cuadra(nombre_nodo):
        s.nodo_nombre, s.senal = nombre_nodo, "pir1"
        s.topic_elegido = "casa/nodo_garaje/pir1"
        return s.topic_cuadra

    c.revisar("el slug exacto cuadra", cuadra("nodo_garaje"), True)
    c.revisar("con espacios y mayúsculas también", cuadra("Nodo Garaje"), True)
    c.revisar("un nombre distinto NO cuadra", cuadra("Garaje"), False)
    c.revisar("una letra de más NO cuadra", cuadra("nodo_garage"), False)
    return c


def ejecutar() -> list[Caso]:
    return [_descubrimiento(), _salvaguarda()]
