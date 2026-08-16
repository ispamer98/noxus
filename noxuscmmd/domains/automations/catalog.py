"""
Todo lo que se puede elegir al montar una automatización: qué la dispara, qué
condiciones puede pedir y qué puede hacer — construido con lo que existe AHORA
MISMO en la casa.

Se arma EN CADA LLAMADA. Nunca en el import, nunca en una constante de módulo.
Es exactamente el motivo que explica el comentario de _build_widget_catalog en
nodes/state.py: lo que se compone en Python dentro de una vista se evalúa una
sola vez, al compilar, y a partir de ahí el desplegable enseña para siempre la
foto del arranque — das de alta una luz y no aparece; borras un equipo y sigue
ofreciéndose. Aquí, en cambio, dar de alta cualquier cosa la hace aparecer en
la siguiente vuelta del sync_loop, sin recargar la página.

Cada opción se identifica con una referencia plana "<tipo>:<id>", la misma
gramática que ya usa el plano (ver nodes/state.py: add_to_floor parte con
split(":", 1)). Las teclas de mando llevan tres trozos porque hacen falta dos
ids: "ir_button:<mando>:<tecla>".
"""
from dataclasses import dataclass, field

from ..devices import registry
from ..nodes import store as nodes_store
from ..security import groups_store
from . import actions as acciones_mod
from . import store as auto_store


# ── Disparadores y condiciones, declarados igual que las acciones ───────────
@dataclass(frozen=True)
class PredicateSpec:
    kind: str
    label: str              # frase en tercera persona: "se abre", "está armado"
    kind_label: str         # bloque del selector
    icon: str
    target_kind: str | None
    params: tuple[dict, ...] = field(default_factory=tuple)
    # Cómo se lee esto en la tarjeta de la regla. "{objetivo}" es el nombre del
    # elemento y "{loquesea}" cualquiera de sus params. Se declara aquí, junto
    # a la definición, en vez de componerlo a base de pegar trozos: pegándolos
    # salían cosas como "PC — apagar / reiniciar apagar".
    frase: str = ""


_DIAS = {"name": "days", "kind": "days", "label": "Días de la semana",
         "default": [0, 1, 2, 3, 4, 5, 6]}

TRIGGER_SPECS: tuple[PredicateSpec, ...] = (
    PredicateSpec("sensor.opened", "se abre", "Sensores", "radar", "sensor", frase="{objetivo} se abre"),
    PredicateSpec("sensor.closed", "se cierra", "Sensores", "radar", "sensor", frase="{objetivo} se cierra"),

    PredicateSpec("light.on", "se enciende", "Luces", "lightbulb", "light", frase="{objetivo} se enciende"),
    PredicateSpec("light.off", "se apaga", "Luces", "lightbulb", "light", frase="{objetivo} se apaga"),

    PredicateSpec("door.opened", "se abre", "Puertas", "door-open", "door", frase="{objetivo} se abre"),
    PredicateSpec("door.closed", "se cierra", "Puertas", "door-closed", "door", frase="{objetivo} se cierra"),

    PredicateSpec("host.online", "se pone en línea", "Equipos", "server", "host", frase="{objetivo} se pone en línea"),
    PredicateSpec("host.offline", "se va de línea", "Equipos", "server-off", "host", frase="{objetivo} se va de línea"),
    PredicateSpec("host.temp_above", "supera una temperatura", "Equipos", "thermometer", "host",
                  ({"name": "value", "kind": "number", "label": "Grados",
                    "default": 70, "min": -50, "max": 150},),
                  frase="{objetivo} pasa de {value} °C"),
    PredicateSpec("host.temp_below", "baja de una temperatura", "Equipos", "thermometer-snowflake", "host",
                  ({"name": "value", "kind": "number", "label": "Grados",
                    "default": 60, "min": -50, "max": 150},),
                  frase="{objetivo} baja de {value} °C"),

    PredicateSpec("group.armed", "se arma", "Alarma", "layers", "group", frase="{objetivo} se arma"),
    PredicateSpec("group.disarmed", "se desarma", "Alarma", "layers", "group", frase="{objetivo} se desarma"),
    PredicateSpec("system.armed", "Se arma el sistema", "Alarma", "shield-check", None, frase="se arma el sistema"),
    PredicateSpec("system.disarmed", "Se desarma el sistema", "Alarma", "shield-off", None, frase="se desarma el sistema"),

    PredicateSpec("time.at", "A una hora concreta", "Horarios", "clock", None,
                  ({"name": "hhmm", "kind": "time", "label": "Hora", "default": "22:00"},
                   _DIAS,
                   {"name": "catch_up_minutes", "kind": "number",
                    "label": "Recuperar si el panel estaba apagado (minutos)",
                    "default": 0, "min": 0, "max": 720,
                    "help": "0 = no recuperar. Si el panel estaba apagado a esa hora, "
                            "no se ejecuta al arrancar."}),
                  frase="a las {hhmm}, {days}"),
    PredicateSpec("time.every", "Cada cierto tiempo", "Horarios", "timer", None,
                  ({"name": "minutes", "kind": "number", "label": "Cada N minutos",
                    "default": 30, "min": 1, "max": 10080},),
                  frase="cada {minutes} min"),
)

