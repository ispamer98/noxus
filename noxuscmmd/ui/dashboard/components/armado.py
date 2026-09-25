"""Avisos no modales del armado: impedimentos y cuenta atrás de salida.

Viven en la pila flotante común de dashboard.py para que aparezcan en cualquier
vista, abajo a la derecha y sin bloquear el resto del panel.
"""
import reflex as rx

from .. import theme
from ....domains.security.arming_state import ArmingState
from ....domains.nodes.state import NodesState


def _abierto(item: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("door-open", size=14, color=theme.WARNING, flex_shrink="0"),
        rx.text(item["nombre"], size="1", color=theme.TEXT),
        align="center", spacing="2", width="100%",
        padding="8px 10px", border_radius="8px",
        background=theme.alpha(theme.WARNING, 0.07),
        border=f"1px solid {theme.alpha(theme.WARNING, 0.22)}",
    )


def dialogo_armado() -> rx.Component:
    """Decisión de armado como panel no modal: informa sin secuestrar la UI."""
    return rx.cond(
        ArmingState.hay_dialogo,
        rx.el.section(
            rx.el.header(
                rx.hstack(
                    rx.icon("shield-alert", size=18, color=theme.WARNING),
                    rx.text("Esto impide armar", size="3", weight="bold",
                            color=theme.TEXT),
                    align="center", spacing="2",
                ),
                rx.el.button(
                    rx.icon("x", size=16),
                    on_click=ArmingState.cerrar,
                    class_name="nx-notice-close",
                    type="button",
                    aria_label="Cerrar",
                ),
                class_name="nx-notice-head",
            ),
            rx.text(
                "Si armas ahora, esto se queda sin vigilar.",
                size="1", color=theme.MUTED,
            ),
            rx.vstack(
                rx.foreach(ArmingState.abiertos, _abierto),
                spacing="1", width="100%", max_height="180px",
                overflow_y="auto",
            ),
            rx.vstack(
                rx.button(
                    rx.icon("shield-check", size=15),
                    "Armar excluyendo esto",
                    on_click=ArmingState.armar_excluyendo,
                    color_scheme="red", size="2", width="100%",
                ),
                rx.button(
                    rx.icon("clock", size=15),
                    "Armar cuando cierren",
                    on_click=ArmingState.armar_al_cerrar,
                    variant="soft", size="2", width="100%",
                ),
                rx.button(
                    "Dejarlo", on_click=ArmingState.cerrar,
                    variant="soft", color_scheme="gray", size="2",
                    width="100%",
                ),
                spacing="2", width="100%",
            ),
            rx.text(
                "Lo que se deje fuera queda apuntado en los registros, y "
                "vuelve a vigilarse en cuanto se desarme.",
                size="1", color=theme.MUTED, style={"line-height": "1.5"},
            ),
            class_name="nx-floating-notice nx-arm-blockers",
            aria_live="assertive",
        ),
    )


def cuenta_atras_salida() -> rx.Component:
    """Cuenta de salida compacta y cancelable, visible desde cualquier vista."""
    return rx.cond(
        ArmingState.contando != "",
        rx.el.section(
            rx.icon("timer", size=20, color=theme.WARNING, flex_shrink="0"),
            rx.el.div(
                rx.text("Saliendo de casa", size="2", weight="bold",
                        color=theme.TEXT),
                rx.text("Se armará al terminar la cuenta.", size="1",
                        color=theme.MUTED),
                class_name="nx-countdown-copy",
            ),
            rx.text(ArmingState.restantes.to_string() + " s", size="5",
                    weight="bold", color=theme.WARNING,
                    font_family=theme.FONT_MONO),
            rx.button("Cancelar", size="1", variant="soft", color_scheme="gray",
                      on_click=ArmingState.cancelar_cuenta, flex_shrink="0"),
            class_name="nx-floating-notice nx-countdown",
            aria_live="polite",
        ),
    )


def indicador_armado_principal() -> rx.Component:
    """Indicador visual en esquina superior izquierda: luz + líneas que se
    vuelven rojas cuando el grupo principal está armado.

    Usa `NodesState.principal_armed` (Var reactiva) para detectar el estado.
    Cuando está armado: color ALERT (rojo) con pulso suave.
    Cuando está desarmado: colores actuales (neutros/cian).
    """
    # Colores calculados reactivamente
    light_color = rx.cond(
        NodesState.principal_armed,
        theme.ALERT,  # Rojo alerta cuando armado
        theme.ACCENT  # Cian normal cuando desarmado
    )
    light_glow = rx.cond(
        NodesState.principal_armed,
        theme.alpha(theme.ALERT, 0.6),
        theme.alpha(theme.ACCENT, 0.4)
    )
    line_color = rx.cond(
        NodesState.principal_armed,
        theme.ALERT,
        theme.BORDER
    )

    return rx.el.div(
        # Luz artificial (círculo superior izquierdo)
        rx.el.div(
            class_name=rx.cond(NodesState.principal_armed, "nx-armed-indicator-light nx-armed-pulse", "nx-armed-indicator-light"),
            style={
                "background": light_color,
                "box_shadow": f"0 0 8px {light_glow}, 0 0 16px {light_glow}, 0 0 32px {light_glow}",
                "transition": "all 0.4s ease",
            },
        ),
        # Líneas colindantes (dos barras que forman esquina)
        rx.el.div(
            class_name="nx-armed-indicator-line nx-armed-indicator-line-h",
            style={"background": line_color, "transition": "all 0.4s ease"},
        ),
        rx.el.div(
            class_name="nx-armed-indicator-line nx-armed-indicator-line-v",
            style={"background": line_color, "transition": "all 0.4s ease"},
        ),
        class_name="nx-armed-indicator",
        # Aria para accesibilidad
        aria_live="polite",
        aria_atomic="true",
        # data attribute para CSS selectors si se prefiere
        custom_attrs={"data-armed": NodesState.principal_armed},
    )
