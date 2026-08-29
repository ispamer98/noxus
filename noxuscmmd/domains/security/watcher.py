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
import time

from ..cameras import fotogramas
from ..devices import registry
from ..nodes import store as nodes_store
from ..notifications import alertas, categorias
from ..notifications.push import enviar_notificacion
from . import arming, groups_store, logs, logs_store, retardos

_STARTED = False

# Cuándo dio la última vuelta. En memoria y no en disco a propósito: quien lo
# consulta es la pantalla de salud, que corre en ESTE mismo proceso, y escribir
# un fichero una vez por segundo para eso sería absurdo. Si el proceso se
# reinicia vuelve a 0, que es exactamente la verdad — no ha dado ninguna vuelta
# todavía.
LATIDO: float = 0.0

# Las capturas de cámara en vuelo. Hay que guardarlas: el bucle de eventos solo
# tiene una referencia DÉBIL a las tareas, así que una tarea que nadie sujete
# puede irse con el recolector de basura a mitad y la foto no aparecería nunca,
# de forma intermitente y sin dejar rastro.
_capturas: set[asyncio.Task] = set()


def _capturar_fotograma(evento_id: int, sensor_id: str) -> None:
    """Pide el fotograma del elemento y lo cuelga del evento, SIN ESPERARLO.

    Esto es lo importante de toda la pieza: se lanza y se sigue. Pedirle una
    imagen a una cámara tarda entre uno y varios segundos, y una de las de esta
    casa se queda colgada más de treinta (ver cameras/fotogramas.py). Esperarla
    aquí pararía la ronda del vigilante, que es la que cuenta los retardos de
    entrada y remata los armados en espera: la casa dejaría de contar el tiempo
    para desarmar mientras espera una foto. La alarma primero, la foto cuando
    llegue.

    Sin id no hay a qué colgarla: `registrar_log` devuelve 0 si descartó el
    evento por repetido, y en ese caso el fotograma que valdría es el de la
    alerta que YA está guardada.
    """
    if not evento_id:
        return
    tarea = asyncio.create_task(_capturar(evento_id, sensor_id))
    _capturas.add(tarea)
    tarea.add_done_callback(_capturas.discard)


async def _capturar(evento_id: int, sensor_id: str) -> None:
    """Nunca levanta: quedarse sin foto no puede tumbar al vigilante."""
    try:
        src = await asyncio.to_thread(nodes_store.src_de_sensor, sensor_id)
        if not src:
            return  # ese elemento no tiene cámara asignada
        nombre = await fotogramas.capturar_para(evento_id, src)
        if nombre:
            await asyncio.to_thread(logs_store.adjuntar_foto, evento_id, nombre)
            print(f"📸 Fotograma {nombre} guardado en el evento {evento_id}")
    except Exception as e:
        print(f"⚠️ Fotograma del evento {evento_id}: {e}")


def _aislados() -> set[str]:
    """Sensores que la alarma trata como si no existieran. registry.isolated_ids()
    ya cubre los de fábrica leyendo del disco; aquí se le suman los dados de
    alta desde la web, que guardan la marca en su propia ficha."""
    dinamicos = {s["id"] for s in nodes_store.read_all()["sensors"] if s.get("isolated")}
    return registry.isolated_ids() | dinamicos


