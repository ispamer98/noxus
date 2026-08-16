"""
Look común para TODOS los diálogos de alta/edición de la app: cabecera con
icono en avatar de color + título, cuerpo con separación generosa entre
campos, pie con acciones — sustituye a los `rx.dialog.title` a secas que
había antes, repetidos y distintos en cada formulario.
"""
import reflex as rx

from .. import theme


def form_dialog_content(
    *,
    icon: str,
    title: str,
    form: rx.Component,
    accent: str = theme.ACCENT,
    max_width: str = "420px",
) -> rx.Component:
    return rx.dialog.content(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=20, color=accent),
                    padding="12px",
                    border_radius="14px",
                    background=theme.alpha(accent, 0.14),
                    border=f"1px solid {theme.alpha(accent, 0.3)}",
                ),
                rx.dialog.title(title, margin="0", size="4", weight="bold"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(border_color=theme.BORDER),
            form,
            spacing="4",
            width="100%",
        ),
        style={
            "max_width": max_width,
            "background": theme.BG_WINDOW,
            "border": f"1px solid {theme.BORDER_STRONG}",
            "border_radius": "18px",
            "padding": "24px",
            "box_shadow": "0 24px 70px -12px rgba(0, 0, 0, 0.65)",
            "backdrop_filter": "blur(16px)",
        },
    )


def field(label: str, *children: rx.Component, hint: str = "") -> rx.Component:
    """Fila "etiqueta + input(s)" — mismo espaciado/tipografía en todos los formularios."""
    return rx.vstack(
        rx.text(label, size="1", color=theme.MUTED, weight="medium", letter_spacing="0.02em"),
        *children,
        *([rx.text(hint, size="1", color=theme.MUTED, opacity="0.7")] if hint else []),
        spacing="1",
        width="100%",
        align="start",
    )


def dialog_footer(*, confirm_label: str, color_scheme: str = "blue", cancel_label: str = "Cancelar") -> rx.Component:
    return rx.hstack(
        rx.dialog.close(rx.button(cancel_label, variant="soft", color_scheme="gray", type="button", size="2")),
        rx.dialog.close(rx.button(confirm_label, type="submit", color_scheme=color_scheme, size="2")),
        spacing="2",
        justify="end",
        width="100%",
        padding_top="2",
    )


def styled_input(**props) -> rx.Component:
    """rx.input con el estilo/tamaño estándar del formulario y autocompletado
    del navegador desactivado (no queremos sugerencias de valores anteriores)."""
    props.setdefault("size", "3")
    props.setdefault("auto_complete", False)
    props.setdefault("width", "100%")
    return rx.input(**props)


def styled_select(trigger_placeholder: str, content: rx.Component, **props) -> rx.Component:
    return rx.select.root(
        rx.select.trigger(placeholder=trigger_placeholder, width="100%", size="3"),
        content,
        **props,
    )


def select_content(*children, **props) -> rx.Component:
    """Lista de un desplegable que se comporta como un desplegable normal.

    Por defecto los select colocan la lista ENCIMA del botón, alineando la
    opción ya elegida con él, y la dejan crecer hasta ocupar la pantalla con
    unas flechitas arriba y abajo para desplazarse. Con listas cortas se nota
    poco; con las largas (el catálogo de widgets, el de sensores, el del plano)
    el resultado es que al abrirla salta a pantalla completa, y girar la rueda
    del ratón la recoloca sola y acaba cerrándose — imposible acertar con la
    opción que buscabas.

    "popper" la ancla debajo del botón como cualquier menú, con el mismo ancho,
    y con una altura tope se desplaza con la rueda como una lista normal. El
    min() con la variable de Radix es para que en una pantalla baja (o con el
    botón cerca del borde) no se salga: se queda con el hueco que de verdad
    haya libre."""
    props.setdefault("position", "popper")
    props.setdefault("side", "bottom")
    props.setdefault("align", "start")
    props.setdefault("max_height", "min(320px, var(--radix-select-content-available-height))")
    props.setdefault("width", "var(--radix-select-trigger-width)")
    return rx.select.content(*children, **props)
