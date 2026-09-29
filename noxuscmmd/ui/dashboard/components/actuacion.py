"""
Forma de actuación de un elemento, IGUAL para puertas, luces y lo que venga:
un relé, dos relés o teclas de un mando. Un solo sitio para los selectores, de
modo que dar de alta cualquier elemento pregunta lo mismo y de la misma manera
(la lectura del formulario está en domains/nodes/state.actuacion_de_formulario).

Los bloques van siempre puestos y se rellena el que corresponda: el submit se
queda solo con los del tipo elegido, y así no hace falta sacar el formulario
entero al estado para esconder la mitad.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from .form_dialog import field, styled_input, styled_select, select_content


def selector_actuacion(name: str, default_value, etiqueta: str, verbos: tuple[str, str]) -> rx.Component:
    """«Cómo se acciona»: relé, dos relés o mando. `verbos` son los de la pareja
    de acciones del elemento: ("abrir", "cerrar") o ("encender", "apagar")."""
    a, b = verbos
    return styled_select(
        etiqueta,
        select_content(
            rx.select.item("Un relé (GPIO por SSH o MQTT)", value="rele"),
            rx.select.item(f"Dos relés: uno para {a} y otro para {b}", value="dos_reles"),
            rx.select.item("Por mando (infrarrojos / RF)", value="mando"),
        ),
        name=name,
        default_value=default_value,
    )


def campo_segundo_rele(default_value: str = "", verbo: str = "cerrar") -> rx.Component:
    return field(
        f"Pin / señal del 2º relé, el de {verbo} (solo con dos relés)",
        styled_input(name="pin2", default_value=default_value, placeholder="23 · segundo_rele"),
    )


def tecla_select(name: str, etiqueta: str, default_value=None) -> rx.Component:
    """Un solo desplegable con las teclas de TODOS los mandos, ya etiquetadas
    "Mando · Tecla". El mando se deduce de la tecla elegida (ver
    NodesState.teclas_de_mando)."""
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        etiqueta,
        select_content(
            rx.foreach(
                NodesState.teclas_de_mando,
                lambda t: rx.select.item(t["etiqueta"], value=t["valor"]),
            ),
        ),
        name=name,
        **kwargs,
    )


def campos_tecla_par(verbo_a: str, verbo_b: str, default_a=None, default_b=None) -> list[rx.Component]:
    return [
        field(f"Tecla de {verbo_a} (solo si es por mando)",
              tecla_select("btn_on", f"Tecla de {verbo_a}", default_a)),
        field(f"Tecla de {verbo_b} (solo si es por mando)",
              tecla_select("btn_off", f"Tecla de {verbo_b}", default_b)),
    ]
