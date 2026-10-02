"""
Verbos de hardware SIN sesión: todo lo que "le hace algo" a un aparato vive
aquí y en ningún otro sitio. Lo llaman los manejadores de NodesState /
HostActionsState (que se quedan solo con lo reactivo: Vars, toasts y registro)
y el motor de automatizaciones, que corre sin ninguna pestaña abierta.

Regla de oro: este módulo NO importa reflex. Si algo de aquí necesitara
`self`, está en el sitio equivocado — va en el State y llama a su verbo.

Por qué vive en domains/nodes/ y no en domains/automations/: las
automatizaciones CONSUMEN los dominios de dispositivo, nunca al revés. Si
estos verbos colgaran de automations, nodes/state.py tendría que importar de
allí y la dependencia quedaría del revés.

Otra diferencia con los States, y no es menor: aquí todo se resuelve leyendo
el almacén, no una Var. Las Vars son copias POR SESIÓN, así que una tecla de
mando o un botón de equipo creados en otra pestaña no existían para quien
pulsaba desde esta hasta recargar. Leyendo del almacén, eso desaparece.
"""
import asyncio
import logging
import re
import time

from . import store
from ..devices import registry, gpio_bus, mqtt_bus, ssh_bus, ir_bus, webos_bus
from ..security import audit, logs
from ..devices.models import SSHSpec
from ...core import bus
from ...core.connectivity import NetUtils


# ── Errores ─────────────────────────────────────────────────────────────────
# Tipados a propósito. Antes varios de estos caminos simplemente NO HACÍAN
# NADA en silencio (un botón inexistente, un mando sin señal aprendida), lo
# que desde el motor sería indistinguible de "salió bien": una regla daría por
# ejecutada una acción que nunca salió. Ahora cada caso es un fallo que se
# puede contar, registrar y enseñar.
class OperationError(Exception):
    """Cualquier fallo al accionar algo. Lo que la interfaz enseña y lo que el
    motor apunta como error de la regla."""


class EntityNotFound(OperationError):
    """La luz/puerta/botón/mando al que apunta la orden ya no existe."""


class NotConfigured(OperationError):
    """Existe, pero le falta algo para poder accionarlo: sin usuario SSH, sin
    señal aprendida, MQTT caído."""


def _salida_ssh(salida: str) -> str:
    """Convierte el convenio textual del bus SSH en un fallo accionable."""
    texto = str(salida or "")
    if texto.lstrip().upper().startswith("ERROR:"):
        raise OperationError(texto)
    return texto


# ── Resolución ──────────────────────────────────────────────────────────────
def find(collection: str, item_id: str, data: dict | None = None) -> dict | None:
    datos = data if data is not None else store.read_all()
    return next((x for x in datos.get(collection, []) if x.get("id") == item_id), None)


def node_name(node_id: str, data: dict | None = None) -> str:
    node = find("nodes", node_id, data)
    return node["name"] if node else "?"


def node_ssh(node_id: str, data: dict | None = None) -> SSHSpec | None:
    """SSHSpec para un nodo accionable por SSH+raspi-gpio — la Raspberry/Pi
    Zero fijas del registry, o un nodo dinámico dado de alta con kind="ssh"
    (mismo mecanismo, sin estar hardcodeado). None = ese nodo va por MQTT."""
    # Solo para LEER un pin: accionar va siempre por MQTT. Un nodo que además
    # es un equipo (la Pi) tiene su SSH en Equipos, con el mismo id.
    host = registry.hosts().get(node_id)
    return host.ssh if host and host.ssh.user else None


def host_ssh(host_id: str) -> SSHSpec | None:
    """None si el equipo no existe o no tiene usuario SSH — y entonces no hay
    consola ni acciones. Se relee del almacén en vez de mirar solo el registry
    en memoria para que quitarle el usuario a un equipo tenga efecto ya, sin
    esperar a reiniciar."""
    host = store.find_host_by_id(host_id)
    if host is not None:
        return SSHSpec(host=host["ip"], user=host["user"], os=host.get("os", "linux")) if host["user"] else None
    # Equipos que no están en el almacén (literales del registry, si queda alguno).
    estatico = registry.hosts().get(host_id)
    return estatico.ssh if estatico and estatico.ssh.user else None


def host_name(host_id: str) -> str:
    host = store.find_host_by_id(host_id)
    return host["name"] if host else host_id


# Serialización POR OBJETIVO. Dos órdenes sobre la MISMA luz se ejecutan una
# detrás de otra; sobre luces distintas siguen yendo en paralelo. Sin esto,
# desde que el motor puede accionar a la vez que una persona, dos órdenes
# opuestas sobre el mismo relé se entrelazan y el estado final depende de cuál
# de los dos SSH conteste antes. De paso arregla el doble clic en la web.
_TARGET_LOCKS: dict[str, asyncio.Lock] = {}
_LIGHT_BACKGROUND_TASKS: set[asyncio.Task] = set()
_CONTINUACIONES_MANDO: set[str] = set()
_LOGGER = logging.getLogger(__name__)


def _lock(target: str) -> asyncio.Lock:
    lock = _TARGET_LOCKS.get(target)
    if lock is None:
        lock = _TARGET_LOCKS[target] = asyncio.Lock()
    return lock


