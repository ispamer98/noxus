import reflex as rx

from ...domains.security.state import SecurityState
from ...domains.notifications.state import PushState
from .components.form_dialog import styled_input
from . import theme
from .state import DashboardState

# Las cinco de Alarma/Grupos/Equipos/Mandos/Automatizaciones ya no tienen fila
# propia en el menú (viven detrás de "Ajustes", ver dashboard/views/
# settings_hub.py), pero SIGUEN siendo vistas de verdad — un widget "Ir a
# Equipos" o un enlace directo caen igual en ellas — así que su título entero
# se queda aquí para que la barra superior diga dónde se está.
VIEW_TITLES = {
    "overview": ("Resumen", "layout-dashboard"),
    "alarm": ("Alarma", "siren"),
    "groups": ("Grupos de Armado", "layers"),
    "floor_plan": ("Plano de Planta", "map"),
    "video_wall": ("Mural", "grid-2x2"),
    "cctv": ("CCTV", "video"),
    "access": ("Control de Accesos", "door-open"),
    "lights": ("Luces", "lightbulb"),
    "ir_remotes": ("Mandos", "gamepad-2"),
    "automations": ("Automatizaciones", "workflow"),
    "equipment": ("Equipos", "server"),
    "settings_hub": ("Ajustes", "settings"),
    "logs": ("Registros", "clipboard-list"),
}


def _view_title() -> rx.Component:
    return rx.box(
        rx.match(
            DashboardState.active_view,
            *[
                (view_id, rx.text(title, size=rx.breakpoints(initial="3", md="4"), weight="bold", color=theme.TEXT, white_space="nowrap", overflow="hidden", text_overflow="ellipsis"))
                for view_id, (title, _) in VIEW_TITLES.items()
            ],
            rx.text("Resumen", size=rx.breakpoints(initial="3", md="4"), weight="bold", color=theme.TEXT),
        ),
        min_width="0",
        overflow="hidden",
        flex="1",
    )


def _arm_toggle_icon() -> rx.Component:
    """Escudo clicable: arma/desarma el sistema. Sustituye al badge de texto
    ARMADO/DESARMADO — más compacto (cabe en móvil) y además es un atajo."""
    return rx.box(
        rx.icon(
            rx.cond(SecurityState.sistema_armado, "shield-check", "shield-off"),
            size=20,
            color=rx.cond(SecurityState.sistema_armado, theme.DANGER, theme.SUCCESS),
        ),
        on_click=SecurityState.conmutar_alarma,
        cursor="pointer",
        padding="8px",
        border_radius="8px",
        flex_shrink="0",
        _hover={"background": rx.cond(SecurityState.sistema_armado, theme.alpha(theme.DANGER, 0.12), theme.alpha(theme.SUCCESS, 0.12))},
        title=rx.cond(SecurityState.sistema_armado, "Sistema ARMADO — pulsa para desarmar", "Sistema DESARMADO — pulsa para armar"),
    )



