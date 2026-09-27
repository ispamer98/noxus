"""Arranque agrupado del panel sin pasear cada evento por el navegador.

Reflex encadena en el cliente los eventos que devuelve un manejador. Durante
la entrada eso convertía cada ``on_load`` y cada bucle que este arrancaba en un
viaje de red separado. Aquí se ejecutan los manejadores iniciales sobre sus
estados reales y solo se devuelven al cliente los eventos que de verdad tienen
que vivir allí (scripts, avisos, redirecciones y eventos normales).
"""
import inspect
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from reflex.event import Event, EventHandler, EventSpec, fix_events
from reflex.state import BaseState


LanzadorFondo = Callable[[BaseState, Event], object]


def _lanzar_fondo(raiz: BaseState, evento: Event) -> object:
    """Usa exactamente el camino interno con el que Reflex arranca un fondo."""
    from reflex.utils.prerequisites import get_app

    tarea = get_app().app._process_background(raiz, evento)
    if tarea is None:
        raise TypeError("Reflex no reconoció el evento como tarea de fondo")
    return tarea


def _eventos(valor: Any) -> Iterator[EventHandler | EventSpec]:
    """Aplana lo que puede devolver o producir un manejador de Reflex."""
    if valor is None:
        return
    if isinstance(valor, list):
        for elemento in valor:
            yield from _eventos(elemento)
        return
    if not isinstance(valor, (EventHandler, EventSpec)):
        raise TypeError(f"evento de entrada inesperado: {type(valor).__name__}")
    yield valor


async def _resultados(
    manejador: EventHandler,
    estado: BaseState,
) -> AsyncIterator[Any]:
    """Invoca los cuatro tipos de manejador igual que ``_process_event``."""
    resultado = manejador.fn(estado)
    if inspect.isawaitable(resultado):
        resultado = await resultado

    if inspect.isasyncgen(resultado):
        async for evento in resultado:
            yield evento
        return

    if inspect.isgenerator(resultado):
        while True:
            try:
                yield next(resultado)
            except StopIteration as fin:
                if fin.value is not None:
                    yield fin.value
                return

    yield resultado


def _es_fondo(evento: EventHandler | EventSpec) -> bool:
    manejador = evento.handler if isinstance(evento, EventSpec) else evento
    return manejador.is_background


def _entregar_evento(
    evento: EventHandler | EventSpec,
    raiz: BaseState,
    token: str,
    router_data: dict[str, Any],
    lanzar: LanzadorFondo,
    para_cliente: list[EventHandler | EventSpec],
    origen: str,
) -> None:
    """Lanza un fondo o conserva para el cliente lo que no pueda lanzar."""
    if not _es_fondo(evento):
        para_cliente.append(evento)
        return
    try:
        fijado = fix_events(
            [evento],
            token=token,
            router_data=router_data,
        )[0]
        lanzar(raiz, fijado)
    except Exception as error:
        # Si cambia una API interna de Reflex, conserva el camino antiguo: el
        # navegador reenviará el evento al backend en vez de perderlo.
        print(
            f"⚠️ No se pudo lanzar en servidor {origen}; "
            f"se devuelve al navegador: {error}"
        )
        para_cliente.append(evento)


async def ejecutar_eventos_entrada(
    estado: BaseState,
    manejadores: list[EventHandler],
    lanzar_fondo: LanzadorFondo | None = None,
) -> list[EventHandler | EventSpec]:
    """Ejecuta en servidor los manejadores iniciales de una sesión.

    Cada manejador corre sobre la instancia de su propio State. Los eventos de
    fondo se entregan directamente a Reflex; el resto vuelve en el mismo orden
    para que el navegador procese lo que solo puede hacer él. Un fallo queda
    aislado al manejador o evento afectado para no romper toda la entrada.

    ``lanzar_fondo`` es sustituible para probar esta coordinación sin crear
    tareas ni acceder a la aplicación real.
    """
    lanzar = lanzar_fondo or _lanzar_fondo
    raiz = estado._get_root_state()
    token = estado.router.session.client_token
    para_cliente: list[EventHandler | EventSpec] = []

    for manejador in manejadores:
        nombre = getattr(manejador.fn, "__qualname__", repr(manejador.fn))
        try:
            clase = raiz.__class__.get_class_substate(manejador.state_full_name)
            propio = await estado.get_state(clase)
            # La lista contiene también fondos directos. Invocar su función
            # aquí bloquearía la entrada hasta que terminase su bucle.
            if manejador.is_background:
                _entregar_evento(
                    manejador,
                    raiz,
                    token,
                    propio.router_data,
                    lanzar,
                    para_cliente,
                    nombre,
                )
                continue
            async for resultado in _resultados(manejador, propio):
                for evento in _eventos(resultado):
                    _entregar_evento(
                        evento,
                        raiz,
                        token,
                        propio.router_data,
                        lanzar,
                        para_cliente,
                        nombre,
                    )
        except Exception as error:
            print(f"⚠️ Error en el manejador de entrada {nombre}: {error}")

    return para_cliente