async def _enviar_a_rele(spec: dict, on: bool) -> None:
    """El transporte de TODOS los relés (luces, puertas, persianas): MQTT.
    ON/OFF en casa/<nodo>/<pin>/set, igual para un ESP32 que para la
    Raspberry — en la Pi lo atiende gpio-mqtt.service (scripts/gpio_mqtt.py),
    que devuelve el nivel real del pin en casa/<nodo>/<pin>. Antes, a la
    Raspberry se le hablaba por SSH + raspi-gpio en cada orden."""
    bus = mqtt_bus.get_running_bus()
    if bus is None:
        raise NotConfigured("MQTT no conectado")
    bus.publish(spec["topic_cmd"], "ON" if on else "OFF")


async def _enviar_por_mando(light: dict, on: bool) -> None:
    """La otra forma de encender una luz: pulsar una tecla de un mando virtual.

    Es lo que hace falta para la luz de un ventilador de techo o de un plafón con
    mando, que no tienen relé por el que pasar. Se pulsa la tecla de encender o
    la de apagar según toque, y se reutiliza `send_remote_button` tal cual — así
    una luz de mando aprovecha el reintento por sesión caducada del Broadlink y
    todo lo demás que ya está resuelto ahí.

    Ojo con lo que NO da esto: no hay confirmación de que la bombilla se haya
    encendido. Con un relé por MQTT el firmware puede publicar su estado real;
    aquí se manda el infrarrojo a ciegas, y el estado que guarda el panel es el
    que se pidió. Si alguien la apaga con el mando físico, el panel no se enterará
    hasta que se le vuelva a dar.
    """
    una_sola = light.get("mando_modo") == store.UNA_TECLA
    # Con una sola tecla (la de encendido de la tele) se manda SIEMPRE la misma:
    # es el propio aparato el que alterna. El panel solo lleva la cuenta de en
    # qué cree que está, que es lo mismo que hace cualquier mando.
    tecla = light.get("btn_on", "") if una_sola else light.get("btn_on" if on else "btn_off", "")
    await _pulsar_tecla_mando(light, tecla, on=on, una_sola=una_sola)


async def _pulsar_tecla_mando(light: dict, tecla: str, *, on: bool,
                              una_sola: bool = False,
                              mantener_s: float | None = None) -> None:
    """Pulsa una tecla de accesorio por el transporte común del mando."""
    mando = light.get("remote_id", "")
    if not mando or not tecla:
        cual = ("la tecla de encendido" if una_sola
                else f'la tecla de {"encender" if on else "apagar"}')
        raise NotConfigured(
            f'A «{light.get("name", light.get("id"))}» le falta {cual} — '
            f'edítalo y elige el botón del mando.')
    # apuntar_estado=False: set_light ya ha dejado escrito el estado ANTES de
    # mandar la orden (y lo deshace si falla). Si además se apuntara aquí, en un
    # accesorio de UNA sola tecla la segunda escritura alternaría lo que acababa
    # de escribir la primera y el botón se quedaría siempre al revés — que es
    # justo lo que pasaba con la tele.
    await send_remote_button(mando, tecla, apuntar_estado=False,
                             mantener_s=mantener_s)


class _FalloParcialSecuencia(Exception):
    """ON llegó; falló una tecla posterior de la secuencia de activación."""


async def _enviar_secuencia_encendido(light: dict) -> None:
    """Envía la secuencia configurada sin duplicar el transporte IR/RF/webOS."""
    for indice, (tecla, pausa) in enumerate(store.secuencia_encendido(light)):
        if pausa:
            await asyncio.sleep(pausa)
        try:
            await _pulsar_tecla_mando(light, tecla, on=True, una_sola=True)
        except Exception as e:
            if indice:
                raise _FalloParcialSecuencia(str(e)) from e
            raise


async def _enviar_resto_encendido(light: dict, incluir_modo: bool) -> None:
    """Envía primero el modo y después la tecla Luz mantenida."""
    modo = store.secuencia_encendido(light)[1:] if incluir_modo else []
    pasos = [(tecla, pausa, None) for tecla, pausa in modo]
    luz = store.luz_a_mantener(light)
    if luz:
        tecla, mantener_s = luz
        pasos.append((tecla, store._pausa_secuencia(
            light.get("pausa_secuencia_s", 1.0)), mantener_s))
    for tecla, pausa, mantener_s in pasos:
        if pausa:
            await asyncio.sleep(pausa)
        try:
            await _pulsar_tecla_mando(light, tecla, on=True, una_sola=True,
                                      mantener_s=mantener_s)
        except Exception as e:
            raise _FalloParcialSecuencia(str(e)) from e


async def _continuar_encendido(light_id: str, light: dict, incluir_modo: bool) -> None:
    """Continúa una activación bajo el lock adquirido por set_light."""
    try:
        await _enviar_resto_encendido(light, incluir_modo)
    except _FalloParcialSecuencia as e:
        await asyncio.to_thread(store.set_mando_state, light_id, True, ciclo_min=60)
        audit.registrar_sistema(logs.LUCES, "LUZ_ERROR",
                                f"{light['name']}: {e}", entidad=light_id)
        raise OperationError(str(e)) from e
    except Exception as e:
        audit.registrar_sistema(logs.LUCES, "LUZ_ERROR",
                                f"{light['name']}: {e}", entidad=light_id)
        raise OperationError(str(e)) from e


def _background_done(task: asyncio.Task) -> None:
    _LIGHT_BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        _LOGGER.error("Secuencia de encendido en segundo plano fallida: %s", error)


