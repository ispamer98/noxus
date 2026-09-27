"""Dashboard de analíticas: una medida por panel y presentación configurable.

La vista solo presenta los datos preparados por MetricasState. Los circulares
representan distribuciones de muestras o eventos, nunca sumas de temperaturas.
"""
import reflex as rx

from ....domains.auth.state import AuthState
from ....domains.infra.metricas_state import MetricasState
from .. import theme
from ..components.form_dialog import field, select_content
from ..components.actions_menu import actions_menu

_COLORES = {
    "accent": theme.ACCENT,
    "purple": theme.PURPLE,
    "success": theme.SUCCESS,
    "warning": theme.WARNING,
    "danger": theme.DANGER,
}
_NOMBRES_COLOR = {
    "accent": "Cielo", "purple": "Lavanda", "success": "Verde",
    "warning": "Ámbar", "danger": "Coral",
}
_FORMATOS = (
    ("linea", "Línea", "chart-line"),
    ("area", "Área", "chart-area"),
    ("barras", "Barras", "chart-no-axes-column-increasing"),
    ("donut", "Anillo", "circle-gauge"),
    ("circular", "Circular", "chart-pie"),
)


def _color_de(clave) -> rx.Var:
    return rx.match(clave.to(str), *[(k, v) for k, v in _COLORES.items()],
                    theme.ACCENT)


def _bocadillo() -> rx.Component:
    return rx.recharts.graphing_tooltip(
        content_style={
            "background": theme.BG_WINDOW,
            "border": f"1px solid {theme.BORDER_STRONG}",
            "borderRadius": "12px",
            "fontSize": "12px",
            "padding": "10px 14px",
            "color": theme.TEXT,
            "boxShadow": "0 12px 30px rgba(0,0,0,.35)",
        },
        item_style={"color": theme.TEXT},
        label_style={"color": theme.MUTED, "marginBottom": "4px"},
        cursor={"fill": theme.alpha(theme.MUTED, 0.05)},
    )


def _ejes(unidad) -> list[rx.Component]:
    return [
        rx.recharts.cartesian_grid(
            horizontal=True, vertical=False,
            stroke=theme.BORDER, stroke_dasharray="3 5",
        ),
        rx.recharts.x_axis(
            data_key="x", tick_line=False, axis_line=False,
            stroke=theme.MUTED, interval="preserveStartEnd",
            min_tick_gap=36, tick={"fontSize": 10}, height=26,
        ),
        rx.recharts.y_axis(
            tick_line=False, axis_line=False, stroke=theme.MUTED,
            width=48, unit=unidad, tick={"fontSize": 10}, tick_count=4,
        ),
        _bocadillo(),
    ]


def _color_sector(panel, sector) -> rx.Var:
    # Una paleta continua: el color identifica sectores, no niveles de peligro.
    secundarios = ["#818cf8", "#c4b5fd", "#7dd3fc", theme.MUTED,
                   "#d8b4fe", "#60a5fa", "#64748b"]
    return rx.match(
        sector["color_index"].to(int),
        (0, _color_de(panel["color"])),
        *[(i + 1, color) for i, color in enumerate(secundarios)],
        theme.MUTED,
    )


def _leyenda_sector(panel, sector) -> rx.Component:
    return rx.hstack(
        rx.box(width="6px", height="6px", border_radius="50%",
               background=_color_sector(panel, sector), flex_shrink="0"),
        rx.text(sector["x"], font_size="12px", color=theme.MUTED,
                title=sector["x"], overflow="hidden", text_overflow="ellipsis",
                white_space="nowrap", min_width="0"),
        rx.spacer(),
        rx.text(sector["porcentaje_texto"], font_size="12px", weight="medium",
                color=theme.TEXT, font_variant_numeric="tabular-nums", white_space="nowrap"),
        spacing="2", align="center", width="100%", min_width="0",
    )


def _circular(panel, anillo: bool) -> rx.Component:
    return rx.flex(
        rx.box(
            rx.recharts.pie_chart(
                rx.recharts.pie(
                    rx.foreach(
                        panel["datos_circulares"].to(list[dict]),
                        lambda sector: rx.recharts.cell(
                            fill=_color_sector(panel, sector), stroke=theme.BG_WINDOW,
                        ),
                    ),
                    data=panel["datos_circulares"],
                    data_key="y", name_key="x", cx="50%", cy="50%",
                    inner_radius="76%" if anillo else 0, outer_radius="92%",
                    padding_angle=2 if anillo else 1,
                    start_angle=90, end_angle=-270,
                    stroke=theme.BG_WINDOW, is_animation_active=False,
                ),
                _bocadillo(), height=190, width="100%",
            ),
            rx.cond(
                anillo,
                rx.vstack(
                    rx.text(panel["datos_circulares"].to(list[dict])[0]["porcentaje_texto"],
                            class_name="nx-num",
                            font_size="23px", weight="medium", color=theme.TEXT,
                            letter_spacing="-.04em"),
                    rx.text("Mayor tramo", font_size="10px", color=theme.MUTED),
                    position="absolute", inset="0", align="center", justify="center",
                    pointer_events="none", spacing="1",
                ),
            ),
            position="relative", width="100%", min_width="0",
            style={"@container metrica (min-width: 430px)": {"width": "47%", "flex_shrink": "0"}},
        ),
        rx.vstack(
            rx.foreach(panel["datos_circulares"].to(list[dict]),
                       lambda sector: _leyenda_sector(panel, sector)),
            spacing="3", width="100%", min_width="0", justify="center",
        ),
        direction="column", align="center", gap="12px", width="100%",
        style={"@container metrica (min-width: 430px)": {"flex_direction": "row", "gap": "20px"}},
    )


