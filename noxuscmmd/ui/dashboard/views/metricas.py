"""
Pestaña «Métricas»: un tablero que monta cada uno.

No hay gráficas fijas. Cada panel es una ficha guardada que dice qué mide, en qué
forma, de cuántos días y de qué color, y esta vista pinta lo que haya. El catálogo
de lo medible sale de lo que la casa ha registrado de verdad — series
muestreadas, familias de eventos y cada acción concreta —, así que un evento
nuevo aparece en el desplegable solo.

Las reglas de las gráficas, que no son estéticas:

UNA MEDIDA POR GRÁFICA, NUNCA DOS EJES. Es la razón de que cada panel sea de una
sola cosa. Con dos escalas verticales se puede hacer que dos líneas parezcan
relacionadas o no a voluntad, moviendo una de las dos, y quien lo mira no tiene
forma de saberlo.

UNA SOLA SERIE POR PANEL, así que no llevan leyenda: el título dice lo que es y
una leyenda de un elemento es un cuadrito que no informa.

LOS COLORES SON LOS DEL TEMA, y el que se ofrece elegir está limitado a cinco a
propósito. El verde y el naranja juntos son el par que peor se distingue: el
validador de paletas de la guía de visualización los separa solo ΔE 6,2 en
deutanopía —el daltonismo más común—, o sea que para bastante gente son el mismo
color. Como aquí cada panel es de una sola serie no se comparan dentro de una
gráfica, pero dos paneles seguidos sí se comparan de un vistazo, así que el
selector avisa de cuál es cuál con su nombre además del color.

LOS TRAMOS VACÍOS SALEN CON CERO (lo rellena MetricasState). Una gráfica que se
salta los días sin datos junta el lunes con el jueves y miente sobre la forma de
la semana.

Y CADA PANEL LLEVA SU NÚMERO ESCRITO debajo del título. Una barra hay que
compararla con sus vecinas; un número se lee. Es también lo que hace que la
pantalla sirva sin distinguir los colores.
"""
import reflex as rx

from ....domains.auth.state import AuthState
from ....domains.infra.metricas_state import MetricasState
from .. import theme
from ..components.form_dialog import select_content

ALTO = 210

# Los cinco colores que se pueden elegir, del tema del panel.
_COLORES = {
    "accent": theme.ACCENT,
    "warning": theme.WARNING,
    "purple": theme.PURPLE,
    "success": theme.SUCCESS,
    "danger": theme.DANGER,
}


def _color_de(clave) -> rx.Var:
    """El color de un panel, resuelto dentro del foreach con rx.match: ahí no se
    puede mirar un diccionario de Python."""
    return rx.match(clave.to(str), *[(k, v) for k, v in _COLORES.items()],
                    theme.ACCENT)


def _bocadillo() -> rx.Component:
    return rx.recharts.graphing_tooltip(
        content_style={
            "background": theme.BG_WINDOW,
            "border": f"1px solid {theme.BORDER_STRONG}",
            "borderRadius": "10px",
            "fontSize": "0.8rem",
            "padding": "8px 10px",
            "color": theme.TEXT,
        },
        item_style={"color": theme.TEXT},
        label_style={"color": theme.MUTED, "marginBottom": "4px"},
        cursor={"fill": "rgba(255,255,255,0.05)"},
    )


def _ejes(unidad) -> list[rx.Component]:
    """Ejes y rejilla recesivos: sin líneas de eje ni marquitas, y solo rejilla
    horizontal, que es la que ayuda a comparar alturas. Las verticales encierran
    cada barra en una celda y no sirven de nada."""
    return [
        rx.recharts.cartesian_grid(horizontal=True, vertical=False,
                                   stroke=theme.BORDER, stroke_dasharray="3 3"),
        rx.recharts.x_axis(data_key="x", tick_line=False, axis_line=False,
                           stroke=theme.MUTED, interval="preserveStartEnd",
                           min_tick_gap=14),
        rx.recharts.y_axis(tick_line=False, axis_line=False, stroke=theme.MUTED,
                           width=38, unit=unidad),
        _bocadillo(),
    ]


