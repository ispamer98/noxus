"""
Que los bucles de fondo mueran con su sesión.

El fallo que cubre: cada pantalla se refresca con un `while True` en un
background event, y nadie los paraba al cerrar el navegador. El 17/08/2026 había
18 sesiones fantasma, el backend al 95 % de CPU y las pulsaciones del panel se
perdían. Ver noxuscmmd/core/sesiones.py.
"""
import asyncio

import wrapt

from tests.comun import Caso

from noxuscmmd.core import sesiones


def ejecutar() -> list[Caso]:
    c = Caso("Guardia de sesiones")
    registro = {}
    original = sesiones._token_to_socket
    sesiones._token_to_socket = lambda: registro
    try:
        # Una sesión que aún no consta NO se mata: el bucle arranca al montar la
        # página y el token puede tardar en registrarse. Sin esto, cada bucle se
        # suicidaría al nacer y ninguna pantalla se refrescaría.
        c.revisar("sesión aún no registrada sigue viva",
                  sesiones.Guardia("nueva").sigue(), True)

        registro["viva"] = object()
        g = sesiones.Guardia("viva")
        c.revisar("sesión conectada sigue viva", g.sigue(), True)
        del registro["viva"]
        c.revisar("sesión que se fue se da por perdida", g.sigue(), False)

        # El agujero por el que se colaban los bucles inmortales: si el
        # navegador se va ANTES de la primera comprobación —una recarga, una
        # pestaña que se cierra al momento—, el guardia no llegó a verlo
        # conectado nunca, y sin plazo eso era un pase vitalicio. Se le sigue
        # dando cuerda al recién nacido, pero solo su minuto.
        nunca = sesiones.Guardia("nunca-llego")
        c.revisar("recién nacido sin ver la sesión, se le da cuerda",
                  nunca.sigue(), True)
        nunca._nacido -= sesiones.GRACIA + 1
        c.revisar("pasado el plazo sin verla nunca, se apaga",
                  nunca.sigue(), False)

        # Pero el plazo NO cuenta cuando no se puede saber si está conectada:
        # ahí se prefiere una sesión fantasma de más a cortar una viva.
        sesiones._token_to_socket = lambda: None
        ciego = sesiones.Guardia("sin-registro")
        ciego._nacido -= sesiones.GRACIA + 1
        c.revisar("sin registro que consultar, el plazo no mata a nadie",
                  ciego.sigue(), True)
        sesiones._token_to_socket = lambda: registro

        # Los dos casos en los que no se puede saber: nunca se mata un bucle por
        # no saber, se prefiere una sesión fantasma de más.
        c.revisar("token vacío sigue vivo", sesiones.Guardia("").sigue(), True)
        sesiones._token_to_socket = lambda: None
        c.revisar("sin registro que consultar sigue vivo",
                  sesiones.Guardia("x").sigue(), True)
        sesiones._token_to_socket = lambda: registro

        # La espera duerme de verdad y contesta si merece la pena seguir.
        registro["t"] = object()
        g2 = sesiones.Guardia("t")
        bucle = asyncio.new_event_loop()
        try:
            t0 = bucle.time()
            c.revisar("espera con sesión viva devuelve True",
                      bucle.run_until_complete(sesiones.espera(g2, 0.12)), True)
            c.cierto("la espera duerme lo pedido", bucle.time() - t0 >= 0.12)
            del registro["t"]
            c.revisar("espera tras desconexión devuelve False",
                      bucle.run_until_complete(sesiones.espera(g2, 0.01)), False)
        finally:
            bucle.close()
    finally:
        sesiones._token_to_socket = original
    return [c, _relevos(), _nombre_del_bucle()]


