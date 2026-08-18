"""
Vista «Accesorios»: lo que se enciende y se apaga pero no es una luz — el
ventilador de techo, la tele, un enchufe.

Comparten colección y mecánica con las luces (ver domains/nodes/store.ASPECTOS):
de ahí les viene gratis salir en el plano, en los accesos rápidos del Resumen,
en las automatizaciones y en la paleta de comandos. Lo que cambia es qué son, y
por eso tienen su propia pestaña en vez de aparecer entre las bombillas.

Casi todos se accionan por mando, así que el formulario viene ya puesto en
«por mando» — a diferencia del de Luces, que viene en «por relé».
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from .. import theme
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input
from ..components.node_select import node_select
from .lights import (
    _aspecto_select, _kind_select, _light_card, _modo_mando_select,
    _room_select, _tecla_select,
)


def _add_aparato_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Añadir accesorio", size="2",
                      variant="surface", color_scheme="cyan"),
        ),
        form_dialog_content(
            icon="toggle-right",
            title="Nuevo accesorio",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Ventilador del salón")),
                    field("Qué es", _aspecto_select(default_value="ventilador")),
                    field("Cómo se enciende", _kind_select(default_value="mando")),
                    field("Teclas del mando", _modo_mando_select(default_value="dos")),
                    field("Tecla de encender · o la única si es de una sola",
                          _tecla_select("btn_on", "Tecla de encender")),
                    field("Tecla de apagar · se ignora si es de una sola",
                          _tecla_select("btn_off", "Tecla de apagar")),
                    # Los de relé siguen siendo posibles (un enchufe con relé),
                    # así que el nodo y el pin se quedan disponibles.
                    field("Nodo (solo si es por relé)", node_select()),
                    field("Pin GPIO o señal MQTT (solo si es por relé)",
                          styled_input(name="pin", placeholder="22 · enchufe_salon")),
                    field("Estancia", _room_select()),
                    dialog_footer(confirm_label="Añadir", color_scheme="cyan"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_light,
                reset_on_submit=True,
            ),
        ),
    )


def accesorios_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("ACCESORIOS", size="1", color=theme.MUTED,
                    letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_aparato_dialog(),
            width="100%", align="center", wrap="wrap",
        ),
        rx.text(
            "El ventilador, la tele, un enchufe: se encienden y se apagan igual "
            "que una luz, casi siempre con una tecla de un mando. Salen también "
            "en el plano, en el Resumen y en las automatizaciones.",
            size="1", color=theme.MUTED,
        ),
        rx.cond(
            NodesState.accesorios.length() == 0,
            rx.text("Aún no hay accesorios dados de alta.", size="1",
                    color=theme.MUTED, italic=True),
            rx.vstack(
                rx.foreach(NodesState.accesorios, _light_card),
                spacing="2", width="100%",
            ),
        ),
        spacing="3",
        width="100%",
        align="start",
        padding_bottom="6",
    )
