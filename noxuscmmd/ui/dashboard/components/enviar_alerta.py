"""
El diálogo de «enviar una alerta», compartido.

Vive aquí y no dentro del Resumen porque se abre desde dos sitios: el acceso
rápido del Resumen y el icono de la barra de arriba. Con el formulario duplicado,
cualquier campo nuevo habría que acordarse de ponerlo en los dos.

Quien lo usa solo pone el DISPARADOR (el botón o el icono que lo abre); el
formulario, los destinatarios y el envío son siempre los mismos.
"""
import reflex as rx

from ....domains.notifications.state import PushState
from .. import theme
from .form_dialog import form_dialog_content, field, dialog_footer, styled_input


def chip_destino(nombre, activo, on_click) -> rx.Component:
    """Pastilla de un destinatario. Se marcan varios: mandar el mismo aviso a
    dos personas es lo normal, y con un desplegable de una sola opción había
    que enviarlo dos veces."""
    return rx.hstack(
        rx.icon(rx.cond(activo, "check", "plus"), size=12,
                color=rx.cond(activo, theme.WARNING, theme.MUTED), flex_shrink="0"),
        rx.text(nombre, size="1",
                weight=rx.cond(activo, "bold", "regular"),
                color=rx.cond(activo, theme.TEXT, theme.MUTED),
                white_space="nowrap"),
        on_click=on_click,
        cursor="pointer",
        align="center", spacing="1",
        padding="6px 12px", border_radius="999px", flex_shrink="0",
        background=rx.cond(activo, theme.alpha(theme.WARNING, 0.14), "transparent"),
        border=f"1px solid {rx.cond(activo, theme.WARNING, theme.BORDER)}",
        _hover={"border_color": theme.BORDER_STRONG},
    )


def dialogo_enviar_alerta(disparador: rx.Component) -> rx.Component:
    """El diálogo entero, con el disparador que le pasen.

    La lista de dispositivos se relee al abrir (on_open_change): las
    suscripciones se dan de alta y de baja desde otros aparatos, y la de esta
    sesión se queda vieja en cuanto alguien vincula un móvil nuevo."""
    return rx.dialog.root(
        rx.dialog.trigger(disparador),
        form_dialog_content(
            icon="bell-ring",
            title="Enviar una alerta",
            accent=theme.WARNING,
            form=rx.form.root(
                rx.vstack(
                    field(
                        "Destinatarios",
                        rx.vstack(
                            chip_destino("Todos", PushState.a_todos, PushState.enviar_a_todos),
                            rx.flex(
                                rx.foreach(
                                    PushState.destinos_ui,
                                    lambda d: chip_destino(
                                        d["nombre"], d["activo"],
                                        PushState.alternar_destino(d["nombre"]),
                                    ),
                                ),
                                gap="8px", wrap="wrap", width="100%",
                            ),
                            rx.text(PushState.resumen_destinos, size="1", color=theme.MUTED),
                            spacing="2", width="100%", align="start",
                        ),
                        hint="Marca los que quieras; sin marcar ninguno va a todos. "
                             "Solo salen los dispositivos con las notificaciones vinculadas.",
                    ),
                    field("Título", styled_input(
                        name="titulo", placeholder="Aviso de Noxus", max_length=60,
                    )),
                    field("Mensaje", rx.text_area(
                        name="mensaje", placeholder="Escribe aquí lo que quieres que les llegue...",
                        rows="4", width="100%", size="3", auto_complete=False,
                    )),
                    dialog_footer(confirm_label="Enviar", color_scheme="orange"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=PushState.enviar_alerta,
                reset_on_submit=True,
            ),
        ),
        on_open_change=PushState.refrescar_dispositivos,
    )