def _grafica(panel) -> rx.Component:
    """Barras o línea según lo que diga la ficha del panel."""
    color = _color_de(panel["color"])
    return rx.match(
        panel["forma"].to(str),
        ("linea", rx.recharts.line_chart(
            *_ejes(panel["unidad"]),
            rx.recharts.line(
                data_key="y", name=panel["medida_nombre"], stroke=color,
                stroke_width=2, type_="monotone",
                # Sin punto en cada muestra: con cientos, la línea desaparece
                # debajo. El punto sale al pasar por encima, que es cuando sirve.
                dot=False,
                active_dot={"r": 4, "stroke": theme.BG_WINDOW, "strokeWidth": 2},
            ),
            data=panel["datos"], height=ALTO, width="100%",
            margin={"top": 8, "right": 8, "bottom": 0, "left": 0},
        )),
        rx.recharts.bar_chart(
            *_ejes(panel["unidad"]),
            rx.recharts.bar(
                data_key="y", name=panel["medida_nombre"], fill=color,
                # Extremos redondeados arriba y anclados a la base abajo: la
                # barra sigue empezando en cero, que es lo que hace comparables
                # las alturas.
                radius=[4, 4, 0, 0],
            ),
            data=panel["datos"], height=ALTO, width="100%",
            max_bar_size=22, bar_category_gap="18%",
            margin={"top": 8, "right": 8, "bottom": 0, "left": 0},
        ),
    )


def _controles_panel(panel) -> rx.Component:
    """Mover, editar y quitar. Solo con el modo edición puesto: sin él, el
    tablero es para mirar y no hay botones que estorben."""
    return rx.cond(
        MetricasState.editando,
        rx.hstack(
            rx.icon_button(rx.icon("chevron-up", size=14), size="1",
                           variant="surface",
                           on_click=MetricasState.mover_panel(panel["id"], -1),
                           title="Subir"),
            rx.icon_button(rx.icon("chevron-down", size=14), size="1",
                           variant="surface",
                           on_click=MetricasState.mover_panel(panel["id"], 1),
                           title="Bajar"),
            rx.icon_button(rx.icon("pencil", size=14), size="1", variant="surface",
                           on_click=MetricasState.editar_panel(panel["id"]),
                           title="Editar"),
            rx.icon_button(rx.icon("trash-2", size=14), size="1", variant="surface",
                           color_scheme="red",
                           on_click=MetricasState.borrar_panel(panel["id"]),
                           title="Quitar"),
            spacing="1", flex_shrink="0",
        ),
    )


def _panel(panel) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text(panel["titulo"], size="2", weight="bold", color=theme.TEXT),
                # El número, escrito. Va en tinta normal y no en el color de la
                # serie: el color lo lleva la gráfica, y un texto coloreado se
                # lee peor y compite con ella.
                rx.text(panel["resumen"], size="1", color=theme.MUTED),
                spacing="0", align="start", min_width="0",
            ),
            rx.spacer(),
            rx.badge(panel["dias_texto"], size="1", variant="surface"),
            _controles_panel(panel),
            width="100%", align="center", spacing="2",
        ),
        rx.cond(
            panel["vacio"],
            rx.box(
                rx.text("Todavía no hay datos de esto en el periodo elegido.",
                        size="1", color=theme.MUTED),
                padding="24px 0",
            ),
            rx.box(_grafica(panel), width="100%"),
        ),
        spacing="2", width="100%",
        padding="14px", border_radius="12px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
    )