_SI_NO_ABIERTO = {"name": "value", "kind": "choice", "label": "Estado",
                  "options": [["true", "Abierto"], ["false", "Cerrado"]], "default": "true"}
_SI_NO_ENCENDIDO = {"name": "value", "kind": "choice", "label": "Estado",
                    "options": [["true", "Encendida"], ["false", "Apagada"]], "default": "true"}
_SI_NO_LINEA = {"name": "value", "kind": "choice", "label": "Estado",
                "options": [["true", "En línea"], ["false", "Fuera de línea"]], "default": "true"}
_SI_NO_ARMADO = {"name": "value", "kind": "choice", "label": "Estado",
                 "options": [["true", "Armado"], ["false", "Desarmado"]], "default": "true"}

CONDITION_SPECS: tuple[PredicateSpec, ...] = (
    PredicateSpec("sensor.is", "está", "Sensores", "radar", "sensor", (_SI_NO_ABIERTO,),
                  frase="{objetivo}: {value}"),
    PredicateSpec("light.is", "está", "Luces", "lightbulb", "light", (_SI_NO_ENCENDIDO,),
                  frase="{objetivo}: {value}"),
    PredicateSpec("door.is", "está", "Puertas", "door-open", "door", (_SI_NO_ABIERTO,),
                  frase="{objetivo}: {value}"),
    PredicateSpec("host.is_online", "está", "Equipos", "server", "host", (_SI_NO_LINEA,),
                  frase="{objetivo}: {value}"),
    PredicateSpec("host.temp", "temperatura de CPU", "Equipos", "thermometer", "host",
                  ({"name": "op", "kind": "choice", "label": "Comparación",
                    "options": [[">", "mayor que"], [">=", "mayor o igual que"],
                                ["<", "menor que"], ["<=", "menor o igual que"]],
                    "default": ">"},
                   {"name": "value", "kind": "number", "label": "Grados",
                    "default": 70, "min": -50, "max": 150}),
                  frase="{objetivo}: CPU {op} {value} °C"),
    PredicateSpec("group.is_armed", "está", "Alarma", "layers", "group", (_SI_NO_ARMADO,),
                  frase="{objetivo}: {value}"),
    PredicateSpec("system.is_armed", "El sistema está", "Alarma", "shield", None, (_SI_NO_ARMADO,),
                  frase="el sistema: {value}"),
    PredicateSpec("time.between", "La hora está entre", "Horarios", "clock", None,
                  ({"name": "from", "kind": "time", "label": "Desde", "default": "08:00"},
                   {"name": "to", "kind": "time", "label": "Hasta", "default": "23:00"}),
                  frase="la hora está entre {from} y {to}"),
    PredicateSpec("day_of_week", "Es uno de estos días", "Horarios", "calendar", None, (_DIAS,),
                  frase="es {days}"),
    PredicateSpec("rule.idle_for", "Esta regla lleva sin ejecutarse", "Control", "hourglass", None,
                  ({"name": "minutes", "kind": "number", "label": "Minutos",
                    "default": 30, "min": 1, "max": 10080},),
                  frase="lleva {minutes} min sin ejecutarse"),
)