def _grafica(panel) -> rx.Component:
    color = _color_de(panel["color"])
    margen = {"top": 10, "right": 12, "bottom": 0, "left": -6}
    return rx.match(
        panel["forma"].to(str),
        ("donut", _circular(panel, True)),
        ("circular", _circular(panel, False)),
        ("linea", rx.recharts.line_chart(
            *_ejes(panel["unidad_grafica"]),
            rx.recharts.line(
                data_key="y", name=panel["medida_nombre"], unit=panel["unidad_grafica"],
                stroke=color, stroke_width=2.5, type_="monotone",
                dot=False, connect_nulls=False, is_animation_active=False,
                active_dot={"r": 4, "stroke": theme.BG_WINDOW, "strokeWidth": 2},
            ),
            data=panel["datos"], height="100%", width="100%", margin=margen,
        )),
        ("area", rx.recharts.area_chart(
            rx.el.svg.defs(
                rx.el.svg.linear_gradient(
                    rx.el.svg.stop(offset="0%", stop_color=color, stop_opacity=0.30),
                    rx.el.svg.stop(offset="95%", stop_color=color, stop_opacity=0.015),
                    id="metric-gradient-" + panel["id"].to(str),
                    x1="0", y1="0", x2="0", y2="1",
                ),
            ),
            *_ejes(panel["unidad_grafica"]),
            rx.recharts.area(
                data_key="y", name=panel["medida_nombre"], unit=panel["unidad_grafica"],
                stroke=color, stroke_width=2.5, type_="monotone",
                fill="url(#metric-gradient-" + panel["id"].to(str) + ")",
                connect_nulls=False, is_animation_active=False,
                active_dot={"r": 4, "stroke": theme.BG_WINDOW, "strokeWidth": 2},
            ),
            data=panel["datos"], height="100%", width="100%", margin=margen,
        )),
        rx.recharts.bar_chart(
            *_ejes(panel["unidad_grafica"]),
            rx.recharts.bar(
                data_key="y", name=panel["medida_nombre"], unit=panel["unidad_grafica"],
                fill=color, radius=[5, 5, 0, 0], is_animation_active=False,
            ),
            data=panel["datos"], height="100%", width="100%", max_bar_size=28,
            bar_category_gap="22%", margin=margen,
        ),
    )


def _accion_icono(icono, titulo, evento, **props) -> rx.Component:
    props.setdefault("size", "1")
    return rx.icon_button(
        rx.icon(icono, size=14), title=titulo, aria_label=titulo,
        on_click=evento, variant="ghost", color_scheme="gray",
        cursor="pointer", **props,
    )


def _controles_panel(panel) -> rx.Component:
    return rx.cond(
        AuthState.puede_ajustes,
        rx.box(
            actions_menu(
                on_edit=MetricasState.editar_panel(panel["id"]),
                edit_label="Configurar panel",
                on_remove=MetricasState.borrar_panel(panel["id"]),
                remove_label="Quitar · se puede deshacer", remove_style="reversible",
                extra_items=(
                    ("copy", "Duplicar", MetricasState.duplicar_panel(panel["id"])),
                    ("arrow-up", "Mover arriba", MetricasState.mover_panel(panel["id"], -1)),
                    ("arrow-down", "Mover abajo", MetricasState.mover_panel(panel["id"], 1)),
                ),
            ),
            flex_shrink="0",
            style={"& [data-nx-menu]": {"width": "44px", "height": "44px", "margin": "-8px"}},
        ),
    )


def _dato_secundario(label, valor) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color=theme.MUTED),
        rx.text(valor, size="1", color=theme.TEXT, weight="medium",
                font_family=theme.FONT_MONO),
        spacing="1", align="start", min_width="0",
    )


