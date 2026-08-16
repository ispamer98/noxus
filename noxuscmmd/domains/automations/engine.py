"""
El motor: mira la casa una vez por segundo y ejecuta las reglas que tocan.

Arranca con el PROCESO (tarea de ciclo de vida registrada en noxuscmmd.py), no
desde el on_load de ningún State. Es la diferencia entre que "enciende las
luces a las 22:00 mientras no estoy" funcione o no funcione: colgado de una
sesión, el motor no existiría hasta que alguien abriera el panel en un
navegador.

Tres ideas sostienen todo lo demás:

1. FLANCOS, NO NIVELES. Se dispara en la transición ("el sensor se ACABA de
   abrir"), no mientras la condición siga siendo cierta. Cada señal se ceba la
   primera vez que se ve, así que al arrancar no se dispara nada — si no,
   reiniciar el panel con una puerta abierta lanzaría media casa de golpe.

2. ECO. Cuando una acción cambia algo, esa señal queda sorda unos segundos.
   Es lo que impide que "la regla A enciende la luz" dispare "la regla B, que
   la apaga", que vuelve a disparar a A. Hace innecesario contar profundidad de
   encadenado: la cadena se corta en el primer eslabón.

3. NADA BLOQUEA EL TICK. Cada regla que dispara se va a su propia tarea, con
   tiempo máximo por acción. Un SSH a un equipo apagado no puede parar el
   reloj ni las demás reglas.
"""
import asyncio
import time
from datetime import datetime

from ..nodes import operations as ops
from ..nodes import store as nodes_store
from ..notifications import push
from ..security import audit, groups_store, logs, shared_state
from . import actions, store

_TICK = 1.0

# Cuánto tiempo queda sorda una señal después de que la haya cambiado una
# acción nuestra. Tiene que dar de sobra para el viaje de ida y vuelta por MQTT
# (mandas ON, el relé conmuta, el aparato publica su estado, sensor_events lo
# escribe en disco) y quedarse corto frente a un cambio de verdad posterior.
_ECO_SEGUNDOS = 3.0

# Las temperaturas cuestan una conexión SSH, así que ni se piden cada segundo
# ni se piden de equipos que no mire ninguna regla.
_PERIODO_NUMERICO = 30.0

_STARTED = False

_prev: dict[str, object] = {}          # señal -> último valor visto
_eco: dict[str, float] = {}            # señal -> monotonic() hasta el que está sorda
_numeros: dict[str, tuple[float, float]] = {}   # señal -> (valor, monotonic)
_vencimientos: dict[str, float] = {}   # "regla:idx" -> monotonic del próximo "cada N"
_corriendo: dict[str, asyncio.Task] = {}
_disparos: dict[str, list[float]] = {}  # regla -> monotonic de los últimos disparos
_reglas_cache: tuple[float, list[dict]] = (-1.0, [])


def note_write(señal: str) -> None:
    """Lo llaman las acciones al cambiar algo. Ver la idea 2 de arriba."""
    _eco[señal] = time.monotonic() + _ECO_SEGUNDOS


# ── Foto del mundo ──────────────────────────────────────────────────────────
class Snapshot:
    """Todo lo que las reglas necesitan mirar, leído UNA vez por vuelta: así
    dos reglas evaluadas en el mismo tick no pueden ver mundos distintos."""

    __slots__ = ("at", "local", "estados", "hosts", "grupos", "armado", "numeros")

    def __init__(self, estados, hosts, grupos, armado, numeros):
        self.at = time.monotonic()
        # Hora LOCAL e ingenua a propósito: el usuario dice "a las 22:30" y se
        # refiere al reloj de su pared. En UTC, una regla de las 22:30 se
        # correría una hora dos veces al año.
        self.local = datetime.now()
        self.estados = estados
        self.hosts = hosts
        self.grupos = grupos
        self.armado = armado
        self.numeros = numeros


def _leer_mundo() -> tuple[dict, dict, dict, bool]:
    return (
        nodes_store.get_all_sensor_states(),
        nodes_store.get_all_host_online(),
        {g["id"]: g for g in groups_store.read_all()},
        shared_state.get_sistema_armado(),
    )


