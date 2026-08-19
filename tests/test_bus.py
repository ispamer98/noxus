"""
Que los bucles de pantalla despierten por aviso y no por sondeo.

Lo que cubre: antes cada bucle releía el JSON cada 0,5 s —y `_read()` de
nodes/store hace cerrojo, json.loads y `_apply_defaults` entero—, dos veces por
segundo POR SESIÓN. Ahora quien escribe avisa (noxuscmmd/core/bus.py).

Lo delicado del bus, y por eso lo que más se prueba aquí, es que un aviso no se
pierda: si llega mientras el bucle estaba leyendo el fichero, la pantalla se
quedaría con el dato viejo hasta el siguiente cambio. De ahí los contadores.

Aquí no se acciona nada: el bus solo cuenta y despierta, no toca la casa.
"""
import asyncio
import pathlib
import tempfile
import threading

from tests.comun import Caso

from noxuscmmd.core import bus


class GuardiaFalso:
    """Un guardia de sesiones de mentira, para no depender del registro real de
    Reflex (eso ya lo prueba test_sesiones.py)."""

    def __init__(self, vivo: bool = True):
        self.vivo = vivo

    def sigue(self) -> bool:
        return self.vivo


def _en_loop(corutina):
    """Cada caso con su loop propio: un asyncio.Event guardado de un loop ya
    cerrado no vale para el siguiente, y el bus guarda uno."""
    bus._reiniciar_para_pruebas()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(corutina(loop))
    finally:
        loop.close()
        bus._reiniciar_para_pruebas()


def ejecutar() -> list[Caso]:
    return [_contadores(), _despertares(), _rafaga(), _integracion()]


def _contadores() -> Caso:
    c = Caso("Bus: los contadores no pierden avisos")
    bus._reiniciar_para_pruebas()
    try:
        c.revisar("un tema sin estrenar vale cero", bus.version(bus.SENSORES), (0,))
        bus.publicar(bus.SENSORES)
        c.revisar("publicar sube el contador", bus.version(bus.SENSORES), (1,))
        bus.publicar(bus.SENSORES)
        c.revisar("y sigue subiendo", bus.version(bus.SENSORES), (2,))
        c.revisar("cada tema lleva el suyo", bus.version(bus.ARMADO), (0,))
        c.revisar("se piden varios de una vez",
                  bus.version(bus.SENSORES, bus.ARMADO), (2, 0))

        # Sin loop ninguno —la migración de shared_state publica al importarse,
        # y las pruebas también— no puede reventar.
        c.cierto("publicar sin loop no revienta", bus.publicar(bus.EQUIPOS) is None)

        # LO IMPORTANTE: un aviso que llega mientras el bucle estaba leyendo el
        # fichero no se pierde. El que espera trae versiones viejas, así que
        # `esperar` tiene que volver EN EL ACTO, sin dormir.
        async def sin_dormir(loop):
            t0 = loop.time()
            nuevas = await bus.esperar((bus.SENSORES,), (0,), 5.0)
            return nuevas, loop.time() - t0

        bus._reiniciar_para_pruebas()
        bus.publicar(bus.SENSORES)
        loop = asyncio.new_event_loop()
        try:
            nuevas, tardo = loop.run_until_complete(sin_dormir(loop))
        finally:
            loop.close()
        c.revisar("un aviso ya ocurrido se ve sin esperar", nuevas, (1,))
        c.cierto("y vuelve en el acto, no duerme el respaldo", tardo < 0.5)
    finally:
        bus._reiniciar_para_pruebas()
    return c


def _despertares() -> Caso:
    c = Caso("Bus: quién despierta a quién")

    # Publicar despierta al que espera ese tema, y pronto: la latencia de la
    # pantalla es justo esto.
    async def despierta(loop):
        loop.call_later(0.05, bus.publicar, bus.ARMADO)
        t0 = loop.time()
        nuevas = await bus.esperar((bus.ARMADO,), (0,), 5.0)
        return nuevas, loop.time() - t0

    nuevas, tardo = _en_loop(despierta)
    c.revisar("el aviso llega", nuevas, (1,))
    c.cierto("y llega antes del respaldo", tardo < 1.0)

    # El caso de MQTT: el callback de paho no corre en el hilo del loop.
    async def desde_otro_hilo(loop):
        threading.Timer(0.05, bus.publicar, args=(bus.SENSORES,)).start()
        t0 = loop.time()
        nuevas = await bus.esperar((bus.SENSORES,), (0,), 5.0)
        return nuevas, loop.time() - t0

    nuevas, tardo = _en_loop(desde_otro_hilo)
    c.revisar("un aviso desde otro hilo también despierta", nuevas, (1,))
    c.cierto("sin esperar al respaldo", tardo < 1.0)

    # Un tema ajeno no adelanta la vuelta: si despertara, el bucle releería el
    # JSON por un cambio que no le toca, que es lo que se venía a quitar.
    async def tema_ajeno(loop):
        loop.call_later(0.05, bus.publicar, bus.EQUIPOS)
        t0 = loop.time()
        nuevas = await bus.esperar((bus.ARMADO,), (0,), 0.4)
        return nuevas, loop.time() - t0

    nuevas, tardo = _en_loop(tema_ajeno)
    c.revisar("un tema ajeno no cuenta como cambio", nuevas, (0,))
    c.cierto("y el plazo se respeta entero", tardo >= 0.4)

    # Sin nadie que publique se vuelve por el respaldo: es lo que cubre que el
    # fichero lo escriba algo de fuera de este proceso.
    async def solo_respaldo(loop):
        t0 = loop.time()
        nuevas = await bus.esperar((bus.SENSORES,), (0,), 0.3)
        return nuevas, loop.time() - t0

    nuevas, tardo = _en_loop(solo_respaldo)
    c.revisar("sin avisos vuelve con lo mismo", nuevas, (0,))
    c.cierto("al agotarse el respaldo", 0.3 <= tardo < 1.5)
    return c