def _remote_con_estado_real(remote_id: str, data: dict) -> bool:
    """Si este mando tiene algún botón webOS, la tele que hay detrás tiene un
    estado de verdad que preguntar por red (webos_bus.is_on()) — no hace falta
    fiarse a ciegas del último que se le pidió. Ver el aviso de `set_light`
    sobre por qué esa suposición se desincroniza sola."""
    mando = find("ir_remotes", remote_id, data)
    # Un mando SIMULADO (de prueba) no tiene tele detrás: preguntar por red
    # iría a la tele LG REAL de la casa, que casi siempre está apagada, y el
    # aparato de prueba no se podía apagar nunca (cada toque «encendía»).
    if not mando or mando.get("simulado"):
        return False
    return any(b.get("kind") == "webos" for b in mando.get("buttons", []))


# ── Luces ───────────────────────────────────────────────────────────────────
async def set_light(light_id: str, on: bool | None = None, *,
                    on_applied=None, on_failed=None) -> bool:
    """Enciende (True), apaga (False) o conmuta (None) una luz. Devuelve el
    estado que se ha aplicado.

    Persiste en disco ANTES de mandar la orden y DESHACE la persistencia si la
    orden falla. Ese orden no es negociable: sync_loop relee el JSON cada 0,5 s,
    así que el disco es la única fuente de verdad y cualquier estado optimista
    que viviera solo en memoria lo pisaría la siguiente vuelta.

    `on_applied` / `on_failed` existen para que una SESIÓN pueda pintar el
    cambio en el instante exacto en que el disco ya lo tiene y todavía no se ha
    mandado nada — que es lo que evita que el icono parezca colgado los 1-3 s
    que puede tardar un encendido por SSH. El motor no los pasa: no tiene
    ninguna pantalla que repintar.
    """
    # Una orden puede llegar horas después de que el aparato haya acabado su
    # ciclo. Caducar antes de leer evita que un conmutar se calcule desde un ON
    # que ya no es cierto. No hay transporte en esta operación.
    await asyncio.to_thread(expirar_accesorios)

    # Una persiana no se «enciende»: encender = subir, apagar = bajar, con el
    # enclavamiento de sus dos relés (ver mover_persiana_rele). Vale para todo
    # lo que llama aquí: el plano, las automatizaciones, Alexa.
    previa = find("lights", light_id)
    if previa and previa.get("kind") == store.PERSIANA_RELE:
        actual = bool(store.read_all()["sensor_states"].get(light_id, False))
        sube = (not actual) if on is None else bool(on)
        await mover_persiana_rele(light_id, "subir" if sube else "bajar")
        if on_applied:
            await on_applied(sube)
        return sube

    lock = _lock(f"light:{light_id}")
    await lock.acquire()
    try:
        data = store.read_all()
        light = find("lights", light_id, data)
        if light is None:
            raise EntityNotFound(f"La luz {light_id} ya no existe")
        # Una luz de mando no cuelga de ningún nodo, así que no se le busca SSH:
        # con node_id vacío esto no tiene nada que resolver.
        por_mando = light.get("kind") == store.LUZ_MANDO
        actual = bool(data["sensor_states"].get(light_id, False))
        # Un accesorio de UNA sola tecla (la tele, el ventilador) no tiene botón
        # de apagar propio: el mismo pulso alterna, así que lo guardado es una
        # SUPOSICIÓN, no un hecho — y basta con que alguien use el mando físico
        # de verdad una sola vez (o que un pulso IR se pierda) para que se
        # desincronice. Con el estado ya mal, «apaga» que coincide por
        # casualidad con lo guardado no manda nada (más abajo), y el aparato se
        # queda atascado en lo que sea que esté de verdad — que es justo lo que
        # le pasaba a la tele. Si el mando tiene un botón webOS, hay un hecho
        # de verdad que preguntar por red en vez de fiarse de lo guardado.
        if (por_mando and light.get("mando_modo") == store.UNA_TECLA
                and _remote_con_estado_real(light.get("remote_id", ""), data)):
            try:
                actual = await webos_bus.is_on()
            except Exception:
                pass  # sin red ahora mismo: se sigue confiando en lo guardado
        nuevo = (not actual) if on is None else bool(on)

        # El estado que pinta el plano es la fuente de verdad para TODAS las
        # luces y accesorios. Una orden explícita «apaga»/«enciende» que ya se
        # cumple no toca el transporte: evita que POWER en una TV/ventilador
        # de una sola tecla haga justo lo contrario y también ahorra pulsos de
        # relé o mando innecesarios. El clic manual llega como el estado
        # contrario, así que continúa conmutando exactamente como antes.
        if on is not None and nuevo == actual:
            return actual

        modo_secuenciado = (por_mando and nuevo
                            and light.get("mando_modo") == store.UNA_TECLA
                            and bool(light.get("modo_encendido")))
        ciclo_min = (store.duracion_ciclo_min(light.get("modo_encendido", ""))
                     if modo_secuenciado else None)
        if por_mando:
            await asyncio.to_thread(store.set_mando_state, light_id, nuevo,
                                    ciclo_min=ciclo_min)
        else:
            await asyncio.to_thread(store.set_sensor_state, light_id, nuevo)
        if on_applied:
            await on_applied(nuevo)
        # SIMULADO: elemento de prueba sin hardware detrás. Cambia de estado
        # en el panel y no manda nada a ningún sitio (ver store: "simulado").
        if light.get("simulado"):
            return nuevo
        try:
            luz_a_mantener = (store.luz_a_mantener(light)
                              if por_mando and nuevo else None)
            if luz_a_mantener:
                await _pulsar_tecla_mando(light, light["btn_on"], on=True, una_sola=True)
                tarea = asyncio.create_task(
                    _continuar_encendido_con_lock(light_id, light, lock, modo_secuenciado))
                _LIGHT_BACKGROUND_TASKS.add(tarea)
                tarea.add_done_callback(_background_done)
                return nuevo
            if modo_secuenciado:
                await _enviar_secuencia_encendido(light)
            elif por_mando:
                await _enviar_por_mando(light, nuevo)
            else:
                await _enviar_a_rele(light, nuevo)
        except _FalloParcialSecuencia as e:
            # ON sí llegó y el aparato está en su primer ciclo (1 h), así que
            # el estado optimista no se revierte. Se deja constancia igual que
            # los demás fallos de luces y el llamador recibe el error.
            await asyncio.to_thread(store.set_mando_state, light_id, True,
                                    ciclo_min=60)
            audit.registrar_sistema(logs.LUCES, "LUZ_ERROR",
                                    f"{light['name']}: {e}", entidad=light_id)
            raise OperationError(str(e)) from e
        except Exception as e:
            # La orden no salió: lo que se pintó era mentira, se deshace.
            if por_mando:
                await asyncio.to_thread(store.set_mando_state, light_id, not nuevo)
            else:
                await asyncio.to_thread(store.set_sensor_state, light_id, not nuevo)
            if on_failed:
                await on_failed(nuevo, e)
            raise OperationError(str(e)) from e
        return nuevo
    finally:
        # Una secuencia con apagado de luz conserva el lock en su tarea de
        # fondo; las demás rutas lo liberan al volver al llamador.
        if not ("tarea" in locals() and tarea and not tarea.done()):
            lock.release()


