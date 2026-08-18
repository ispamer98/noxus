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
from ..security import audit, logs, shared_state
from ..notifications import push

# Cada cuánto se mira. Doce segundos: suficiente para que quepa una persona
# cruzando y poco como para no pedirle un fotograma a la cámara sin parar.
PERIODO = 12.0

# Cuánto se calla tras avisar de una cámara, en segundos.
ENFRIAMIENTO = 180.0

# Tras estos fallos seguidos de una cámara se deja de insistir hasta que vuelva.
# La cámara «fija» de esta casa contesta 200 con cero bytes y tarda medio
# minuto: sin esto llenaría el log y frenaría la vuelta entera.
FALLOS_PARA_RENDIRSE = 5


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
        self.ultimo_aviso = 0.0
        self.fallos = 0

    def en_enfriamiento(self, ahora: float) -> bool:
        return (ahora - self.ultimo_aviso) < ENFRIAMIENTO


async def _mirar(ojo: _Ojo, umbral: float, nombre: str) -> None:
    src = _src_de(ojo.id)
    if not src:
        return
    datos = await fotogramas.capturar(src)
    if not datos:
        ojo.fallos += 1
        if ojo.fallos == FALLOS_PARA_RENDIRSE:
            print(f"⚠️ Movimiento: «{nombre}» no da fotograma; se deja de "
                  f"insistir hasta que vuelva.")
        return
    if ojo.fallos >= FALLOS_PARA_RENDIRSE:
        print(f"✅ Movimiento: «{nombre}» vuelve a dar imagen.")
    ojo.fallos = 0

    anterior, ojo.anterior = ojo.anterior, datos
    if anterior is None:
        return  # primera vuelta: no hay con qué comparar

    ahora = time.time()
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
        audit.registrar_sistema, logs.CCTV, "MOVIMIENTO_DETECTADO",
        f"{nombre} · {cambio}% de la imagen", entidad=ojo.id)
    # El fotograma se guarda igual que los de la alarma, así que se ve desde el
    # registro con la misma ruta que ya comprueba la sesión.
    try:
        if isinstance(evento, int):
            await asyncio.to_thread(fotogramas.guardar, datos, evento)
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
