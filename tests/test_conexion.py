"""Saber si un equipo está en línea: ping normal y comprobación de puerto (Echo).

Solo habla con el propio equipo de pruebas (127.0.0.1); no toca la red de casa.
"""
import asyncio

from tests.comun import Caso

from noxuscmmd.core.connectivity import NetUtils


def _puerto() -> Caso:
    c = Caso("«ip:puerto» comprueba el puerto y no hace ping")
    bucle = asyncio.new_event_loop()

    async def prueba():
        servidor = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        puerto = servidor.sockets[0].getsockname()[1]
        abierto = await NetUtils.ping(f"127.0.0.1:{puerto}")
        servidor.close()
        await servidor.wait_closed()
        cerrado = await NetUtils.ping(f"127.0.0.1:{puerto}")
        return abierto, cerrado

    try:
        abierto, cerrado = bucle.run_until_complete(prueba())
        c.cierto("con el puerto abierto, en línea", abierto)
        c.cierto("con el puerto cerrado, sin conexión", not cerrado)
        c.cierto("una dirección normal sigue yendo por ping",
                 bucle.run_until_complete(NetUtils.ping("127.0.0.1")))
    finally:
        bucle.close()
    return c


def ejecutar() -> list[Caso]:
    return [_puerto()]