TRIGGERS_BY_KIND = {t.kind: t for t in TRIGGER_SPECS}
CONDITIONS_BY_KIND = {c.kind: c for c in CONDITION_SPECS}

# Acciones cuyo objetivo YA se explica solo: "TV · Subir volumen" o "Reiniciar
# servicios NOXUS" no necesitan que se les pegue detrás "— pulsar tecla".
_SOLO_ENTIDAD = {"ir_button.press", "host_button.run", "rule.run"}


# ── Inventario de entidades ─────────────────────────────────────────────────
def _sensores(data: dict) -> list[tuple[str, str]]:
    """Los de fábrica y los dados de alta desde la web comparten espacio de
    ids (sensor_states es un único diccionario plano), así que aquí van juntos.
    Los ocultos se descartan: si no se ven en el panel, tampoco tiene sentido
    ofrecerlos para automatizar."""
    ocultos = registry.hidden_ids()
    vistos, salida = set(), []
    for s in data["factory_sensors"] + data["sensors"]:
        if s["id"] in ocultos or s["id"] in vistos:
            continue
        vistos.add(s["id"])
        salida.append((s["id"], s["name"]))
    return salida


def _nodos(data: dict) -> list[tuple[str, str]]:
    """Nodos con pines accionables: la Raspberry/Pi Zero de siempre más los
    dados de alta desde la web."""
    salida = [(nid, h.name) for nid, h in registry.gpio_hosts().items()]
    salida += [(n["id"], n["name"]) for n in data["nodes"]]
    return salida


def entities(kind: str, data: dict | None = None) -> list[dict]:
    """[{"value": "<tipo>:<id>", "label": ...}] de una familia. Vacío si no hay
    ninguna — quien llama decide si eso significa "no ofrecer este bloque"."""
    datos = data if data is not None else nodes_store.read_all()

    def refs(pares, prefijo=kind):
        return [{"value": f"{prefijo}:{i}", "label": n} for i, n in pares]

    if kind == "light":
        return refs([(l["id"], l["name"]) for l in datos["lights"]])
    if kind == "door":
        return refs([(d["id"], d["name"]) for d in datos["doors"]])
    if kind == "sensor":
        return refs(_sensores(datos))
    if kind == "node":
        return refs(_nodos(datos))
    if kind == "host":
        return refs([(h["id"], h["name"]) for h in datos["hosts"]])
    if kind == "host_button":
        nombres = {h["id"]: h["name"] for h in datos["hosts"]}
        return refs([
            (b["id"], f"{nombres.get(b['host_id'], b['host_id'])} · {b['label']}")
            for b in datos["host_buttons"]
        ])
    if kind == "ir_button":
        return [
            {"value": f"ir_button:{r['id']}:{b['id']}",
             "label": f"{r['name']} · {b['label']}"}
            for r in datos["ir_remotes"] for b in r.get("buttons", [])
        ]
    if kind == "group":
        return refs([(g["id"], g["name"]) for g in groups_store.read_all()])
    if kind == "rule":
        return refs([(r["id"], r["name"] or "(sin nombre)") for r in auto_store.read_all()])
    return []


_FAMILIAS = ("light", "door", "sensor", "node", "host", "host_button",
             "ir_button", "group", "rule")


