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
import re

from . import store
from ..devices import registry, gpio_bus, mqtt_bus, ssh_bus, ir_bus, webos_bus
from ..devices.models import SSHSpec
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


# ── Resolución ──────────────────────────────────────────────────────────────
def find(collection: str, item_id: str, data: dict | None = None) -> dict | None:
    datos = data if data is not None else store.read_all()
    return next((x for x in datos.get(collection, []) if x.get("id") == item_id), None)


def node_name(node_id: str, data: dict | None = None) -> str:
    host = registry.gpio_hosts().get(node_id)
    if host:
        return host.name
    node = find("nodes", node_id, data)
    return node["name"] if node else "?"


def node_ssh(node_id: str, data: dict | None = None) -> SSHSpec | None:
    """SSHSpec para un nodo accionable por SSH+raspi-gpio — la Raspberry/Pi
    Zero fijas del registry, o un nodo dinámico dado de alta con kind="ssh"
    (mismo mecanismo, sin estar hardcodeado). None = ese nodo va por MQTT."""
    host = registry.gpio_hosts().get(node_id)
    if host:
        return host.ssh
    node = find("nodes", node_id, data)
    if node and node.get("kind") == "ssh":
        return SSHSpec(host=node["ip"], user=node.get("user", ""))
    return None


def host_ssh(host_id: str) -> SSHSpec | None:
    """None si el equipo no existe o no tiene usuario SSH — y entonces no hay
    consola ni acciones. Se relee del almacén en vez de mirar solo el registry
    en memoria para que quitarle el usuario a un equipo tenga efecto ya, sin
    esperar a reiniciar."""
    host = store.find_host_by_id(host_id)
    if host is not None:
        return SSHSpec(host=host["ip"], user=host["user"], os=host.get("os", "linux")) if host["user"] else None
    # Equipos que no están en el almacén (cam_ptz_host/cam_fija_host, que
    # siguen siendo literales del registry porque no se gestionan desde la web).
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


def _lock(target: str) -> asyncio.Lock:
    lock = _TARGET_LOCKS.get(target)
    if lock is None:
        lock = _TARGET_LOCKS[target] = asyncio.Lock()
    return lock


async def _enviar_a_rele(spec: dict, on: bool, ssh: SSHSpec | None) -> None:
    """El transporte común de luces y puertas: SSH+raspi-gpio si el nodo lo
    admite, MQTT si no. Es la única bifurcación de transporte que hay para los
    relés, y está en un sitio para que no se separen."""
    if ssh:
        await gpio_bus.set_pin(ssh, spec["pin"], on, timeout=3)
        return
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
    await send_remote_button(mando, tecla, apuntar_estado=False)


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
    async with _lock(f"light:{light_id}"):
        data = store.read_all()
        light = find("lights", light_id, data)
        if light is None:
            raise EntityNotFound(f"La luz {light_id} ya no existe")
        nuevo = (not data["sensor_states"].get(light_id, False)) if on is None else bool(on)
        # Una luz de mando no cuelga de ningún nodo, así que no se le busca SSH:
        # con node_id vacío esto no tiene nada que resolver.
        por_mando = light.get("kind") == store.LUZ_MANDO
        ssh = None if por_mando else node_ssh(light["node_id"], data)

        await asyncio.to_thread(store.set_sensor_state, light_id, nuevo)
        if on_applied:
            await on_applied(nuevo)
        try:
            if por_mando:
                await _enviar_por_mando(light, nuevo)
            else:
                await _enviar_a_rele(light, nuevo, ssh)
        except Exception as e:
            # La orden no salió: lo que se pintó era mentira, se deshace.
            await asyncio.to_thread(store.set_sensor_state, light_id, not nuevo)
            if on_failed:
                await on_failed(nuevo, e)
            raise OperationError(str(e)) from e
        return nuevo


# ── Puertas ─────────────────────────────────────────────────────────────────
# Tarea de pulso en curso por puerta (id -> asyncio.Task), del PROCESO entero,
# no de la sesión. Tiene que ser este mismo diccionario para todos: si el motor
# llevara el suyo aparte, "Cortar pulso" desde la web no cancelaría un pulso
# lanzado por una regla, y el auto-cierre de esa regla pisaría después un
# "Mantener abierto" hecho a mano.
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
        try:
            await _enviar_a_rele(door, on, node_ssh(door["node_id"], data))
        except NotConfigured:
            raise
        except Exception as e:
            raise OperationError(str(e)) from e
        return door


