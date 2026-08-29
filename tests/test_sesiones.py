"""
Que los bucles de fondo mueran con su sesión.

El fallo que cubre: cada pantalla se refresca con un `while True` en un
background event, y nadie los paraba al cerrar el navegador. El 17/08/2026 había
18 sesiones fantasma, el backend al 95 % de CPU y las pulsaciones del panel se
perdían. Ver noxuscmmd/core/sesiones.py.
"""
import asyncio

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
    return [c, _relevos()]


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
