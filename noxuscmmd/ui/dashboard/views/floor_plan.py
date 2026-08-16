"""
Vista "Plano": el plano de planta a tamaño completo, reutilizando
floor_plan_content() de ui/views/device_list.py tal cual (mismo componente
que ya usa el popover compacto de la vista clásica).

Lo único que añade esta vista es el botón de modo edición: por defecto el
plano es de solo lectura (cada marcador ejecuta su acción al pulsarlo) y solo
con "Recolocar iconos" activo se pueden arrastrar — así nadie mueve un icono
sin querer mientras usa el plano.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from ...views.device_list import (
    floor_plan_content, PLAN_COMMIT_SCRIPT, PLAN_RESET_SCRIPT, FLOOR_COLORS,
)
from .. import theme
from ..state import DashboardState
from ..components.floor_fields import FLOOR_ICON_OPTIONS
from ..components.icon_picker import icon_grid

_LEGEND = [
    ("triangle-alert", theme.DANGER, "En alarma: abierto — rojo parpadeando"),
    ("circle-dot", FLOOR_COLORS[""], "En reposo: el color que le pongas a cada uno"),
    ("lightbulb", theme.WARNING, "Luz encendida / puerta abriéndose"),
]


def _legend_item(icon: str, color: str, label: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=14, color=color),
        rx.text(label, size="1", color=theme.MUTED),
        spacing="2",
        align="center",
    )


def _color_swatch(clave: str, color: str, ref) -> rx.Component:
    return rx.popover.close(
        rx.box(
            width="18px", height="18px", border_radius="50%",
            background=color, cursor="pointer",
            border=f"1px solid {theme.BORDER_STRONG}",
            on_click=NodesState.set_floor_color(ref, clave),
            title=clave or "por defecto",
        ),
    )


def _color_picker(entry: dict) -> rx.Component:
    """Color del marcador EN REPOSO — el mismo criterio para las cuatro
    familias: sensor o puerta cerrada, luz apagada, cámara siempre (no tiene
    estado). Lo que el sistema sigue poniendo por su cuenta es el rojo
    parpadeante de alarma (abierto) y el ámbar de "luz encendida / puerta
    abriéndose": eso no se puede cambiar desde aquí a propósito, para que
    ningún ajuste estético pueda esconder un aviso. Ver device_list.py."""
    ref = entry["ref"].to(str)
    return rx.popover.root(
        rx.popover.trigger(
            rx.box(
                width="18px", height="18px", border_radius="50%",
                background=rx.match(
                    entry["color"].to(str),
                    *[(k, v) for k, v in FLOOR_COLORS.items() if k],
                    FLOOR_COLORS[""],
                ),
                border=f"1px solid {theme.BORDER_STRONG}",
                cursor="pointer", flex_shrink="0",
                title="Color del marcador",
            ),
        ),
        rx.popover.content(
            rx.hstack(
                *[_color_swatch(k, v, ref) for k, v in FLOOR_COLORS.items() if k],
                spacing="2",
            ),
            side="bottom", align="end",
            style={
                "padding": "8px", "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}", "border_radius": "10px",
            },
        ),
    )


def _placed_row(entry: dict) -> rx.Component:
    """Un elemento ya puesto en el plano: se le puede cambiar el icono al
    vuelo o quitarlo (quitarlo NO borra el elemento, solo deja de pintarse)."""
    return rx.hstack(
        rx.icon(entry["icon"].to(str), size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.text(entry["label"], size="2", color=theme.TEXT),
        rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray"),
        rx.spacer(),
        rx.box(
            icon_grid(
                entry["icon"].to(str),
                lambda icon: NodesState.set_floor_icon(entry["ref"].to(str), icon),
                FLOOR_ICON_OPTIONS,
            ),
            width="90px",
            flex_shrink="0",
        ),
        _color_picker(entry),
        # Integrado: en reposo se pinta solo el icono con un brillo suave, sin
        # aro ni fondo, como un piloto del propio aparato. Al abrirse/dispararse
        # recupera el aspecto llamativo — ver _quiet() en device_list.py.
        rx.icon(
            rx.cond(entry["subtle"], "sparkles", "circle"),
            size=15,
            color=rx.cond(entry["subtle"], theme.ACCENT, theme.MUTED),
            cursor="pointer",
            on_click=NodesState.toggle_floor_subtle(entry["ref"].to(str)),
            title=rx.cond(entry["subtle"], "Integrado en el plano", "Integrar en el plano"),
        ),
        rx.icon(
            "x", size=15, color=theme.DANGER, cursor="pointer",
            on_click=NodesState.remove_from_floor(entry["ref"].to(str)),
            title="Quitar del plano",
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="7px 10px",
        border_radius="8px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
    )


def _available_row(entry: dict) -> rx.Component:
    """Un elemento del sistema que todavía no está en el plano — al pulsarlo
    aparece en el centro, listo para arrastrarlo donde toque."""
    return rx.hstack(
        rx.icon(entry["icon"].to(str), size=15, color=theme.MUTED, flex_shrink="0"),
        rx.text(entry["label"], size="2", color=theme.TEXT),
        rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray"),
        rx.spacer(),
        rx.icon("plus", size=15, color=theme.SUCCESS, flex_shrink="0"),
        on_click=NodesState.add_to_floor(entry["ref"].to(str)),
        cursor="pointer",
        spacing="2",
        align="center",
        width="100%",
        padding="7px 10px",
        border_radius="8px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )


def _available_section(section: dict) -> rx.Component:
    """Un bloque por tipo (Sensores, Cámaras, Puertas, Luces) con lo que queda
    por colocar de esa familia — ver NodesState.floor_available_grouped.

    El .to(list[dict]) es obligatorio: el valor de una clave de dict llega sin
    tipo y rx.foreach no puede recorrerlo sin saber qué es."""
    items = section["items"].to(list[dict])
    return rx.vstack(
        rx.hstack(
            rx.text(
                section["kind_label"], size="1", color=theme.TEXT,
                weight="bold", letter_spacing="0.04em",
            ),
            rx.badge(items.length(), variant="soft", size="1", color_scheme="gray"),
            spacing="2",
            align="center",
        ),
        rx.foreach(items, _available_row),
        spacing="1",
        width="100%",
        align="start",
    )


def _editor_panel() -> rx.Component:
    return rx.vstack(
        rx.text("EN EL PLANO", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
        rx.cond(
            NodesState.floor_placed.length() > 0,
            rx.vstack(rx.foreach(NodesState.floor_placed, _placed_row), spacing="2", width="100%"),
            rx.text("Todavía no hay nada en el plano.", size="1", color=theme.MUTED, italic=True),
        ),
        rx.divider(opacity="0.1", margin_y="2"),
        rx.text("AÑADIR AL PLANO", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
        rx.cond(
            NodesState.floor_available.length() > 0,
            rx.vstack(
                rx.foreach(NodesState.floor_available_grouped, _available_section),
                spacing="3", width="100%",
            ),
            rx.text("Ya está todo el sistema en el plano.", size="1", color=theme.MUTED, italic=True),
        ),
        spacing="2",
        width="100%",
        max_width="720px",
        padding="14px",
        border_radius="12px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER_STRONG}",
    )


def floor_plan_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.cond(
                DashboardState.editing_floor_plan,
                rx.hstack(
                    rx.icon("move", size=15, color=theme.WARNING),
                    rx.text(
                        'Arrastra los iconos y pulsa "Listo" para guardar',
                        size="2", color=theme.WARNING, weight="medium",
                    ),
                    spacing="2", align="center",
                ),
                rx.fragment(),
            ),
            rx.spacer(),
            rx.cond(
                DashboardState.editing_floor_plan,
                rx.button(
                    rx.icon("check", size=14), "Listo",
                    # Aquí es donde se GRABA: el script devuelve todas las
                    # posiciones movidas y save_floor_positions las escribe de
                    # una vez. Antes cada suelta guardaba por su cuenta.
                    on_click=[
                        rx.call_script(
                            PLAN_COMMIT_SCRIPT,
                            callback=NodesState.save_floor_positions,
                        ),
                        DashboardState.toggle_editing_floor_plan,
                    ],
                    size="1", variant="solid", color_scheme="green",
                ),
                # Discreto a propósito: el plano se usa mucho más de lo que se
                # edita, así que el botón se mantiene tenue hasta pasar por
                # encima (mismo criterio que el enlace al panel en la clásica).
                rx.hstack(
                    rx.icon("pencil", size=13, color=theme.MUTED),
                    rx.text("Editar plano", size="1", color=theme.MUTED),
                    on_click=[
                        rx.call_script(PLAN_RESET_SCRIPT),
                        DashboardState.toggle_editing_floor_plan,
                    ],
                    cursor="pointer",
                    spacing="1",
                    align="center",
                    padding="5px 9px",
                    border_radius="8px",
                    opacity="0.55",
                    transition="opacity 0.15s ease, background 0.15s ease",
                    _hover={"opacity": "1", "background": theme.BG_CARD},
                ),
            ),
            width="100%",
            max_width="720px",
            align="center",
            wrap="wrap",
        ),
        rx.box(
            floor_plan_content(),
            width="100%",
            max_width="720px",
        ),
        rx.cond(DashboardState.editing_floor_plan, _editor_panel(), rx.fragment()),
        rx.hstack(
            *[_legend_item(icon, color, label) for icon, color, label in _LEGEND],
            spacing="4",
            wrap="wrap",
            padding_top="2",
        ),
        spacing="4",
        width="100%",
        align="center",
    )
