"""
El vigilante que compara fotogramas y avisa. Tarea de proceso, como el resto de
lo que tiene que funcionar con el panel cerrado.

Condiciones para mirar siquiera, y son deliberadamente restrictivas:
  · encendido en Ajustes;
  · el sistema ARMADO, salvo que se desmarque a propósito. Mirar las cámaras de
    dentro de casa mientras la familia está dentro no es vigilar, es otra cosa;
  · solo las cámaras que se hayan marcado.

Cuando algo se mueve: se guarda el fotograma (el mismo almacén que usa la
alarma, con su endpoint que pide sesión) y se avisa una vez, con enfriamiento —
un aviso por segundo mientras alguien pasea por el salón sería inservible.
"""
import asyncio
import time

from . import fotogramas, movimiento, movimiento_store
from ..security import audit, logs, logs_store, shared_state
from ..notifications import categorias, push

# Cada cuánto se LANZA una captura, sin esperar a que vuelva la anterior.
#
# Pedirle un fotograma a esta cámara cuesta 1,4 s casi fijos, y ese tiempo es
# abrir la sesión con la nube de Tuya, no traer la imagen: pedirla pequeña
# (31 KB en vez de 168) tarda exactamente lo mismo. Así que encadenando —pedir,
# esperar, pedir— no se puede bajar de un fotograma cada segundo y medio, y
# alguien que cruza deprisa cabe entero en ese hueco.
#
# Lo que sí se puede: SOLAPARLAS. Dos peticiones a la vez tardan lo mismo que
# una sola (1,29 s las dos, medido), o sea que la espera se paraleliza. Lanzando
# una cada medio segundo hay fotograma nuevo cada medio segundo, con tres
# peticiones en vuelo. Medido sostenido: 90 capturas en 45 s, NINGUNA fallida.
DISPARO = 0.5

# Cada cuánto se releen los ajustes y se decide si toca vigilar. No hace falta
# más fino: es un JSON pequeño y la decisión no cambia entre dos disparos.
PERIODO = 2.0

# Cuánto se calla tras avisar de una cámara, en segundos. Con el ritmo de dos
# segundos, sin esto llegarían treinta avisos por minuto mientras alguien se
# mueve por el salón. Un minuto es el equilibrio: se entera uno de que hay
# alguien, y si sigue habiendo movimiento vuelve a avisar al minuto siguiente.
ENFRIAMIENTO = 60.0

# Tras estos fallos seguidos, una cámara se da por caída y se deja de pedirle
# fotograma en cada vuelta. La «fija» de esta casa, cuando está desconectada,
# se come los 4 s enteros del temporizador: con dos cámaras marcadas eso
# convertía una vuelta de 12 s en una de 17-19 s, así que la cámara rota
# retrasaba la vigilancia de la que funciona.
FALLOS_PARA_RENDIRSE = 5

# Lo viejo que puede ser el fotograma anterior para que comparar con él
# signifique algo. Si una cámara se salta unas cuantas vueltas, la foto guardada
# acaba siendo de hace un buen rato, y entonces lo que se mide ya no es «algo se
# ha movido» sino «ha pasado el tiempo»: cambia la luz, entra el modo noche, y
# salta un aviso que no tiene nada detrás. Ocho segundos dan margen a tres
# capturas fallidas seguidas; a partir de ahí se tira y se empieza de cero.
CADUCIDAD_ANTERIOR = 8.0

# Cada cuánto se prueba si la caída ha vuelto. Es lo único que se le pide
# mientras está caída: un intento por minuto en vez de uno cada vuelta. En
# cuanto conteste, se vuelve a mirar a su ritmo normal sin tener que tocar nada.
REINTENTO_CAIDA = 60.0


def _src_de(camara_id: str) -> str:
    """El stream de go2rtc de una cámara. Misma convención que
    cameras/wall.catalogo_camaras: las de fábrica son su id sin el "cam_"."""
    if camara_id.startswith("cam_"):
        return camara_id[4:]
    from ..nodes import store as nodes_store
    for c in nodes_store.read_all().get("cameras", []):
        if c["id"] == camara_id and c.get("kind") == "go2rtc":
            return c.get("url", "")
    return ""


