"""El arranque del panel se agrupa en un único evento de websocket.

Son dobles puros: no se carga ningún dominio ni se crea ninguna tarea real. Se
comprueba la coordinación que evita que los toques esperen tras los on_load.
"""
import asyncio

from reflex.event import BACKGROUND_TASK_MARKER, EventHandler, EventSpec

from tests.comun import Caso

from noxuscmmd.core import entrada as entrada_modulo
from noxuscmmd.core.entrada import ejecutar_eventos_entrada
from noxuscmmd.ui.dashboard.state import DashboardState


class _EstadoSync:
    pass


class _EstadoAsync:
    pass


class _EstadoGenerador:
    pass


class _EstadoError:
    pass


class _EstadoGeneradorAsync:
    pass


class _EstadoFondoDirecto:
    pass


class _RaizFalsa:
    estados = {
        "estado.sync": _EstadoSync,
        "estado.async": _EstadoAsync,
        "estado.generador": _EstadoGenerador,
        "estado.error": _EstadoError,
        "estado.generador_async": _EstadoGeneradorAsync,
        "estado.fondo_directo": _EstadoFondoDirecto,
    }

    @classmethod
    def get_class_substate(cls, ruta):
        return cls.estados[ruta]


class _SesionFalsa:
    client_token = "token-prueba"


class _RouterFalso:
    session = _SesionFalsa()


class _SubestadoFalso:
    def __init__(self, nombre, llamadas):
        self.nombre = nombre
        self.llamadas = llamadas
        self.router_data = {"pathname": "/panel"}


class _EntradaFalsa:
    router = _RouterFalso()

    def __init__(self, raiz, estados):
        self.raiz = raiz
        self.estados = estados

    def _get_root_state(self):
        return self.raiz

    async def get_state(self, clase):
        return self.estados[clase]


def _handler(funcion, estado="evento.devuelto"):
    return EventHandler(fn=funcion, state_full_name=estado)


def _fondo(funcion, estado="evento.fondo"):
    setattr(funcion, BACKGROUND_TASK_MARKER, True)
    return _handler(funcion, estado)


def _nombre(evento):
    manejador = evento.handler if isinstance(evento, EventSpec) else evento
    return manejador.fn.__name__