async def _continuar_encendido_con_lock(light_id: str, light: dict,
                                        lock: asyncio.Lock, incluir_modo: bool) -> None:
    try:
        await _continuar_encendido(light_id, light, incluir_modo)
    finally:
        lock.release()


# ── Puertas ─────────────────────────────────────────────────────────────────
# Tarea de pulso en curso por puerta (id -> asyncio.Task), del PROCESO entero,
# no de la sesión. Tiene que ser este mismo diccionario para todos: si el motor
# llevara el suyo aparte, "Cortar pulso" desde la web no cancelaría un pulso
# lanzado por una regla, y el auto-cierre de esa regla pisaría después un
# "Mantener abierto" hecho a mano.
# ── Persianas de dos relés ────────────────────────────────────────────────
# Un relé por sentido (pin_subir / pin_bajar). La regla de oro: NUNCA los dos
# a la vez — el motor recibiría tensión en ambos sentidos. Por eso se apaga
# siempre primero el contrario, y al acabar el recorrido se apagan los dos.
_PERSIANA_TASKS: dict[str, asyncio.Task] = {}


async def mover_persiana_rele(light_id: str, accion: str, *, fin: bool = False) -> dict:
    """accion: "subir" | "bajar" | "parar". Devuelve la ficha. `fin=True` es la
    parada automática al acabar el recorrido (queda «subida»/«bajada»); un
    «parar» a mano la deja «parada» a medias."""
    if accion not in ("subir", "bajar", "parar"):
        raise OperationError(f"Acción de persiana desconocida: {accion}")
    async with _lock(f"light:{light_id}"):
        data = store.read_all()
        p = find("lights", light_id, data)
        if p is None:
            raise EntityNotFound(f"La persiana {light_id} ya no existe")
        tarea = _PERSIANA_TASKS.pop(light_id, None)
        if tarea and not tarea.done() and tarea is not asyncio.current_task():
            tarea.cancel()
        if not p.get("simulado"):
            sube = {"pin": p["pin_subir"], "topic_cmd": p["topic_subir"]}
            baja = {"pin": p["pin_bajar"], "topic_cmd": p["topic_bajar"]}
            try:
                if accion == "subir":
                    await _enviar_a_rele(baja, False)
                    await _enviar_a_rele(sube, True)
                elif accion == "bajar":
                    await _enviar_a_rele(sube, False)
                    await _enviar_a_rele(baja, True)
                else:
                    await _enviar_a_rele(sube, False)
                    await _enviar_a_rele(baja, False)
            except NotConfigured:
                raise
            except Exception as e:
                raise OperationError(f"{p['name']}: {e}") from e
        if accion != "parar":
            await asyncio.to_thread(store.set_sensor_state, light_id, accion == "subir")
            await asyncio.to_thread(store.set_persiana_estado, light_id,
                                    "subiendo" if accion == "subir" else "bajando")
            segundos = float(p.get("recorrido_s") or 7)
            _PERSIANA_TASKS[light_id] = asyncio.create_task(_fin_recorrido(light_id, segundos))
        elif fin:
            subida = bool(store.read_all()["sensor_states"].get(light_id, False))
            await asyncio.to_thread(store.set_persiana_estado, light_id,
                                    "subida" if subida else "bajada")
        else:
            await asyncio.to_thread(store.set_persiana_estado, light_id, "parada")
        return p