def pulse_door(door_id: str, seconds: float | None = None, *, on_finish=None) -> asyncio.Task:
    """Abrir (pulso): activa el relé unos segundos y lo vuelve a cerrar solo.
    Cancelable con cancel_door_pulse() o por cualquier otro pulso de la misma
    puerta. `seconds=None` toma el pulso configurado en la ficha.

    Devuelve la tarea sin esperarla — quien llama decide si le importa cuándo
    acaba. `on_finish` recibe el mensaje del resultado para que una sesión
    pueda pintarlo."""
    cancel_door_pulse(door_id)

    async def _pulse():
        nombre = (find("doors", door_id) or {}).get("name", door_id)
        try:
            door = await send_door_state(door_id, True)
            espera = float(door.get("pulse_seconds", 2)) if seconds is None else float(seconds)
            await asyncio.sleep(espera)
            await send_door_state(door_id, False)
            msg = f"✅ {door['name']} abierta"
        except asyncio.CancelledError:
            # El re-raise es lo que deja la tarea CANCELADA y no "terminada":
            # es la diferencia entre "se cortó el pulso" y "el pulso acabó
            # solo", y de ella depende que el auto-cierre no pise un
            # "Mantener abierto" posterior.
            msg = f"⏹️ Pulso de {nombre} cortado"
            raise
        except Exception as e:
            msg = f"❌ {nombre}: {e}"
        finally:
            if on_finish:
                await on_finish(msg)
            _DOOR_PULSE_TASKS.pop(door_id, None)

    tarea = asyncio.create_task(_pulse())
    _DOOR_PULSE_TASKS[door_id] = tarea
    return tarea


# ── Mandos IR / RF / webOS ──────────────────────────────────────────────────
def _apuntar_estado_de_accesorios(remote_id: str, button_id: str) -> None:
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
    for luz in datos.get("lights", []):
        if luz.get("kind") != store.LUZ_MANDO or luz.get("remote_id") != remote_id:
            continue
        if luz.get("mando_modo") == store.UNA_TECLA:
            if luz.get("btn_on") == button_id:
                store.set_sensor_state(luz["id"], not estados.get(luz["id"], False))
        elif luz.get("btn_on") == button_id:
            store.set_sensor_state(luz["id"], True)
        elif luz.get("btn_off") == button_id:
            store.set_sensor_state(luz["id"], False)


async def send_remote_button(remote_id: str, button_id: str, *,
                             apuntar_estado: bool = True) -> str:
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
    if not boton.get("code"):
        raise NotConfigured(
            f'"{boton["label"]}" todavía no tiene señal — entra en '
            f'"Colocar botones" y edítalo para aprendérsela.'
        )
    try:
        if boton.get("kind") == "webos":
            await webos_bus.send_command(boton["code"])
        else:
            await ir_bus.send_button(boton["code"])
        if apuntar_estado:
            await asyncio.to_thread(_apuntar_estado_de_accesorios, remote_id, button_id)
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
        return await ssh_bus.accion_apagar(ssh)
    if accion == "reiniciar":
        return await ssh_bus.accion_reiniciar(ssh)
    if accion == "temperatura":
        return await ssh_bus.accion_temperatura(ssh)
    raise NotConfigured(f"acción desconocida: {accion}")


async def run_host_command(host_id: str, cmd: str, timeout: int = 8) -> str:
    ssh = host_ssh(host_id)
    if ssh is None:
        raise NotConfigured("este equipo no tiene usuario SSH configurado")
    return await ssh_bus.ssh_execute(ssh, cmd, timeout=timeout)


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
            return await ssh_bus.ssh_execute(ssh, btn["value"], timeout=8)
        if btn["kind"] == "pin_write_on":
            await gpio_bus.set_pin(ssh, btn["value"], True, timeout=3)
            return f"Pin {btn['value']} -> ON"
        if btn["kind"] == "pin_write_off":
            await gpio_bus.set_pin(ssh, btn["value"], False, timeout=3)
            return f"Pin {btn['value']} -> OFF"
        if btn["kind"] == "pin_read":
            return await gpio_bus.read_pin(ssh, btn["value"], timeout=3)
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
        ssh = node_ssh(node_id, data)
        if ssh:
            try:
                await gpio_bus.set_pin(ssh, pin, on, timeout=3)
            except Exception as e:
                raise OperationError(str(e)) from e
            return
        bus = mqtt_bus.get_running_bus()
        if bus is None:
            raise NotConfigured("MQTT no conectado")
        bus.publish(store.command_topic(node_name(node_id, data), pin), "ON" if on else "OFF")


async def read_node_pin(node_id: str, pin: str) -> str:
    ssh = node_ssh(node_id)
    if ssh is None:
        raise NotConfigured("ese nodo no se puede leer por SSH")
    return await gpio_bus.read_pin(ssh, pin, timeout=3)
