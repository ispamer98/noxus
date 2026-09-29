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


def _remote_con_estado_real(remote_id: str, data: dict) -> bool:
    """Si este mando tiene algún botón webOS, la tele que hay detrás tiene un
    estado de verdad que preguntar por red (webos_bus.is_on()) — no hace falta
    fiarse a ciegas del último que se le pidió. Ver el aviso de `set_light`
    sobre por qué esa suposición se desincroniza sola."""
    mando = find("ir_remotes", remote_id, data)
    return bool(mando) and any(b.get("kind") == "webos" for b in mando.get("buttons", []))


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
        ssh = None if por_mando else node_ssh(light["node_id"], data)

        # El estado que pinta el plano es la fuente de verdad para TODAS las
        # luces y accesorios. Una orden explícita «apaga»/«enciende» que ya se
        # cumple no toca el transporte: evita que POWER en una TV/ventilador
        # de una sola tecla haga justo lo contrario y también ahorra pulsos de
        # relé o mando innecesarios. El clic manual llega como el estado
        # contrario, así que continúa conmutando exactamente como antes.
        if on is not None and nuevo == actual:
            return actual

        await asyncio.to_thread(store.set_sensor_state, light_id, nuevo)
        if on_applied:
            await on_applied(nuevo)
        try:
            if por_mando:
                await _enviar_por_mando(light, nuevo)
            elif light.get("kind") == store.ACT_DOS_RELES:
                # Dos relés: uno enciende y otro apaga, cada uno con su pulso.
                await _pulsar_dos_reles(light, ssh, nuevo,
                                        float(light.get("pulse_seconds", 1) or 1))
            else:
                await _enviar_a_rele(light, nuevo, ssh)
        except Exception as e:
            # La orden no salió: lo que se pintó era mentira, se deshace.
            await asyncio.to_thread(store.set_sensor_state, light_id, not nuevo)
            if on_failed:
                await on_failed(nuevo, e)
            raise OperationError(str(e)) from e
        return nuevo


# ── Actuación con dos relés ─────────────────────────────────────────────────
def _segundo_rele(item: dict) -> dict:
    """La ficha vista como su SEGUNDO relé: mismo nodo, pero con el pin y el
    topic del otro. Así el transporte (`_enviar_a_rele`) no tiene que saber que
    existen dos."""
    return {**item, "pin": item.get("pin2", ""), "topic_cmd": item.get("topic_cmd2", "")}


def _tipo(item: dict) -> str:
    return item.get("kind") or store.ACT_RELE


def _comprobar_dos_reles(item: dict) -> None:
    if not item.get("pin") or not item.get("pin2"):
        raise NotConfigured(
            f'A «{item.get("name", item.get("id"))}» le falta el pin de uno de '
            f'sus dos relés — edítalo y rellena los dos.')


async def _pulsar_dos_reles(item: dict, ssh: SSHSpec | None, primero: bool, segundos: float) -> None:
    """Pulso en uno de los dos relés (`primero`=True: el 1º, si no el 2º).

    ENCLAVAMIENTO: antes de activar uno se apaga el otro, y al acabar (o si se
    corta a mitad) se apaga el que se activó. Los dos relés de un motor NUNCA
    pueden estar activos a la vez: sería mandarle a la vez abrir y cerrar."""
    _comprobar_dos_reles(item)
    este = item if primero else _segundo_rele(item)
    otro = _segundo_rele(item) if primero else item
    await _enviar_a_rele(otro, False, ssh)
    await _enviar_a_rele(este, True, ssh)
    try:
        await asyncio.sleep(segundos)
    finally:
        await asyncio.shield(_enviar_a_rele(este, False, ssh))


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


