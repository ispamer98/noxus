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

# Cada cuánto se mira. Dos segundos, y el número tiene medida detrás: pedirle un
# fotograma al salón tarda 1,5 s de mediana (1,13 el mejor, 1,77 el peor), y en
# una prueba de 60 s a este ritmo salieron 30 capturas y NINGUNA fallida.
#
# Estuvo en doce segundos y era demasiado: con dos capturas separadas doce
# segundos —diecisiete en la práctica, porque la cámara caída se comía el
# temporizador— alguien que cruza el salón pasa entera la ventana sin aparecer
# en ninguna de las dos fotos, y para el vigilante no ha ocurrido nada. Mirar
# cada dos segundos es lo que convierte esto en algo que sirve.
#
# Si una captura tarda más que esto, la siguiente sale en cuanto termina: el
# ritmo lo marca la cámara y nunca se acumulan peticiones encima de ella.
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
        visto = await asyncio.to_thread(
            movimiento.analizar, anterior, datos, umbral)
    except movimiento.NoSePuedeComparar:
        return
    if not visto.hay:
        return

    ojo.ultimo_aviso = ahora
    # Se apuntan las dos cifras: la MANCHA es la que decide (la zona con cuerpo
    # que ha cambiado) y el total va detrás para poder entender después por qué
    # saltó, sobre todo si algún día salta cuando no debía.
    evento = await asyncio.to_thread(
        audit.registrar_sistema, logs.ALARMA, "MOVIMIENTO_DETECTADO",
        f"{nombre} · {visto.mancha}% de la imagen (cambio total {visto.total}%)",
        entidad=ojo.id)
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


# Cada cuánto se vuelven a leer los nombres de las cámaras. Van aparte del
# ritmo de mirar porque cambian cuando alguien renombra una cámara, o sea casi
# nunca, y releer nodos_dinamicos.json treinta veces por minuto para eso es
# trabajo tirado (ver nodes/store._read, que normaliza el fichero entero).
REFRESCO_NOMBRES = 30.0


async def _mirar_sin_levantar(ojo: _Ojo, umbral: float, nombre: str) -> None:
    """`_mirar` envuelto: un fallo con UNA cámara no puede llevarse por delante
    la vuelta de las demás, que es lo que pasaría al mirarlas en paralelo."""
    try:
        await _mirar(ojo, umbral, nombre)
    except Exception as e:
        print(f"⚠️ Movimiento: fallo mirando {ojo.id}: {e}")


async def run_forever() -> None:
    ojos: dict[str, _Ojo] = {}
    nombres: dict[str, str] = {}
    nombres_vistos = 0.0
    while True:
        principio = time.monotonic()
        try:
            config = movimiento_store.leer()
            mirando = bool(config["activada"] and config["camaras"])
            if mirando and config["solo_armado"]:
                mirando = await asyncio.to_thread(shared_state.get_sistema_armado)
            if not mirando:
                # Se olvida lo visto: al volver se empieza con una foto nueva en
                # vez de comparar contra una de antes de apagarlo.
                ojos.clear()
            else:
                if (time.monotonic() - nombres_vistos) > REFRESCO_NOMBRES or not nombres:
                    from ..nodes import store as nodes_store
                    datos = await asyncio.to_thread(nodes_store.read_all)
                    nombres = {c["id"]: c.get("name", c["id"])
                               for c in datos.get("cameras", []) + datos.get("factory_cameras", [])}
                    nombres_vistos = time.monotonic()

                # En paralelo, no una detrás de otra: encadenarlas hacía que el
                # ritmo fuera la SUMA de lo que tarda cada cámara, así que con
                # dos ya no se podía mirar cada dos segundos.
                await asyncio.gather(*[
                    _mirar_sin_levantar(
                        ojos.setdefault(cam, _Ojo(cam)),
                        config["umbral"],
                        nombres.get(cam, cam))
                    for cam in config["camaras"]
                ])
        except Exception as e:
            print(f"⚠️ Movimiento: error en el bucle: {e}")
            await asyncio.sleep(5)

        # Lo que falte para completar el periodo. Si la cámara ha tardado más
        # que eso, la siguiente vuelta sale ya: nunca se le encima una petición
        # a otra, que es de donde salían los «0 bytes».
        resto = PERIODO - (time.monotonic() - principio)
        if resto > 0:
            await asyncio.sleep(resto)