def _panel(panel, editable: bool = True) -> rx.Component:
    color = _color_de(panel["color"])
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon(panel["icono"].to(str), size=17, color=color, flex_shrink="0"),
                rx.vstack(
                    rx.text(panel["titulo"], font_size="14px", weight="medium",
                            color=theme.TEXT, line_height="1.45", title=panel["titulo"],
                            overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
                            max_width="100%"),
                    spacing="1", align="start", min_width="0", flex="1",
                ),
                _controles_panel(panel) if editable else rx.fragment(),
                width="100%", align="center", spacing="3",
            ),
            rx.hstack(
                rx.text(panel["valor_texto"], color=theme.TEXT,
                        class_name="nx-num",
                        font_size="32px", font_weight="500", letter_spacing="-.055em",
                        line_height="1.15", font_variant_numeric="tabular-nums"),
                rx.text(panel["valor_etiqueta"], font_size="11px", color=theme.MUTED,
                        padding_bottom="3px"),
                spacing="3", align="end", width="100%", padding_top="2px", wrap="wrap",
            ),
            rx.cond(
                panel["vacio"],
                rx.vstack(
                    rx.icon("chart-no-axes-combined", size=24, color=theme.MUTED),
                    rx.text(rx.cond(panel["error"] != "", "Revisa la configuración",
                                    "Sin datos en este periodo"), size="2", color=theme.TEXT),
                    rx.text(rx.cond(panel["error"] != "", panel["error"], "Prueba otro periodo o una fuente diferente."),
                            size="1", color=theme.MUTED, text_align="center", max_width="300px"),
                    align="center", justify="center", spacing="3", width="100%", min_height="200px",
                ),
                rx.box(
                    _grafica(panel), width="100%", min_width="0",
                    height=rx.cond(panel["es_circular"], "auto", "220px"),
                    padding_top="4px",
                    style={"@container metrica (min-width: 430px)": {
                        "height": rx.cond(panel["es_circular"], "auto", "240px"),
                    }},
                ),
            ),
            rx.hstack(
                rx.text(panel["periodo_texto"], font_size="11px", color=theme.MUTED,
                        line_height="1.5", min_width="0"),
                rx.spacer(),
                rx.text(panel["agrupacion_texto"], font_size="11px", color=theme.MUTED,
                        text_align="right", line_height="1.5", min_width="0"),
                spacing="3", width="100%", align="start", padding_top="2px",
            ),
            rx.el.details(
                rx.el.summary(
                    rx.hstack(
                        rx.text(panel["maximo_etiqueta"], " ", panel["maximo_texto"],
                                font_size="11px", color=theme.MUTED),
                        rx.spacer(),
                        rx.text("Detalles", font_size="11px", color=theme.MUTED),
                        rx.icon("chevron-down", size=13, color=theme.MUTED,
                                class_name="analytics-chevron"),
                        spacing="2", align="center", width="100%",
                    ),
                    cursor="pointer", list_style_type="none", min_height="40px",
                    display="flex", align_items="center",
                    style={"&::-webkit-details-marker": {"display": "none"},
                           "&:focus-visible": {"outline": f"2px solid {theme.ACCENT}", "outline_offset": "3px"}},
                ),
                rx.vstack(
                    rx.grid(
                        _dato_secundario(panel["minimo_etiqueta"], panel["minimo_texto"]),
                        _dato_secundario(panel["maximo_etiqueta"], panel["maximo_texto"]),
                        _dato_secundario(panel["ultimo_etiqueta"], panel["ultimo_texto"]),
                        columns="3", spacing="3", width="100%",
                    ),
                    rx.text(panel["medida_nombre"], " · ", panel["muestras_texto"], " · ", panel["ultima_lectura_texto"],
                            font_size="11px", color=theme.MUTED, line_height="1.5"),
                    rx.cond(panel["es_circular"],
                            rx.text(panel["circular_detalle"], size="1", color=theme.MUTED)),
                    spacing="3", padding="6px 0 12px", width="100%", align="start",
                ),
                width="100%", border_top=f"1px solid {theme.BORDER}",
                style={"&[open] .analytics-chevron": {"transform": "rotate(180deg)"}},
            ),
            spacing="3", align="start", width="100%",
        ),
        padding=["18px 18px 6px", "22px 22px 6px"], border_radius="18px",
        background=f"linear-gradient(160deg, {theme.alpha(theme.ACCENT, .022)}, transparent 55%), {theme.BG_CARD}",
        border=f"1px solid {theme.BORDER}", min_width="0", width="100%",
        grid_column=rx.cond(panel["ancho"] == "amplio", "1 / -1", "auto") if editable else "auto",
        container_type="inline-size", container_name="metrica",
        transition="border-color .18s ease", _hover={"border_color": theme.BORDER_STRONG},
    )


def _selector(opciones, valor, cambio, placeholder="Selecciona") -> rx.Component:
    return rx.select.root(
        rx.select.trigger(placeholder=placeholder, width="100%", size="2"),
        select_content(rx.foreach(
            opciones, lambda opcion: rx.select.item(
                opcion["nombre"], value=opcion["id"],
            ),
        )),
        value=valor, on_change=cambio, width="100%",
    )


def _seccion_editor(numero: str, titulo: str, *children) -> rx.Component:
    return rx.vstack(
        rx.text(titulo, font_size="13px", weight="medium", color=theme.TEXT),
        *children,
        align="start", spacing="4", width="100%", min_width="0",
    )


def _opcion_formato(clave: str, nombre: str, icono: str) -> rx.Component:
    elegido = MetricasState.ed_forma == clave
    return rx.button(
        rx.icon(icono, size=20),
        rx.text(nombre, size="1"),
        on_click=MetricasState.set_ed_forma(clave),
        variant="surface", color_scheme="gray", height="72px",
        display="flex", flex_direction="column", gap="7px", padding="10px 4px",
        background=rx.cond(elegido, theme.alpha(theme.ACCENT, .10), "transparent"),
        border=rx.cond(elegido, f"1px solid {theme.ACCENT}", f"1px solid {theme.BORDER}"),
        color=rx.cond(elegido, theme.ACCENT, theme.MUTED),
        border_radius="11px", cursor="pointer", aria_pressed=elegido,
        _hover={"background": theme.BG_CARD_HOVER},
    )