def _registrar_tarea(door_id: str, coro_fn) -> asyncio.Task:
    """Lanza `coro_fn()` como LA tarea de esa puerta: cancela la anterior y
    espera a que acabe de soltar sus relés antes de empezar, para que el "apagar"
    de la vieja no llegue después del "encender" de la nueva."""
    previo = _DOOR_PULSE_TASKS.get(door_id)
    cancel_door_pulse(door_id)

    async def _envuelta():
        if previo is not None and not previo.done():
            await asyncio.wait([previo])
        try:
            return await coro_fn()
        finally:
            # Solo se borra si sigue siendo ESTA tarea la registrada: la vieja
            # acababa después de registrarse la nueva y se llevaba su entrada.
            if _DOOR_PULSE_TASKS.get(door_id) is asyncio.current_task():
                _DOOR_PULSE_TASKS.pop(door_id, None)

    tarea = asyncio.create_task(_envuelta())
    _DOOR_PULSE_TASKS[door_id] = tarea
    return tarea


async def _ctx_puerta(door_id: str) -> tuple[dict, SSHSpec | None]:
    data = store.read_all()
    door = find("doors", door_id, data)
    if door is None:
        raise EntityNotFound(f"La puerta {door_id} ya no existe")
    return door, node_ssh(door.get("node_id", ""), data)


async def _tecla_puerta(door: dict, abrir: bool) -> None:
    tecla = door.get("btn_on" if abrir else "btn_off", "")
    mando = door.get("remote_id", "")
    if not mando or not tecla:
        raise NotConfigured(
            f'A «{door.get("name", door.get("id"))}» le falta la tecla de '
            f'{"abrir" if abrir else "cerrar"} — edítala y elige el botón del mando.')
    await send_remote_button(mando, tecla, apuntar_estado=False)


async def _rele_puerta(door_id: str, on: bool) -> dict:
    """ON/OFF directo al relé de una puerta de UN relé, por SSH (raspi-gpio) o
    MQTT según de qué nodo cuelgue. Devuelve la ficha."""
    async with _lock(f"door:{door_id}"):
        door, ssh = await _ctx_puerta(door_id)
        try:
            await _enviar_a_rele(door, on, ssh)
        except NotConfigured:
            raise
        except Exception as e:
            raise OperationError(str(e)) from e
        return door


async def _energizar(door_id: str, primero: bool) -> dict:
    """Empieza el movimiento: `primero` = abrir, si no cerrar. Relé (ON), mando
    (pulsa la tecla) o dos relés (enciende el que toca, con el otro ya apagado)."""
    async with _lock(f"door:{door_id}"):
        door, ssh = await _ctx_puerta(door_id)
        try:
            tipo = _tipo(door)
            if tipo == store.ACT_MANDO:
                await _tecla_puerta(door, primero)
            elif tipo == store.ACT_DOS_RELES:
                _comprobar_dos_reles(door)
                este = door if primero else _segundo_rele(door)
                otro = _segundo_rele(door) if primero else door
                await _enviar_a_rele(otro, False, ssh)
                await _enviar_a_rele(este, True, ssh)
            else:
                await _enviar_a_rele(door, True, ssh)
        except (NotConfigured, EntityNotFound):
            raise
        except Exception as e:
            raise OperationError(str(e)) from e
        return door


async def _soltar(door_id: str) -> None:
    """Deja los relés de la puerta sin corriente. Con un relé es lo que la
    vuelve a cerrar/bloquear; con dos, lo que para el motor. Con mando no hay
    nada que soltar."""
    async with _lock(f"door:{door_id}"):
        door, ssh = await _ctx_puerta(door_id)
        tipo = _tipo(door)
        if tipo == store.ACT_MANDO:
            return
        fichas = [door] if tipo == store.ACT_RELE else [door, _segundo_rele(door)]
        error = None
        for ficha in fichas:
            # Se intenta apagar TODOS aunque uno falle: dejar el otro relé
            # activo por un error en el primero sería lo peor.
            try:
                await _enviar_a_rele(ficha, False, ssh)
            except Exception as e:
                error = error or e
        if error:
            raise OperationError(str(error)) from error


