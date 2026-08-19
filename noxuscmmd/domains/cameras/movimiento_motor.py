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
from ..notifications import push

# Cada cuánto se mira. Doce segundos: suficiente para que quepa una persona
# cruzando y poco como para no pedirle un fotograma a la cámara sin parar.
PERIODO = 12.0

# Cuánto se calla tras avisar de una cámara, en segundos.
ENFRIAMIENTO = 180.0

# Tras estos fallos seguidos, una cámara se da por caída y se deja de pedirle
# fotograma en cada vuelta. La «fija» de esta casa, cuando está desconectada,
# se come los 4 s enteros del temporizador: con dos cámaras marcadas eso
# convertía una vuelta de 12 s en una de 17-19 s, así que la cámara rota
# retrasaba la vigilancia de la que funciona.
FALLOS_PARA_RENDIRSE = 5

# Lo viejo que puede ser el fotograma anterior para que comparar con él
# signifique algo. Si una cámara se salta unas cuantas vueltas —la del salón
# contesta «0 bytes» de vez en cuando—, la foto guardada acaba siendo de hace
# minutos, y entonces lo que se mide ya no es «algo se ha movido» sino «ha
# pasado el rato»: cambia la luz, entra el modo noche, y salta un aviso que no
# tiene nada detrás. Pasado este tiempo se tira y se empieza de cero.
CADUCIDAD_ANTERIOR = PERIODO * 3

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

    def en_enfriamiento(self, ahora: float) -> bool:
        return (ahora - self.ultimo_aviso) < ENFRIAMIENTO

    def caida(self) -> bool:
        return self.fallos >= FALLOS_PARA_RENDIRSE

    def toca_reintentar(self, ahora: float) -> bool:
        """Una caída solo se prueba una vez por minuto. Las demás vueltas se la
        salta entera, que es lo que devuelve el ritmo a las que sí funcionan."""
        return (ahora - self.ultimo_intento) >= REINTENTO_CAIDA


async def _mirar(ojo: _Ojo, umbral: float, nombre: str) -> None:
    src = _src_de(ojo.id)
    if not src:
        return

    # Una cámara caída no se pide en cada vuelta: solo se prueba si ha vuelto
    # una vez por minuto. Mientras tanto ni se la espera, así que no le quita
    # tiempo a las que sí están dando imagen.
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
    if ojo.caida():
        print(f"✅ Movimiento: «{nombre}» vuelve a dar imagen.")
        # La foto guardada es de hace un buen rato: compararla con la de ahora
        # daría un cambio enorme que no es movimiento, sino el tiempo que ha
        # pasado. Se empieza de cero.
        ojo.anterior = None
        ojo.momento_anterior = 0.0
    ojo.fallos = 0

    ahora = time.time()
    anterior, ojo.anterior = ojo.anterior, datos
    rancia = anterior is not None and (ahora - ojo.momento_anterior) > CADUCIDAD_ANTERIOR
    ojo.momento_anterior = ahora
    if anterior is None:
        return  # primera vuelta: no hay con qué comparar
    if rancia:
        # Se queda la de ahora como referencia para la vuelta siguiente, pero
        # con esta no se compara: ver CADUCIDAD_ANTERIOR.
        return

    if ojo.en_enfriamiento(ahora):
        return
    try:
        hay, cambio = await asyncio.to_thread(
            movimiento.hay_movimiento, anterior, datos, umbral)
    except movimiento.NoSePuedeComparar:
        return
    if not hay:
        return

    ojo.ultimo_aviso = ahora
    evento = await asyncio.to_thread(
        audit.registrar_sistema, logs.ALARMA, "MOVIMIENTO_DETECTADO",
        f"{nombre} · {cambio}% de la imagen", entidad=ojo.id)
    # El fotograma se guarda igual que los de la alarma, así que se ve desde el
    # registro con la misma ruta que ya comprueba la sesión. Guardarlo NO basta:
    # hay que colgárselo al evento (adjuntar_foto), que es lo que hace que el
    # registro sepa que esa entrada tiene imagen. Sin eso el fichero quedaba en
    # la carpeta sin que nada apuntara a él.
    try:
        if isinstance(evento, int) and evento:
            nombre = await asyncio.to_thread(fotogramas.guardar, datos, evento)
            if nombre:
                await asyncio.to_thread(logs_store.adjuntar_foto, evento, nombre)
                print(f"📸 Movimiento: fotograma {nombre} en el evento {evento}")
    except Exception as e:
        print(f"⚠️ Movimiento: no se pudo guardar el fotograma: {e}")
    await asyncio.to_thread(
        push.enviar_notificacion,
        "Movimiento detectado",
        f"{nombre}: algo se ha movido.",
        tag=f"movimiento:{ojo.id}",
    )


async def run_forever() -> None:
    ojos: dict[str, _Ojo] = {}
    while True:
        await asyncio.sleep(PERIODO)
        try:
            config = movimiento_store.leer()
            if not config["activada"] or not config["camaras"]:
                ojos.clear()
                continue
            if config["solo_armado"] and not await asyncio.to_thread(
                    shared_state.get_sistema_armado):
                ojos.clear()
                continue

            from ..nodes import store as nodes_store
            datos = await asyncio.to_thread(nodes_store.read_all)
            nombres = {c["id"]: c.get("name", c["id"])
                       for c in datos.get("cameras", []) + datos.get("factory_cameras", [])}

            for camara_id in config["camaras"]:
                ojo = ojos.setdefault(camara_id, _Ojo(camara_id))
                try:
                    await _mirar(ojo, config["umbral"], nombres.get(camara_id, camara_id))
                except Exception as e:
                    print(f"⚠️ Movimiento: fallo mirando {camara_id}: {e}")
        except Exception as e:
            print(f"⚠️ Movimiento: error en el bucle: {e}")
            await asyncio.sleep(5)