def _señales(snap: Snapshot) -> dict[str, object]:
    """La foto aplanada a "nombre de señal -> valor", que es sobre lo que se
    detectan los flancos."""
    salida: dict[str, object] = {f"state:{k}": v for k, v in snap.estados.items()}
    salida.update({f"host:{k}": v for k, v in snap.hosts.items()})
    salida.update({f"group:{k}": g["armed"] for k, g in snap.grupos.items()})
    salida["system"] = snap.armado
    salida.update(snap.numeros)
    return salida


def _cambios(señales: dict[str, object], ahora: float) -> dict[str, tuple]:
    """Qué ha cambiado desde la vuelta anterior. Devuelve señal -> (antes,
    ahora). Se calcula UNA vez por tick y lo consultan todas las reglas: si
    cada regla llamara a su propio detector, la primera se llevaría la
    transición y las demás no verían nada."""
    salida: dict[str, tuple] = {}
    for clave, valor in señales.items():
        if clave not in _prev:
            # Primera vez que se ve: se toma como punto de partida y no se
            # dispara. Mismo criterio que el vigilante de alarma y que el
            # registro de conexiones de los equipos.
            _prev[clave] = valor
            continue
        anterior = _prev[clave]
        if anterior == valor:
            continue
        _prev[clave] = valor
        if _eco.get(clave, 0.0) > ahora:
            # Lo hemos causado nosotros hace un momento: no es noticia.
            continue
        salida[clave] = (anterior, valor)
    return salida


async def _muestrear_numeros(reglas: list[dict]) -> dict[str, float]:
    """Temperaturas de CPU de los equipos que MIRE alguna regla activa, y solo
    cada _PERIODO_NUMERICO. Devuelve las que se tengan; una que no se pueda
    leer simplemente no aparece, y una condición que no se puede evaluar no se
    da por cumplida."""
    querido = set()
    for r in reglas:
        for p in list(r["triggers"]) + list(r["conditions"]):
            if p["kind"] in ("host.temp_above", "host.temp_below", "host.temp"):
                _, host_id = actions.partir(p["target"])
                if host_id:
                    querido.add(host_id)

    ahora = time.monotonic()
    for host_id in querido:
        clave = f"temp:{host_id}"
        valor, cuando = _numeros.get(clave, (None, -_PERIODO_NUMERICO))
        if ahora - cuando < _PERIODO_NUMERICO:
            continue
        try:
            leido = await asyncio.wait_for(ops.read_host_temperature(host_id), timeout=12)
        except Exception:
            leido = None
        # Una lectura fallida NO borra la última buena: un equipo que tarda en
        # contestar una vez no debe hacer "desaparecer" el dato y con él la
        # condición que lo mira.
        _numeros[clave] = (leido if leido is not None else valor, ahora)
    return {k: v for k, (v, _) in _numeros.items() if v is not None}


# ── Disparadores ────────────────────────────────────────────────────────────
_FLANCOS = {
    # kind -> (prefijo de la señal, valor que tiene que tomar)
    "sensor.opened": ("state", True), "sensor.closed": ("state", False),
    "light.on": ("state", True), "light.off": ("state", False),
    "door.opened": ("state", True), "door.closed": ("state", False),
    "host.online": ("host", True), "host.offline": ("host", False),
    "group.armed": ("group", True), "group.disarmed": ("group", False),
}


def _señal_de(kind: str, target: str) -> str:
    prefijo = _FLANCOS[kind][0]
    _, ident = actions.partir(target)
    return f"{prefijo}:{ident}"