async def _soltar_seguro(door_id: str) -> None:
    try:
        await asyncio.shield(_soltar(door_id))
    except Exception:
        pass


async def parar_puerta(door_id: str) -> None:
    """Corta lo que esté en marcha: cancela la tarea y deja los relés sin
    corriente. Es lo que hace "Cortar pulso"."""
    cancel_door_pulse(door_id)
    await _soltar(door_id)


async def send_door_state(door_id: str, on: bool) -> dict:
    """Abrir (True) / cerrar (False) y dejarlo así. Con un relé, es
    ON/OFF directo. Con dos relés o mando, el movimiento completo (ver
    hold_door_open / close_door). Devuelve la ficha de la puerta, que es lo que
    necesita quien llama para poner su nombre en el mensaje."""
    door, _ = await _ctx_puerta(door_id)
    if _tipo(door) == store.ACT_RELE:
        return await _rele_puerta(door_id, on)
    if on:
        return await hold_door_open(door_id)
    await close_door(door_id)
    return door


async def _recorrido_apertura(door_id: str, pulso: float) -> None:
    await _energizar(door_id, True)
    await asyncio.sleep(pulso)
    # Con dos relés el motor para al acabar el recorrido; con uno, el relé se
    # queda activo (es lo que mantiene abierto) hasta que se cierre.
    door, _ = await _ctx_puerta(door_id)
    if _tipo(door) == store.ACT_DOS_RELES:
        await _soltar(door_id)


async def _recorrido_cierre(door_id: str, pulso: float, con_fase: bool) -> None:
    door, _ = await _ctx_puerta(door_id)
    tipo = _tipo(door)
    if tipo == store.ACT_RELE:
        await _soltar(door_id)
        if con_fase:
            await asyncio.sleep(pulso)
        return
    await _energizar(door_id, False)
    await asyncio.sleep(pulso)
    if tipo == store.ACT_DOS_RELES:
        await _soltar(door_id)


async def _fase(door_id: str, fase: str, mantenida: bool | None = None) -> None:
    await asyncio.to_thread(store.set_door_runtime, door_id, fase, mantenida)


def pulse_door(door_id: str, seconds: float | None = None, *, on_finish=None) -> asyncio.Task:
    """Abrir (pulso). Cancelable con cancel_door_pulse() o por cualquier otro
    pulso de la misma puerta. `seconds=None` toma el pulso configurado en la
    ficha (`pulse_seconds`: lo que tarda el recorrido).

    Una PUERTA abre y se acabó: con un relé lo activa `pulse_seconds` y lo
    suelta; con dos relés pulsa el de abrir; con mando manda la tecla.
    Un PORTÓN (modo "porton") hace el recorrido completo: abre (fase
    "abriendo"), sigue abierto `paso_seconds` para que entre o salga el coche
    mientras el plano enseña el magnético (fase "paso") y cierra por sí solo
    (fase "cerrando"), que es lo que lo deja bloqueado.

    Devuelve la tarea sin esperarla — quien llama decide si le importa cuándo
    acaba. `on_finish` recibe el mensaje del resultado para que una sesión
    pueda pintarlo."""
    async def _pulse():
        nombre = (find("doors", door_id) or {}).get("name", door_id)
        try:
            door, _ = await _ctx_puerta(door_id)
            pulso = float(door.get("pulse_seconds", 2)) if seconds is None else float(seconds)
            await _fase(door_id, "abriendo", False)
            await _recorrido_apertura(door_id, pulso)
            if door.get("modo") == store.MODO_PORTON:
                await _fase(door_id, "paso")
                await asyncio.sleep(float(door.get("paso_seconds", 3)))
                await _fase(door_id, "cerrando")
                await _recorrido_cierre(door_id, pulso, True)
            elif _tipo(door) == store.ACT_RELE:
                await _soltar(door_id)
            msg = f"✅ {nombre} abierta"
        except asyncio.CancelledError:
            # El re-raise es lo que deja la tarea CANCELADA y no "terminada":
            # es la diferencia entre "se cortó el pulso" y "el pulso acabó
            # solo", y de ella depende que el auto-cierre no pise un
            # "Mantener abierto" posterior. Con dos relés, además, el motor no
            # puede quedarse en marcha.
            if _tipo(find("doors", door_id) or {}) == store.ACT_DOS_RELES:
                await _soltar_seguro(door_id)
            msg = f"⏹️ Pulso de {nombre} cortado"
            raise
        except Exception as e:
            await _soltar_seguro(door_id)
            msg = f"❌ {nombre}: {e}"
        finally:
            await asyncio.to_thread(store.set_door_runtime, door_id, "")
            if on_finish:
                await on_finish(msg)

    return _registrar_tarea(door_id, _pulse)


