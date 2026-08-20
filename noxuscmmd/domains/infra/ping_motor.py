"""
Quién está en línea. Tarea de proceso, como el resto de lo que tiene que
funcionar con el panel cerrado.

POR QUÉ EXISTE ESTE FICHERO. Esto vivía dentro de `InfraState`, en un bucle por
sesión, con un global (`_PING_STARTED`) para que solo pingara el primero que
cargara la página: los demás se limitaban a leer lo que aquel dejaba. Y
funcionó hasta que los bucles de sesión empezaron a morirse con su navegador
(core/sesiones.py, y hacía falta: había 18 sesiones fantasma comiéndose la
CPU). Desde entonces:

    quien pingaba cerraba el navegador -> su bucle moría
    -> pero `_PING_STARTED` seguía puesto
    -> NADIE volvía a pingar en todo el proceso.

El estado de los equipos se quedaba congelado en la última foto, y ahí seguía
hasta reiniciar el servicio: un PC apagado hace horas figuraba en línea, y un
móvil que se había ido de la VPN, también. Sin ningún error por ningún lado —
el fichero simplemente dejaba de escribirse.

La lección, que es la razón del fichero y no del parche: **quién está en línea
es un dato de la casa, no de una pantalla**. No puede depender de que haya un
navegador abierto, igual que no dependen de eso la alarma ni las
automatizaciones. Aquí no hace falta ningún global: hay un run_forever y lo
arranca el lifespan, así que hay exactamente uno por proceso por construcción.

Los States solo LEEN lo que este bucle deja en nodos_dinamicos.json
(`InfraState.actualizar_estados`), que es una lectura con cerrojo compartido y
no frena a nadie.
"""
import asyncio
import time

from ..devices import registry
from ..nodes import store as nodes_store
from ..security import audit, logs
from ...core.connectivity import NetUtils

# Cada cuánto se pinga a todos. Ocho segundos es lo que había y va bien: los
# pings salen en paralelo, así que la vuelta dura lo que el más lento.
PERIODO = 8.0

# Cuánto tiene que aguantar un equipo en su estado nuevo antes de que se
# apunte. Un ping perdido suelto no es una desconexión: sin esta espera, un
# equipo por wifi o al otro lado de la VPN llenaba el registro de pares
# desconectado/conectado cada pocos minutos, y con ese ruido el histórico de
# equipos no servía para nada.
#
# Asimétrico a propósito: con un minuto seguían colándose desconexiones falsas
# de equipos que solo habían perdido la VPN un rato, así que para apuntar que
# uno se ha ido se le dan cinco minutos. La vuelta se mantiene en un minuto —
# ahí no hay falsa alarma que evitar y no interesa que un equipo que ya está
# de vuelta tarde cinco minutos en constar como conectado.
#
# OJO CON LO QUE ESTO ES Y LO QUE NO: esta espera es solo para el REGISTRO de
# eventos. Lo que se pinta en el panel es el ping crudo de la última vuelta,
# sin retrasos, porque para mirar si un equipo responde ahora mismo lo que
# interesa es ahora mismo.
_ESTABILIZACION_DESCONEXION = 300.0  # segundos
_ESTABILIZACION_CONEXION = 60.0  # segundos

# Estado CRUDO en curso de cada equipo y desde cuándo lo está: (online, t).
_PENDIENTE: dict[str, tuple[bool, float]] = {}

# Último estado que se llegó a APUNTAR de cada equipo. Es lo que garantiza que
# los eventos alternen: nunca dos conexiones ni dos desconexiones seguidas del
# mismo equipo, porque solo se apunta lo que difiere de esto.
_REGISTRADO: dict[str, bool] = {}


def _registrar_cambios_de_conexion(estados: dict[str, bool], hosts: dict) -> None:
    """Apunta los equipos que se conectan o se desconectan, una vez confirmado.

    Confirmado = el estado nuevo lleva ya su espera de estabilización seguida
    (cinco minutos para irse, uno para volver). Y solo si difiere del último
    apuntado, así que la secuencia de un equipo siempre alterna
    conectado/desconectado.
    """
    ahora = time.monotonic()
    for host_id, online in estados.items():
        crudo, desde = _PENDIENTE.get(host_id, (online, ahora))
        if crudo != online:
            crudo, desde = online, ahora  # acaba de cambiar: empieza la cuenta
        _PENDIENTE[host_id] = (crudo, desde)

        if host_id not in _REGISTRADO:
            # Primera vuelta con este equipo: se toma como punto de partida.
            # Si no, al arrancar el panel se apuntaría de golpe el estado de
            # todos como si acabase de cambiar.
            _REGISTRADO[host_id] = online
            continue
        if _REGISTRADO[host_id] == online:
            continue
        espera = _ESTABILIZACION_CONEXION if online else _ESTABILIZACION_DESCONEXION
        if (ahora - desde) < espera:
            continue

        _REGISTRADO[host_id] = online
        host = hosts.get(host_id)
        nombre = getattr(host, "name", host_id)
        ip = getattr(getattr(host, "ssh", None), "host", "")
        audit.registrar_sistema(
            logs.EQUIPOS,
            "EQUIPO_CONECTADO" if online else "EQUIPO_DESCONECTADO",
            f"{nombre} · {ip}" if ip else nombre,
            entidad=host_id,
        )


async def una_vuelta() -> dict[str, bool]:
    """Pinga a todos una vez, apunta lo que cambie y lo deja guardado.

    Aparte de run_forever para poder comprobarla sin poner en marcha el bucle.
    """
    host_items = list(registry.hosts().items())
    resultados = await NetUtils.ping_all(
        [(h.ssh.host, h.ping_retries) for _, h in host_items]
    )
    estados = {hid: online for (hid, _), online in zip(host_items, resultados)}
    _registrar_cambios_de_conexion(estados, dict(host_items))
    await asyncio.to_thread(nodes_store.set_host_online_bulk, estados)
    return estados


async def run_forever() -> None:
    while True:
        try:
            await una_vuelta()
        except Exception as e:
            print(f"⚠️ Ping de equipos: {e}")
        await asyncio.sleep(PERIODO)