# El nombre que sale en los avisos ("Ajustes de las notificaciones") vivía
# aquí, en un engranaje suelto siempre visible — se ha movido dentro de
# "Ajustes" (ver dashboard/views/settings_hub.py:_ajustes_avisos_dialog). Es
# exactamente el tipo de cosa que se toca una vez y no debía estar tentando a
# quien no debería tocarla en una barra que se ve todo el rato.
def _panel_dispositivo() -> rx.Component:
    """El chip de la barra: dice qué dispositivo es este y deja arreglarlo.

    Antes era un botón que lanzaba el alta directamente, así que si algo no
    cuadraba (el nombre mal, los avisos dejaron de llegar, se dio de alta dos
    veces) no había ningún sitio donde mirarlo ni arreglarlo. Ahora abre una
    ventanita con lo que hay y las tres cosas que se pueden hacer.

    Sin jerga a propósito: ni "suscripción", ni "endpoint", ni "service
    worker". Aquí se habla de "este dispositivo" y de "avisos"."""
    vinculado = PushState.current_user != ""
    return rx.popover.root(
        rx.popover.trigger(
            rx.hstack(
                rx.icon(
                    rx.cond(vinculado, "circle-user-round", "circle-user"),
                    size=20,
                    color=rx.cond(vinculado, theme.SUCCESS, theme.WARNING),
                    flex_shrink="0",
                ),
                rx.cond(
                    vinculado,
                    rx.text(PushState.current_user, size="2", color=theme.TEXT,
                            weight="medium", white_space="nowrap",
                            display=["none", "none", "block"]),
                    rx.text("Sin vincular", size="2", color=theme.MUTED,
                            white_space="nowrap", display=["none", "none", "block"]),
                ),
                cursor="pointer", align="center", spacing="2",
                padding=["6px", "6px", "6px 12px"],
                border_radius="999px", flex_shrink="0",
                background=theme.BG_CARD,
                border=f"1px solid {rx.cond(vinculado, theme.BORDER, theme.WARNING)}",
                title="Este dispositivo",
                _hover={"border_color": theme.BORDER_STRONG, "background": theme.BG_CARD_HOVER},
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.hstack(
                    rx.icon(rx.cond(vinculado, "bell-ring", "bell-off"), size=16,
                            color=rx.cond(vinculado, theme.SUCCESS, theme.WARNING),
                            flex_shrink="0"),
                    rx.text(
                        rx.cond(vinculado, "Este dispositivo recibe avisos",
                                "Este dispositivo no recibe avisos"),
                        size="2", weight="bold", color=theme.TEXT,
                    ),
                    spacing="2", align="center",
                ),
                rx.text(
                    rx.cond(
                        vinculado,
                        "Su nombre es el que aparece en los registros junto a todo lo "
                        "que se hace desde aquí.",
                        "Actívalo para recibir avisos y para que lo que hagas desde este "
                        "aparato quede identificado en los registros.",
                    ),
                    size="1", color=theme.MUTED,
                ),
                rx.cond(
                    PushState.aviso != "",
                    rx.text(PushState.aviso, size="1", color=theme.WARNING,
                            padding="8px", border_radius="8px", width="100%",
                            background=theme.alpha(theme.WARNING, 0.08)),
                ),
                rx.divider(border_color=theme.BORDER),
                rx.cond(
                    vinculado,
                    rx.vstack(
                        rx.text("NOMBRE DE ESTE DISPOSITIVO", size="1", color=theme.MUTED,
                                letter_spacing="0.05em", weight="bold"),
                        rx.hstack(
                            styled_input(
                                value=PushState.nombre_nuevo,
                                on_change=PushState.set_nombre_nuevo,
                                placeholder="Mi iPhone",
                                max_length=30, size="2",
                            ),
                            rx.button("Guardar", on_click=PushState.renombrar,
                                      size="2", variant="surface", flex_shrink="0"),
                            spacing="2", width="100%",
                        ),
                        rx.divider(border_color=theme.BORDER),
                        rx.button(
                            rx.icon("refresh-cw", size=14), "¿No te llegan los avisos?",
                            on_click=PushState.reactivar,
                            size="2", variant="soft", width="100%",
                        ),
                        rx.text("Vuelve a activarlos desde cero, sin perder el nombre.",
                                size="1", color=theme.MUTED),
                        rx.button(
                            rx.icon("log-out", size=14), "Desvincular este dispositivo",
                            on_click=PushState.desvincular,
                            size="2", variant="soft", color_scheme="red", width="100%",
                        ),
                        spacing="2", width="100%",
                    ),
                    rx.button(
                        rx.icon("bell-ring", size=14), "Activar los avisos aquí",
                        on_click=PushState.suscribir,
                        size="2", color_scheme="orange", width="100%",
                    ),
                ),
                spacing="3", width="100%",
            ),
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.BORDER_STRONG}",
            border_radius="12px",
            padding="16px",
            width="min(330px, 92vw)",
        ),
        on_open_change=PushState.abrir_panel,
    )


def topbar() -> rx.Component:
    return rx.hstack(
        _view_title(),
        _arm_toggle_icon(),
        rx.badge(
            rx.cond(SecurityState.puerta_abierta, "PUERTA ABIERTA", "PUERTA CERRADA"),
            color_scheme=rx.cond(SecurityState.puerta_abierta, "orange", "gray"),
            variant="surface",
            size="2",
            # !important necesario: los componentes Radix (Box/Flex/Badge...) traen su propio
            # display incondicional en su CSS base (.rt-Badge{display:inline-flex}, etc.), que
            # Emotion inserta con MENOS prioridad que ese CSS estático — sin !important, a igual
            # especificidad gana la regla de Radix y el elemento se ve en todos los anchos.
            display=["none !important", "none !important", "flex !important"],
            flex_shrink="0",
        ),
        rx.spacer(display=["none !important", "none !important", "flex !important"]),
        rx.el.span(
            id="nx-clock",
            display=["none !important", "none !important", "inline !important"],
            style={
                "font_family": theme.FONT_MONO,
                "font_size": "0.85rem",
                "color": theme.MUTED,
                "letter_spacing": "0.03em",
                "white_space": "nowrap",
            },
        ),
        rx.box(
            rx.icon("clipboard-list", size=18, color=theme.MUTED),
            on_click=DashboardState.set_view("logs"),
            cursor="pointer",
            padding="8px",
            border_radius="8px",
            flex_shrink="0",
            _hover={"background": theme.alpha(theme.ACCENT, 0.10)},
            title="Ver registros",
        ),
        _panel_dispositivo(),
        width="100%",
        align="center",
        spacing="3",
        padding=["10px 12px", "10px 12px", "14px 24px"],
        background=theme.BG_TOPBAR,
        border_bottom=f"1px solid {theme.BORDER}",
        backdrop_filter="blur(12px)",
        position="sticky",
        top="0",
        z_index="40",
        overflow_x="hidden",
    )