def _editor_apariencia() -> rx.Component:
    return _seccion_editor(
        "02", "Dale forma",
        rx.grid(
            *[_opcion_formato(*formato) for formato in _FORMATOS],
            columns="5", spacing="1", width="100%",
        ),
        rx.cond(
            (MetricasState.ed_forma == "donut") | (MetricasState.ed_forma == "circular"),
            rx.text(
                rx.cond(
                    MetricasState.ed_es_serie,
                    "Los sectores muestran cuántas muestras hay en cada rango de valores.",
                    "Los sectores muestran la distribución de eventos del periodo.",
                ),
                size="1", color=theme.MUTED, line_height="1.6",
            ),
        ),
        rx.flex(
            field(
                "Color",
                rx.hstack(
                    *[
                        rx.icon_button(
                            rx.icon(
                                rx.cond(MetricasState.ed_color == clave, "check", "circle"),
                                size=14,
                            ),
                            title=nombre, aria_label=nombre,
                            aria_pressed=MetricasState.ed_color == clave,
                            on_click=MetricasState.set_ed_color(clave),
                            width="44px", height="44px", border_radius="50%",
                            color=_COLORES[clave],
                            background=theme.alpha(_COLORES[clave], .16),
                            border=rx.cond(
                                MetricasState.ed_color == clave,
                                f"2px solid {_COLORES[clave]}", "2px solid transparent",
                            ),
                            cursor="pointer",
                        )
                        for clave, nombre in _NOMBRES_COLOR.items()
                    ],
                    spacing="2",
                ),
            ),
            field(
                "Ancho del panel",
                _selector(
                    [{"id": "normal", "nombre": "Media fila"},
                     {"id": "amplio", "nombre": "Fila completa"}],
                    MetricasState.ed_ancho, MetricasState.set_ed_ancho,
                ),
            ),
            gap="18px", width="100%", direction=rx.breakpoints(initial="column", lg="row"),
        ),
    )


def _editor_tiempo() -> rx.Component:
    return _seccion_editor(
        "03", "Tiempo y cálculo",
        rx.grid(
            field("Periodo", _selector(
                [{"id": "relativo", "nombre": "Últimos días"},
                 {"id": "personalizado", "nombre": "Fechas concretas"}],
                MetricasState.ed_periodo, MetricasState.set_ed_periodo,
            )),
            rx.cond(
                MetricasState.ed_periodo == "relativo",
                field("Ventana de tiempo", _selector(
                    [{"id": str(d), "nombre": "Últimas 24 horas" if d == 1 else f"Últimos {d} días"}
                     for d in (1, 7, 30, 90, 365)],
                    MetricasState.ed_dias.to_string(), MetricasState.set_ed_dias,
                )),
            ),
            columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%",
        ),
        rx.cond(
            MetricasState.ed_periodo == "personalizado",
            rx.grid(
                field("Desde", rx.input(
                    type="datetime-local", value=MetricasState.ed_desde,
                    on_change=MetricasState.set_ed_desde, width="100%",
                    aria_label="Fecha y hora de inicio",
                    style={"color_scheme": "dark"},
                )),
                field("Hasta (sin incluir)", rx.input(
                    type="datetime-local", value=MetricasState.ed_hasta,
                    on_change=MetricasState.set_ed_hasta, width="100%",
                    aria_label="Fecha y hora de fin",
                    style={"color_scheme": "dark"},
                )),
                columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%",
            ),
        ),
        rx.grid(
            field("Agrupar datos", _selector(
                MetricasState.agrupaciones_ui,
                MetricasState.ed_agrupacion, MetricasState.set_ed_agrupacion,
            )),
            field("Cálculo", _selector(
                MetricasState.operaciones_ui,
                MetricasState.ed_operacion, MetricasState.set_ed_operacion,
            )),
            columns=rx.breakpoints(initial="1", sm="2"), spacing="3", width="100%",
        ),
        rx.cond(
            MetricasState.ed_agrupacion == "intervalo",
            field(
                "Duración del intervalo · minutos",
                rx.input(
                    type="number", min=5, max=1440,
                    value=MetricasState.ed_intervalo_minutos.to_string(),
                    on_change=MetricasState.set_ed_intervalo_minutos,
                    width="100%", aria_label="Intervalo en minutos",
                ),
                hint="De 5 a 1.440 minutos. Por ejemplo, 15 para cada cuarto de hora.",
            ),
        ),
        rx.vstack(
            rx.hstack(
                rx.icon("clock-3", size=15, color=theme.MUTED),
                rx.text("Solo una franja horaria", size="2", color=theme.TEXT),
                rx.spacer(),
                rx.switch(checked=MetricasState.ed_franja,
                          on_change=MetricasState.set_ed_franja,
                          aria_label="Filtrar por franja horaria"),
                width="100%", align="center", spacing="2",
            ),
            rx.cond(
                MetricasState.ed_franja,
                rx.vstack(
                    rx.grid(
                        field("Hora de inicio", rx.input(
                            type="time", value=MetricasState.ed_hora_desde,
                            on_change=MetricasState.set_ed_hora_desde,
                            aria_label="Hora inicial de la franja", width="100%",
                            style={"color_scheme": "dark"},
                        )),
                        field("Hora de fin", rx.input(
                            type="time", value=MetricasState.ed_hora_hasta,
                            on_change=MetricasState.set_ed_hora_hasta,
                            aria_label="Hora final de la franja", width="100%",
                            style={"color_scheme": "dark"},
                        )),
                        columns="2", spacing="3", width="100%",
                    ),
                    rx.text(
                        "Se aplica cada día. 14:00–15:00 aísla una hora; "
                        "22:00–06:00 incluye la madrugada. Hora local del servidor.",
                        size="1", color=theme.MUTED, line_height="1.6",
                    ),
                    spacing="2", width="100%",
                ),
            ),
            spacing="3", width="100%", padding="14px", border_radius="12px",
            background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
        ),
    )