async def _fin_recorrido(light_id: str, segundos: float) -> None:
    await asyncio.sleep(segundos)
    try:
        await mover_persiana_rele(light_id, "parar", fin=True)
    except Exception as e:
        print(f"⚠️ Persiana {light_id}: no se pudo parar al final del recorrido: {e}")


_DOOR_PULSE_TASKS: dict[str, asyncio.Task] = {}


def cancel_door_pulse(door_id: str) -> None:
    task = _DOOR_PULSE_TASKS.get(door_id)
    if task and not task.done():
        task.cancel()


async def send_door_state(door_id: str, on: bool) -> dict:
    """Envía ON/OFF al relé de una puerta, por SSH (raspi-gpio) o por MQTT
    según de qué nodo cuelgue. Devuelve la ficha de la puerta, que es lo que
    necesita quien llama para poner su nombre en el mensaje."""
    async with _lock(f"door:{door_id}"):
        data = store.read_all()
        door = find("doors", door_id, data)
        if door is None:
            raise EntityNotFound(f"La puerta {door_id} ya no existe")
        if door.get("simulado"):
            return door  # de prueba: no hay cerradura de verdad a la que hablar
        try:
            await _enviar_a_rele(door, on)
        except NotConfigured:
            raise
        except Exception as e:
            raise OperationError(str(e)) from e
        return door


# Cuándo empezó el «abrir para pasar» en curso de cada puerta (time.monotonic).
# Con los tiempos de su ficha dice en qué punto de la maniobra está, que es lo
# que necesita hold_door para saber si la puerta está ya abierta o no.
_PASE_INICIO: dict[str, float] = {}


def tiempos_maniobra(door: dict) -> tuple[float, float, float]:
    """(apertura, espera, cierre) en segundos. Sin tiempos propios, el tránsito
    genérico de la ficha para abrir y cerrar, y ninguna espera."""
    apertura = float(door.get("apertura_s") or 0)
    espera = float(door.get("espera_s") or 0)
    cierre = float(door.get("cierre_s") or 0)
    if not any((apertura, espera, cierre)):
        transito = float(door.get("transito_s") or 3)
        return transito, 0.0, transito
    return apertura, espera, cierre


def fase_pase(door_id: str, door: dict | None = None) -> str:
    """"abriendo", "abierta", "cerrando" o "" según lo que lleve el último
    «abrir para pasar» de esa puerta."""
    inicio = _PASE_INICIO.get(door_id)
    door = door or find("doors", door_id)
    if inicio is None or door is None:
        return ""
    apertura, espera, cierre = tiempos_maniobra(door)
    t = time.monotonic() - inicio
    if t < apertura:
        return "abriendo"
    if t < apertura + espera:
        return "abierta"
    if t < apertura + espera + cierre:
        return "cerrando"
    return ""


def puerta_abierta(door_id: str, data: dict | None = None) -> bool:
    """Lo mejor que se sabe de si la puerta está (o va a quedar) abierta: un
    «abrir para pasar» que aún no ha empezado a cerrar, que se haya dejado
    mantenida abierta, o el magnético de su Puerta del plano."""
    data = data if data is not None else store.read_all()
    door = find("doors", door_id, data)
    if door is None:
        return False
    if fase_pase(door_id, door) in ("abriendo", "abierta"):
        return True
    estados = data.get("sensor_states", {})
    if estados.get(door_id, False):
        return True
    magnetico = next((p.get("sensor_id") for p in data.get("puertas", [])
                      if p.get("cerradura_id") == door_id), "")
    return bool(magnetico) and bool(estados.get(magnetico, False))


async def _un_pulso(door_id: str, segundos: float) -> None:
    # Si se cancela a mitad NO se suelta aquí: quien cancela manda justo
    # después su propia orden, y un OFF tardío de esta tarea la pisaría.
    await send_door_state(door_id, True)
    await asyncio.sleep(segundos)
    await send_door_state(door_id, False)


def pulse_door(door_id: str, seconds: float | None = None, *, on_finish=None) -> asyncio.Task:
    """Abrir (pulso): activa el relé unos segundos y lo vuelve a cerrar solo.
    Cancelable con cancel_door_pulse() o por cualquier otro pulso de la misma
    puerta. `seconds=None` toma el pulso configurado en la ficha.

    Con una cerradura de DOS pulsos (store.MODO_DOS_PULSOS) la puerta no se
    cierra sola: al acabar apertura + espera se da el segundo pulso, el de
    cierre. Mantenerla abierta a mitad cancela la tarea y, con ella, ese pulso.

    Devuelve la tarea sin esperarla — quien llama decide si le importa cuándo
    acaba. `on_finish` recibe el mensaje del resultado para que una sesión
    pueda pintarlo."""
    cancel_door_pulse(door_id)

    async def _pulse():
        nombre = (find("doors", door_id) or {}).get("name", door_id)
        try:
            door = find("doors", door_id) or {}
            espera = float(door.get("pulse_seconds", 2)) if seconds is None else float(seconds)
            _PASE_INICIO[door_id] = time.monotonic()
            await _un_pulso(door_id, espera)
            msg = f"✅ {nombre} abierta"
            if door.get("modo") == store.MODO_DOS_PULSOS:
                apertura, abierta, _ = tiempos_maniobra(door)
                await asyncio.sleep(max(0.0, apertura + abierta - espera))
                await _un_pulso(door_id, espera)
                msg = f"✅ {nombre}: abierta y cerrada"
        except asyncio.CancelledError:
            # El re-raise es lo que deja la tarea CANCELADA y no "terminada":
            # es la diferencia entre "se cortó el pulso" y "el pulso acabó
            # solo", y de ella depende que el auto-cierre no pise un
            # "Mantener abierto" posterior.
            msg = f"⏹️ Pulso de {nombre} cortado"
            raise
        except Exception as e:
            _PASE_INICIO.pop(door_id, None)
            msg = f"❌ {nombre}: {e}"
        finally:
            if on_finish:
                await on_finish(msg)
            _DOOR_PULSE_TASKS.pop(door_id, None)

    tarea = asyncio.create_task(_pulse())
    _DOOR_PULSE_TASKS[door_id] = tarea
    return tarea