async def _alertar(g: dict, nombre_sensor: str, sensor_id: str,
                   con_retardo: bool = False) -> None:
    titulo = f"🚨 ALERTA: {g['name']}"
    cuerpo = f"{nombre_sensor} se ha abierto con el grupo '{g['name']}' armado."
    if con_retardo:
        cuerpo += " Se agotó el tiempo para desarmar."
    # Un tag por sensor y grupo: un contacto que rebota (una puerta que se mueve
    # con el viento) refresca su propio aviso en vez de enterrar la pantalla
    # bajo veinte iguales — y una alerta de OTRO sensor sigue llegando aparte,
    # que es justo lo que no se puede perder. Nunca silencioso: esto es la
    # alarma.
    clave = f"alerta:{g['id']}:{sensor_id}"
    if await asyncio.to_thread(alertas.silenciado, clave):
        # Alguien pidió que esto se callara un rato. Se apunta igual, Y CON SU
        # FOTO: silenciar es no querer el ruido, no querer que no conste. Si algo
        # se abrió mientras la alarma estaba callada, la imagen es justo lo que
        # se va a querer mirar después.
        evento = logs.registrar_log(
            "GRUPO_ALERTA", "sistema",
            f"{g['name']}: {nombre_sensor} abierto (silenciado)")
        _capturar_fotograma(evento, sensor_id)
        return
    await asyncio.to_thread(
        enviar_notificacion, titulo, cuerpo, "todos", clave,
        False, alertas.ACCIONES_ALARMA, categoria=categorias.ALARMA,
    )
    # Queda pendiente de que alguien diga «visto». Si nadie lo dice, se repite.
    await asyncio.to_thread(alertas.crear, clave, titulo, cuerpo)
    evento = logs.registrar_log("GRUPO_ALERTA", "sistema",
                                f"{g['name']}: {nombre_sensor} abierto")
    # El aviso ya ha salido: la foto se pide después y por su cuenta, para que
    # nadie espere a la cámara para enterarse de que ha saltado la alarma.
    _capturar_fotograma(evento, sensor_id)


async def _repetir_sin_confirmar() -> None:
    """Repite a todos los dispositivos las alertas que nadie ha confirmado.

    Es lo que convierte un aviso en una alarma: si el primero llegó mientras el
    móvil estaba boca abajo, el segundo llega un minuto después, y el tercero
    otro minuto más tarde. A la tercera se deja — a esas alturas ya está claro
    que nadie está mirando, y seguir para siempre es castigo, no aviso."""
    for clave, ficha in await asyncio.to_thread(alertas.a_repetir):
        vuelta = ficha.get("repeticiones", 0) + 1
        await asyncio.to_thread(
            enviar_notificacion,
            f"🔁 SIN CONFIRMAR ({vuelta}) · {ficha['titulo']}",
            ficha["cuerpo"] + " Nadie lo ha confirmado todavía.",
            "todos", clave, False, alertas.ACCIONES_ALARMA,
            categoria=categorias.ALARMA,
        )
        await asyncio.to_thread(alertas.marcar_repetida, clave)
        logs.registrar(logs.ALARMA, "ALERTA_REPETIDA", "sistema",
                       f"{ficha['titulo']} — nadie la confirmó en "
                       f"{int(alertas.ESPERA)} s (aviso {vuelta})")


async def _limpiar_caducadas() -> None:
    """Tira las pendientes que llevan medio día sin que nadie diga «visto».

    Una alerta pendiente no caduca sola: deja de repetirse a los tres avisos,
    pero se queda en alertas.json, y desde que hay barra de alertas en el panel
    eso significa que se queda pintada en la pantalla para siempre. La escoba
    tiene que pasar desde aquí porque este es el único bucle que corre sin que
    nadie tenga el panel abierto.

    Quien decide si toca es alertas.limpiar_si_toca, mirando la marca que guarda
    en disco: en la inmensa mayoría de las vueltas esto es una lectura y vuelta
    al bucle."""
    cuantas = await asyncio.to_thread(alertas.limpiar_si_toca)
    if cuantas:
        logs.registrar(logs.ALARMA, "ALERTA_CADUCADA", "sistema",
                       f"{cuantas} alerta(s) descartadas: nadie las confirmó en "
                       f"{int(alertas.CADUCIDAD)} h")


