"""La fila de modos de la casa, fija arriba del Resumen.

Solo pinta. Poner un modo lo resuelve ModesState, que además comprueba el
permiso — el botón puede estar a la vista y el evento seguir siendo invocable
desde fuera.

DOS FORMAS SEGÚN EL ANCHO, y es el mismo árbol de componentes con CSS distinto,
no dos versiones que haya que mantener a la par:

- En el móvil, cuadrícula de 2×2 con el icono y nada más. El nombre y el «qué
  lanza» se esconden ahí: en una pantalla de teléfono, cuatro botones con dos
  líneas de texto cada uno se comían el arranque del Resumen, y el Resumen es
  para ver el estado de la casa, no para leer qué hace cada modo. Eso se lee
  donde se decide, que es el editor (Ajustes → Modos), y ahí sale entero.
- De tablet en adelante, la fila de siempre con nombre y resumen.
"""
import reflex as rx

from .. import theme
from ....domains.modes.state import ModesState
from ....domains.auth.state import AuthState


def _boton_modo(modo: rx.Var) -> rx.Component:
    activo = modo["activo"]
    return rx.vstack(
        rx.cond(
            ModesState.aplicando == modo["id"],
            rx.spinner(size="2"),
            # .to(str) en el icono y en el color: dentro de un foreach el valor
            # de una clave es una Var de tipo Any, y rx.icon exige una cadena.
            # Es el mismo apaño que usa el plano con floor_icon.
            rx.icon(modo["icono"].to(str), size=20,
                    color=rx.cond(activo, modo["color"].to(str), theme.MUTED)),
        ),
        # Los dos textos desaparecen en el móvil. Se esconden con CSS en vez de
        # montar otro árbol con rx.cond: así el botón es UNO, y lo que cambia es
        # cómo se ve.
        rx.text(modo["nombre"], size="1", weight="bold",
                color=rx.cond(activo, theme.TEXT, theme.MUTED),
                white_space="nowrap",
                display=["none", "none", "block"]),
        rx.text(modo["resumen"], size="1", color=theme.MUTED,
                white_space="nowrap",
                style={"font-size": "0.65rem", "opacity": "0.75"},
                display=["none", "none", "block"]),
        on_click=ModesState.poner(modo["id"]),
        cursor="pointer",
        spacing="1", align="center", justify="center",
        # En el móvil, cuadrado justo: 52 px es más pequeño que el botón con
        # texto de antes y sigue por encima de los 44 px que hace falta para
        # acertarle con el dedo sin pelearse.
        padding=["0", "0", "10px 16px"],
        width=["52px", "52px", "auto"],
        height=["52px", "52px", "auto"],
        min_width=["52px", "52px", "96px"],
        border_radius="12px",
        flex_shrink="0",
        background=rx.cond(activo, theme.alpha(theme.ACCENT, 0.12), theme.BG_CARD),
        border=rx.cond(
            activo,
            f"1px solid {theme.alpha(theme.ACCENT, 0.55)}",
            f"1px solid {theme.BORDER}",
        ),
        transition="background 0.15s ease, border-color 0.15s ease",
        _hover={"background": theme.BG_CARD_HOVER},
    )


def fila_modos() -> rx.Component:
    """Fija arriba del Resumen: en qué está la casa y cómo cambiarlo de un
    toque. Se le enseña a quien puede armar — un modo puede armar la casa, así
    que si no puede armar tampoco tiene sentido ofrecerle esto."""
    return rx.cond(
        AuthState.puede_armar,
        rx.vstack(
            rx.hstack(
                rx.text("Modo de la casa", size="1", weight="bold",
                        color=theme.MUTED, letter_spacing="0.08em",
                        text_transform="uppercase"),
                rx.cond(
                    ModesState.activo == "",
                    rx.text("sin poner", size="1", color=theme.MUTED),
                ),
                align="center", spacing="2",
            ),
            rx.box(
                rx.hstack(
                    rx.foreach(ModesState.modos, _boton_modo),
                    spacing="2", align="stretch",
                    # En el móvil, UNA fila de cuatro y centrada. Cuatro
                    # cuadrados de 52 px con sus huecos son 232 px, así que
                    # caben en cualquier teléfono sin apretar.
                    #
                    # Las columnas son de ancho fijo y no `1fr`: estirarlas al
                    # ancho de la pantalla daría cuatro botones enormes, que es
                    # lo contrario de lo que se busca.
                    display=["grid", "grid", "flex"],
                    grid_template_columns=["repeat(4, 52px)", "repeat(4, 52px)",
                                           "none"],
                    justify_content=["center", "center", "start"],
                ),
                # De tablet en adelante la fila puede no caber y rueda ella, no
                # la página. En el móvil ya no hace falta: la cuadrícula cabe.
                width="100%",
                overflow_x=["visible", "visible", "auto"],
                padding_bottom="4px",
            ),
            # En el móvil el bloque entero va centrado, rótulo incluido, para que
            # la fila de cuatro no quede colgando a la izquierda.
            # `align` no admite una lista como el resto de props: exige
            # rx.breakpoints (es un Literal con valores cerrados).
            spacing="2", width="100%",
            align=rx.breakpoints(initial="center", md="start"),
            on_mount=ModesState.on_load,
        ),
    )
