"""Terminal de despliegue: acceso cerrado y lectura compartida del journal.

No ejecuta systemctl ni journalctl: las respuestas del sistema se sustituyen
antes de llamar al código que decide qué enseñar.
"""
import asyncio

from tests.comun import Caso

from noxuscmmd.domains.infra import despliegue


class _PeticionFalsa:
    def __init__(self, cookie: str = ""):
        self.cookies = ({despliegue.sessions.NOMBRE_COOKIE: cookie}
                        if cookie else {})


def _prueba_acceso() -> Caso:
    c = Caso("Terminal de despliegue · permisos")
    verificar_real = despliegue.sessions.verificar
    dispositivo_real = despliegue.auth_store.dispositivo
    puede_real = despliegue.permisos.puede
    leer_real = despliegue._leer
    try:
        despliegue.sessions.verificar = lambda cookie: "admin" if cookie == "buena" else None
        despliegue.auth_store.dispositivo = lambda id_: {
            "id": id_, "ver_despliegue": True}
        despliegue.permisos.puede = lambda id_, capacidad: id_ == "admin"

        respuesta = asyncio.run(despliegue.ver_log(_PeticionFalsa()))
        c.revisar("sin sesión responde 401", respuesta.status_code, 401)

        despliegue.auth_store.dispositivo = lambda id_: {"id": id_}
        respuesta = asyncio.run(despliegue.ver_log(_PeticionFalsa("buena")))
        c.revisar("sin la casilla activada responde 403", respuesta.status_code, 403)

        despliegue.auth_store.dispositivo = lambda id_: {
            "id": id_, "ver_despliegue": True}
        despliegue.permisos.puede = lambda *_: False
        respuesta = asyncio.run(despliegue.ver_log(_PeticionFalsa("buena")))
        c.revisar("sin rol administrador responde 403", respuesta.status_code, 403)

        despliegue.permisos.puede = lambda *_: True

        async def _log_falso():
            return "registro de prueba"

        despliegue._leer = _log_falso
        respuesta = asyncio.run(despliegue.ver_log(_PeticionFalsa("buena")))
        c.revisar("con ambos permisos responde 200", respuesta.status_code, 200)
        c.revisar("devuelve el registro en texto", respuesta.body,
                  b"registro de prueba")
        c.revisar("impide cachearlo fuera del panel",
                  respuesta.headers.get("cache-control"), "no-store")
    finally:
        despliegue.sessions.verificar = verificar_real
        despliegue.auth_store.dispositivo = dispositivo_real
        despliegue.permisos.puede = puede_real
        despliegue._leer = leer_real
    return c


def _prueba_cache() -> Caso:
    c = Caso("Terminal de despliegue · lectura compartida")
    run_real = despliegue._run
    llamadas = []

    async def _run_falso(*args):
        llamadas.append(args)
        return "active\n" if args[0] == "systemctl" else "línea del journal\n"

    async def _ejecutar():
        despliegue._CACHE.update(t=0.0, texto="")
        primera = await despliegue._leer()
        segunda = await despliegue._leer()
        return primera, segunda

    try:
        despliegue._run = _run_falso
        primera, segunda = asyncio.run(_ejecutar())
        c.cierto("incluye el estado del servicio",
                 primera.startswith("● noxus-panel.service: active"))
        c.cierto("incluye las líneas del journal",
                 "línea del journal" in primera)
        c.revisar("la siguiente lectura reutiliza la caché", segunda, primera)
        c.revisar("solo lanza los dos comandos de una lectura", len(llamadas), 2)
    finally:
        despliegue._run = run_real
        despliegue._CACHE.update(t=0.0, texto="")
    return c


def ejecutar() -> list[Caso]:
    return [_prueba_acceso(), _prueba_cache()]
