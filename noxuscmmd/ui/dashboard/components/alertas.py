"""
Alertas sin confirmar, con sus dos botones.

Viven en la pila flotante común abajo a la derecha. No llevan botón de cerrar:
se quitan confirmando o silenciando, que es la decisión que hay que tomar.

Aparece en todas las vistas porque cuelga del shell del dashboard, así que da
igual en qué pestaña estuviera el panel cuando saltó.
"""
import reflex as rx

from ....domains.notifications.alertas_state import AlertasState, MINUTOS_SILENCIO
from .. import theme


def _fila(a: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("siren", size=20, color=theme.DANGER, flex_shrink="0"),
        rx.vstack(
            rx.hstack(
                rx.text(a["titulo"], size="2", weight="bold", color=theme.TEXT),
                # El recuento va preformateado desde el State: concatenar el
                # valor de una clave de dict dentro de un foreach rompe el
                # frontend en esta version de Reflex.
                rx.text(a["cuando"], size="1", color=theme.MUTED),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.text(a["cuerpo"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("check", size=14), "Visto",
            on_click=lambda: AlertasState.confirmar(a["clave"]),
            size="2", color_scheme="green", flex_shrink="0",
        ),
        rx.button(
            rx.icon("bell-off", size=14), f"Silenciar {int(MINUTOS_SILENCIO)} min",
            on_click=lambda: AlertasState.silenciar(a["clave"]),
            size="2", variant="surface", flex_shrink="0",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="10px 12px",
        border_radius="10px",
        background=theme.alpha(theme.DANGER, 0.10),
        border=f"1px solid {theme.DANGER}",
        class_name="nx-floating-notice nx-alert-notice",
    )


def banner_alertas() -> rx.Component:
    return rx.cond(
        AlertasState.hay_pendientes,
        rx.vstack(
            rx.foreach(AlertasState.pendientes, _fila),
            spacing="2",
            width="100%",
            class_name="nx-notice-group",
        ),
    )
