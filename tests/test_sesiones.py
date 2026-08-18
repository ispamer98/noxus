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
    return [c]