def labels(data: dict | None = None) -> dict[str, str]:
    """referencia -> nombre de AHORA, para que la lista de reglas pueda
    escribir "Si el PC se pone en línea → Encender Salón" sin cruzar cuatro
    colecciones por fila. Una referencia que no esté aquí es una regla rota:
    apunta a algo que ya no existe."""
    datos = data if data is not None else nodes_store.read_all()
    salida: dict[str, str] = {}
    for familia in _FAMILIAS:
        for e in entities(familia, datos):
            salida[e["value"]] = e["label"]
    return salida


# ── Construcción de las secciones ───────────────────────────────────────────
def _seccion(catalogo: list[dict], etiqueta: str, icono: str, opciones: list[dict]) -> None:
    """Las familias vacías no se añaden: un encabezado suelto sin nada debajo
    solo estorba (mismo criterio que _build_widget_catalog)."""
    if not opciones:
        return
    existente = next((s for s in catalogo if s["label"] == etiqueta), None)
    if existente:
        existente["options"].extend(opciones)
    else:
        catalogo.append({"label": etiqueta, "icon": icono, "options": opciones})


def clave_de(spec) -> str:
    """Los disparadores/condiciones se identifican con `kind` y las acciones
    con `type`. Es la única diferencia entre las dos declaraciones, y se
    resuelve aquí para que el resto del módulo las trate igual."""
    return getattr(spec, "kind", None) or spec.type


def _opciones_de(spec, data: dict, componer) -> list[dict]:
    clave = clave_de(spec)
    if spec.target_kind is None:
        return [{"value": f"{clave}|", "label": spec.label, "icon": spec.icon,
                 "kind": clave, "target": ""}]
    return [
        {"value": f"{clave}|{e['value']}", "label": componer(e["label"], spec),
         "icon": spec.icon, "kind": clave, "target": e["value"]}
        for e in entities(spec.target_kind, data)
    ]


def _predicados(specs, data: dict) -> list[dict]:
    catalogo: list[dict] = []
    for spec in specs:
        _seccion(catalogo, spec.kind_label, spec.icon,
                 _opciones_de(spec, data, lambda nombre, s: f"{nombre} {s.label}"))
    return catalogo


def build_trigger_catalog(data: dict | None = None) -> list[dict]:
    return _predicados(TRIGGER_SPECS, data if data is not None else nodes_store.read_all())


def build_condition_catalog(data: dict | None = None) -> list[dict]:
    return _predicados(CONDITION_SPECS, data if data is not None else nodes_store.read_all())


def build_action_catalog(data: dict | None = None) -> list[dict]:
    datos = data if data is not None else nodes_store.read_all()
    catalogo: list[dict] = []
    for spec in acciones_mod.ACTION_SPECS:
        def componer(nombre, s=spec):
            return nombre if s.type in _SOLO_ENTIDAD else f"{nombre} — {s.label}"
        opciones = [
            {**o, "value": f"{spec.type}|{o['target']}", "kind": spec.type}
            for o in _opciones_de(spec, datos, componer)
        ]
        _seccion(catalogo, spec.kind_label, spec.icon, opciones)
    return catalogo


def params_de(kind: str) -> tuple[dict, ...]:
    """Los ajustes que pide un disparador/condición/acción. La vista los pinta
    genéricamente a partir de esto, que es lo que hace que una acción nueva no
    obligue a tocar la interfaz."""
    spec = (TRIGGERS_BY_KIND.get(kind) or CONDITIONS_BY_KIND.get(kind)
            or acciones_mod.BY_TYPE.get(kind))
    return spec.params if spec else ()


# ── Resumen en lenguaje llano ───────────────────────────────────────────────
# La tarjeta de cada regla enseña lo que hace escrito en cristiano. Se genera
# desde el propio JSON de la regla, así que no puede mentir: si alguien edita
# un paso, el resumen cambia con él.
_DIAS_CORTOS = ("L", "M", "X", "J", "V", "S", "D")