async def hold_door(door_id: str, abierta: bool) -> tuple[dict, bool]:
    """Mantener abierta (True) o cerrada (False), según cómo trabaje la
    cerradura. Devuelve la ficha y si la puerta se va a MOVER (estaba en el
    otro estado), que es lo que decide si el plano pinta la maniobra.

    - Un pulso: el relé se queda activado (abierta) o se suelta (cerrada).
    - Dos pulsos: un único pulso, y solo si hace falta; si ya estaba así, otro
      pulso la movería justo al revés.

    Se apunta como estado de la cerradura sin esperar a que conteste: muchas no
    contestan nunca y el plano se quedaba igual que antes de pulsar."""
    data = store.read_all()
    door = find("doors", door_id, data)
    if door is None:
        raise EntityNotFound(f"La puerta {door_id} ya no existe")
    estaba = puerta_abierta(door_id, data)
    cancel_door_pulse(door_id)
    _PASE_INICIO.pop(door_id, None)
    if door.get("modo") == store.MODO_DOS_PULSOS:
        # Un pulso cortado a medias pudo dejar el relé activado: sin soltarlo
        # antes, el pulso de ahora no sería un pulso.
        await send_door_state(door_id, False)
        if estaba != abierta:
            await _un_pulso(door_id, float(door.get("pulse_seconds", 2)))
    else:
        await send_door_state(door_id, abierta)
    await asyncio.to_thread(store.set_sensor_state, door_id, abierta)
    return door, estaba != abierta


# ── Mandos IR / RF / webOS ──────────────────────────────────────────────────
def _apuntar_estado_de_accesorios(remote_id: str, button_id: str) -> list[dict]:
    """Pone al día el estado de lo que se accione con ESA tecla.

    El porqué: una misma luz o una tele se pueden encender desde sitios muy
    distintos —su botón del plano, el acceso rápido del Resumen, la paleta, una
    automatización o pulsando la tecla del mando virtual— y hasta ahora solo los
    caminos que pasaban por `set_light` dejaban constancia. Pulsando la tecla
    directamente, el aparato se encendía pero su botón seguía diciendo «apagado»:
    dos verdades para la misma cosa.

    Ahora cualquier pulsación mira si esa tecla es la de encender o la de apagar
    de algún accesorio y apunta el estado que corresponda. Con las de UNA sola
    tecla se alterna, que es exactamente lo que hace el aparato.

    Se hace DESPUÉS de que la orden haya salido bien: si el infrarrojo falla, no
    se apunta un estado que no ha llegado a pasar.

    Solo cuenta cuando la tecla se pulsa POR SU CUENTA (desde Mandos, la paleta,
    un widget de tecla o una automatización). Cuando la orden viene del botón del
    propio accesorio, quien apunta es `set_light` y esto se salta con
    apuntar_estado=False.
    """
    datos = store.read_all()
    estados = datos.get("sensor_states", {})
    ahora = time.time()
    encendidas = []
    for luz in datos.get("lights", []):
        if luz.get("kind") != store.LUZ_MANDO or luz.get("remote_id") != remote_id:
            continue
        if luz.get("mando_modo") == store.UNA_TECLA:
            if luz.get("btn_on") == button_id:
                nuevo = not estados.get(luz["id"], False)
                ciclo = (store.duracion_ciclo_min(luz.get("modo_encendido", ""))
                         if nuevo and luz.get("modo_encendido") else None)
                cambio = store.set_mando_state(luz["id"], nuevo, ahora,
                                                ciclo_min=ciclo)
                if cambio and nuevo:
                    encendidas.append(luz)
        elif luz.get("btn_on") == button_id:
            store.set_mando_state(luz["id"], True, ahora)
        elif luz.get("btn_off") == button_id:
            store.set_mando_state(luz["id"], False, ahora)
    return encendidas


async def _continuar_desde_mando(light: dict) -> None:
    light_id = light["id"]
    lock = _lock(f"light:{light_id}")
    try:
        await lock.acquire()
        try:
            data = store.read_all()
            actual = find("lights", light_id, data)
            if actual is None or not data.get("sensor_states", {}).get(light_id, False):
                return
            await _continuar_encendido(
                light_id, actual, incluir_modo=bool(actual.get("modo_encendido")))
        finally:
            lock.release()
    finally:
        _CONTINUACIONES_MANDO.discard(light_id)


def _continuacion_mando_done(task: asyncio.Task, light_id: str) -> None:
    _CONTINUACIONES_MANDO.discard(light_id)
    _background_done(task)


