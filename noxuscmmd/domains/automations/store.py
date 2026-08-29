"""
Persistencia de las automatizaciones. DOS ficheros, a propósito:

- automatizaciones.json        las reglas — configuración hecha a mano, que si
                               se pierde no se recupera.
- automatizaciones_estado.json cuándo se ejecutó cada una por última vez, con
                               qué resultado y sus marcas horarias — se
                               reescribe en cada disparo y es reconstruible.

Separarlos evita reescribir el trabajo del usuario cada vez que salta una
regla. Y son ficheros propios, no una colección más en nodos_dinamicos.json,
por dos motivos: ese fichero se reescribe ENTERO con fsync bajo cerrojo
exclusivo en cada mensaje MQTT y cada ronda de ping (meterle las escrituras del
motor frenaría el camino de la alarma), y su _apply_defaults normaliza el
documento completo en cada lectura descartando claves que no conozca.

La escritura es ATÓMICA (temporal + os.replace), a diferencia de
groups_store/access, que truncan el fichero en el sitio: ahí un corte de luz a
mitad deja un JSON partido, y el _read siguiente devuelve la lista vacía en
silencio. Para las reglas eso significaría "no hay automatizaciones" y el motor
se quedaría mudo sin que nadie se entere, así que aquí un fichero ilegible se
DENUNCIA en vez de tragárselo.
"""
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

from ...core import bus

ARCHIVO = Path(os.getenv("AUTOMATIZACIONES_FILE", "automatizaciones.json"))
ARCHIVO_ESTADO = Path(os.getenv("AUTOMATIZACIONES_ESTADO_FILE", "automatizaciones_estado.json"))


class ArchivoCorrupto(Exception):
    """El fichero de reglas existe pero no se puede leer. NO se confunde con
    "no hay reglas": el motor se planta y avisa en vez de comportarse como si
    el usuario no hubiera configurado nada."""


# La ficha de una regla, campo a campo. TODAS las reglas se reescriben con
# exactamente estas claves (ver _normalizar), igual que se hace con los equipos
# en nodes/store.py: una regla creada hoy y una de la primera versión tienen la
# misma forma, y así se ven también al abrir el JSON a mano.
_DEFECTOS_REGLA = {
    "name": "",
    "description": "",
    "icon": "workflow",
    "folder_id": "",
    "enabled": True,
    "triggers": (),
    "match": "all",          # "all" = se cumplen TODAS · "any" = basta UNA
    "conditions": (),
    "actions": (),
    "cooldown_seconds": 60,
    "max_fires_per_minute": 10,
    "disabled_reason": "",   # lo rellena el cortafuegos o la revisión de referencias
}