def _preview_editor() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Vista previa", font_size="10px", weight="medium",
                    class_name="nx-label", color=theme.MUTED),
            rx.spacer(),
            rx.button(
                rx.icon("refresh-cw", size=14),
                rx.cond(MetricasState.preview_desactualizada, "Actualizar vista", "Actualizar"),
                on_click=MetricasState.actualizar_preview, height="40px",
                size="1", variant="surface", color_scheme="gray", cursor="pointer",
            ),
            width="100%", align="center", spacing="2",
        ),
        rx.cond(MetricasState.preview, _panel(MetricasState.preview, editable=False)),
        rx.text("Usa tu histórico real. Nada se guarda hasta confirmar.",
                font_size="11px", color=theme.MUTED, line_height="1.6"),
        spacing="3", width="100%", min_width="0", align="start",
    )


def _editor() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.hstack(
                rx.vstack(
                    rx.text("Tu panel", font_size="9px", class_name="nx-label",
                            color=theme.ACCENT, weight="medium"),
                    rx.dialog.title(
                        rx.cond(MetricasState.panel_en_edicion == "nuevo",
                                "Una nueva perspectiva", "Ajusta cada detalle"),
                        margin="0", font_size=["20px", "23px"], font_weight="500",
                        letter_spacing="-.04em", color=theme.TEXT,
                    ),
                    rx.dialog.description(
                        "Elige qué ver, cómo verlo y con qué nivel de detalle.",
                        font_size="12px", color=theme.MUTED, margin="0",
                        display=rx.breakpoints(initial="none", sm="block"),
                    ),
                    spacing="1", align="start", min_width="0", flex="1",
                ),
                _accion_icono("x", "Cerrar editor", MetricasState.cerrar_editor,
                              width="44px", height="44px", flex_shrink="0"),
                width="100%", align="center", spacing="2",
                padding=["16px 18px", "22px 24px"],
                border_bottom=f"1px solid {theme.BORDER}", flex_shrink="0",
            ),
            rx.grid(
                rx.vstack(
                    rx.tabs.root(
                        rx.tabs.list(
                            rx.tabs.trigger("Datos", value="datos", flex="1", height="44px"),
                            rx.tabs.trigger("Diseño", value="diseno", flex="1", height="44px"),
                            rx.tabs.trigger("Periodo", value="tiempo", flex="1", height="44px"),
                            width="100%", size="2",
                        ),
                        rx.tabs.content(
                            _seccion_editor(
                                "01", "Qué quieres observar",
                                field("Fuente de datos",
                                    rx.select.root(
                                        rx.select.trigger(placeholder="Elige una medida", width="100%"),
                                        select_content(rx.foreach(
                                            MetricasState.catalogo_agrupado,
                                            lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                                        )),
                                        value=MetricasState.ed_medida,
                                        on_change=MetricasState.set_ed_medida, width="100%",
                                    ),
                                ),
                                field("Nombre del panel",
                                    rx.input(
                                        value=MetricasState.ed_titulo,
                                        on_change=MetricasState.set_ed_titulo,
                                        placeholder="Nombre de la medida", width="100%", max_length=120,
                                    ),
                                    hint="Déjalo vacío para usar el nombre de la fuente.",
                                ),
                                rx.hstack(
                                    rx.icon("database", size=15, color=theme.MUTED, flex_shrink="0"),
                                    rx.text("Las fuentes disponibles proceden del histórico de tu casa.",
                                            font_size="12px", color=theme.MUTED, line_height="1.7"),
                                    spacing="2", align="start", padding_top="8px",
                                ),
                            ),
                            value="datos", padding_top="24px",
                        ),
                        rx.tabs.content(_editor_apariencia(), value="diseno", padding_top="24px"),
                        rx.tabs.content(_editor_tiempo(), value="tiempo", padding_top="24px"),
                        default_value="datos", width="100%", min_width="0",
                    ),
                    rx.button(
                        rx.icon("eye", size=16),
                        rx.cond(MetricasState.preview_movil_abierta, "Ocultar vista previa", "Ver vista previa"),
                        on_click=MetricasState.alternar_preview_movil,
                        aria_expanded=MetricasState.preview_movil_abierta,
                        aria_controls="analytics-editor-preview",
                        variant="surface", color_scheme="gray", height="44px", width="100%",
                        cursor="pointer", display=rx.breakpoints(initial="flex", md="none"),
                    ),
                    spacing="5", width="100%", min_width="0", align="start",
                ),
                rx.box(
                    _preview_editor(), id="analytics-editor-preview",
                    min_width="0", width="100%", align_self="start",
                    style={
                        "display": rx.cond(MetricasState.preview_movil_abierta, "block", "none"),
                        "@media screen and (min-width: 1024px)": {
                            "display": "block", "position": "sticky", "top": "0",
                        },
                    },
                ),
                columns=rx.breakpoints(initial="1", md="2"),
                spacing="6", padding=["18px", "24px"],
                overflow_y="auto", min_height="0", width="100%", flex="1",
                style={
                    "& .rt-TextFieldRoot, & [role='combobox']": {"min_height": "44px", "min_width": "0"},
                    "& input": {"min_width": "0", "font_size": "16px"},
                    "& .rt-TabsTrigger": {"cursor": "pointer"},
                },
            ),
            rx.vstack(
                rx.cond(
                    MetricasState.ed_error != "",
                    rx.text(MetricasState.ed_error, font_size="12px", color=theme.DANGER,
                            role="alert", width="100%", line_height="1.6"),
                ),
                rx.hstack(
                    rx.text("Cambios sin guardar", font_size="11px", color=theme.MUTED,
                            display=rx.breakpoints(initial="none", sm="block")),
                    rx.spacer(),
                    rx.button("Cancelar", on_click=MetricasState.cerrar_editor,
                              variant="surface", color_scheme="gray", cursor="pointer",
                              height="44px", padding="0 18px"),
                    rx.button(rx.icon("check", size=16), "Guardar panel",
                              on_click=MetricasState.guardar_panel, cursor="pointer",
                              height="44px", padding="0 20px"),
                    spacing="3", width="100%", align="center",
                ),
                spacing="3", width="100%", padding=["14px 18px", "18px 24px"],
                border_top=f"1px solid {theme.BORDER}", flex_shrink="0",
            ),
            max_width="1040px", width="calc(100vw - 24px)", padding="0",
            max_height="calc(100dvh - 32px)", height=["calc(100dvh - 32px)", "auto"],
            background=theme.BG_WINDOW, border=f"1px solid {theme.BORDER_STRONG}",
            border_radius=["16px", "20px"], box_shadow="0 32px 120px rgba(0,0,0,.7)",
            overflow="hidden", display="flex", flex_direction="column",
        ),
        open=MetricasState.editor_abierto,
        on_open_change=MetricasState.cambiar_editor_abierto,
    )