def _dispara_hora(trigger: dict, servidas: dict, indice: int,
                  ahora: datetime, arrancando: bool) -> tuple[bool, str]:
    """A una hora concreta. Devuelve (dispara, marca que hay que apuntar).

    La marca es "AAAA-MM-DD HH:MM" y se compara como TEXTO, que en ese formato
    ordena igual que en el tiempo. Con `<=` en vez de `!=`, un salto del reloj
    hacia atrás (una corrección de NTP, un cambio a mano) no puede hacer que se
    repita un minuto ya servido.

    Los cambios de hora salen gratis: en marzo las 02:30 no existen, así que
    (hora, minuto) nunca coincide y ese día se salta; en octubre ocurren dos
    veces, pero las dos generan la misma marca y solo dispara la primera."""
    p = trigger["params"]
    dias = p.get("days") or [0, 1, 2, 3, 4, 5, 6]
    try:
        hh, mm = (int(x) for x in str(p.get("hhmm", "")).split(":"))
    except (TypeError, ValueError):
        return False, ""
    servida = servidas.get(str(indice), "")

    if ahora.weekday() in dias and (ahora.hour, ahora.minute) == (hh, mm):
        marca = ahora.strftime("%Y-%m-%d %H:%M")
        return (marca > servida), marca

    # Recuperación de una hora perdida con el panel apagado. Solo en la primera
    # vuelta tras arrancar y solo si se ha pedido: por defecto NO se recupera,
    # porque que "apagar las luces a las 22:00" salte a las 03:00 al encender
    # el panel es peor que no saltar.
    margen = float(p.get("catch_up_minutes") or 0)
    if not arrancando or margen <= 0:
        return False, ""
    prevista = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if prevista > ahora:
        return False, ""
    if prevista.weekday() not in dias:
        return False, ""
    if (ahora - prevista).total_seconds() > margen * 60:
        return False, ""
    marca = prevista.strftime("%Y-%m-%d %H:%M")
    return (marca > servida), marca


def _dispara_intervalo(regla_id: str, indice: int, trigger: dict, ahora: float) -> bool:
    """Cada N minutos, sobre reloj MONÓTONO: inmune a NTP y a los cambios de
    hora. A cambio, el ciclo empieza de cero al arrancar el proceso — guardar
    un vencimiento monótono entre reinicios no significaría nada, y guardarlo
    en hora de pared traería de vuelta el problema del cambio de hora."""
    try:
        minutos = max(1.0, float(trigger["params"].get("minutes", 30)))
    except (TypeError, ValueError):
        return False
    clave = f"{regla_id}:{indice}"
    vence = _vencimientos.get(clave)
    if vence is None:
        _vencimientos[clave] = ahora + minutos * 60
        return False
    if ahora < vence:
        return False
    _vencimientos[clave] = ahora + minutos * 60
    return True


def _disparado(regla: dict, snap: Snapshot, cambios: dict,
               servidas: dict, arrancando: bool) -> tuple[bool, dict]:
    """¿Toca ejecutar esta regla? Basta con que se cumpla UNO de sus
    disparadores. Devuelve también las marcas horarias que hay que apuntar
    aunque luego no llegue a ejecutarse por condiciones o enfriamiento."""
    dispara = False
    marcas: dict[str, str] = {}
    for i, t in enumerate(regla["triggers"]):
        kind = t["kind"]
        if kind in _FLANCOS:
            _, esperado = _FLANCOS[kind]
            cambio = cambios.get(_señal_de(kind, t["target"]))
            if cambio and cambio[1] == esperado:
                dispara = True
        elif kind == "system.armed" or kind == "system.disarmed":
            cambio = cambios.get("system")
            if cambio and cambio[1] == (kind == "system.armed"):
                dispara = True
        elif kind in ("host.temp_above", "host.temp_below"):
            _, host_id = actions.partir(t["target"])
            cambio = cambios.get(f"temp:{host_id}")
            if cambio:
                antes, ahora_v = cambio
                umbral = float(t["params"].get("value", 0))
                # Por CRUCE, no por nivel: una vez disparado, el valor ya está
                # al otro lado del umbral y no puede volver a disparar hasta
                # que cruce de vuelta. Es histéresis gratis.
                if kind == "host.temp_above" and antes <= umbral < ahora_v:
                    dispara = True
                if kind == "host.temp_below" and antes >= umbral > ahora_v:
                    dispara = True
        elif kind == "time.at":
            salta, marca = _dispara_hora(t, servidas, i, snap.local, arrancando)
            if marca:
                marcas[str(i)] = marca
            if salta:
                dispara = True
        elif kind == "time.every":
            if _dispara_intervalo(regla["id"], i, t, snap.at):
                dispara = True
    return dispara, marcas