async def _armados_en_espera(todos: list[dict], sensores: dict,
                             aislados: set[str]) -> None:
    """Termina los armados que quedaron a medias: los de cuenta atrás de salida
    cuando se agota, y los de «armar cuando cierren» cuando ya no queda nada
    abierto. Lo hace este bucle y no un temporizador para que sobrevivan a un
    reinicio del panel — ver la cabecera de retardos.py."""
    esperando = await asyncio.to_thread(retardos.pendientes)
    if not esperando:
        return
    ahora = time.time()
    por_id = {g["id"]: g for g in todos}

    for group_id, ficha in list(esperando.items()):
        g = por_id.get(group_id)
        if g is None:
            await asyncio.to_thread(retardos.cancelar, group_id)
            continue
        if g["armed"]:
            # Alguien lo armó por otro lado mientras esperaba.
            await asyncio.to_thread(retardos.cancelar, group_id)
            continue

        excluidos = set(ficha.get("bypass", [])) | aislados
        if ficha.get("modo") == retardos.AL_CERRAR:
            sigue_abierto = [
                m for m in g["members"]
                if m["id"] not in excluidos and sensores.get(m["id"], False)
            ]
            if sigue_abierto:
                continue
            motivo = "todo cerrado"
        else:
            if ficha.get("arma_en", 0) > ahora:
                continue
            motivo = "fin de la cuenta atrás de salida"

        await asyncio.to_thread(retardos.cancelar, group_id)
        if ficha.get("bypass"):
            await asyncio.to_thread(retardos.poner_bypass, group_id,
                                    ficha["bypass"])
        try:
            await arming.set_group_armed(group_id, True,
                                         ficha.get("por") or "sistema")
            logs.registrar(logs.ALARMA, "ARMADO_EN_ESPERA",
                           ficha.get("por") or "sistema", motivo,
                           grupo=g["name"])
        except arming.ArmingError:
            pass


async def _vuelta(ultimo_abierto: dict[tuple[str, str], bool]) -> None:
    todos = await asyncio.to_thread(groups_store.read_all)
    sensores = await asyncio.to_thread(nodes_store.get_all_sensor_states)
    aislados = await asyncio.to_thread(_aislados)

    await _armados_en_espera(todos, sensores, aislados)
    # Las repeticiones van fuera del bloque de grupos armados: una alerta sin
    # confirmar tiene que seguir insistiendo aunque entretanto se desarme. Y la
    # escoba, por lo mismo: una pendiente caducada hay que quitarla de la barra
    # esté la casa armada o no.
    await _repetir_sin_confirmar()
    await _limpiar_caducadas()

    grupos_armados = [g for g in todos if g["armed"]]
    if not grupos_armados:
        return
    conf = await asyncio.to_thread(retardos.leer)

    # Retardos de entrada agotados: quien abrió no ha desarmado a tiempo.
    for group_id, sensor_id in retardos.entradas_vencidas():
        g = next((x for x in grupos_armados if x["id"] == group_id), None)
        await asyncio.to_thread(retardos.cerrar_entrada, group_id, sensor_id)
        if g is None:
            continue
        nombre = next((m["name"] for m in g["members"] if m["id"] == sensor_id),
                      sensor_id)
        await _alertar(g, nombre, sensor_id, con_retardo=True)

    for g in grupos_armados:
        excluidos = aislados | set(conf["bypass"].get(g["id"], []))
        for m in g["members"]:
            if m["id"] in excluidos:
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
                margen = retardos.retardo_entrada(g["id"], m["id"], conf)
                if margen:
                    # Con retardo de entrada no se avisa todavía: se abre la
                    # cuenta y se avisa si nadie desarma a tiempo. Desarmar
                    # borra las entradas del grupo (ver retardos.limpiar_bypass),
                    # que es lo que cancela el disparo.
                    await asyncio.to_thread(retardos.abrir_entrada, g["id"],
                                            m["id"], margen)
                    logs.registrar(logs.ALARMA, "ENTRADA_EN_CURSO", "sistema",
                                   f"{m['name']} — {margen} s para desarmar",
                                   grupo=g["name"])
                    continue
                await _alertar(g, m["name"], m["id"])
            else:
                await asyncio.to_thread(retardos.cerrar_entrada, g["id"], m["id"])
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
                global LATIDO
                LATIDO = time.time()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"⚠️ Error en el vigilante de alarma: {e}")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        _STARTED = False
        return