def _equipo(e) -> rx.Component:
    return rx.hstack(
        rx.icon("server", size=16,
                color=rx.cond(e["en_metricas"], theme.ACCENT, theme.MUTED)),
        rx.vstack(
            rx.text(e["nombre"], size="2", color=theme.TEXT),
            rx.text(e["estado"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.switch(checked=e["en_metricas"],
                  on_change=lambda _: MetricasState.alternar_equipo(e["id"]),
                  aria_label=e["nombre"]),
        align="center", spacing="3", width="100%", min_width="0",
        padding="12px 14px", border_radius="12px",
        background=theme.BG_CARD, class_name="nx-card", border=f"1px solid {theme.BORDER}",
    )


def _equipos() -> rx.Component:
    return rx.cond(
        MetricasState.editando & AuthState.puede_ajustes,
        rx.vstack(
            rx.hstack(
                rx.icon("database", size=16, color=theme.ACCENT),
                rx.text("Fuentes del histórico", size="3", weight="medium", color=theme.TEXT),
                spacing="2", align="center",
            ),
            rx.text(
                "Activa los equipos cuya disponibilidad quieres registrar. "
                "Se guarda una muestra cada cinco minutos; el recuento total se guarda siempre.",
                size="2", color=theme.MUTED, line_height="1.6",
            ),
            rx.grid(
                rx.foreach(MetricasState.equipos, _equipo),
                columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                spacing="3", width="100%",
            ),
            spacing="3", width="100%", padding_top="24px", align="start",
        ),
    )


def _indicador(dato) -> rx.Component:
    color = _color_de(dato["color"])
    return rx.vstack(
        rx.hstack(
            rx.text(dato["label_corto"], font_size="12px", color=theme.MUTED,
                    line_height="1.45", min_width="0", white_space="nowrap", overflow="hidden", text_overflow="ellipsis"),
            rx.spacer(),
            rx.icon(dato["icono"].to(str), size=16, color=color, flex_shrink="0"),
            spacing="2", width="100%", align="center",
        ),
        rx.hstack(
            rx.text(dato["valor"], color=theme.TEXT, font_weight="500",
                    class_name="nx-num",
                    font_size=["28px", "32px"], letter_spacing="-.06em",
                    font_variant_numeric="tabular-nums", line_height="1.15"),
            rx.text(dato["unidad"], font_size="16px", color=theme.MUTED, padding_bottom="2px"),
            align="end", spacing="1", width="100%",
        ),
        rx.hstack(
            rx.box(width="4px", height="4px", border_radius="50%",
                   background=rx.cond(dato["obsoleto"], theme.WARNING, theme.MUTED),
                   flex_shrink="0"),
            rx.text(dato["lectura_corta"], font_size="10px",
                    color=rx.cond(dato["obsoleto"], theme.WARNING, theme.MUTED),
                    title=dato["detalle"], line_height="1.4"),
            spacing="2", align="center", width="100%",
        ),
        spacing="2", align="start", min_width="0", title=dato["label"].to(str) + " · " + dato["detalle"].to(str),
        padding=["14px", "20px"],
        background="rgba(255,255,255,.025)", border=f"1px solid {theme.BORDER}",
        border_radius="14px",
    )


def _cabecera() -> rx.Component:
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.hstack(
                    rx.icon("activity", size=15, color=theme.ACCENT),
                    rx.text("Analítica", font_size="10px", weight="medium",
                            class_name="nx-label", color=theme.ACCENT),
                    spacing="2", align="center",
                ),
                rx.heading("Salud de la casa", color=theme.TEXT, font_weight="500",
                           font_size=["28px", "32px", "36px"], letter_spacing="-.05em",
                           line_height="1.15"),
                rx.text("Temperaturas, recursos y actividad.",
                        font_size="13px", color=theme.MUTED, line_height="1.6"),
                spacing="2", align="start", min_width="0",
            ),
            rx.hstack(
                _accion_icono("refresh-cw", "Actualizar lecturas", MetricasState.actualizar,
                              width="44px", height="44px", size="2"),
                rx.cond(AuthState.puede_ajustes,
                    rx.button(
                        rx.icon(rx.cond(MetricasState.editando, "check", "settings-2"), size=16),
                        rx.text(rx.cond(MetricasState.editando, "Listo", "Organizar"), display=rx.breakpoints(initial="none", xs="block")),
                        on_click=MetricasState.alternar_edicion,
                        variant="surface", color_scheme="gray", cursor="pointer",
                        height="44px", padding=["0", "0 15px"], width=["44px", "auto"], font_size="12px",
                        aria_label=rx.cond(MetricasState.editando, "Finalizar organización", "Organizar paneles"),
                    ),
                ),
                rx.cond(AuthState.puede_ajustes,
                    rx.button(
                        rx.icon("plus", size=16), "Añadir panel",
                        on_click=MetricasState.nuevo_panel, cursor="pointer",
                        height="44px", padding="0 16px", font_size="12px",
                        color=theme.BG_APP, background=theme.ACCENT,
                        _hover={"background": "#7dd3fc"},
                    ),
                ),
                spacing="2", align="center", flex_shrink="0", wrap="wrap",
            ),
            direction=rx.breakpoints(initial="column", md="row"),
            align=rx.breakpoints(initial="start", md="center"), justify="between",
            gap="18px", width="100%",
        ),
        rx.cond(
            MetricasState.indicadores_salud.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.text("Últimas lecturas", font_size="9px", class_name="nx-label",
                            weight="medium", color=theme.MUTED),
                    rx.spacer(),
                    rx.text("Muestreo cada 5 min", font_size="10px", color=theme.MUTED),
                    width="100%", align="center", spacing="2",
                ),
                rx.grid(
                    rx.foreach(MetricasState.indicadores_salud, _indicador),
                    columns=rx.breakpoints(initial="2", lg="4"),
                    spacing="3", width="100%",
                ),
                spacing="3", width="100%", align="start",
            ),
        ),
        spacing="5", width="100%", align="start",
    )