def ejecutar() -> list[Caso]:
    c = Caso("Entrada agrupada del panel")
    llamadas = []

    def cliente_uno(_estado):
        pass

    def cliente_dos(_estado):
        pass

    def cliente_tres(_estado):
        pass

    def cliente_cuatro(_estado):
        pass

    def cliente_cinco(_estado):
        pass

    async def fondo_uno(_estado):
        pass

    async def fondo_con_fallo(_estado):
        pass

    async def fondo_dos(_estado):
        pass

    async def fondo_directo(estado):
        # Si el orquestador lo invocase como un manejador normal, esta marca
        # delataría la regresión (en producción sería un bucle que no termina).
        llamadas.append(("fondo_directo_invocado", estado.nombre))

    evento_cliente_uno = _handler(cliente_uno)
    evento_cliente_dos = _handler(cliente_dos)()
    evento_cliente_tres = _handler(cliente_tres)
    evento_cliente_cuatro = _handler(cliente_cuatro)()
    evento_cliente_cinco = _handler(cliente_cinco)
    evento_fondo_uno = _fondo(fondo_uno)
    evento_fondo_falla = _fondo(fondo_con_fallo)()
    evento_fondo_dos = _fondo(fondo_dos)
    evento_fondo_directo = _fondo(fondo_directo, "estado.fondo_directo")

    def manejador_sync(estado):
        llamadas.append(("sync", estado.nombre))
        return [evento_cliente_uno, evento_fondo_uno]

    async def manejador_async(estado):
        llamadas.append(("async", estado.nombre))
        return evento_cliente_dos

    def manejador_generador(estado):
        llamadas.append(("generador", estado.nombre))
        yield evento_fondo_falla
        yield evento_cliente_tres
        return evento_cliente_cuatro

    def manejador_error(estado):
        llamadas.append(("error", estado.nombre))
        raise RuntimeError("fallo aislado")

    async def manejador_generador_async(estado):
        llamadas.append(("generador_async", estado.nombre))
        yield [None, evento_cliente_cinco, evento_fondo_dos]

    manejadores = [
        _handler(manejador_sync, "estado.sync"),
        _handler(manejador_async, "estado.async"),
        _handler(manejador_generador, "estado.generador"),
        _handler(manejador_error, "estado.error"),
        _handler(manejador_generador_async, "estado.generador_async"),
        evento_fondo_directo,
    ]
    estados = {
        clase: _SubestadoFalso(nombre, llamadas)
        for nombre, clase in _RaizFalsa.estados.items()
    }
    entrada = _EntradaFalsa(_RaizFalsa(), estados)
    lanzados = []

    def lanzar(raiz, evento):
        if evento.name.endswith("fondo_con_fallo"):
            raise TypeError("API interna simulada")
        lanzados.append((raiz, evento))

    bucle = asyncio.new_event_loop()
    try:
        cliente = bucle.run_until_complete(
            ejecutar_eventos_entrada(entrada, manejadores, lanzar_fondo=lanzar)
        )
    finally:
        bucle.close()

    c.revisar(
        "ejecuta sync, async y ambos generadores sobre su propio State",
        llamadas,
        [
            ("sync", "estado.sync"),
            ("async", "estado.async"),
            ("generador", "estado.generador"),
            ("error", "estado.error"),
            ("generador_async", "estado.generador_async"),
        ],
    )
    c.revisar(
        "solo lanza en servidor los fondos que acepta la API",
        [evento.name.rsplit(".", 1)[-1] for _, evento in lanzados],
        ["fondo_uno", "fondo_dos", "fondo_directo"],
    )
    c.revisar(
        "los eventos de cliente conservan orden y el fondo fallido vuelve atrás",
        [_nombre(evento) for evento in cliente],
        [
            "cliente_uno",
            "cliente_dos",
            "fondo_con_fallo",
            "cliente_tres",
            "cliente_cuatro",
            "cliente_cinco",
        ],
    )
    c.revisar(
        "los fondos usan la raíz, el token y la ruta de la sesión",
        [
            (raiz is entrada.raiz, evento.token, evento.router_data)
            for raiz, evento in lanzados
        ],
        [
            (True, "token-prueba", {"pathname": "/panel"}),
            (True, "token-prueba", {"pathname": "/panel"}),
            (True, "token-prueba", {"pathname": "/panel"}),
        ],
    )
    puerta = Caso("La entrada no carga la casa sin permiso")
    llamadas_entrada = []

    async def ejecutar_falso(_estado, manejadores, lanzar_fondo=None):
        llamadas_entrada.append([
            manejador.fn.__name__ for manejador in manejadores
        ])
        return []

    class _AuthFalsa:
        def __init__(self, acceso):
            self.acceso = acceso
            # Los campos que mira la entrada para redirigir a una tablet de habitación
            self._rol = "familia"
            self._id = ""

        def _ve(self, _capacidad):
            return self.acceso

    class _DashboardFalso:
        def __init__(self, acceso):
            self.auth = _AuthFalsa(acceso)

        async def get_state(self, _clase):
            return self.auth

    original = entrada_modulo.ejecutar_eventos_entrada
    entrada_modulo.ejecutar_eventos_entrada = ejecutar_falso
    bucle = asyncio.new_event_loop()
    try:
        bucle.run_until_complete(
            DashboardState.entrar.fn(_DashboardFalso(False)))
        puerta.revisar(
            "sin acceso solo identifica, canjea y vigila",
            llamadas_entrada,
            [["identificar", "canjear_de_la_url", "vigilar_acceso"]],
        )

        llamadas_entrada.clear()
        bucle.run_until_complete(
            DashboardState.entrar.fn(_DashboardFalso(True)))
        puerta.revisar("con acceso continúa con el resto de cargas",
                       len(llamadas_entrada), 2)
        puerta.cierto("la carga administrativa queda después de la puerta",
                      "on_load" in llamadas_entrada[1])
    finally:
        bucle.close()
        entrada_modulo.ejecutar_eventos_entrada = original

    return [c, puerta]
