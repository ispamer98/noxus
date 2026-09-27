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
import inspect
import time

_app = None

# ── Un bucle por sesión y por nombre ─────────────────────────────────────────
# Desde que los on_load se relanzan en CADA (re)conexión del websocket —que es
# lo que hace que una pestaña que vuelve de segundo plano recupere sus
# actualizaciones sin recargar la página—, el mismo bucle puede volver a
# arrancar sobre una sesión que ya lo tenía girando. Sin esto se acumularían:
# la misma avería de las sesiones fantasma, pero desde dentro de una sesión
# viva y sin que nadie cierre nada.
#
# Cada arranque toma un número y deja obsoleto al anterior; el viejo se apaga
# solo en su siguiente vuelta (ver Guardia.sigue). Así queda SIEMPRE uno, el
# más reciente, sin tener que acordarse de dar de baja nada a mano.
#
# EL NOMBRE LLEVA EL STATE DELANTE, y no es un adorno. Nueve States distintos
# llaman `sync_loop` a su bucle (seguridad, nodos, grupos, accesos, registros,
# automatizaciones, inventario, alertas, registry). Identificándolos solo por
# el nombre de la función, los nueve compartían la clave `(token,
# "sync_loop")`: cada uno que arrancaba dejaba obsoletos a los ocho anteriores
# y estos se apagaban en su primera vuelta. De los nueve sobrevivía UNO —el
# último en arrancar—, así que en una pestaña recién abierta casi nada se
# refrescaba solo: el escudo del armado se quedaba en verde con la casa
# armada, y un cambio hecho en otro dispositivo no llegaba nunca. Con el State
# delante, cada bucle tiene su propia clave y solo se releva a sí mismo, que
# es lo único que este mecanismo quería evitar. Sacar ese nombre tiene truco
# —el `self` de un bucle de fondo es un StateProxy, no el State—: ver guardia().
#
# Todo esto vive en el hilo del bucle de eventos —guardia() solo se llama desde
# manejadores async—, así que un dict pelado basta: no hace falta cerrojo.
_relevos: dict[tuple[str, str], int] = {}


def _relevar(token: str, nombre: str) -> int:
    clave = (token, nombre)
    numero = _relevos.get(clave, 0) + 1
    _relevos[clave] = numero
    return numero


def _vigente(token: str, nombre: str, numero: int) -> bool:
    return _relevos.get((token, nombre)) == numero


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


# Cuánto se le perdona a un bucle no haber visto NUNCA su sesión conectada.
#
# El «antes la vio» de abajo existe porque el bucle arranca al montar la página
# y en las primeras vueltas el token puede no constar todavía. Pero como pase
# indefinido dejaba un agujero por el que se colaba la avería entera: si el
# navegador se iba antes de la primera comprobación —una recarga, una pestaña
# que se cierra al momento, el wifi que se cae—, ese bucle no había llegado a
# verlo conectado nunca, y entonces ninguna desconexión posterior lo mataba. En
# el arranque del 29/08/2026 se veía a las claras en el log: de dos sesiones
# fantasma, la que llegó a estar conectada murió a los dos avisos y la otra
# seguía mandando actualizaciones a nadie cientos de veces.
#
# Un minuto es de sobra: el token se registra al conectar el websocket, y el
# on_load que arranca el bucle llega POR ese websocket, así que en la práctica
# ya consta en la primera vuelta. Y cuando no se puede saber si está conectada
# —no hay registro que consultar— no se cuenta el plazo: ahí se sigue
# prefiriendo una sesión fantasma de más a cortarle el refresco a una viva.
GRACIA = 60.0


class Guardia:
    """Vigila UNA sesión. La da por perdida al desconectarse, y también si en
    su primer minuto de vida no llega a verla conectada ni una vez.

    Ese «antes la vio» importa: el bucle arranca al montar la página, y en las
    primeras vueltas el token puede no estar todavía registrado. Sin esa
    condición, cada bucle se suicidaría al nacer y ninguna pantalla se
    refrescaría nunca. Pero con la condición a secas, un bucle que no llegara a
    ver su sesión no moría jamás — de ahí el plazo (ver GRACIA).
    """

    def __init__(self, token: str, nombre: str = "", numero: int = 0):
        self._token = token
        self._nombre = nombre
        self._numero = numero
        self._vista = False
        self._nacido = time.monotonic()

    @property
    def token(self) -> str:
        return self._token

    def sigue(self) -> bool:
        # Ha arrancado otro bucle igual para esta misma sesión —una reconexión
        # relanza los on_load—: manda el nuevo y este sobra. Se mira ANTES que
        # la conexión, porque en ese momento la sesión está viva y por ahí no
        # se distinguiría que hay dos girando.
        if self._nombre and not _vigente(self._token, self._nombre, self._numero):
            return False
        estado = conectada(self._token)
        if estado is None:
            return True
        if estado:
            self._vista = True
            return True
        # Desconectada: se apaga si se la llegó a ver, y también si ya se le
        # dio su plazo de cortesía sin haberla visto nunca.
        if self._vista or time.monotonic() - self._nacido > GRACIA:
            self._olvidar()
            return False
        return True

    def _olvidar(self) -> None:
        """Borra el apunte de este bucle al apagarse, para que el registro no
        crezca sin fin. Solo si sigue siendo el vigente: si no, el apunte ya es
        de un relevo más nuevo y no hay que tocarlo."""
        if self._nombre and _vigente(self._token, self._nombre, self._numero):
            _relevos.pop((self._token, self._nombre), None)

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

    El NOMBRE del bucle se compone del State y de la función que llama, sin
    tener que pasarlo: junto al token identifica «este bucle, en esta sesión»,
    que es lo que permite que un arranque nuevo releve al anterior en vez de
    sumarse a él (ver _relevos). La función se saca del marco de quien llama
    porque los dieciséis bucles que hay ya llamaban a `guardia(self)` a secas,
    y hacerles pasar su propio nombre era pedir que alguien se lo dejara justo
    en el que importa.

    El State va DELANTE porque nueve bucles distintos se llaman `sync_loop` y
    sin él compartían clave, matándose entre ellos — ver el comentario largo
    de _relevos.

    Sin token no se releva a nadie: todas las sesiones que no lo tengan
    compartirían clave y se apagarían unas a otras.
    """
    marco = inspect.currentframe()
    quien = marco.f_back.f_code.co_name if marco and marco.f_back else ""
    async with estado:
        try:
            token = estado.router.session.client_token
        except Exception:
            token = ""
    if not token or not quien:
        return Guardia(token)
    # `estado.__class__` y NO `type(estado)`: dentro de un bucle de fondo, el
    # `self` que llega aqui no es el State, es el StateProxy con el que Reflex
    # lo envuelve (ver reflex/state.py, "For background tasks, proxy the
    # state"). `type()` mira el objeto de verdad y devuelve "StateProxy" para
    # todos por igual; `__class__` lo reenvia al State envuelto, que es de
    # quien queremos el nombre. Con `type()`, los nueve `sync_loop` volvian a
    # compartir la clave `(token, "StateProxy.sync_loop")` y a matarse entre
    # ellos: justo la averia que este nombre existe para evitar.
    nombre = f"{estado.__class__.__name__}.{quien}"
    return Guardia(token, nombre, _relevar(token, nombre))