# ── Condiciones ─────────────────────────────────────────────────────────────
def _si(params: dict, clave: str = "value", por_defecto: bool = True) -> bool:
    valor = params.get(clave, por_defecto)
    if isinstance(valor, bool):
        return valor
    return str(valor).lower() in ("true", "1", "on", "si", "sí")


def _entre(ahora_hm: str, desde: str, hasta: str) -> bool:
    if desde <= hasta:
        return desde <= ahora_hm <= hasta
    # Cruza la medianoche: "de 22:00 a 06:00" son dos trozos, no un rango.
    return ahora_hm >= desde or ahora_hm <= hasta


def _condicion(c: dict, snap: Snapshot, estado_regla: dict) -> bool:
    kind, target, p = c["kind"], c["target"], c["params"]
    _, ident = actions.partir(target)

    if kind in ("sensor.is", "light.is", "door.is"):
        return snap.estados.get(ident, False) == _si(p)
    if kind == "host.is_online":
        return snap.hosts.get(ident, False) == _si(p)
    if kind == "group.is_armed":
        grupo = snap.grupos.get(ident)
        return bool(grupo and grupo["armed"]) == _si(p)
    if kind == "system.is_armed":
        return snap.armado == _si(p)
    if kind == "host.temp":
        valor = snap.numeros.get(f"temp:{ident}")
        if valor is None:
            # No se ha podido leer. Una condición que no se puede evaluar NO se
            # da por cumplida: dar "sí" por defecto es como acaba un ventilador
            # encendido toda la noche.
            return False
        umbral = float(p.get("value", 0))
        op = p.get("op", ">")
        return {">": valor > umbral, ">=": valor >= umbral,
                "<": valor < umbral, "<=": valor <= umbral}.get(op, False)
    if kind == "time.between":
        return _entre(snap.local.strftime("%H:%M"),
                      str(p.get("from", "00:00")), str(p.get("to", "23:59")))
    if kind == "day_of_week":
        return snap.local.weekday() in (p.get("days") or [])
    if kind == "rule.idle_for":
        minutos = float(p.get("minutes", 30))
        ultima = float(estado_regla.get("last_run", 0) or 0)
        if not ultima:
            return True
        return (time.time() - ultima) >= minutos * 60
    return False


def _condiciones_ok(regla: dict, snap: Snapshot, estado_regla: dict) -> bool:
    condiciones = regla["conditions"]
    if not condiciones:
        return True
    resultados = [_condicion(c, snap, estado_regla) for c in condiciones]
    return all(resultados) if regla["match"] == "all" else any(resultados)


# ── Ejecución ───────────────────────────────────────────────────────────────
async def _ejecutar_pasos(regla: dict) -> tuple[int, list[str]]:
    """Los pasos, EN ORDEN. Devuelve (cuántos salieron, errores)."""
    hechos, errores = 0, []
    for paso in regla["actions"]:
        repeticiones = max(1, int(paso.get("repeat", 1)))
        pausa = float(paso.get("repeat_pause", 0.4))
        for n in range(repeticiones):
            if n:
                await asyncio.sleep(pausa)
            try:
                # El tiempo máximo NO es opcional: ir_bus.send_button no tiene
                # ninguno, y un SSH contra una conexión a medio abrir puede
                # quedarse esperando mucho más de lo que dice su timeout de
                # conexión. Sin esto, un aparato inalcanzable deja la regla
                # colgada para siempre.
                await asyncio.wait_for(actions.dispatch(paso),
                                       timeout=float(paso.get("timeout", 20)))
                hechos += 1
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                errores.append(f"{paso.get('type')}: se agotó el tiempo")
                if not paso.get("continue_on_error"):
                    return hechos, errores
            except Exception as e:
                errores.append(f"{paso.get('type')}: {e}")
                if not paso.get("continue_on_error"):
                    return hechos, errores
    return hechos, errores