def _relevos() -> Caso:
    """El relevo entre bucles de la MISMA sesion.

    Hace falta desde que los eventos de entrada son on_load: Reflex los reenvia
    en cada (re)conexion del websocket —eso es lo que hace que una pestana que
    vuelve de segundo plano recupere sus actualizaciones sin recargar—, asi que
    el mismo bucle arranca otra vez sobre una sesion que ya lo tenia girando.
    Sin relevo se acumularian, que es exactamente la averia de las sesiones
    fantasma pero desde dentro de una sesion viva.
    """
    c = Caso("Sesiones: un bucle nuevo releva al viejo")
    registro = {"t": object()}
    original = sesiones._token_to_socket
    sesiones._token_to_socket = lambda: registro
    try:
        primero = sesiones.Guardia("t", "vigilar", sesiones._relevar("t", "vigilar"))
        c.revisar("el unico que hay sigue vivo", primero.sigue(), True)

        segundo = sesiones.Guardia("t", "vigilar", sesiones._relevar("t", "vigilar"))
        c.revisar("al arrancar otro igual, el viejo se apaga", primero.sigue(), False)
        c.revisar("y el nuevo se queda", segundo.sigue(), True)

        # Otro bucle DISTINTO de la misma sesion no se ve afectado: el relevo es
        # por nombre, no por sesion entera.
        otro = sesiones.Guardia("t", "otro_bucle", sesiones._relevar("t", "otro_bucle"))
        c.revisar("un bucle con otro nombre sigue vivo", otro.sigue(), True)
        c.revisar("y no ha tocado al primero", segundo.sigue(), True)

        # Y el mismo nombre en OTRA sesion tampoco: dos moviles con el panel
        # abierto tienen cada uno el suyo.
        registro["otra"] = object()
        ajena = sesiones.Guardia("otra", "vigilar", sesiones._relevar("otra", "vigilar"))
        c.revisar("el mismo bucle en otra sesion vive aparte", ajena.sigue(), True)
        c.revisar("sin apagar el de la primera", segundo.sigue(), True)

        # Al desconectarse la sesion, el bucle se apaga y borra su apunte: el
        # registro no puede crecer sin fin.
        del registro["t"]
        c.revisar("desconectada, el bucle se apaga", segundo.sigue(), False)
        c.revisar("y deja de constar",
                  ("t", "vigilar") in sesiones._relevos, False)

        # Un guardia SIN nombre (no se pudo saber quien llama, o no hay token)
        # se comporta como siempre: nunca se le releva.
        registro["t"] = object()
        suelto = sesiones.Guardia("t")
        c.revisar("un guardia sin nombre sigue vivo", suelto.sigue(), True)
        sesiones._relevar("t", "vigilar")
        c.revisar("y no le afecta que arranquen otros", suelto.sigue(), True)
    finally:
        sesiones._token_to_socket = original
        sesiones._relevos.clear()
    return c


# ── El nombre que compone guardia() ──────────────────────────────────────────
# Reflex entrega a un `@rx.event(background=True)` un StateProxy, no el State
# (reflex/state.py: "For background tasks, proxy the state"). El proxy es un
# wrapt.ObjectProxy: `type()` ve el proxy y `__class__` ve lo envuelto. De ahi
# sale el fallo que esto cubre — con `type()`, los nueve `sync_loop` del panel
# compartian la clave `(token, "StateProxy.sync_loop")`, se relevaban entre
# ellos y sobrevivia UNO: el escudo del armado no cambiaba al pulsarlo, ni el
# resto de pantallas se enteraban de nada hasta recargar.
class _SesionFalsa:
    client_token = "t"


class _RouterFalso:
    session = _SesionFalsa()


class _StateFalso:
    router = _RouterFalso()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _OtroStateFalso(_StateFalso):
    pass


class _ProxyFalso(wrapt.ObjectProxy):
    """Lo mismo que hace reflex.istate.proxy.StateProxy: envolver el State."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def _nombre_del_bucle() -> Caso:
    c = Caso("Sesiones: el nombre del bucle sale del State, no del proxy")
    registro = {"t": object()}
    original = sesiones._token_to_socket
    sesiones._token_to_socket = lambda: registro
    bucle = asyncio.new_event_loop()
    try:
        async def sync_loop(estado):
            return await sesiones.guardia(estado)

        # Con el State pelado (un bucle que no fuera background).
        bucle.run_until_complete(sync_loop(_StateFalso()))
        c.cierto("el nombre lleva el State delante",
                 ("t", "_StateFalso.sync_loop") in sesiones._relevos)

        # Y con el proxy, que es lo que llega de verdad en un bucle de fondo.
        primero = bucle.run_until_complete(sync_loop(_ProxyFalso(_StateFalso())))
        c.cierto("envuelto en el proxy, el nombre es el mismo",
                 ("t", "_StateFalso.sync_loop") in sesiones._relevos)
        c.revisar("y no cuela el nombre del proxy",
                  ("t", "_ProxyFalso.sync_loop") in sesiones._relevos, False)

        # Lo que importa: dos States distintos con el bucle llamado igual NO se
        # relevan entre si aunque los dos lleguen envueltos.
        bucle.run_until_complete(sync_loop(_ProxyFalso(_OtroStateFalso())))
        c.revisar("otro State con el mismo nombre de bucle no apaga al primero",
                  primero.sigue(), True)
    finally:
        bucle.close()
        sesiones._token_to_socket = original
        sesiones._relevos.clear()
    return c