def _rango(clave: str, titulo: str) -> rx.Component:
    return rx.button(
        titulo, on_click=MetricasState.set_rango_global(clave),
        variant="ghost", color_scheme="gray", size="1",
        background=rx.cond(MetricasState.rango_global == clave, theme.alpha(theme.MUTED, .12), "transparent"),
        color=rx.cond(MetricasState.rango_global == clave, theme.TEXT, theme.MUTED),
        border_radius="7px", padding="0 13px", height="36px", min_width="48px",
        cursor="pointer", aria_pressed=MetricasState.rango_global == clave,
    )


def _categoria(categoria) -> rx.Component:
    elegida = MetricasState.filtro_paneles == categoria["id"]
    return rx.button(
        rx.text(categoria["nombre"], font_size="12px"),
        rx.text(categoria["cuantos"], font_size="10px", opacity=".6"),
        on_click=MetricasState.set_filtro_paneles(categoria["id"]),
        variant="ghost", color_scheme="gray", size="1",
        color=rx.cond(elegida, theme.ACCENT, theme.MUTED),
        border_bottom=rx.cond(elegida, f"2px solid {theme.ACCENT}", "2px solid transparent"),
        border_radius="0", height="44px", padding="0 14px", margin="0",
        white_space="nowrap", flex_shrink="0", cursor="pointer",
        aria_pressed=elegida,
    )


