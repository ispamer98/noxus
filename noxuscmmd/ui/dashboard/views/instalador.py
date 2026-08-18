"""
Pantalla «Modo instalador» (Ajustes): de lo que se oye por MQTT a un aparato
dado de alta, en tres pasos.

El orden de la lista lo pone el dominio (lo que se acaba de mover, primero), y
es lo que hace que la forma natural de usar esto sea: darle a escuchar, ir al
sitio, abrir la ventana o pasar por delante del detector, y ver aparecer arriba
lo que se acaba de tocar.
"""
import reflex as rx

from ....domains.devices.instalador_state import (
    CLASES_SENSOR, FICHA, HECHO, NOMBRES_CLASE, NOMBRES_TIPO, TIPOS,
    InstaladorState,
)
from .. import theme
from ..components.form_dialog import select_content


def _aviso() -> rx.Component:
    return rx.cond(
        InstaladorState.mensaje != "",
        rx.box(
            rx.text(InstaladorState.mensaje, size="1", color=theme.TEXT),
            padding="9px 11px", border_radius="10px", width="100%",
            background=rx.cond(InstaladorState.error, "#3a1a1a", theme.BG_CARD),
            border=f"1px solid {theme.BORDER}",
        ),
    )


def _hallazgo(h: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("radio", size=15, flex_shrink="0",
                color=rx.cond(h["elegible"], theme.ACCENT, theme.MUTED)),
        rx.vstack(
            rx.text(h["titulo"], size="2", weight="bold", color=theme.TEXT),
            rx.text(h["topic"], size="1", color=theme.MUTED),
            rx.hstack(
                rx.text(h["valor"], size="1", color=theme.TEXT),
                rx.text("·", size="1", color=theme.MUTED),
                rx.text(h["hace"], size="1", color=theme.MUTED),
                rx.text("·", size="1", color=theme.MUTED),
                rx.text(h["etiqueta_estado"], size="1", color=theme.MUTED),
                spacing="2", align="center", wrap="wrap",
            ),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.cond(
            h["elegible"],
            rx.button("Dar de alta", size="1", variant="surface",
                      on_click=InstaladorState.elegir(h["topic"])),
            rx.badge(h["sugerencia"], size="1", variant="soft"),
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _paso_oir() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.cond(
                InstaladorState.escuchando,
                rx.button(rx.icon("square", size=14), "Dejar de escuchar",
                          size="2", variant="surface", color_scheme="red",
                          on_click=InstaladorState.detener),
                rx.button(rx.icon("ear", size=14), "Escuchar la casa",
                          size="2", on_click=InstaladorState.empezar),
            ),
            rx.button("Empezar de cero", size="2", variant="surface",
                      on_click=InstaladorState.olvidar,
                      disabled=~InstaladorState.escuchando),
            rx.spacer(),
            rx.cond(
                InstaladorState.escuchando,
                rx.hstack(
                    rx.spinner(size="1"),
                    rx.text("escuchando…", size="1", color=theme.MUTED),
                    spacing="2", align="center",
                ),
            ),
            align="center", spacing="3", width="100%", wrap="wrap",
        ),
        _aviso(),
        rx.cond(
            InstaladorState.hallazgos.length() > 0,
            rx.vstack(
                rx.foreach(InstaladorState.hallazgos, _hallazgo),
                spacing="2", width="100%",
            ),
            rx.box(
                rx.text(
                    rx.cond(
                        InstaladorState.escuchando,
                        "Todavía no ha llegado nada. Ve al sitio y mueve el "
                        "aparato: abre la ventana, pasa por delante del "
                        "detector o pulsa el botón — aparecerá aquí arriba.",
                        "Dale a «Escuchar la casa» y luego mueve el aparato que "
                        "quieras dar de alta.",
                    ),
                    size="1", color=theme.MUTED,
                ),
                padding="14px", border_radius="10px", width="100%",
                background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
            ),
        ),
        spacing="3", width="100%", align="start",
    )


def _paso_ficha() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon_button(rx.icon("arrow-left", size=14), size="1",
                           variant="surface", on_click=InstaladorState.volver,
                           title="Volver a la lista"),
            rx.text(InstaladorState.topic_elegido, size="2", weight="bold",
                    color=theme.TEXT),
            align="center", spacing="3", width="100%", wrap="wrap",
        ),
        _aviso(),
        rx.vstack(
            rx.text("QUÉ ES", size="1", color=theme.MUTED, weight="bold",
                    letter_spacing="0.08em"),
            rx.select.root(
                rx.select.trigger(variant="surface"),
                # Lista fija de Python, así que se despliega aquí: un rx.foreach
                # sobre una constante es trabajo del frontend para nada.
                select_content(
                    *[rx.select.item(NOMBRES_TIPO[t], value=t) for t in TIPOS],
                ),
                value=InstaladorState.ficha_tipo,
                on_change=InstaladorState.set_ficha_tipo,
                size="2",
            ),
            rx.cond(
                InstaladorState.es_sensor,
                rx.select.root(
                    rx.select.trigger(variant="surface"),
                    select_content(
                        *[rx.select.item(NOMBRES_CLASE[c], value=c)
                          for c in CLASES_SENSOR],
                    ),
                    value=InstaladorState.ficha_clase,
                    on_change=InstaladorState.set_ficha_clase,
                    size="2",
                ),
            ),
            rx.text("CÓMO SE LLAMA", size="1", color=theme.MUTED, weight="bold",
                    letter_spacing="0.08em"),
            rx.input(value=InstaladorState.ficha_nombre,
                     on_change=InstaladorState.set_ficha_nombre,
                     placeholder="Ventana del salón", size="2", width="100%"),
            rx.checkbox("Enseñarlo en el plano",
                        checked=InstaladorState.ficha_en_plano,
                        on_change=InstaladorState.toggle_en_plano, size="2"),
            spacing="2", width="100%", align="start",
        ),
        rx.vstack(
            rx.text("EL NODO", size="1", color=theme.MUTED, weight="bold",
                    letter_spacing="0.08em"),
            rx.cond(
                InstaladorState.nodo_hay_que_crearlo,
                rx.vstack(
                    rx.text(
                        "Este nodo no está dado de alta todavía. Se crea ahora "
                        "con este nombre — no lo cambies salvo que sepas lo que "
                        "haces: el nombre es lo que forma el topic.",
                        size="1", color=theme.MUTED,
                    ),
                    rx.input(value=InstaladorState.nodo_nombre,
                             on_change=InstaladorState.set_nodo_nombre,
                             size="2", width="100%"),
                    rx.input(value=InstaladorState.nodo_ip,
                             on_change=InstaladorState.set_nodo_ip,
                             placeholder="IP del nodo (opcional)", size="2",
                             width="100%"),
                    spacing="2", width="100%", align="start",
                ),
                rx.text("Ya existe: " + InstaladorState.nodo_nombre.to(str),
                        size="2", color=theme.TEXT),
            ),
            spacing="2", width="100%", align="start",
        ),
        # El espejo de lo que se va a escuchar de verdad. Es la comprobación que
        # justifica esta pantalla: si no cuadra, se dice aquí y no al día
        # siguiente, cuando el sensor no se mueva.
        rx.box(
            rx.cond(
                InstaladorState.topic_cuadra,
                rx.hstack(
                    rx.icon("check", size=14, color="#4ade80"),
                    rx.text("Cuadra con lo que se ha oído: " +
                            InstaladorState.resumen_topic.to(str),
                            size="1", color=theme.TEXT),
                    spacing="2", align="center", wrap="wrap",
                ),
                rx.hstack(
                    rx.icon("triangle-alert", size=14, color="#f87171"),
                    rx.text("Con ese nombre de nodo se escucharía " +
                            InstaladorState.resumen_topic.to(str) +
                            ", que no es lo que se ha oído.",
                            size="1", color=theme.TEXT),
                    spacing="2", align="center", wrap="wrap",
                ),
            ),
            padding="9px 11px", border_radius="10px", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        ),
        rx.hstack(
            rx.button("Dar de alta", size="2", on_click=InstaladorState.guardar,
                      disabled=~InstaladorState.topic_cuadra),
            rx.button("Cancelar", size="2", variant="surface",
                      on_click=InstaladorState.volver),
            spacing="3", align="center", wrap="wrap",
        ),
        spacing="4", width="100%", align="start",
    )


def _paso_hecho() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("check", size=16, color="#4ade80"),
            rx.text(InstaladorState.creado_texto, size="2", color=theme.TEXT),
            align="center", spacing="3", wrap="wrap",
        ),
        rx.hstack(
            rx.button("Dar de alta otro", size="2",
                      on_click=InstaladorState.otro_mas),
            spacing="3", align="center",
        ),
        spacing="3", width="100%", align="start",
        padding="14px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def instalador_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Modo instalador", size="5", color=theme.TEXT),
            rx.text(
                "Escucha lo que la casa publica y lo convierte en un sensor, una "
                "luz o una puerta sin escribir un topic a mano. Se deja de "
                "escuchar al salir de esta pantalla.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),
        rx.match(
            InstaladorState.paso,
            (FICHA, _paso_ficha()),
            (HECHO, _paso_hecho()),
            _paso_oir(),
        ),
        spacing="5", width="100%", align="start", max_width="640px",
        padding_bottom="6",
        on_unmount=InstaladorState.on_unmount,
    )