def _rafaga() -> Caso:
    c = Caso("Bus: ráfagas y fin de sesión")

    # Un aluvión de mensajes MQTT no puede convertirse en un aluvión de
    # relecturas: la segunda vuelta espera al mínimo aunque el aviso ya esté.
    async def agrupa(loop):
        aviso = bus.Aviso(bus.SENSORES, minimo=0.25)
        g = GuardiaFalso()
        bus.publicar(bus.SENSORES)
        await aviso.espera(g, 5.0)          # primera: vuelve enseguida
        bus.publicar(bus.SENSORES)          # ráfaga, pegada a la anterior
        t0 = loop.time()
        await aviso.espera(g, 5.0)
        return loop.time() - t0

    tardo = _en_loop(agrupa)
    c.cierto("una ráfaga no dispara dos lecturas seguidas", tardo >= 0.2)

    # Y lo que apaga el bucle: si el navegador se fue, la espera dice que no
    # merece la pena seguir (misma señal que sesiones.espera).
    async def sesion_muerta(loop):
        aviso = bus.Aviso(bus.ARMADO)
        bus.publicar(bus.ARMADO)
        return await aviso.espera(GuardiaFalso(vivo=False), 5.0)

    c.revisar("con el navegador cerrado, el bucle se va",
              _en_loop(sesion_muerta), False)

    async def sesion_viva(loop):
        aviso = bus.Aviso(bus.ARMADO)
        bus.publicar(bus.ARMADO)
        return await aviso.espera(GuardiaFalso(vivo=True), 5.0)

    c.revisar("con el navegador abierto, sigue", _en_loop(sesion_viva), True)
    return c


def _integracion() -> Caso:
    """El camino entero: escribir en el store despierta al que espera.

    Las piezas por separado ya están probadas arriba; lo que se comprueba aquí
    es que los setters AVISAN, que es lo único que hace que la pantalla se
    entere. Si alguien añade mañana otra forma de escribir el estado en vivo y
    se olvida del aviso, el panel se quedaría con el dato viejo hasta que
    venciera el respaldo, y eso no da error por ningún lado: se ve tarde y ya.
    """
    from noxuscmmd.domains.nodes import store
    from noxuscmmd.domains.security import shared_state

    c = Caso("Bus: enganchado con quien escribe")

    # SALVAGUARDA. Esto es de lo poco aquí que ESCRIBE, así que antes de tocar
    # nada se comprueba que el fichero es el de la casa de mentira. Si el
    # aislamiento fallara, esta prueba estaría marcando sensores de la casa de
    # verdad como abiertos.
    raiz_temporal = pathlib.Path(tempfile.gettempdir())

    def _en_la_casa_de_mentira(ruta) -> bool:
        return raiz_temporal in pathlib.Path(ruta).resolve().parents

    # Los DOS ficheros, no solo el de nodos: aquí abajo se llama a
    # set_sistema_armado, y sin aislar eso DESARMA LA ALARMA DE LA CASA.
    nodos_ok = _en_la_casa_de_mentira(store.ARCHIVO)
    estado_ok = _en_la_casa_de_mentira(shared_state.ESTADO_FILE)
    c.cierto("el fichero de nodos es el de pruebas, no el de la casa", nodos_ok)
    c.cierto("el de la alarma también", estado_ok)
    if not (nodos_ok and estado_ok):
        c.fallos.append(f"{c.titulo}: ABORTADA, los ficheros no están aislados")
        return c

    async def cambio_de_sensor(loop):
        aviso = bus.Aviso(bus.SENSORES, bus.EQUIPOS)
        g = GuardiaFalso()
        loop.call_later(0.05, store.set_sensor_state, "sensor_de_prueba_bus", True)
        t0 = loop.time()
        seguir = await aviso.espera(g, 5.0)
        return seguir, loop.time() - t0

    seguir, tardo = _en_loop(cambio_de_sensor)
    c.revisar("un sensor que cambia despierta al bucle", seguir, True)
    c.cierto("y sin esperar al respaldo de 3 s", tardo < 1.0)
    c.revisar("el valor escrito está en el fichero",
              store.get_all_sensor_states().get("sensor_de_prueba_bus"), True)

    async def cambio_de_armado(loop):
        aviso = bus.Aviso(bus.ARMADO)
        loop.call_later(0.05, shared_state.set_sistema_armado, False)
        t0 = loop.time()
        await aviso.espera(GuardiaFalso(), 5.0)
        return loop.time() - t0

    c.cierto("armar o desarmar también despierta", _en_loop(cambio_de_armado) < 1.0)

    # Y al revés: el ping de equipos es otro tema, así que no puede colarse
    # como si fuera un sensor.
    async def equipos_no_es_sensores(loop):
        aviso = bus.Aviso(bus.SENSORES)
        loop.call_later(0.05, store.set_host_online_bulk, {"equipo_de_prueba": True})
        t0 = loop.time()
        await aviso.espera(GuardiaFalso(), 0.4)
        return loop.time() - t0

    c.cierto("el ping de equipos no despierta al que mira sensores",
             _en_loop(equipos_no_es_sensores) >= 0.4)
    return c