def _dias_texto(dias) -> str:
    dias = sorted(set(dias or []))
    if not dias or len(dias) == 7:
        return "todos los días"
    if dias == [0, 1, 2, 3, 4]:
        return "de lunes a viernes"
    if dias == [5, 6]:
        return "fines de semana"
    return ", ".join(_DIAS_CORTOS[d] for d in dias if 0 <= d < 7)


def _param_texto(campo: dict, valor) -> str:
    """Un ajuste, escrito para leerse. Las opciones se traducen con SUS PROPIAS
    etiquetas declaradas, así que añadir una opción nueva se lee bien sin tocar
    nada de aquí."""
    if campo["kind"] == "days":
        return _dias_texto(valor)
    if campo["kind"] in ("choice", "tristate"):
        etiquetas = {str(v): t for v, t in campo.get("options", [])}
        return etiquetas.get(str(valor), str(valor)).lower()
    if campo["kind"] == "bool":
        etiqueta = campo.get("label", "").lower()
        return etiqueta if valor else f"no {etiqueta}"
    if campo["kind"] == "number":
        try:
            return f"{float(valor):g}"
        except (TypeError, ValueError):
            return str(valor)
    return str(valor)


def _componer(spec, target: str, params: dict, labels: dict) -> str:
    """Rellena la plantilla `frase` de la especificación. Sin plantilla, se cae
    a "objetivo + etiqueta", que es lo que valía antes de que las hubiera."""
    nombre = labels.get(target, "") if target else ""
    if target and not nombre:
        nombre = "⚠️ ya no existe"
    valores = {"objetivo": nombre}
    for campo in spec.params:
        valores[campo["name"]] = _param_texto(
            campo, params.get(campo["name"], campo.get("default")))
    if not spec.frase:
        return f"{nombre} {spec.label}".strip()
    try:
        return spec.frase.format(**valores).strip()
    except (KeyError, IndexError):
        return f"{nombre} {spec.label}".strip()


def frase_predicado(p: dict, labels: dict, tabla: dict) -> str:
    spec = tabla.get(p["kind"])
    if spec is None:
        return p["kind"]
    return _componer(spec, p["target"], p["params"], labels)


def frase_accion(a: dict, labels: dict) -> str:
    spec = acciones_mod.BY_TYPE.get(a["type"])
    if spec is None:
        return a["type"]
    texto = _componer(spec, a["target"], a["params"], labels)
    veces = int(a.get("repeat", 1))
    return f"{texto} ×{veces}" if veces > 1 else texto


def resumir(regla: dict, labels: dict) -> str:
    """«A las 22:30 de lunes a viernes · si PC está en línea → PC — apagar»"""
    if regla["triggers"]:
        cuando = " o ".join(frase_predicado(t, labels, TRIGGERS_BY_KIND)
                            for t in regla["triggers"])
    else:
        cuando = "Solo a mano"
    partes = [cuando]
    if regla["conditions"]:
        union = " y " if regla["match"] == "all" else " o "
        partes.append("si " + union.join(
            frase_predicado(c, labels, CONDITIONS_BY_KIND) for c in regla["conditions"]))
    hacer = " · ".join(frase_accion(a, labels) for a in regla["actions"])
    return f"{' · '.join(partes)} → {hacer or 'no hace nada'}"


def build_all(data: dict | None = None) -> dict:
    """Una sola lectura del almacén para todo el catálogo — se llama en cada
    _reload() de la pestaña, así que no conviene que abra el fichero diez
    veces."""
    datos = data if data is not None else nodes_store.read_all()
    todos_los_params = {}
    for coleccion in (TRIGGER_SPECS, CONDITION_SPECS, acciones_mod.ACTION_SPECS):
        for spec in coleccion:
            todos_los_params[clave_de(spec)] = [dict(p) for p in spec.params]
    return {
        "triggers": build_trigger_catalog(datos),
        "conditions": build_condition_catalog(datos),
        "actions": build_action_catalog(datos),
        "params": todos_los_params,
        "labels": labels(datos),
    }
