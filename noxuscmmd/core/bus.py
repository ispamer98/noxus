"""Avisar a los bucles de pantalla de que algo cambió, en vez de que lo
pregunten cada medio segundo.

Por qué existe. Las pantallas se refrescan con un bucle por sesión que releía
el JSON cada 0,5 s (`SecurityState.sync_loop`, `NodesState.sync_loop`). Esa
lectura no es barata: `nodes/store._read()` abre el fichero, toma el cerrojo,
hace `json.loads` y pasa `_apply_defaults`, que recorre nodos, sensores, luces
y botones y encima sincroniza los planos. Con dos pestañas abiertas eso salían
cuatro normalizaciones completas por segundo sin que hubiera cambiado nada, y
el estado de la casa cambia unas cuantas veces al minuto, no dos veces por
segundo.

Ahora quien ESCRIBE avisa (`publicar`) y quien pinta espera ese aviso. Los
avisos son la señal, no el dato: aquí no viaja ningún valor, solo un contador
por tema. El que despierta vuelve a leer el fichero, que sigue siendo la única
fuente de verdad — así un aviso perdido o de más no puede descuadrar nada.

El respaldo. La espera SIEMPRE tiene un tope (`respaldo`), así que si alguien
escribiera esos JSON desde fuera de este proceso —otro worker, un script, una
edición a mano— el cambio se ve igual, con el retraso del tope en vez de al
instante. Hoy el backend es un solo proceso (granian sin workers extra) y todos
los que escriben están dentro, pero eso es una circunstancia, no una garantía,
y no merece la pena montarlo sobre ella.

Se publica desde HILOS: los callbacks de MQTT llegan en el hilo de paho y los
setters se llaman con `asyncio.to_thread`. Por eso el contador va con un cerrojo
de threading y el despertar se pide con `call_soon_threadsafe`, que es lo único
que se puede tocar de un loop desde fuera de su hilo.

Uso, sustituyendo el `sleep` del bucle:

    aviso = bus.Aviso(bus.SENSORES, bus.ARMADO)
    guardia = await sesiones.guardia(self)
    while True:
        ...
        if not await aviso.espera(guardia, 3.0):
            return          # el navegador se fue: el bucle se va con él
"""
import asyncio
import threading

# Temas. Uno por dato que se mira en vivo; el nombre es solo una clave.
SENSORES = "nodes.sensor_states"   # sensores, puertas y luces por MQTT
EQUIPOS = "nodes.host_online"      # el ping a los equipos extra
ARMADO = "security.armado"         # el sistema de alarma, armado o no
ENTIDADES = "entities.changed"     # altas, ediciones y bajas de configuración
DISPOSITIVOS = "auth.dispositivos"  # roles, altas, bajas e invitaciones

# Cuánto se agrupa una ráfaga. Un aluvión de mensajes MQTT no debe convertirse
# en un aluvión de relecturas del JSON: si el aviso anterior fue hace menos de
# esto, se espera a que se cumpla y se atiende todo de una vez.
MINIMO = 0.3

# Algunos selectores no interrumpen una espera larga de forma fiable cuando el
# aviso llega desde un hilo externo (MQTT, pings). Este margen es el respaldo:
# el contador sigue siendo la fuente de verdad y evita que una pantalla tarde
# todo su `respaldo` en reflejar un cambio.
RESPALDO_HILO = 0.5

_cerrojo = threading.Lock()
_versiones: dict[str, int] = {}
_loop: asyncio.AbstractEventLoop | None = None
_evento: asyncio.Event | None = None


def version(*temas: str) -> tuple[int, ...]:
    """El contador de cada tema, para comparar después."""
    with _cerrojo:
        return tuple(_versiones.get(t, 0) for t in temas)


def publicar(tema: str) -> None:
    """«Esto ha cambiado». Se llama DESPUÉS de escribir, nunca antes: quien
    despierte va a leer el fichero, y tiene que encontrarse el valor nuevo.

    Vale llamarla desde cualquier hilo y sin que haya loop ninguno (en las
    pruebas, o en la migración que corre al importar): entonces solo sube el
    contador, y el que espere lo verá al comparar.
    """
    with _cerrojo:
        _versiones[tema] = _versiones.get(tema, 0) + 1
        loop, evento = _loop, _evento
    if loop is None or evento is None:
        return
    try:
        loop.call_soon_threadsafe(_despertar)
    except RuntimeError:
        # El loop se está cerrando (apagando el servicio). Nadie a quien avisar.
        pass


def _despertar() -> None:
    """Suelta a todos los que esperan y deja un evento nuevo para la siguiente
    ronda. Corre SIEMPRE en el hilo del loop, que es lo que hace seguro tocar
    aquí un asyncio.Event."""
    global _evento
    with _cerrojo:
        viejo, _evento = _evento, asyncio.Event()
    if viejo is not None:
        viejo.set()


async def esperar(temas: tuple[str, ...], vistas: tuple[int, ...],
                  respaldo: float) -> tuple[int, ...]:
    """Duerme hasta que cambie alguno de `temas` o se agote `respaldo`.

    Devuelve los contadores del momento en que despierta: el que llama los
    guarda y los pasa en la vuelta siguiente. Comparar contadores en vez de
    fiarse del evento es lo que impide perder un aviso que llegue entre dos
    esperas —mientras el bucle estaba leyendo el fichero, por ejemplo—.
    """
    global _loop, _evento
    with _cerrojo:
        if _loop is None:
            _loop = asyncio.get_running_loop()
        if _evento is None:
            _evento = asyncio.Event()
        loop = _loop

    plazo = loop.time() + respaldo
    while True:
        with _cerrojo:
            ahora = tuple(_versiones.get(t, 0) for t in temas)
            evento = _evento
        if ahora != vistas:
            return ahora
        resto = plazo - loop.time()
        if resto <= 0:
            return ahora
        try:
            await asyncio.wait_for(evento.wait(), min(resto, RESPALDO_HILO))
        except (asyncio.TimeoutError, TimeoutError):
            # También mira el contador cada medio segundo. Normalmente el
            # evento despierta antes; esto cubre callbacks externos que el
            # selector haya dejado encolados sin despertar su poll interno.
            continue
        # Si despertó por un tema que no es el nuestro, la vuelta del bucle
        # vuelve a dormir con lo que quede de plazo.


class Aviso:
    """La espera de UN bucle, con su memoria de lo que ya vio."""

    def __init__(self, *temas: str, minimo: float = MINIMO):
        self._temas = temas
        self._vistas = version(*temas)
        self._minimo = minimo
        self._ultimo: float | None = None

    async def espera(self, guardia, respaldo: float) -> bool:
        """Espera el próximo cambio y dice si merece la pena seguir.

        Devuelve False cuando el navegador de esta sesión ya no está, igual que
        `sesiones.espera`: es lo que apaga el bucle (ver core/sesiones.py).
        """
        loop = asyncio.get_running_loop()
        if self._ultimo is not None:
            resto = self._minimo - (loop.time() - self._ultimo)
            if resto > 0:
                await asyncio.sleep(resto)
        self._vistas = await esperar(self._temas, self._vistas, respaldo)
        self._ultimo = loop.time()
        return guardia.sigue()


def _reiniciar_para_pruebas() -> None:
    """Deja el bus como recién importado. Solo lo usan las pruebas, que crean
    un loop por caso: un asyncio.Event guardado de un loop ya cerrado no vale
    para el siguiente."""
    global _loop, _evento
    with _cerrojo:
        _versiones.clear()
        _loop = None
        _evento = None
