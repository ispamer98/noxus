"""
Pantalla «Comandos de voz» (Ajustes): frases atadas a acciones, y la clave que
necesita el atajo del móvil.

Dos bloques y en este orden: primero las frases, que es lo que se viene a hacer
aquí, y debajo la clave, que se saca una vez y no se vuelve a tocar.
"""
import reflex as rx

from ....domains.devices.voz_state import DIAS_CLAVE, VozState
from .. import theme
from ..components.form_dialog import select_content


def _fila(g: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("mic", size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.vstack(
            rx.text('"' + g["frase"].to(str) + '"', size="2", weight="bold",
                    color=theme.TEXT),
            rx.text(g["etiqueta"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        # Cambiar la acción sin borrar la frase: lo normal es querer que «buenas
        # noches» haga otra cosa, no dejar de decir «buenas noches».
        rx.select.root(
            rx.select.trigger(placeholder="Cambiar acción", variant="surface"),
            select_content(
                rx.foreach(
                    VozState.catalogo,
                    lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                ),
            ),
            value=g["comando"],
            on_change=lambda v: VozState.cambiar_accion(g["id"], v),
            size="1",
        ),
        rx.icon_button(rx.icon("trash-2", size=13), size="1", variant="surface",
                       color_scheme="red", on_click=VozState.borrar(g["id"]),
                       title="Quitar la frase"),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _clave() -> rx.Component:
    return rx.vstack(
        rx.text("CLAVE PARA EL ATAJO", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        rx.text(
            f"La necesita el Atajo de Siri o la rutina de Alexa. Vale {DIAS_CLAVE} "
            "días y hereda los permisos de ESTE dispositivo: la clave de un "
            "invitado enciende luces y no abre la puerta.",
            size="1", color=theme.MUTED,
        ),
        rx.cond(
            VozState.hay_clave,
            rx.vstack(
                rx.box(
                    rx.text(VozState.clave, size="1",
                            style={"font-family": theme.FONT_MONO,
                                   "word-break": "break-all"},
                            color=theme.TEXT),
                    padding="10px", border_radius="8px", width="100%",
                    background=theme.BG_WINDOW,
                    border=f"1px solid {theme.BORDER_STRONG}",
                ),
                rx.hstack(
                    rx.button(rx.icon("copy", size=14), "Copiar",
                              on_click=rx.set_clipboard(VozState.clave),
                              size="2"),
                    rx.button("Ocultar", on_click=VozState.olvidar_clave,
                              size="2", variant="surface"),
                    spacing="2",
                ),
                rx.text(
                    "Cópiala ahora: no se guarda en ningún sitio y al ocultarla "
                    "no se puede volver a ver. Si la pierdes, generas otra.",
                    size="1", color=theme.WARNING,
                ),
                spacing="2", width="100%",
            ),
            rx.button(rx.icon("key-round", size=14), "Generar una clave",
                      on_click=VozState.generar_clave, size="2",
                      variant="surface"),
        ),
        rx.divider(border_color=theme.BORDER),
        rx.text("CÓMO SE MONTA EL ATAJO", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        # El ejemplo va en texto plano y no en una captura: un atajo se monta
        # una vez y lo que hace falta es poder copiar los cuatro datos.
        rx.box(
            rx.text(
                "En Atajos (iPhone): «Obtener contenido de una URL»\n"
                "  URL:      https://panel.noxuscmmd.uk/api/voz\n"
                "  Método:   POST\n"
                "  Cabecera: X-Noxus-Clave = la clave de arriba\n"
                "  Cuerpo (JSON):  texto = [Texto dictado]\n\n"
                "Luego «Obtener valor de mensaje del diccionario» y «Decir»,\n"
                "para que Siri lea la respuesta en voz alta.",
                size="1", color=theme.MUTED,
                style={"font-family": theme.FONT_MONO, "white-space": "pre-wrap",
                       "line-height": "1.6"},
            ),
            padding="10px", border_radius="8px", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        ),
        spacing="2", width="100%",
    )


def voz_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Comandos de voz", size="5", color=theme.TEXT),
            rx.text(
                "Ata una frase a una acción. Lo que escribas aquí se reconoce "
                "EXACTO, así que es la forma de que «buenas noches» haga lo que "
                "tú quieras y no lo que el sistema adivine.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),
        rx.hstack(
            rx.input(value=VozState.nueva_frase,
                     on_change=VozState.set_nueva_frase,
                     placeholder="Lo que vas a decir: buenas noches",
                     size="2", flex="1", min_width="180px"),
            rx.select.root(
                rx.select.trigger(placeholder="Qué tiene que hacer", width="100%"),
                select_content(
                    rx.foreach(
                        VozState.catalogo,
                        lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                    ),
                ),
                value=VozState.nuevo_comando,
                on_change=VozState.set_nuevo_comando,
                size="2",
            ),
            rx.button(rx.icon("plus", size=14), "Añadir",
                      on_click=VozState.anadir, size="2", flex_shrink="0"),
            spacing="2", width="100%", wrap="wrap",
        ),
        rx.cond(
            VozState.hay_guardados,
            rx.vstack(rx.foreach(VozState.guardados, _fila),
                      spacing="2", width="100%"),
            rx.box(
                rx.text("Todavía no has atado ninguna frase. Sin frases, el "
                        "asistente intenta adivinar por parecido — funciona, "
                        "pero pregunta cuando duda.",
                        size="1", color=theme.MUTED),
                padding="18px 0",
            ),
        ),
        rx.divider(border_color=theme.BORDER),
        _clave(),
        spacing="4", width="100%", max_width="720px", align="start",
        padding_bottom="6",
        on_mount=VozState.on_load,
    )