# Ajustes por paso de acción, con sus valores por defecto.
_DEFECTOS_ACCION = {
    "type": "",
    "target": "",
    "params": {},
    "repeat": 1,
    # Entre repeticiones tiene que haber hueco: dos send_data seguidos sin
    # pausa el aparato receptor se los come, y el "bajar velocidad dos veces"
    # acaba bajando una sola.
    "repeat_pause": 0.4,
    "timeout": 20,
    "continue_on_error": False,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _ahora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _entero(valor, por_defecto: int, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return por_defecto


def _decimal(valor, por_defecto: float, minimo: float, maximo: float) -> float:
    try:
        return max(minimo, min(maximo, float(valor)))
    except (TypeError, ValueError):
        return por_defecto


def _normalizar_accion(paso: dict) -> dict:
    return {
        "type": str(paso.get("type", "")),
        "target": str(paso.get("target", "")),
        "params": paso.get("params") if isinstance(paso.get("params"), dict) else {},
        "repeat": _entero(paso.get("repeat"), 1, 1, 50),
        "repeat_pause": _decimal(paso.get("repeat_pause"), 0.4, 0.0, 60.0),
        "timeout": _entero(paso.get("timeout"), 20, 1, 3600),
        "continue_on_error": bool(paso.get("continue_on_error", False)),
    }


def _normalizar_predicado(p: dict) -> dict:
    """Disparadores y condiciones comparten forma: qué mira (`kind`), sobre qué
    (`target`) y con qué ajustes (`params`)."""
    return {
        "kind": str(p.get("kind", "")),
        "target": str(p.get("target", "")),
        "params": p.get("params") if isinstance(p.get("params"), dict) else {},
    }


def _normalizar(regla: dict, posicion: int) -> dict:
    return {
        "id": regla.get("id") or _new_id("auto"),
        "created_at": regla.get("created_at") or _ahora(),
        "name": (regla.get("name") or "").strip(),
        "description": (regla.get("description") or "").strip(),
        "icon": regla.get("icon") or "workflow",
        "folder_id": regla.get("folder_id") or "",
        "enabled": bool(regla.get("enabled", True)),
        "triggers": [_normalizar_predicado(t) for t in regla.get("triggers") or []],
        "match": "any" if regla.get("match") == "any" else "all",
        "conditions": [_normalizar_predicado(c) for c in regla.get("conditions") or []],
        "actions": [_normalizar_accion(a) for a in regla.get("actions") or []],
        "cooldown_seconds": _entero(regla.get("cooldown_seconds"), 60, 0, 86400),
        "max_fires_per_minute": _entero(regla.get("max_fires_per_minute"), 10, 1, 600),
        "disabled_reason": (regla.get("disabled_reason") or "").strip(),
        "order": _entero(regla.get("order"), posicion, 0, 100000),
    }


def _aplicar_defectos(data: dict) -> dict:
    reglas = [_normalizar(r, i) for i, r in enumerate(data.get("rules") or [])]
    reglas.sort(key=lambda r: r["order"])
    # Se reasigna 0..N-1 para que el orden no acumule huecos ni empates al
    # borrar reglas o moverlas muchas veces (mismo criterio que los equipos).
    for posicion, regla in enumerate(reglas):
        regla["order"] = posicion
    carpetas = [
        {"id": c.get("id") or _new_id("carp"),
         "name": (c.get("name") or "").strip(),
         "created_at": c.get("created_at") or _ahora()}
        for c in data.get("folders") or []
    ]
    return {"rules": reglas, "folders": carpetas}


# ── Lectura / escritura ─────────────────────────────────────────────────────
def _read() -> dict:
    if not ARCHIVO.exists():
        return {"rules": [], "folders": []}
    try:
        with open(ARCHIVO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            crudo = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except json.JSONDecodeError as e:
        raise ArchivoCorrupto(f"{ARCHIVO} no se puede leer: {e}") from e
    except OSError as e:
        raise ArchivoCorrupto(f"No se puede abrir {ARCHIVO}: {e}") from e
    # Una versión anterior podría haber guardado la lista pelada, como grupos.
    if isinstance(crudo, list):
        crudo = {"rules": crudo, "folders": []}
    return _aplicar_defectos(crudo)


def _write(data: dict) -> None:
    """Temporal + os.replace: o queda el fichero viejo entero o el nuevo
    entero, nunca uno a medias. El fsync antes del replace es lo que garantiza
    que el contenido está en disco y no solo en la caché del sistema."""
    datos = _aplicar_defectos(data)
    tmp = ARCHIVO.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        json.dump(datos, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, ARCHIVO)
    bus.publicar(bus.ENTIDADES)


def _mutar(mutador):
    """Lee, deja que el mutador cambie el documento y lo vuelve a escribir.
    Devuelve lo que devuelva el mutador."""
    data = _read()
    resultado = mutador(data)
    _write(data)
    return resultado


# ── Reglas ──────────────────────────────────────────────────────────────────
def read_all() -> list[dict]:
    return _read()["rules"]


def enabled_rules() -> list[dict]:
    """Las que el motor debe evaluar: activadas y con algo que hacer. Una regla
    sin acciones no se evalúa aunque esté activada — no tendría efecto y solo
    gastaría vueltas."""
    return [r for r in read_all() if r["enabled"] and r["actions"]]


def get_rule(rule_id: str) -> dict | None:
    return next((r for r in read_all() if r["id"] == rule_id), None)


def add_rule(**campos) -> dict:
    def _op(data):
        regla = _normalizar({**campos, "id": _new_id("auto")}, len(data["rules"]))
        regla["order"] = len(data["rules"])
        data["rules"].append(regla)
        return regla
    return _mutar(_op)


def update_rule(rule_id: str, **campos) -> dict | None:
    def _op(data):
        for i, r in enumerate(data["rules"]):
            if r["id"] == rule_id:
                data["rules"][i] = _normalizar({**r, **campos, "id": rule_id}, i)
                return data["rules"][i]
        return None
    return _mutar(_op)


def delete_rule(rule_id: str) -> None:
    def _op(data):
        data["rules"] = [r for r in data["rules"] if r["id"] != rule_id]
    _mutar(_op)
    borrar_estado(rule_id)


def set_enabled(rule_id: str, enabled: bool, motivo: str = "") -> dict | None:
    """Activa o desactiva. `motivo` solo se guarda al desactivar: es lo que
    permite distinguir "la apagó el usuario" de "la apagó el cortafuegos" o
    "apunta a algo que ya no existe", y enseñarlo en su tarjeta."""
    return update_rule(rule_id, enabled=enabled,
                       disabled_reason="" if enabled else motivo)


def duplicate_rule(rule_id: str) -> dict | None:
    original = get_rule(rule_id)
    if original is None:
        return None
    copia = {k: v for k, v in original.items() if k not in ("id", "created_at", "order")}
    copia["name"] = f"{original['name']} (copia)"
    # La copia nace APAGADA: duplicar es el paso previo a editar, y una copia
    # idéntica ejecutándose a la vez que la original es justo lo que nadie
    # quiere (dos órdenes iguales, o dos contrarias, sobre el mismo aparato).
    copia["enabled"] = False
    return add_rule(**copia)


def move_rule(rule_id: str, direction: int) -> None:
    def _op(data):
        reglas = data["rules"]
        i = next((n for n, r in enumerate(reglas) if r["id"] == rule_id), None)
        if i is None:
            return
        j = i + direction
        if 0 <= j < len(reglas):
            reglas[i], reglas[j] = reglas[j], reglas[i]
            for posicion, regla in enumerate(reglas):
                regla["order"] = posicion
    _mutar(_op)


# ── Carpetas (solo organizativas, no afectan a la ejecución) ────────────────
def list_folders() -> list[dict]:
    return _read()["folders"]


def add_folder(name: str) -> dict:
    def _op(data):
        carpeta = {"id": _new_id("carp"), "name": name.strip(), "created_at": _ahora()}
        data["folders"].append(carpeta)
        return carpeta
    return _mutar(_op)


def delete_folder(folder_id: str) -> None:
    """Borra la carpeta, no sus reglas: se quedan sueltas en "Sin carpeta"."""
    def _op(data):
        data["folders"] = [c for c in data["folders"] if c["id"] != folder_id]
        for r in data["rules"]:
            if r["folder_id"] == folder_id:
                r["folder_id"] = ""
    _mutar(_op)


# ── Estado de ejecución (fichero aparte, lo escribe el motor) ───────────────
DEFECTOS_ESTADO = {
    "last_run": 0.0,        # time.time(), NO monotonic: tiene que cruzar reinicios
    "last_result": "",      # "ok" | "error" | "parcial"
    "last_detail": "",
    "last_error": "",
    "run_count": 0,
    "trigger_stamps": {},   # índice del disparador -> "YYYY-MM-DD HH:MM" ya servido
}


def read_state() -> dict[str, dict]:
    if not ARCHIVO_ESTADO.exists():
        return {}
    try:
        with open(ARCHIVO_ESTADO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            datos = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return datos if isinstance(datos, dict) else {}
    except (json.JSONDecodeError, OSError):
        # Aquí sí se puede empezar de cero sin mentirle a nadie: perder el
        # estado solo significa que la próxima vuelta vuelve a cebar marcas y
        # contadores. No es configuración de nadie.
        return {}


def get_state(rule_id: str) -> dict:
    return {**DEFECTOS_ESTADO, **read_state().get(rule_id, {})}


def _mutar_estado(mutador):
    datos = read_state()
    resultado = mutador(datos)
    tmp = ARCHIVO_ESTADO.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        json.dump(datos, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, ARCHIVO_ESTADO)
    return resultado


def mark_run(rule_id: str, *, resultado: str, detalle: str = "",
             error: str = "", stamps: dict | None = None) -> None:
    def _op(datos):
        actual = {**DEFECTOS_ESTADO, **datos.get(rule_id, {})}
        actual["last_run"] = time.time()
        actual["last_result"] = resultado
        actual["last_detail"] = detalle
        actual["last_error"] = error
        actual["run_count"] = int(actual.get("run_count", 0)) + 1
        if stamps:
            actual["trigger_stamps"] = {**actual.get("trigger_stamps", {}), **stamps}
        datos[rule_id] = actual
    _mutar_estado(_op)


def save_trigger_stamps(rule_id: str, stamps: dict) -> None:
    """Apunta las marcas horarias YA SERVIDAS aunque la regla no llegara a
    ejecutarse (por condiciones o enfriamiento). Si no se guardaran, el minuto
    seguiría contando como pendiente y la regla lo reintentaría en cada una de
    las 60 vueltas que caben dentro."""
    def _op(datos):
        actual = {**DEFECTOS_ESTADO, **datos.get(rule_id, {})}
        actual["trigger_stamps"] = {**actual.get("trigger_stamps", {}), **stamps}
        datos[rule_id] = actual
    _mutar_estado(_op)


def borrar_estado(rule_id: str) -> None:
    def _op(datos):
        datos.pop(rule_id, None)
    _mutar_estado(_op)
