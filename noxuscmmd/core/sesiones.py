"""Saber si la sesión de un navegador sigue conectada, para que los bucles de
fondo se apaguen con ella.

Existe por un fallo concreto. Las pantallas de este panel se refrescan con
bucles `@rx.event(background=True)` que giran en un `while True` (la alarma, la
vigilancia de permisos cada tres segundos, los registros, las alertas...). Hay
UNO POR SESIÓN, y nadie los para cuando el navegador se cierra: Reflex se entera al ir a mandarles la actualización —avisa con
«Attempting to send delta to disconnected client»— pero el bucle sigue girando
para siempre.

El 17 de agosto de 2026 eso dejó el backend al 95 % de CPU con 18 sesiones
fantasma acumuladas en ocho horas y solo dos navegadores de verdad conectados:
el bucle de eventos no tenía hueco para atender las pulsaciones, así que los
mandos de la casa tardaban o se perdían directamente. Reiniciar el servicio lo
limpia, pero se vuelve a llenar con el uso normal.

Reflex ya lleva la cuenta de quién está conectado —lo consulta en
`token_to_socket` antes de mandar cada delta, ver `reflex/istate/shared.py`—, así
que aquí no se inventa nada: se pregunta por lo mismo.

Uso, sustituyendo el `sleep` del bucle:

    @rx.event(background=True)
    async def mi_bucle(self):
        guardia = await sesiones.guardia(self)
        while True:
            ...
            if not await guardia.espera(3):
                return          # el navegador se fue: el bucle se va con él

Los bucles que reflejan el estado en vivo de la casa ya no esperan un tiempo
fijo: esperan a que quien escribe avise (ver core/bus.py), y el guardia se
consulta igual — `bus.Aviso.espera` devuelve lo mismo que esta.
"""
import asyncio

_app = None


def _token_to_socket():
    """El registro de sesiones conectadas de Reflex, o None si no se puede ver.

    Se guarda la app en un global porque esto se consulta en cada vuelta de cada
    bucle de cada sesión: son muchas veces por segundo, y no es sitio para
    resolver imports.
    """
    global _app
    try:
        if _app is None:
            from reflex.utils.prerequisites import get_app
            _app = get_app().app
        return _app.event_namespace._token_manager.token_to_socket
    except Exception:
        # Sin registro que consultar no se mata ningún bucle: se prefiere una
        # sesión fantasma de más a cortarle el refresco a una pantalla viva.
        return None


def conectada(token: str) -> bool | None:
    """¿Sigue ahí ese navegador? None cuando no se puede saber."""
    if not token:
        return None
    registro = _token_to_socket()
    if registro is None:
        return None
    return token in registro


class Guardia:
    """Vigila UNA sesión. Solo la da por perdida si antes la vio conectada.

    Ese «antes la vio» importa: el bucle arranca al montar la página, y en las
    primeras vueltas el token puede no estar todavía registrado. Sin esa
    condición, cada bucle se suicidaría al nacer y ninguna pantalla se
    refrescaría nunca.
    """

    def __init__(self, token: str):
        self._token = token
        self._vista = False

    @property
    def token(self) -> str:
        return self._token

    def sigue(self) -> bool:
        estado = conectada(self._token)
        if estado is None:
            return True
        if estado:
            self._vista = True
            return True
        return not self._vista

    async def espera(self, segundos: float) -> bool:
        """Duerme lo que se le diga y dice si merece la pena seguir."""
        await asyncio.sleep(segundos)
        return self.sigue()


async def espera(vigia: Guardia, segundos: float) -> bool:
    """`Guardia.espera` en forma de función, que es como se lee en los bucles:

        if not await sesiones.espera(guardia, 0.5):
            return
    """
    return await vigia.espera(segundos)


async def guardia(estado) -> Guardia:
    """Un Guardia para la sesión del estado que lo pide.

    Se lee el token una sola vez, al empezar: no cambia mientras la sesión vive,
    y así el bucle no tiene que entrar en `async with self` solo para esto.
    """
    async with estado:
        try:
            token = estado.router.session.client_token
        except Exception:
            token = ""
    return Guardia(token)
