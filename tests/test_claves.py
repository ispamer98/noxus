"""
Que una clave de voz NO sea una sesión.

Lo era: se emitía con `emitir()` y duraba un año, así que quien la viera —en un
log de Cloudflare, en el historial de Atajos del móvil, en la barra de
direcciones— la pegaba como cookie y entraba al panel como ese dispositivo.

Aquí se comprueban las dos direcciones del aislamiento, que es lo único que
importa: una no puede hacerse pasar por la otra.
"""
import time

from tests.comun import Caso

from noxuscmmd.domains.auth import sessions


def ejecutar() -> list[Caso]:
    c = Caso("Claves de voz y sesiones, separadas")

    cookie = sessions.emitir("disp_1", duracion=3600)
    clave = sessions.emitir_voz("disp_1", duracion=3600)

    c.revisar("la cookie identifica a su dispositivo",
              sessions.verificar(cookie), "disp_1")
    c.revisar("la clave de voz identifica al suyo",
              sessions.verificar_voz(clave), "disp_1")

    # Lo importante: ninguna vale como la otra.
    c.revisar("una clave de voz NO vale como cookie",
              sessions.verificar(clave), None)
    c.revisar("una cookie NO vale como clave de voz",
              sessions.verificar_voz(cookie), None)

    # Y no se puede convertir una en otra quitando el prefijo, porque el literal
    # va dentro del mensaje firmado.
    sin_prefijo = clave.split(".", 1)[1]
    c.revisar("quitarle el prefijo no la convierte en cookie",
              sessions.verificar(sin_prefijo), None)
    c.revisar("ponerle el prefijo a una cookie tampoco la convierte",
              sessions.verificar_voz(f"voz.{cookie}"), None)

    # Lo de siempre: firma manipulada y caducidad.
    partes = clave.split(".")
    manipulada = ".".join(partes[:3] + ["0" * len(partes[3])])
    c.revisar("una firma manipulada no vale",
              sessions.verificar_voz(manipulada), None)
    c.revisar("una clave caducada no vale",
              sessions.verificar_voz(sessions.emitir_voz("disp_1", duracion=-10)), None)
    c.revisar("una clave vacía no vale", sessions.verificar_voz(""), None)
    c.revisar("cualquier basura tampoco", sessions.verificar_voz("voz.a.b"), None)
    return [c]