def _cortafuegos(regla: dict, ahora: float) -> bool:
    """True si la regla se ha desmadrado. Desactivarla y avisar, en vez de
    estrangularla en silencio: una regla que se autolimita sin decir nada es
    indistinguible de una rota."""
    recientes = [t for t in _disparos.get(regla["id"], []) if ahora - t < 60]
    recientes.append(ahora)
    _disparos[regla["id"]] = recientes
    return len(recientes) > regla["max_fires_per_minute"]


async def _disparar(regla: dict, marcas: dict) -> str:
    ahora = time.monotonic()
    if _cortafuegos(regla, ahora):
        motivo = (f"se ha disparado más de {regla['max_fires_per_minute']} veces "
                  f"en un minuto — revisa si choca con otra automatización")
        await asyncio.to_thread(store.set_enabled, regla["id"], False, motivo)
        audit.registrar_sistema(logs.AUTOMATIZACIONES, "AUTOMATIZACION_DESACTIVADA",
                                f"{regla['name']}: {motivo}", entidad=regla["id"])
        await asyncio.to_thread(push.enviar_notificacion,
                                "⚠️ Automatización desactivada",
                                f"«{regla['name']}» {motivo}")
        return motivo

    hechos, errores = await _ejecutar_pasos(regla)
    if not errores:
        resultado, accion = "ok", "AUTOMATIZACION_EJECUTADA"
    elif hechos:
        resultado, accion = "parcial", "AUTOMATIZACION_PARCIAL"
    else:
        resultado, accion = "error", "AUTOMATIZACION_FALLIDA"
    detalle = f"{hechos} de {len(regla['actions'])} acciones"

    await asyncio.to_thread(store.mark_run, regla["id"], resultado=resultado,
                            detalle=detalle, error="; ".join(errores)[:300],
                            stamps=marcas)
    # UNA línea por ejecución, no por acción: logs.registrar se come una
    # entrada idéntica a la anterior (pensado para sensores que rebotan), así
    # que "pulsa dos veces" perdería la segunda y el registro mentiría. Y con
    # 1500 entradas de tope, unas pocas reglas habladoras se llevarían por
    # delante meses de histórico de alarma.
    audit.registrar_sistema(
        logs.AUTOMATIZACIONES, accion,
        f"{regla['name']} · {detalle}" + (f" · {errores[0]}" if errores else ""),
        entidad=regla["id"],
    )
    return detalle


async def ejecutar_ahora(rule_id: str) -> str:
    """Ejecuta una regla a mano, saltándose disparadores y condiciones — es lo
    que hace el botón "Ejecutar ahora" y la acción "ejecutar otra
    automatización". El enfriamiento tampoco aplica: lo ha pedido alguien."""
    regla = await asyncio.to_thread(store.get_rule, rule_id)
    if regla is None:
        raise actions.ActionError("esa automatización ya no existe")
    return await _disparar(regla, {})


# ── El bucle ────────────────────────────────────────────────────────────────
def _reglas_activas() -> list[dict]:
    """Relee el fichero solo cuando cambia. El motor da una vuelta por segundo
    y las reglas se tocan cada muchos días: abrir y parsear el JSON 86.400
    veces al día para leer lo mismo no tiene sentido."""
    global _reglas_cache
    try:
        marca = store.ARCHIVO.stat().st_mtime if store.ARCHIVO.exists() else 0.0
    except OSError:
        marca = 0.0
    if marca != _reglas_cache[0]:
        _reglas_cache = (marca, store.enabled_rules())
    return _reglas_cache[1]


def _terminada(rule_id: str, tarea: asyncio.Task) -> None:
    _corriendo.pop(rule_id, None)
    if tarea.cancelled():
        return
    # Hay que recoger la excepción aunque no se use, o Python avisa de una
    # excepción de tarea que nadie miró.
    error = tarea.exception()
    if error:
        print(f"⚠️ La automatización {rule_id} terminó con error: {error}")


