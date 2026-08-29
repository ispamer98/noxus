"""Los mandos expuestos a Alexa son pulsadores, no luces con estado."""
import asyncio

from tests.comun import Caso
from noxuscmmd.domains.devices import hue


def _pulsador() -> Caso:
    c = Caso("Alexa: acciones como pulsadores")
    luz = {"_voz": "voz_prueba", "name": "Botón de prueba", "_comando": "x"}
    ejecutadas = []
    original = hue._ejecutar

    async def falso(item):
        ejecutadas.append(item["_voz"])

    hue._ejecutar = falso
    hue._encendidos[luz["_voz"]] = True
    try:
        asyncio.run(hue._pulsar(luz))
        c.revisar("la orden se ejecuta una vez", ejecutadas, ["voz_prueba"])
        c.revisar("vuelve a apagado para el siguiente clic",
                  hue._encendidos[luz["_voz"]], False)
    finally:
        hue._ejecutar = original
        hue._encendidos.pop(luz["_voz"], None)
    return c


def ejecutar() -> list[Caso]:
    return [_pulsador()]