def _programar_continuacion_mando(luces: list[dict]) -> None:
    for light in luces:
        if not (light.get("modo_encendido") or store.luz_a_mantener(light)):
            continue
        light_id = light["id"]
        if light_id in _CONTINUACIONES_MANDO:
            continue
        _CONTINUACIONES_MANDO.add(light_id)
        tarea = asyncio.create_task(_continuar_desde_mando(light))
        _LIGHT_BACKGROUND_TASKS.add(tarea)
        tarea.add_done_callback(
            lambda task, light_id=light_id: _continuacion_mando_done(task, light_id))


def expirar_accesorios(ahora: float | None = None) -> list[str]:
    """Apaga en el almacén los accesorios por mando cuyo ciclo haya acabado.

    El vistazo inicial evita reescribir el JSON cada tres segundos por cada
    sesión cuando no hay nada que caducar. La decisión y todas las transiciones
    viven en un único ``_mutate``; por eso dos pestañas concurrentes solo
    reciben una lista no vacía y solo una registra el evento.
    """
    if ahora is None:
        ahora = time.time()

    def vencido(light: dict, estados: dict) -> bool:
        ciclo = light.get("ciclo_min")
        if ciclo == 0:
            return False  # Continuo se queda encendido hasta una orden de apagar.
        minutos = ciclo if isinstance(ciclo, (int, float)) and ciclo > 0 else light.get("auto_apagado_min", 0)
        inicio = light.get("encendido_en")
        return (light.get("kind") == store.LUZ_MANDO
                and bool(estados.get(light.get("id"), False))
                and isinstance(inicio, (int, float))
                and isinstance(minutos, (int, float)) and minutos > 0
                and ahora >= inicio + minutos * 60)

    previo = store.read_all()
    if not any(vencido(light, previo.get("sensor_states", {}))
               for light in previo.get("lights", [])):
        return []

    def _expirar(data):
        expirados = []
        estados = data["sensor_states"]
        for light in data["lights"]:
            if vencido(light, estados):
                if store._aplicar_estado_mando(data, light["id"], False, ahora):
                    expirados.append((light["id"], light["name"]))
        return expirados

    expirados = store._mutate(_expirar)
    if not expirados:
        return []
    bus.publicar(bus.SENSORES)
    for light_id, nombre in expirados:
        audit.registrar_sistema(
            logs.LUCES, "ACCESORIO_APAGADO_AUTOMATICO", nombre, entidad=light_id)
    return [nombre for _, nombre in expirados]


async def _despertar_tv_si_hace_falta(remote: dict) -> None:
    """Antes de un comando webOS (abrir una app, Home...), enciende la tele si
    hace falta.

    El botón «Encender» del mando es infrarrojos normal, y en esta TV es un
    interruptor único: el mismo código enciende y apaga. Pulsarlo a ciegas
    antes de cada app apagaría la tele las veces que ya estuviera encendida —
    que es el caso normal al pedir «pon Netflix». Por eso solo se pulsa cuando
    `webos_bus.is_on()` confirma que de verdad no responde por red."""
    if await webos_bus.is_on():
        return
    encender = next(
        (b for b in remote.get("buttons", [])
         if b.get("kind") == "ir" and b.get("icon") == "power" and b.get("code")),
        None)
    if encender is None:
        return
    await ir_bus.send_button(encender["code"])
    # webOS tarda unos segundos en arrancar y abrir el WebSocket; sin esta
    # espera, send_command() de justo después llegaría antes de que la tele
    # pudiera escucharlo.
    await asyncio.sleep(8)


async def send_remote_button(remote_id: str, button_id: str, *,
                             apuntar_estado: bool = True,
                             mantener_s: float | None = None) -> str:
    """Dispara una tecla de un mando virtual — por infrarrojos/radiofrecuencia
    (Broadlink) o por red (webOS de la TV LG) según su `kind`. Devuelve
    "Mando · Tecla" para el mensaje y el registro."""
    data = store.read_all()
    remote = find("ir_remotes", remote_id, data)
    if remote is None:
        raise EntityNotFound(f"El mando {remote_id} ya no existe")
    boton = next((b for b in remote.get("buttons", []) if b.get("id") == button_id), None)
    if boton is None:
        raise EntityNotFound(f"Esa tecla ya no existe en {remote['name']}")
    etiqueta = f"{remote['name']} · {boton['label']}"
    if remote.get("simulado"):
        # Mando de prueba: la tecla «funciona» (los aparatos que cuelgan de él
        # cambian de estado) pero no sale ninguna señal.
        if apuntar_estado:
            await asyncio.to_thread(_apuntar_estado_de_accesorios, remote_id, button_id)
        return etiqueta
    if not boton.get("code"):
        raise NotConfigured(
            f'"{boton["label"]}" todavía no tiene señal — entra en '
            f'"Colocar botones" y edítalo para aprendérsela.'
        )
    try:
        if boton.get("kind") == "webos":
            if mantener_s is not None:
                raise NotConfigured(
                    f'{etiqueta}: una pulsación mantenida solo admite botones IR')
            await _despertar_tv_si_hace_falta(remote)
            await webos_bus.send_command(boton["code"])
        else:
            if mantener_s is None:
                await ir_bus.send_button(boton["code"])
            else:
                await ir_bus.send_hold(boton["code"], mantener_s)
        if apuntar_estado:
            luces = await asyncio.to_thread(
                _apuntar_estado_de_accesorios, remote_id, button_id)
            _programar_continuacion_mando(luces)
    except Exception as e:
        # La etiqueta va DENTRO del error: quien lo recoge (la barra de estado
        # de la web, el registro de una regla) casi nunca tiene a mano de qué
        # tecla se trataba, y "falló el envío" a secas no sirve de nada.
        raise OperationError(f"{etiqueta}: {e}") from e
    return etiqueta


