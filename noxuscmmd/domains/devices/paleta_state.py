"""
Paleta de comandos: escribir dos letras y hacer cualquier cosa de la casa.

Se abre con Ctrl+K (o ⌘K) y con la lupa de la barra superior. Es una lista de
comandos concretos, filtrada mientras se escribe.

NO TIENE EJECUTOR PROPIO, y eso es lo importante del diseño: todo lo que hace
pasa por `automations.actions.dispatch`, el mismo despachador que usan las
automatizaciones y los modos de casa. Así, cuando cambie lo que significa
«encender una luz» —o se añada una acción nueva—, la paleta cambia con ello sin
enterarse. Un segundo camino que hiciera lo mismo por su cuenta es como acaban
divergiendo dos comportamientos que deberían ser uno.

Lo que se ofrece son comandos YA CONCRETOS («Encender Salón», «Apagar Salón»),
no acciones con parámetros a rellenar. Una paleta que te pregunta cosas después
de elegir deja de ser rápida, que es su única razón de existir.

Los permisos se comprueban al EJECUTAR, no al listar. A propósito: la lista sale
igual para todos, y quien no puede hacer algo se lleva la negativa del propio
manejador (ver auth/permisos.py). Filtrar la lista por rol sería otro sitio más
donde acordarse de qué puede quién, y esconder un botón nunca ha sido un permiso.
"""
import reflex as rx

from .comandos import CAPACIDAD, TOPE, buscar, comandos
from ..auth import permisos
from ..automations import actions
from ..modes import state as modes_state
from ..security import audit, logs


class PaletaState(rx.State):
    abierta: bool = False
    busqueda: str = ""
    # Se construye al abrir y no en cada tecla: recorre cuatro ficheros, y
    # hacerlo con cada letra que se escribe sería leer el disco por pulsación.
    _todos: list[dict] = []

    @rx.event
    def abrir(self):
        self.busqueda = ""
        self._todos = comandos()
        self.abierta = True

    @rx.event
    def set_abierta(self, abierta: bool):
        """Por aquí pasa el cierre con Esc y el de pulsar fuera. Sin esto, el
        estado se queda creyendo que la paleta sigue abierta y no se vuelve a
        abrir hasta recargar."""
        self.abierta = abierta
        if not abierta:
            self.busqueda = ""

    @rx.event
    def set_busqueda(self, valor: str):
        self.busqueda = valor

    @rx.event
    async def ejecutar(self, comando_id: str):
        """Hace lo que diga el comando. Cierra la paleta antes de empezar: una
        acción puede tardar (un SSH, un pulso de puerta) y dejar el diálogo
        abierto mientras da la sensación de que no se ha enterado."""
        comando = next((c for c in self._todos if c["id"] == comando_id), None)
        self.abierta = False
        if comando is None:
            return
        paso = comando["paso"]
        tipo = paso["type"]

        if tipo == "vista":
            from ...ui.dashboard.state import DashboardState
            panel = await self.get_state(DashboardState)
            panel.active_view = paso["target"]
            return

        if tipo == "modo":
            if (no := await permisos.denegar(self, permisos.ARMAR)):
                return no
            quien = await audit.usuario_de(self)
            ok, resumen = await modes_state.aplicar(paso["target"], quien)
            if ok:
                return rx.toast.success(f"{comando['etiqueta']} · {resumen}",
                                        position="top-center")
            return rx.toast.error(f"{comando['etiqueta']}: {resumen}",
                                  position="top-center", duration=10000)

        # Todo lo demás son pasos del despachador de siempre. El permiso se pide
        # según la familia: encender una luz no es lo mismo que armar la casa.
        capacidad = CAPACIDAD.get(tipo, permisos.AJUSTES)
        if (no := await permisos.denegar(self, capacidad)):
            return no
        try:
            resumen = await actions.dispatch(paso)
        except Exception as e:
            return rx.toast.error(f"{comando['etiqueta']}: {e}",
                                  position="top-center", duration=10000)
        await audit.registrar(self, logs.SISTEMA, "PALETA_COMANDO",
                              f"{comando['etiqueta']} · {resumen}")
        return rx.toast.success(resumen or comando["etiqueta"],
                                position="top-center")

    @rx.var
    def resultados(self) -> list[dict]:
        """Los que casan con lo escrito. Todas las palabras tienen que aparecer,
        en cualquier orden: así «apagar salon» encuentra «Apagar Salón» sin que
        importe cómo se teclee."""
        if not self.busqueda.strip():
            # Sin escribir nada se ofrecen los primeros del catálogo, que es
            # mejor que una lista vacía: la paleta se abre y ya hay algo.
            encontrados = self._todos[:TOPE]
        else:
            encontrados = buscar(self.busqueda, self._todos)[:TOPE]
        return [{k: c[k] for k in ("id", "etiqueta", "familia", "icono")}
                for c in encontrados]

    @rx.var
    def sin_resultados(self) -> bool:
        return self.abierta and len(self.resultados) == 0