async def _vuelta(arrancando: bool) -> None:
    reglas = await asyncio.to_thread(_reglas_activas)
    if not reglas:
        # Sin ninguna regla activa no hay nada que mirar. Merece el atajo: esto
        # da una vuelta por segundo para siempre, y leer cuatro ficheros 86.400
        # veces al día para no hacer nada con ellos no tiene sentido. Al
        # aparecer la primera regla, la vuelta siguiente ceba las señales.
        return
    estados, hosts, grupos, armado = await asyncio.to_thread(_leer_mundo)
    numeros = await _muestrear_numeros(reglas)
    snap = Snapshot(estados, hosts, grupos, armado, numeros)
    cambios = _cambios(_señales(snap), snap.at)
    estados_reglas = await asyncio.to_thread(store.read_state)

    for regla in reglas:
        try:
            if regla["id"] in _corriendo:
                # Ya se está ejecutando. Sin esto, una regla que tarda 30 s con
                # el disparador todavía cierto apila una tarea nueva por
                # segundo.
                continue
            estado_regla = {**store.DEFECTOS_ESTADO, **estados_reglas.get(regla["id"], {})}
            dispara, marcas = _disparado(regla, snap, cambios,
                                         estado_regla.get("trigger_stamps", {}), arrancando)
            if marcas:
                # Se apuntan aunque no llegue a ejecutarse: si no, el minuto
                # seguiría contando como pendiente y se reintentaría en cada
                # una de las 60 vueltas que caben dentro.
                await asyncio.to_thread(store.save_trigger_stamps, regla["id"], marcas)
            if not dispara:
                continue
            if not _condiciones_ok(regla, snap, estado_regla):
                continue
            espera = max(0.0, time.time() - float(estado_regla.get("last_run", 0) or 0))
            if regla["cooldown_seconds"] and espera < regla["cooldown_seconds"]:
                continue
            tarea = asyncio.create_task(_disparar(regla, marcas), name=f"nx_regla|{regla['id']}")
            _corriendo[regla["id"]] = tarea
            tarea.add_done_callback(lambda t, rid=regla["id"]: _terminada(rid, t))
        except Exception as e:
            # Una regla mal formada no puede impedir que se evalúen las demás.
            print(f"⚠️ Automatización {regla.get('id')} descartada en esta vuelta: {e}")


# Se enganchan al importar, no al arrancar el bucle: "Ejecutar ahora" desde la
# web puede correr una regla antes (o sin) que el bucle esté en marcha, y sin
# esto sus cambios no quedarían silenciados por el eco.
actions.set_hooks(echo=note_write, run_rule=ejecutar_ahora)


async def run_forever() -> None:
    """Tarea de ciclo de vida. Estructuralmente imposible de matar: Reflex no
    reinicia una tarea de ciclo de vida que revienta, así que cualquier error
    se cuenta y se vuelve a empezar.

    La cancelación es la excepción: se sale sin más. Reflex remata sus tareas
    de ciclo de vida con `add_done_callback(lambda t: t.result())`
    (app_mixins/lifespan.py), así que relanzar el CancelledError deja un
    traceback en el journal en CADA reinicio del servicio — un apagado normal
    contado como si fuera un fallo."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    arrancando = True
    try:
        while True:
            try:
                await _vuelta(arrancando)
                arrancando = False
            except asyncio.CancelledError:
                raise
            except store.ArchivoCorrupto as e:
                # No se ejecuta NADA hasta que se arregle. Seguir como si no
                # hubiera reglas sería lo peor de los dos mundos: el panel diría
                # que todo va bien y la casa no haría nada.
                print(f"⛔ Motor de automatizaciones detenido: {e}")
                await asyncio.sleep(30)
            except Exception as e:
                print(f"⚠️ Error en la vuelta del motor de automatizaciones: {e}")
            await asyncio.sleep(_TICK)
    except asyncio.CancelledError:
        _STARTED = False
        return