def _editor() -> rx.Component:
    """El formulario del panel. Los cinco campos son los cinco que tiene una
    ficha: qué mide, cómo se pinta, cuánto abarca, cómo se llama y de qué color."""
    return rx.cond(
        MetricasState.editor_abierto,
        rx.vstack(
            rx.text("Panel", size="2", weight="bold", color=theme.TEXT),
            rx.text("Qué mide", size="1", color=theme.MUTED),
            rx.select.root(
                rx.select.trigger(placeholder="Elige una medida", width="100%"),
                select_content(
                    rx.foreach(
                        MetricasState.catalogo_agrupado,
                        lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                    ),
                ),
                value=MetricasState.ed_medida,
                on_change=MetricasState.set_ed_medida,
                width="100%",
            ),
            rx.text("Forma", size="1", color=theme.MUTED),
            rx.select.root(
                rx.select.trigger(width="100%"),
                select_content(
                    rx.foreach(
                        MetricasState.formas_ui,
                        lambda f: rx.select.item(f["nombre"], value=f["id"]),
                    ),
                ),
                value=MetricasState.ed_forma,
                on_change=MetricasState.set_ed_forma,
                width="100%",
            ),
            rx.hstack(
                rx.vstack(
                    rx.text("Días", size="1", color=theme.MUTED),
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        select_content(
                            rx.foreach(MetricasState.dias_ui,
                                       lambda d: rx.select.item(d, value=d)),
                        ),
                        value=MetricasState.ed_dias.to_string(),
                        on_change=MetricasState.set_ed_dias,
                        width="100%",
                    ),
                    spacing="1", align="start", flex="1",
                ),
                rx.vstack(
                    rx.text("Color", size="1", color=theme.MUTED),
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        select_content(
                            rx.foreach(MetricasState.colores_ui,
                                       lambda c: rx.select.item(c, value=c)),
                        ),
                        value=MetricasState.ed_color,
                        on_change=MetricasState.set_ed_color,
                        width="100%",
                    ),
                    spacing="1", align="start", flex="1",
                ),
                spacing="3", width="100%",
            ),
            rx.text("Título (si lo dejas vacío se pone el de la medida)",
                    size="1", color=theme.MUTED),
            rx.input(value=MetricasState.ed_titulo,
                     on_change=MetricasState.set_ed_titulo, width="100%"),
            rx.hstack(
                rx.button("Guardar", on_click=MetricasState.guardar_panel, size="2"),
                rx.button("Cancelar", on_click=MetricasState.cerrar_editor,
                          size="2", variant="surface"),
                spacing="2",
            ),
            spacing="2", width="100%",
            padding="14px", border_radius="12px",
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.BORDER_STRONG}",
        ),
    )


def _equipo(e) -> rx.Component:
    return rx.hstack(
        rx.icon("server", size=14,
                color=rx.cond(e["en_metricas"], theme.ACCENT, theme.MUTED)),
        rx.text(e["nombre"], size="2", color=theme.TEXT),
        rx.spacer(),
        rx.text(e["estado"], size="1", color=theme.MUTED),
        rx.switch(checked=e["en_metricas"],
                  on_change=lambda _: MetricasState.alternar_equipo(e["id"])),
        align="center", spacing="3", width="100%",
        padding="8px 10px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _equipos() -> rx.Component:
    """Qué equipos guardan su estado en el histórico.

    Apagados por defecto a propósito: son 288 muestras al día POR equipo, y
    guardarlas de los once para acabar mirando dos es engordar la base para
    nada. El recuento total se guarda siempre, así que la gráfica de «equipos en
    línea» no depende de esto."""
    return rx.cond(
        MetricasState.editando,
        rx.vstack(
            rx.text("QUÉ EQUIPOS SE GUARDAN EN EL HISTÓRICO", size="1",
                    color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.text("Solo los encendidos guardan si estaban en línea, cada cinco "
                    "minutos. El recuento total se guarda siempre.",
                    size="1", color=theme.MUTED),
            rx.foreach(MetricasState.equipos, _equipo),
            spacing="2", width="100%", padding_top="2",
        ),
    )


def metricas_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.cond(
                AuthState.puede_ajustes,
                rx.button(
                    rx.icon(rx.cond(MetricasState.editando, "check", "pencil"),
                            size=14),
                    rx.cond(MetricasState.editando, "Listo", "Editar tablero"),
                    on_click=MetricasState.alternar_edicion,
                    size="2",
                    variant=rx.cond(MetricasState.editando, "solid", "surface"),
                ),
            ),
            rx.cond(
                MetricasState.editando,
                rx.button(rx.icon("plus", size=14), "Añadir panel",
                          on_click=MetricasState.nuevo_panel, size="2",
                          variant="surface"),
            ),
            spacing="2", width="100%", wrap="wrap",
        ),
        _editor(),
        rx.cond(
            MetricasState.hay_paneles,
            rx.vstack(
                rx.foreach(MetricasState.paneles, _panel),
                spacing="3", width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.icon("chart-line", size=26, color=theme.MUTED),
                    rx.text("El tablero está vacío.", size="2", color=theme.TEXT),
                    rx.text("Pulsa «Editar tablero» y añade paneles. Puedes medir "
                            "cualquier cosa que la casa haya registrado: aperturas "
                            "por hora, temperatura, si un equipo concreto estaba "
                            "en línea, o cualquier evento del registro.",
                            size="1", color=theme.MUTED, text_align="center"),
                    spacing="2", align="center", max_width="460px",
                ),
                padding="32px", width="100%",
                display="flex", justify_content="center",
            ),
        ),
        _equipos(),
        spacing="3", width="100%", max_width="1100px",
        on_mount=MetricasState.on_load,
    )
