"""La fila de modos de la casa, fija bajo el estado de la casa en el Resumen.

Solo pinta. Poner un modo lo resuelve ModesState, que además comprueba el
permiso — el botón puede estar a la vista y el evento seguir siendo invocable
desde fuera.

DOS FORMAS SEGÚN EL ANCHO, y es el mismo árbol de componentes con CSS distinto
(assets/nx.css, .nx-modes), no dos versiones que haya que mantener a la par:

- En el móvil, cuatro botones iguales con el icono y nada más. El nombre y el
  «qué lanza» se esconden ahí: en una pantalla de teléfono, cuatro botones con
  texto se comían el arranque del Resumen, y el Resumen es para ver el estado
  de la casa, no para leer qué hace cada modo. Eso se lee donde se decide, que
  es el editor (Ajustes → Modos), y ahí sale entero.
- De tablet en adelante, chips con icono y nombre.
"""
import reflex as rx

from .. import theme
from ....domains.modes.state import ModesState
from ....domains.auth.state import AuthState


def _boton_modo(modo: rx.Var) -> rx.Component:
    activo = modo["activo"]
    return rx.el.button(
        rx.cond(
            ModesState.aplicando == modo["id"],
            rx.spinner(size="2"),
            # .to(str) en el icono y en el color: dentro de un foreach el valor
            # de una clave es una Var de tipo Any, y rx.icon exige una cadena.
            # Es el mismo apaño que usa el plano con floor_icon.
            rx.icon(modo["icono"].to(str), size=18,
                    color=rx.cond(activo, modo["color"].to(str), theme.MUTED)),
        ),
        # El nombre desaparece en el móvil (nx.css): cuatro botones con texto
        # se comían el arranque del Resumen. Lo que lanza cada modo va en el
        # title, y entero en el editor (Ajustes → Modos), que es donde se decide.
        rx.el.span(modo["nombre"]),
        on_click=ModesState.poner(modo["id"]),
        class_name="nx-mode",
        custom_attrs={"data-activo": activo},
        title=modo["nombre"].to(str) + " — " + modo["resumen"].to(str),
        aria_label=modo["nombre"].to(str),
        aria_pressed=activo,
        type="button",
    )


def fila_modos() -> rx.Component:
    """Fija bajo el estado de la casa: en qué modo está y cómo cambiarlo de un
    toque. Se le enseña a quien puede armar — un modo puede armar la casa, así
    que si no puede armar tampoco tiene sentido ofrecerle esto."""
    return rx.cond(
        AuthState.puede_armar,
        rx.el.div(
            rx.el.span("Modo", class_name="nx-modes-label"),
            rx.foreach(ModesState.modos, _boton_modo),
            class_name="nx-modes",
            role="group",
            aria_label="Modo de la casa",
            on_mount=ModesState.on_load,
        ),
    )