def _barra_periodo() -> rx.Component:
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.hstack(
                    rx.text("Tu histórico", font_size="17px", weight="medium",
                            color=theme.TEXT, letter_spacing="-.025em"),
                    rx.cond(MetricasState.editando, rx.badge("Organizando", size="1", variant="soft")),
                    spacing="2", align="center",
                ),
                rx.text(MetricasState.resumen_rango, font_size="11px", color=theme.MUTED),
                spacing="1", align="start",
            ),
            rx.box(
                rx.hstack(
                    _rango("panel", "Por panel"), _rango("1", "24 h"),
                    _rango("7", "7 días"), _rango("30", "30 días"), _rango("90", "90 días"),
                    spacing="1", padding="4px", border_radius="11px",
                    border=f"1px solid {theme.BORDER}", background="rgba(0,0,0,.12)",
                ),
                display=rx.breakpoints(initial="none", sm="block"), flex_shrink="0",
            ),
            rx.box(
                _selector(
                    [{"id": "panel", "nombre": "Periodo de cada panel"},
                     {"id": "1", "nombre": "Últimas 24 horas"},
                     {"id": "7", "nombre": "Últimos 7 días"},
                     {"id": "30", "nombre": "Últimos 30 días"},
                     {"id": "90", "nombre": "Últimos 90 días"}],
                    MetricasState.rango_global, MetricasState.set_rango_global,
                ),
                width="100%", display=rx.breakpoints(initial="block", sm="none"),
                style={"& button": {"min_height": "44px"}},
            ),
            direction=rx.breakpoints(initial="column", sm="row"),
            align=rx.breakpoints(initial="start", sm="center"), justify="between",
            gap="14px", width="100%",
        ),
        rx.box(
            rx.hstack(
                rx.foreach(MetricasState.categorias_paneles, _categoria),
                spacing="0", width="max-content", min_width="100%",
            ),
            overflow_x="auto", width="100%", min_width="0",
            border_bottom=f"1px solid {theme.BORDER}",
            style={"scrollbar_width": "thin", "scrollbar_color": f"{theme.BORDER_STRONG} transparent"},
        ),
        rx.cond(
            MetricasState.editando,
            rx.text(
                "Todos los paneles de esta categoría están visibles. Usa su menú para moverlos, duplicarlos o ajustarlos.",
                font_size="12px", color=theme.MUTED, line_height="1.6",
            ),
        ),
        spacing="4", width="100%", align="start",
    )


def _vacio() -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.icon("chart-area", size=32, color=theme.ACCENT),
            padding="22px", border_radius="22px",
            background=theme.alpha(theme.ACCENT, .08),
            border=f"1px solid {theme.alpha(theme.ACCENT, .20)}",
        ),
        rx.heading("Un tablero tan único como tu casa", size="5",
                   color=theme.TEXT, letter_spacing="-.025em", text_align="center"),
        rx.text(
            "Empieza con una selección de métricas disponibles o diseña tu primer "
            "panel. Tú eliges qué observar y cómo verlo.",
            size="2", color=theme.MUTED, max_width="420px", text_align="center",
            line_height="1.7",
        ),
        rx.cond(
            AuthState.puede_ajustes,
            rx.flex(
                rx.button(rx.icon("sparkles", size=16), "Crear tablero inicial",
                          on_click=MetricasState.crear_dashboard_base, cursor="pointer"),
                rx.button("Crear desde cero", on_click=MetricasState.nuevo_panel,
                          variant="surface", color_scheme="gray", cursor="pointer"),
                gap="12px", wrap="wrap", justify="center", padding_top="8px",
            ),
            rx.text("Una persona con permisos de ajustes puede añadir paneles.",
                    size="1", color=theme.MUTED),
        ),
        align="center", justify="center", spacing="4", width="100%", padding=["32px 18px", "54px 24px"],
        border=f"1px dashed {theme.BORDER_STRONG}", border_radius="18px",
        background=f"radial-gradient(ellipse at 50% 0%, {theme.alpha(theme.ACCENT, .04)}, transparent 65%)",
    )


def metricas_view() -> rx.Component:
    return rx.vstack(
        _cabecera(),
        rx.box(width="100%", height="1px",
               background=f"linear-gradient(90deg, {theme.alpha(theme.ACCENT, .20)}, {theme.BORDER} 40%, transparent)"),
        _barra_periodo(),
        rx.cond(
            MetricasState.hay_paneles,
            rx.vstack(
                rx.grid(
                    rx.foreach(MetricasState.paneles_visibles, lambda p: _panel(p)),
                    gap="16px", width="100%", align_items="start",
                    grid_template_columns="minmax(0, 1fr)",
                    style={"@container analitica (min-width: 850px)": {
                        "grid_template_columns": "repeat(2, minmax(0, 1fr))",
                    }},
                ),
                rx.cond(
                    MetricasState.paneles_filtrados_count == 0,
                    rx.text("No hay paneles en esta categoría.", size="2", color=theme.MUTED, padding="20px"),
                ),
                rx.cond(
                    MetricasState.hay_mas_paneles,
                    rx.button(
                        rx.icon("plus", size=15), "Mostrar más paneles",
                        on_click=MetricasState.mostrar_mas_paneles,
                        variant="surface", color_scheme="gray", height="44px",
                        padding="0 22px", font_size="12px", cursor="pointer",
                        align_self="center", margin_top="4px",
                    ),
                ),
                spacing="4", width="100%", align="start",
            ),
            _vacio(),
        ),
        _equipos(),
        rx.hstack(
            rx.icon("clock-3", size=12, color=theme.MUTED),
            rx.text("Consulta ", MetricasState.ultima_actualizacion,
                    " · Hora local del servidor", font_size="10px", color=theme.MUTED),
            rx.spacer(),
            rx.text("NOXUS", font_size="9px", letter_spacing=".18em", color=theme.MUTED, opacity=".55"),
            width="100%", spacing="2", align="center", wrap="wrap",
        ),
        _editor(),
        spacing="5", width="100%", max_width="1480px", min_width="0",
        container_type="inline-size", container_name="analitica",
        align="start", padding_bottom="24px", on_mount=MetricasState.on_load,
    )
