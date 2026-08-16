"""
Qué puede HACER una automatización, declarado como datos.

Cada acción es un ActionSpec: cómo se llama, en qué bloque del selector va, si
necesita un objetivo y qué ajustes pide. De esa misma declaración salen tres
cosas que antes habría que escribir por triplicado: las opciones del selector
(catalog.py), los campos del formulario (la vista los pinta genéricamente a
partir de `params`) y el despacho real (`run`). Añadir una acción nueva es
añadir una línea a ACTION_SPECS.

Este módulo NO habla con el hardware: para eso están nodes/operations.py y
security/arming.py. Aquí solo se traduce "el registro de una acción" a "qué
verbo hay que llamar", y se devuelve un resumen legible de lo que se hizo, que
es lo que acaba en el registro de eventos.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..nodes import operations as ops
from ..notifications import push
from ..security import arming, groups_store, logs
from ..security.audit import SISTEMA


class ActionError(Exception):
    """No se pudo ejecutar el paso. El motor lo apunta como error de la regla."""


# ── Enganches que pone el motor ─────────────────────────────────────────────
# Se inyectan en vez de importarse para no cerrar el círculo: el motor importa
# este módulo, así que este módulo no puede importar el motor.
#
# `_avisar_eco` es la pieza que evita las guerras entre reglas: cuando una
# acción cambia algo, el detector de flancos ignora ese cambio durante unos
# segundos. Sin ello, "la regla A enciende la luz" dispara "la regla B, que la
# apaga", que vuelve a disparar a A, y así toda la noche.
_avisar_eco: Callable[[str], None] | None = None
_ejecutar_regla: Callable[[str], Awaitable[str]] | None = None


def set_hooks(*, echo=None, run_rule=None) -> None:
    global _avisar_eco, _ejecutar_regla
    _avisar_eco = echo
    _ejecutar_regla = run_rule


def _eco(*señales: str) -> None:
    if _avisar_eco:
        for s in señales:
            _avisar_eco(s)


# ── Ayudas para leer el objetivo ────────────────────────────────────────────
def partir(target: str, trozos: int = 2) -> list[str]:
    """Un objetivo es "<tipo>:<id>" y, para las teclas de mando y los pines,
    "<tipo>:<id>:<id2>". Se parte con un tope a propósito: un split(":") sin
    límite se rompería con cualquier id que llevara dos puntos."""
    partes = target.split(":", trozos - 1)
    while len(partes) < trozos:
        partes.append("")
    return partes


def _tri(params: dict, clave: str = "on", por_defecto: str = "on") -> bool | None:
    """"on"/"off"/"toggle" -> True/False/None, que es justo lo que esperan los
    verbos de operations para "enciende / apaga / dale la vuelta"."""
    valor = str(params.get(clave, por_defecto)).lower()
    if valor in ("toggle", "conmutar", "none"):
        return None
    return valor in ("on", "true", "1", "si", "sí")


def _num(params: dict, clave: str, por_defecto: float) -> float:
    try:
        return float(params.get(clave, por_defecto))
    except (TypeError, ValueError):
        return por_defecto


# ── Los verbos ──────────────────────────────────────────────────────────────
async def _run_light(target: str, params: dict) -> str:
    _, light_id = partir(target)
    estado = await ops.set_light(light_id, _tri(params))
    _eco(f"state:{light_id}")
    nombre = (ops.find("lights", light_id) or {}).get("name", light_id)
    return f"{nombre}: {'encendida' if estado else 'apagada'}"


async def _run_door_pulse(target: str, params: dict) -> str:
    _, door_id = partir(target)
    segundos = _num(params, "seconds", 0)
    # Se ESPERA a que acabe el pulso, al revés que en la web: dentro de una
    # secuencia, el paso siguiente tiene que ver la puerta ya cerrada. Si no,
    # "abre y luego avisa" avisaría mientras aún se está abriendo.
    tarea = ops.pulse_door(door_id, segundos or None)
    _eco(f"state:{door_id}")
    try:
        await tarea
    except asyncio.CancelledError:
        raise
    except Exception as e:
        raise ActionError(str(e)) from e
    nombre = (ops.find("doors", door_id) or {}).get("name", door_id)
    return f"{nombre}: abierta por pulso"


async def _run_door_hold(target: str, params: dict) -> str:
    _, door_id = partir(target)
    abierta = bool(_tri(params, "open"))
    ops.cancel_door_pulse(door_id)
    door = await ops.send_door_state(door_id, abierta)
    _eco(f"state:{door_id}")
    return f"{door['name']}: mantenida {'abierta' if abierta else 'cerrada'}"


async def _run_node_pin(target: str, params: dict) -> str:
    # El pin va en los ajustes y no en el objetivo porque no hay una lista de
    # pines que ofrecer: son los que tenga cableados quien monte el nodo.
    _, node_id = partir(target)
    pin = str(params.get("pin", "")).strip()
    if not pin:
        raise ActionError("falta indicar qué pin escribir")
    encendido = bool(_tri(params))
    await ops.set_node_pin(node_id, pin, encendido)
    return f"{ops.node_name(node_id)} pin {pin}: {'ON' if encendido else 'OFF'}"


async def _run_ir(target: str, params: dict) -> str:
    _, remote_id, button_id = partir(target, 3)
    return await ops.send_remote_button(remote_id, button_id)


async def _run_host_button(target: str, params: dict) -> str:
    _, button_id = partir(target)
    salida = await ops.run_host_button(button_id)
    etiqueta = (ops.find("host_buttons", button_id) or {}).get("label", button_id)
    return f"{etiqueta}: {salida[:120]}" if salida else etiqueta


async def _run_host_action(target: str, params: dict) -> str:
    _, host_id = partir(target)
    accion = str(params.get("accion", "apagar"))
    salida = await ops.host_action(host_id, accion)
    # El equipo se va a caer: se apunta ya para que el flanco de "se ha ido de
    # línea" que llegará en unos segundos no dispare otra regla como si se
    # hubiera apagado solo.
    if accion in ("apagar", "reiniciar"):
        _eco(f"host:{host_id}")
    nombre = ops.host_name(host_id)
    return f"{nombre}: {accion} · {salida[:120]}" if salida else f"{nombre}: {accion}"


async def _run_wol(target: str, params: dict) -> str:
    _, host_id = partir(target)
    await asyncio.to_thread(ops.wake_host, host_id)
    _eco(f"host:{host_id}")
    return f"{ops.host_name(host_id)}: encendido por Wake-on-LAN"


async def _run_group_arm(target: str, params: dict) -> str:
    _, group_id = partir(target)
    quiero = _tri(params, "armed")
    if quiero is None:
        group, nuevo = await arming.toggle_group_armed(group_id, SISTEMA)
    else:
        group = await arming.set_group_armed(group_id, quiero, SISTEMA)
        nuevo = quiero
    _eco(f"group:{group_id}")
    if group["is_principal"]:
        _eco("system")
    return f"{group['name']}: {'armado' if nuevo else 'desarmado'}"


async def _run_system_arm(target: str, params: dict) -> str:
    quiero = _tri(params, "armed")
    nuevo = (await arming.toggle_system_armed(SISTEMA) if quiero is None
             else await arming.set_system_armed(quiero, SISTEMA))
    _eco("system")
    principal = await asyncio.to_thread(groups_store.ensure_principal_group)
    _eco(f"group:{principal['id']}")
    return f"Sistema: {'armado' if nuevo else 'desarmado'}"


async def _run_notify(target: str, params: dict) -> str:
    titulo = str(params.get("title") or "NOXUS").strip()
    cuerpo = str(params.get("body") or "").strip()
    destino = str(params.get("destino") or push.TODOS)
    await asyncio.to_thread(push.enviar_notificacion, titulo, cuerpo, destino)
    return f"Aviso enviado: {titulo}"


async def _run_log(target: str, params: dict) -> str:
    texto = str(params.get("text") or "").strip()
    logs.registrar(logs.AUTOMATIZACIONES, "NOTA", SISTEMA, texto)
    return f"Anotado: {texto[:80]}"


async def _run_wait(target: str, params: dict) -> str:
    segundos = _num(params, "seconds", 5)
    await asyncio.sleep(max(0.0, segundos))
    return f"Esperados {segundos:g} s"


async def _run_rule(target: str, params: dict) -> str:
    _, rule_id = partir(target)
    if _ejecutar_regla is None:
        raise ActionError("el motor no está en marcha")
    return await _ejecutar_regla(rule_id)


async def _run_rule_enable(target: str, params: dict) -> str:
    from . import store
    _, rule_id = partir(target)
    activar = bool(_tri(params, "enabled"))
    regla = await asyncio.to_thread(
        store.set_enabled, rule_id, activar,
        "" if activar else "desactivada por otra automatización",
    )
    if regla is None:
        raise ActionError("esa automatización ya no existe")
    return f"{regla['name']}: {'activada' if activar else 'desactivada'}"


# ── Declaración ─────────────────────────────────────────────────────────────
# Vocabulario de `params` que entiende la vista y pinta sola:
#   bool     interruptor
#   tristate desplegable encender/apagar/conmutar
#   choice   desplegable con opciones fijas
#   number   número con mínimo/máximo
#   text     texto libre
_TRISTATE_ONOFF = {"name": "on", "kind": "tristate", "label": "Qué hacer",
                   "options": [["on", "Encender"], ["off", "Apagar"], ["toggle", "Conmutar"]],
                   "default": "on"}


@dataclass(frozen=True)
class ActionSpec:
    type: str
    label: str
    kind_label: str                 # bloque del selector
    icon: str
    target_kind: str | None         # None = no lleva objetivo
    run: Callable[[str, dict], Awaitable[str]]
    params: tuple[dict, ...] = field(default_factory=tuple)
    # Cómo se lee en la tarjeta de la regla — ver PredicateSpec.frase.
    frase: str = ""


ACTION_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec("light.set", "encender / apagar", "Luces", "lightbulb",
               "light", _run_light, (_TRISTATE_ONOFF,), frase="{objetivo}: {on}"),
    ActionSpec("door.pulse", "abrir (pulso)", "Puertas", "door-open",
               "door", _run_door_pulse,
               ({"name": "seconds", "kind": "number", "label": "Segundos",
                 "default": 0, "min": 0, "max": 600,
                 "help": "0 = el pulso configurado en la ficha de la puerta"},),
               frase="abrir {objetivo}"),
    ActionSpec("door.hold", "mantener abierta / cerrada", "Puertas", "lock",
               "door", _run_door_hold,
               ({"name": "open", "kind": "bool", "label": "Mantener abierta", "default": False},),
               frase="mantener {objetivo} {open}"),
    ActionSpec("node_pin.set", "escribir un pin", "Pines", "toggle-left",
               "node", _run_node_pin,
               ({"name": "pin", "kind": "text", "label": "Pin", "default": ""},
                _TRISTATE_ONOFF),
               frase="{objetivo} pin {pin}: {on}"),
    ActionSpec("ir_button.press", "pulsar tecla", "Mandos", "gamepad-2",
               "ir_button", _run_ir, frase="pulsar {objetivo}"),
    ActionSpec("host_button.run", "ejecutar botón", "Equipos", "square-mouse-pointer",
               "host_button", _run_host_button, frase="{objetivo}"),
    ActionSpec("host.action", "apagar / reiniciar", "Equipos", "power",
               "host", _run_host_action,
               ({"name": "accion", "kind": "choice", "label": "Acción",
                 "options": [["apagar", "Apagar"], ["reiniciar", "Reiniciar"]],
                 "default": "apagar"},),
               frase="{objetivo}: {accion}"),
    ActionSpec("host.wol", "encender (Wake-on-LAN)", "Equipos", "zap",
               "host", _run_wol, frase="encender {objetivo} (WOL)"),
    ActionSpec("group.arm", "armar / desarmar", "Alarma", "layers",
               "group", _run_group_arm,
               ({**_TRISTATE_ONOFF, "name": "armed", "label": "Qué hacer",
                 "options": [["on", "Armar"], ["off", "Desarmar"], ["toggle", "Conmutar"]]},),
               frase="{objetivo}: {armed}"),
    ActionSpec("system.arm", "Armar / desarmar el sistema", "Alarma", "shield",
               None, _run_system_arm,
               ({**_TRISTATE_ONOFF, "name": "armed", "label": "Qué hacer",
                 "options": [["on", "Armar"], ["off", "Desarmar"], ["toggle", "Conmutar"]]},),
               frase="el sistema: {armed}"),
    ActionSpec("notify", "Enviar un aviso al móvil", "Avisos", "bell",
               None, _run_notify,
               ({"name": "title", "kind": "text", "label": "Título", "default": "NOXUS"},
                {"name": "body", "kind": "text", "label": "Mensaje", "default": ""}),
               frase="avisar «{title}»"),
    ActionSpec("log", "Anotar en el registro", "Avisos", "clipboard-list",
               None, _run_log,
               ({"name": "text", "kind": "text", "label": "Texto", "default": ""},),
               frase="anotar «{text}»"),
    ActionSpec("wait", "Esperar", "Control", "timer",
               None, _run_wait,
               ({"name": "seconds", "kind": "number", "label": "Segundos",
                 "default": 5, "min": 0, "max": 3600},),
               frase="esperar {seconds} s"),
    ActionSpec("rule.run", "ejecutar", "Control", "play",
               "rule", _run_rule, frase="ejecutar «{objetivo}»"),
    ActionSpec("rule.enable", "activar / desactivar", "Control", "toggle-right",
               "rule", _run_rule_enable,
               ({"name": "enabled", "kind": "bool", "label": "Activarla", "default": True},),
               frase="«{objetivo}»: {enabled}"),
)

BY_TYPE = {a.type: a for a in ACTION_SPECS}


async def dispatch(paso: dict) -> str:
    """Ejecuta UN paso y devuelve el resumen de lo que hizo."""
    spec = BY_TYPE.get(paso.get("type", ""))
    if spec is None:
        raise ActionError(f"acción desconocida: {paso.get('type')}")
    try:
        return await spec.run(paso.get("target", ""), paso.get("params") or {})
    except asyncio.CancelledError:
        raise
    except ActionError:
        raise
    except (ops.OperationError, arming.ArmingError) as e:
        raise ActionError(str(e)) from e
    except Exception as e:
        raise ActionError(f"{type(e).__name__}: {e}") from e