class _Ojo:
    """Lo que se recuerda de UNA cámara entre vuelta y vuelta."""

    def __init__(self, camara_id: str):
        self.id = camara_id
        self.anterior: bytes | None = None
        self.momento_anterior = 0.0
        self.ultimo_aviso = 0.0
        self.fallos = 0
        self.ultimo_intento = 0.0
        # Con las capturas solapadas, la que se pidió antes puede volver
        # después. Cada una lleva su número y solo se queda la más nueva: sin
        # esto se compararía hacia atrás y saldrían diferencias inventadas.
        self.orden_anterior = -1
        # Serializa la parte de comparar y avisar. Las capturas van en
        # paralelo, que es lo que da el ritmo; decidir, de una en una, o dos
        # que vuelven juntas mandarían dos avisos del mismo movimiento.
        self.cerrojo = asyncio.Lock()

    def en_enfriamiento(self, ahora: float) -> bool:
        return (ahora - self.ultimo_aviso) < ENFRIAMIENTO

    def caida(self) -> bool:
        return self.fallos >= FALLOS_PARA_RENDIRSE

    def llega_tarde(self, orden: int) -> bool:
        """¿Este fotograma es más viejo que el último que ya se miró?

        Con los disparos solapados pasa de verdad: se piden cada medio segundo
        y cada uno tarda 1,4 s, así que el número 7 puede volver antes que el 6.
        Comparar el 6 contra el 7 mediría el movimiento AL REVÉS y daría una
        diferencia que no ha ocurrido.
        """
        return orden <= self.orden_anterior

    def toca_reintentar(self, ahora: float) -> bool:
        """Una caída solo se prueba una vez por minuto. Las demás vueltas se la
        salta entera, que es lo que devuelve el ritmo a las que sí funcionan."""
        return (ahora - self.ultimo_intento) >= REINTENTO_CAIDA


async def _mirar(ojo: _Ojo, umbral: float, nombre: str, orden: int) -> None:
    """Pide un fotograma y, si toca, decide y avisa.

    `orden` es el número del disparo. Como van solapados, el que se pidió antes
    puede volver después: comparar entonces contra un fotograma MÁS NUEVO daría
    una diferencia que no ha ocurrido, así que el que llega tarde se descarta.
    """
    src = _src_de(ojo.id)
    if not src:
        return

    # Una cámara caída no se pide en cada disparo: solo se prueba si ha vuelto
    # una vez por minuto. Mientras tanto ni se la espera, así que no le quita
    # ritmo a las que sí están dando imagen.
    principio = time.time()
    if ojo.caida() and not ojo.toca_reintentar(principio):
        return
    ojo.ultimo_intento = principio

    datos = await fotogramas.capturar(src)
    if not datos:
        ojo.fallos += 1
        if ojo.fallos == FALLOS_PARA_RENDIRSE:
            print(f"⚠️ Movimiento: «{nombre}» no da fotograma; se prueba solo "
                  f"una vez por minuto hasta que vuelva.")
        return
    volvio = ojo.caida()
    ojo.fallos = 0

    async with ojo.cerrojo:
        if volvio:
            print(f"✅ Movimiento: «{nombre}» vuelve a dar imagen.")
            # La foto guardada es de hace un buen rato: compararla con la de
            # ahora daría un cambio enorme que no es movimiento, sino el tiempo
            # que ha pasado. Se empieza de cero.
            ojo.anterior = None
            ojo.momento_anterior = 0.0

        if ojo.llega_tarde(orden):
            return  # ya hay uno más nuevo: este no dice nada

        ahora = time.time()
        anterior = ojo.anterior
        rancia = anterior is not None and (ahora - ojo.momento_anterior) > CADUCIDAD_ANTERIOR
        ojo.anterior = datos
        ojo.momento_anterior = ahora
        ojo.orden_anterior = orden

        if anterior is None:
            return  # el primero: no hay con qué comparar
        if rancia:
            # Se queda el de ahora como referencia, pero con este no se
            # compara: ver CADUCIDAD_ANTERIOR.
            return
        if ojo.en_enfriamiento(ahora):
            return
        try:
            visto = await asyncio.to_thread(
                movimiento.analizar, anterior, datos, umbral)
        except movimiento.NoSePuedeComparar:
            return
        if not visto.hay:
            return
        # La mancha dice «algo con cuerpo se ha movido», pero eso también lo
        # deja una lámpara que ilumina solo un rincón. Antes de avisar, se
        # confirma con el detector de personas sobre el fotograma de verdad.
        if not await asyncio.to_thread(movimiento.hay_persona, datos):
            return
        ojo.ultimo_aviso = ahora

    # Fuera del cerrojo: avisar y guardar la foto no pueden frenar el ritmo de
    # las capturas siguientes.
    #
    # Y el AVISO VA PRIMERO. Guardar la foto y colgarla del evento toca disco, y
    # quien recibe «algo se ha movido en el salón» quiere el aviso cuanto antes;
    # la imagen puede llegar al registro medio segundo después, que es
    # exactamente lo que ya hace el vigilante de la alarma (ver
    # cameras/fotogramas.py: el evento se guarda antes de tener la foto).
    evento = await asyncio.to_thread(
        audit.registrar_sistema, logs.ALARMA, "MOVIMIENTO_DETECTADO",
        f"{nombre} · {visto.mancha}% de la imagen (cambio total {visto.total}%)",
        entidad=ojo.id)
    aviso = asyncio.create_task(asyncio.to_thread(
        push.enviar_notificacion,
        "Movimiento detectado",
        f"{nombre}: algo se ha movido.",
        tag=f"movimiento:{ojo.id}",
        # Lleva al Registro, que es donde está el evento CON SU FOTO. Antes
        # abría el panel por donde estuviera y había que buscar el evento a
        # mano. Verla pide la misma capacidad que el mural (CAMARAS), así que
        # administrador y familia entran y un invitado no.
        url="/panel?vista=logs",
        categoria=categorias.MOVIMIENTO,
    ))
    _avisos.add(aviso)
    aviso.add_done_callback(_avisos.discard)

    try:
        if isinstance(evento, int) and evento:
            nombre_foto = await asyncio.to_thread(fotogramas.guardar, datos, evento)
            if nombre_foto:
                await asyncio.to_thread(logs_store.adjuntar_foto, evento, nombre_foto)
                print(f"📸 Movimiento: fotograma {nombre_foto} en el evento {evento}")
    except Exception as e:
        print(f"⚠️ Movimiento: no se pudo guardar el fotograma: {e}")