def close_door(door_id: str, *, on_finish=None) -> asyncio.Task:
    """Cerrar y bloquear: recorrido de cierre y se quita lo de "mantenida".
    Con un relé, es apagarlo (la cerradura vuelve a quedar echada); con dos
    relés, pulsa el de cerrar; con mando, manda la tecla de cerrar. En un
    portón (o con dos relés/mando) el recorrido se enseña como fase "cerrando"
    durante `pulse_seconds`, y al acabar el plano vuelve a dar el magnético en
    reposo.

    Comparte registro con pulse_door: cancela el pulso que hubiera en marcha,
    y "Cortar pulso" también corta un cierre en curso."""
    async def _cerrar():
        nombre = (find("doors", door_id) or {}).get("name", door_id)
        try:
            door, _ = await _ctx_puerta(door_id)
            pulso = float(door.get("pulse_seconds", 2))
            visual = door.get("modo") == store.MODO_PORTON
            if visual or _tipo(door) != store.ACT_RELE:
                await _fase(door_id, "cerrando", False)
            else:
                await _fase(door_id, "", False)
            await _recorrido_cierre(door_id, pulso, visual)
            msg = f"🔒 {nombre} cerrada y bloqueada"
        except asyncio.CancelledError:
            if _tipo(find("doors", door_id) or {}) == store.ACT_DOS_RELES:
                await _soltar_seguro(door_id)
            msg = f"⏹️ Cierre de {nombre} cortado"
            raise
        except Exception as e:
            await _soltar_seguro(door_id)
            msg = f"❌ {nombre}: {e}"
        finally:
            await asyncio.to_thread(store.set_door_runtime, door_id, "")
            if on_finish:
                await on_finish(msg)

    return _registrar_tarea(door_id, _cerrar)


def hold_door_open(door_id: str) -> asyncio.Task:
    """Liberar: recorrido de apertura y se queda abierta hasta que alguien
    cierre (`mantenida`), con el magnético a la vista. Con un relé, el relé
    sigue activo; con dos relés o mando, el movimiento acaba y no se manda nada
    más. Devuelve la tarea; su resultado es la ficha de la puerta."""
    async def _liberar():
        try:
            door, _ = await _ctx_puerta(door_id)
            pulso = float(door.get("pulse_seconds", 2))
            await _fase(door_id, "abriendo", False)
            if _tipo(door) == store.ACT_RELE and door.get("modo") != store.MODO_PORTON:
                await _energizar(door_id, True)
            else:
                await _recorrido_apertura(door_id, pulso)
            await asyncio.to_thread(store.set_door_runtime, door_id, "", True)
            return door
        except asyncio.CancelledError:
            if _tipo(find("doors", door_id) or {}) == store.ACT_DOS_RELES:
                await _soltar_seguro(door_id)
            await asyncio.to_thread(store.set_door_runtime, door_id, "")
            raise
        except BaseException:
            await asyncio.to_thread(store.set_door_runtime, door_id, "")
            raise

    return _registrar_tarea(door_id, _liberar)


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
            await _despertar_tv_si_hace_falta(remote)
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