# ── Equipos ─────────────────────────────────────────────────────────────────
# Nombre de la acción en el registro. Fuera del despachador para que se lea de
# un vistazo qué queda apuntado con cada una, y compartido con el motor: si
# cada uno usara sus propios nombres, el filtro de Registros enseñaría dos
# vocabularios para el mismo suceso.
ACCIONES_LOG = {
    "apagar": "EQUIPO_APAGADO",
    "reiniciar": "EQUIPO_REINICIADO",
    "temperatura": "TEMPERATURA_CONSULTADA",
}


async def host_action(host_id: str, accion: str) -> str:
    """Las tres acciones genéricas de siempre sobre cualquier equipo con
    usuario SSH. Devuelve la salida en texto."""
    ssh = host_ssh(host_id)
    if ssh is None:
        raise NotConfigured("este equipo no tiene usuario SSH configurado")
    if accion == "apagar":
        return _salida_ssh(await ssh_bus.accion_apagar(ssh))
    if accion == "reiniciar":
        return _salida_ssh(await ssh_bus.accion_reiniciar(ssh))
    if accion == "temperatura":
        return _salida_ssh(await ssh_bus.accion_temperatura(ssh))
    raise NotConfigured(f"acción desconocida: {accion}")


async def run_host_command(host_id: str, cmd: str, timeout: int = 8) -> str:
    ssh = host_ssh(host_id)
    if ssh is None:
        raise NotConfigured("este equipo no tiene usuario SSH configurado")
    return _salida_ssh(await ssh_bus.ssh_execute(ssh, cmd, timeout=timeout))


async def run_host_button(button_id: str) -> str:
    """Ejecuta uno de los botones personalizados de un equipo (comando SSH,
    escribir pin, leer pin). Devuelve la salida en texto."""
    btn = find("host_buttons", button_id)
    if btn is None:
        raise EntityNotFound(f"El botón {button_id} ya no existe")
    ssh = host_ssh(btn["host_id"])
    if ssh is None:
        raise NotConfigured("este equipo no tiene usuario SSH configurado")
    try:
        if btn["kind"] == "ssh_command":
            return _salida_ssh(
                await ssh_bus.ssh_execute(ssh, btn["value"], timeout=8))
        if btn["kind"] == "pin_write_on":
            await gpio_bus.set_pin(ssh, btn["value"], True, timeout=3)
            return f"Pin {btn['value']} -> ON"
        if btn["kind"] == "pin_write_off":
            await gpio_bus.set_pin(ssh, btn["value"], False, timeout=3)
            return f"Pin {btn['value']} -> OFF"
        if btn["kind"] == "pin_read":
            return _salida_ssh(
                await gpio_bus.read_pin(ssh, btn["value"], timeout=3))
    except OperationError:
        raise
    except Exception as e:
        raise OperationError(str(e)) from e
    raise NotConfigured(f"tipo de botón desconocido: {btn['kind']}")


_TEMP = re.compile(r"(-?\d+(?:[.,]\d+)?)")


async def read_host_temperature(host_id: str) -> float | None:
    """Temperatura de CPU en grados, ya en número. None si el equipo no la
    sabe dar — accion_temperatura devuelve texto pensado para enseñar
    ("48.3 °C", "No se pudo leer temperatura", "ERROR: ..."), y una condición
    que no se puede evaluar NO se da por cumplida."""
    salida = await host_action(host_id, "temperatura")
    if not salida or salida.startswith("ERROR"):
        return None
    m = _TEMP.search(salida)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def wake_host(host_id: str) -> None:
    """Wake-on-LAN a cualquier equipo que tenga MAC en su ficha (antes esto
    solo sabía encender el PC, con la MAC incrustada en el código)."""
    host = store.find_host_by_id(host_id)
    if host is None:
        raise EntityNotFound(f"El equipo {host_id} ya no existe")
    if not host.get("mac"):
        raise NotConfigured(f"{host['name']} no tiene MAC configurada")
    NetUtils.send_wol(host["mac"])


# ── Pines sueltos ───────────────────────────────────────────────────────────
async def set_node_pin(node_id: str, pin: str, on: bool) -> None:
    """Escribe un pin de un nodo que no tiene ninguna luz ni puerta encima —
    para que una automatización pueda accionar cualquier salida, no solo las
    que alguien haya dado de alta como algo."""
    async with _lock(f"node_pin:{node_id}:{pin}"):
        data = store.read_all()
        bus = mqtt_bus.get_running_bus()
        if bus is None:
            raise NotConfigured("MQTT no conectado")
        bus.publish(store.command_topic(node_name(node_id, data), pin), "ON" if on else "OFF")


async def read_node_pin(node_id: str, pin: str) -> str:
    ssh = node_ssh(node_id)
    if ssh is None:
        raise NotConfigured("ese nodo no se puede leer por SSH")
    return await gpio_bus.read_pin(ssh, pin, timeout=3)
