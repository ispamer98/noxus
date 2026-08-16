"""
Selector de catálogo: un diálogo con buscador y las opciones AGRUPADAS por
bloque, con su icono y su cabecera.

Sustituye al desplegable único que se usaba para añadir widgets, y es el mismo
que usan los tres bloques del editor de automatizaciones. El motivo es el
mismo en los dos sitios: cuando el catálogo pasa de veinte opciones, un
`<select>` corrido obliga a recorrerlo entero para saber qué hay, y no deja
buscar. Aquí las familias se ven de un vistazo y escribir dos letras filtra.

El filtrado lo hace QUIEN LLAMA, en Python, y pasa las secciones ya filtradas:
comparar cadenas dentro de rx.foreach exige condicionales anidados que no hay
manera de leer ni de mantener.

Forma que espera de cada sección:
    {"label": "Luces", "icon": "lightbulb",
     "options": [{"label": "Salón — encender / apagar", "value": "light.set|light:ab"}]}
"""
import reflex as rx

from .. import theme


def _opcion(opt: dict, on_pick) -> rx.Component:
    return rx.hstack(
        rx.text(opt["label"], size="2", color=theme.TEXT),
        rx.spacer(),
        rx.icon("plus", size=14, color=theme.MUTED),
        on_click=on_pick(opt["value"]),
        cursor="pointer",
        align="center",
        width="100%",
        padding="9px 12px",
        border_radius="9px",
        border=f"1px solid {theme.BORDER}",
        background=theme.BG_CARD,
        _hover={"background": theme.alpha(theme.ACCENT, 0.10),
                "border_color": theme.alpha(theme.ACCENT, 0.45)},
    )


def _seccion(section: dict, on_pick) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon(section["icon"].to(str), size=14, color=theme.ACCENT),
            rx.text(section["label"], size="1", weight="bold", color=theme.MUTED,
                    letter_spacing="0.08em", text_transform="uppercase"),
            rx.spacer(),
            rx.badge(section["options"].to(list[dict]).length().to_string(), variant="soft",
                     size="1", color_scheme="gray"),
            align="center",
            spacing="2",
            width="100%",
            padding_top="2",
        ),
        rx.foreach(section["options"].to(list[dict]), lambda o: _opcion(o, on_pick)),
        spacing="2",
        width="100%",
        align="start",
    )


def catalog_picker(*, is_open, title: str | rx.Var, sections, query,
                   on_query, on_pick, on_close, on_open_change,
                   icon: str = "list-plus",
                   empty_text: str = "No hay nada que ofrecer todavía.") -> rx.Component:
    """El diálogo.

    `is_open`        Var booleano que dice si está abierto.
    `on_close`       evento sin argumentos — lo dispara la X.
    `on_open_change` evento que recibe un booleano — lo dispara Escape y el
                     clic fuera, y tiene que cerrar cuando llegue False.
    """
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.icon(icon, size=18, color=theme.ACCENT),
                        padding="10px",
                        border_radius="12px",
                        background=theme.alpha(theme.ACCENT, 0.14),
                        border=f"1px solid {theme.alpha(theme.ACCENT, 0.3)}",
                    ),
                    rx.dialog.title(title, margin="0", size="4", weight="bold"),
                    rx.spacer(),
                    rx.icon("x", size=18, color=theme.MUTED, cursor="pointer",
                            on_click=on_close),
                    align="center",
                    spacing="3",
                    width="100%",
                ),
                rx.input(
                    rx.input.slot(rx.icon("search", size=15, color=theme.MUTED)),
                    placeholder="Buscar...",
                    value=query,
                    on_change=on_query,
                    size="3",
                    width="100%",
                    auto_complete=False,
                ),
                rx.cond(
                    sections.to(list[dict]).length() > 0,
                    rx.vstack(
                        rx.foreach(sections.to(list[dict]), lambda s: _seccion(s, on_pick)),
                        spacing="4",
                        width="100%",
                        align="start",
                        max_height="min(56vh, 460px)",
                        overflow_y="auto",
                        padding_right="2",
                    ),
                    rx.text(empty_text, size="2", color=theme.MUTED, padding_y="6"),
                ),
                spacing="4",
                width="100%",
                align="start",
            ),
            style={
                "max_width": "560px",
                "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}",
                "border_radius": "18px",
                "padding": "22px",
                "box_shadow": "0 24px 70px -12px rgba(0, 0, 0, 0.65)",
                "backdrop_filter": "blur(16px)",
            },
        ),
        open=is_open,
        # Cerrar con Escape o pulsando fuera tiene que llegar al estado igual
        # que la X, o la Var se queda diciendo que el diálogo sigue abierto y
        # no se puede volver a abrir. `on_open_change` recibe si queda abierto
        # o cerrado, así que el manejador es uno que acepte ese booleano.
        on_open_change=on_open_change,
    )