# Cada cuánto se vuelven a leer los nombres de las cámaras. Van aparte del
# ritmo de mirar porque cambian cuando alguien renombra una cámara, o sea casi
# nunca, y releer nodos_dinamicos.json treinta veces por minuto para eso es
# trabajo tirado (ver nodes/store._read, que normaliza el fichero entero).
REFRESCO_NOMBRES = 30.0

# Los avisos en vuelo. Sin guardar la referencia, el recolector de basura
# puede llevarse una tarea a medio enviar (lo dice la documentación de
# asyncio.create_task); mismo patrón que security/watcher.py con sus fotos.
_avisos: set = set()


async def _mirar_sin_levantar(ojo: _Ojo, umbral: float, nombre: str,
                              orden: int) -> None:
    """`_mirar` envuelto: un fallo con UNA cámara no puede llevarse por delante
    el disparo de las demás ni parar el bucle."""
    try:
        await _mirar(ojo, umbral, nombre, orden)
    except Exception as e:
        print(f"⚠️ Movimiento: fallo mirando {ojo.id}: {e}")


async def run_forever() -> None:
    ojos: dict[str, _Ojo] = {}
    en_vuelo: set = set()
    nombres: dict[str, str] = {}
    nombres_vistos = 0.0
    ajustes_vistos = 0.0
    config = None
    orden = 0

    while True:
        try:
            # Los ajustes no se releen en cada disparo: dos por segundo para
            # mirar un JSON que casi nunca cambia es trabajo tirado.
            if config is None or (time.monotonic() - ajustes_vistos) > PERIODO:
                config = movimiento_store.leer()
                ajustes_vistos = time.monotonic()

            mirando = bool(config["activada"] and config["camaras"])
            if mirando and config["solo_armado"]:
                mirando = await asyncio.to_thread(shared_state.get_sistema_armado)

            if not mirando:
                # Se olvida lo visto: al volver se empieza con una foto nueva en
                # vez de comparar contra una de antes de apagarlo. Y no se le
                # pide NADA a las cámaras mientras tanto.
                ojos.clear()
                await asyncio.sleep(PERIODO)
                continue

            if (time.monotonic() - nombres_vistos) > REFRESCO_NOMBRES or not nombres:
                from ..nodes import store as nodes_store
                datos = await asyncio.to_thread(nodes_store.read_all)
                nombres = {c["id"]: c.get("name", c["id"])
                           for c in datos.get("cameras", []) + datos.get("factory_cameras", [])}
                nombres_vistos = time.monotonic()

            # Se DISPARAN y no se esperan: aquí está el ritmo. Cada captura
            # tarda 1,4 s, pero solapadas llegan cada medio segundo, y por eso
            # se caza a alguien que solo cruza.
            orden += 1
            for cam in config["camaras"]:
                ojo = ojos.setdefault(cam, _Ojo(cam))
                tarea = asyncio.create_task(_mirar_sin_levantar(
                    ojo, config["umbral"], nombres.get(cam, cam), orden))
                en_vuelo.add(tarea)
                tarea.add_done_callback(en_vuelo.discard)

            # Freno de mano: si las capturas empiezan a tardar mucho más de la
            # cuenta, se dejan de lanzar hasta que bajen. Sin esto, una cámara
            # que se atasca acumularía peticiones sin fin encima de ella.
            if len(en_vuelo) >= len(config["camaras"]) * 6:
                print(f"⚠️ Movimiento: {len(en_vuelo)} capturas en vuelo, "
                      f"se espera a que bajen")
                while len(en_vuelo) > len(config["camaras"]) * 2:
                    await asyncio.sleep(DISPARO)

            await asyncio.sleep(DISPARO)
        except Exception as e:
            print(f"⚠️ Movimiento: error en el bucle: {e}")
            await asyncio.sleep(5)
