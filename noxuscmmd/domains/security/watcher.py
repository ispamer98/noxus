"""
El vigilante de la alarma: si un sensor de un grupo ARMADO se abre, avisa.

Vivía dentro de GroupsState como manejador de fondo, arrancado desde su
on_load. Eso significaba que **el único emisor de alertas del sistema no
existía hasta que alguien abría el panel en un navegador**: tras un reinicio
del proceso la casa podía quedarse armada sin nadie vigilando. Sacarlo aquí lo
convierte en una tarea del ciclo de vida del proceso, que arranca con la
aplicación y no depende de que haya una pestaña abierta.

Sacarlo no ha costado nada más que dejar de leer dos Vars: `sensor_state` y
`sensors` de NodesState son copias en memoria de nodos_dinamicos.json que su
sync_loop refresca cada 0,5 s, así que leer el fichero directamente da lo mismo
—de hecho, un poco más fresco— sin necesitar sesión.
"""
import asyncio

from ..devices import registry
from ..nodes import store as nodes_store
from ..notifications.push import enviar_notificacion
from . import groups_store, logs

_STARTED = False


def _aislados() -> set[str]:
    """Sensores que la alarma trata como si no existieran. registry.isolated_ids()
    ya cubre los de fábrica leyendo del disco; aquí se le suman los dados de
    alta desde la web, que guardan la marca en su propia ficha."""
    dinamicos = {s["id"] for s in nodes_store.read_all()["sensors"] if s.get("isolated")}
    return registry.isolated_ids() | dinamicos


async def _vuelta(ultimo_abierto: dict[tuple[str, str], bool]) -> None:
    todos = await asyncio.to_thread(groups_store.read_all)
    grupos_armados = [g for g in todos if g["armed"]]
    if not grupos_armados:
        return
    sensores = await asyncio.to_thread(nodes_store.get_all_sensor_states)
    aislados = await asyncio.to_thread(_aislados)

    for g in grupos_armados:
        for m in g["members"]:
            if m["id"] in aislados:
                continue
            key = (g["id"], m["id"])
            abierto = sensores.get(m["id"], False)
            previo = ultimo_abierto.get(key)
            if previo is None:
                # Primera vuelta con este sensor: se toma como punto de
                # partida. Si no, al arrancar se avisaría de golpe de todo lo
                # que estuviera abierto como si acabase de abrirse.
                ultimo_abierto[key] = abierto
                continue
            if previo == abierto:
                continue
            ultimo_abierto[key] = abierto
            if abierto:
                titulo = f"🚨 ALERTA: {g['name']}"
                cuerpo = f"{m['name']} se ha abierto con el grupo '{g['name']}' armado."
                await asyncio.to_thread(enviar_notificacion, titulo, cuerpo, "todos")
                logs.registrar_log("GRUPO_ALERTA", "sistema", f"{g['name']}: {m['name']} abierto")
            else:
                logs.registrar_log("GRUPO_CERRADO", "sistema", f"{g['name']}: {m['name']} cerrado")


async def run_forever() -> None:
    """Tarea de ciclo de vida. Un solo vigilante por proceso, y estructuralmente
    imposible de matar: cualquier error se cuenta y se sigue vigilando. Lo que
    NO puede pasar es que este bucle se caiga en silencio y la casa se quede
    armada sin nadie mirando.

    La cancelación (apagado del proceso) sale sin ruido: Reflex remata sus
    tareas de ciclo de vida llamando a `.result()`, así que relanzar el
    CancelledError dejaría un traceback en el journal en cada reinicio, como si
    un apagado normal fuera un fallo."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    ultimo_abierto: dict[tuple[str, str], bool] = {}
    try:
        while True:
            try:
                await _vuelta(ultimo_abierto)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"⚠️ Error en el vigilante de alarma: {e}")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        _STARTED = False
        return
