"""
La navegación principal del panel: el menú lateral en escritorio
(`sidebar()`) y la barra inferior en móvil (`mobile_bottom_nav()`) — dos
componentes distintos porque en pantallas estrechas un lateral de 232px no
cabe, pero comparten la misma lista `NAV_ITEMS` para que nunca se desincronicen
entre sí.

`topbar.py` tiene la tabla hermana `VIEW_TITLES`: esta de aquí es solo lo que
tiene fila propia en el menú (cinco vistas); esa otra es TODAS las vistas que
existen, incluidas las que solo se llega por dentro de Ajustes. Buscar aquí un
título perdido es buscar en el sitio equivocado.
"""
import reflex as rx

from . import theme
from .state import DashboardState

# (view_id, icon, etiqueta) — lo mínimo posible, para que cualquiera —
# incluida una persona mayor que no ha tocado un ordenador en su vida— vea
# de un vistazo TODO lo que hay y no se pierda. El criterio no es "qué se usa
# alguna vez" sino "qué necesita su PROPIA pestaña":
#
#   Resumen  → todo lo accionable de la casa (luces, puertas, equipos,
#              mandos...), en accesos rápidos agrupados. Es la pantalla en la
#              que se vive.
#   Plano    → el mapa de la casa, tocar para actuar. Vistoso y rápido.
#   Mural    → todas las cámaras colocadas en una rejilla, igual de vistoso
#              y directo que el Plano — por eso tiene fila propia y no está
#              detrás de Ajustes ni dentro de CCTV.
#   Equipos  → la única "gestión" que se queda a la vista, porque es la que
#              más se usa día a día (apagar el PC, entrar por RDP).
#   Ajustes  → todo lo demás: Alarma, Grupos, Accesos, CCTV, Luces (dar de
#              alta/editar), Mandos, Automatizaciones. Instalar/configurar
#              una vez, no tocar más — para quien de verdad sepa lo que hace
#              (ver dashboard/views/settings_hub.py).
#
# Luces y Registros YA NO tienen fila propia: encender una luz concreta es un
# acceso rápido del Resumen, y Registros ya tiene su propio icono fijo en la
# barra de arriba (ver topbar.py) — repetirlo aquí era la misma puerta dos
# veces. Ninguna vista desaparece ni cambia de id: solo cambia desde dónde se
# llega a ella, así que los widgets "Ir a..." del Resumen y cualquier
# automatización que ya apuntara a alguna de estas siguen funcionando igual.
NAV_ITEMS = [
    ("overview", "layout-dashboard", "Resumen"),
    ("floor_plan", "map", "Plano"),
    ("video_wall", "grid-2x2", "Mural"),
    ("equipment", "server", "Equipos"),
    ("settings_hub", "settings", "Ajustes"),
]


def _nav_item(view_id: str, icon: str, label: str) -> rx.Component:
    # "Ajustes" se marca activo también estando DENTRO de una de las cinco
    # pantallas de configuración que agrupa (ver DashboardState.settings_hub_
    # active) — si no, entrar en "Equipos" desde ahí dejaría el menú entero
    # sin ninguna fila resaltada.
    is_active = (
        DashboardState.settings_hub_active if view_id == "settings_hub"
        else DashboardState.active_view == view_id
    )
    return rx.hstack(
        rx.box(
            width="3px",
            height="20px",
            border_radius="2px",
            background=rx.cond(is_active, theme.ACCENT, "transparent"),
            flex_shrink="0",
        ),
        rx.icon(
            icon,
            size=18,
            color=rx.cond(is_active, theme.ACCENT, theme.MUTED),
            flex_shrink="0",
        ),
        rx.cond(
            ~DashboardState.sidebar_collapsed,
            rx.text(
                label,
                size="2",
                weight=rx.cond(is_active, "bold", "medium"),
                color=rx.cond(is_active, theme.TEXT, theme.MUTED),
                white_space="nowrap",
            ),
        ),
        on_click=DashboardState.set_view(view_id),
        cursor="pointer",
        align="center",
        spacing="3",
        width="100%",
        padding_y="10px",
        padding_right="3",
        border_radius="8px",
        background=rx.cond(is_active, theme.alpha(theme.ACCENT, 0.10), "transparent"),
        _hover={"background": theme.alpha(theme.ACCENT, 0.06)},
        title=label,
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("shield-half", size=22, color=theme.ACCENT, flex_shrink="0"),
                rx.cond(
                    ~DashboardState.sidebar_collapsed,
                    rx.vstack(
                        rx.text("NOXUS", size="3", weight="bold", letter_spacing="0.12em", color=theme.TEXT),
                        rx.text("CONTROL CENTER", size="1", color=theme.MUTED, letter_spacing="0.08em"),
                        spacing="0",
                    ),
                ),
                align="center",
                spacing="3",
                width="100%",
                padding="18px 16px",
            ),
            rx.divider(border_color=theme.BORDER),
            rx.vstack(
                *[_nav_item(v, i, l) for v, i, l in NAV_ITEMS],
                spacing="1",
                width="100%",
                padding="10px",
            ),
            rx.spacer(),
            rx.divider(border_color=theme.BORDER),
            rx.vstack(
                rx.hstack(
                    rx.icon(
                        rx.cond(DashboardState.sidebar_collapsed, "chevrons-right", "chevrons-left"),
                        size=16,
                        color=theme.MUTED,
                    ),
                    rx.cond(
                        ~DashboardState.sidebar_collapsed,
                        rx.text("Colapsar", size="1", color=theme.MUTED),
                    ),
                    on_click=DashboardState.toggle_sidebar,
                    cursor="pointer",
                    spacing="3",
                    align="center",
                    padding="8px",
                    width="100%",
                    _hover={"opacity": "0.7"},
                ),
                spacing="1",
                width="100%",
                padding="10px",
            ),
            height="100%",
            width="100%",
            spacing="0",
        ),
        width=rx.cond(DashboardState.sidebar_collapsed, "68px", "232px"),
        min_width=rx.cond(DashboardState.sidebar_collapsed, "68px", "232px"),
        height="100vh",
        position="sticky",
        top="0",
        background=theme.BG_SIDEBAR,
        border_right=f"1px solid {theme.BORDER}",
        transition="width 0.16s ease, min-width 0.16s ease",
        overflow="hidden",
        z_index="50",
        # En móvil la navegación pasa a la barra inferior (mobile_bottom_nav).
        # !important: .rt-Box trae display:block incondicional en su CSS base, con más
        # prioridad de cascada que el estilo condicional que genera Emotion — sin
        # !important esta regla pierde y el sidebar se queda visible en cualquier ancho.
        display=["none !important", "none !important", "block !important"],
    )


# Etiquetas cortas solo para la barra inferior (columnas estrechas); el
# sidebar de escritorio usa la etiqueta completa de NAV_ITEMS.
_MOBILE_SHORT_LABEL = {
    "floor_plan": "Plano",
}


def _mobile_nav_item(view_id: str, icon: str, label: str) -> rx.Component:
    is_active = (
        DashboardState.settings_hub_active if view_id == "settings_hub"
        else DashboardState.active_view == view_id
    )
    short_label = _MOBILE_SHORT_LABEL.get(view_id, label)
    return rx.vstack(
        rx.icon(icon, size=18, color=rx.cond(is_active, theme.ACCENT, theme.MUTED)),
        rx.text(
            short_label,
            size="1",
            color=rx.cond(is_active, theme.ACCENT, theme.MUTED),
            weight=rx.cond(is_active, "bold", "medium"),
            white_space="nowrap",
        ),
        on_click=DashboardState.set_view(view_id),
        cursor="pointer",
        align="center",
        justify="center",
        spacing="1",
        flex_shrink="0",
        min_width="58px",
        padding_y="2",
    )


def mobile_bottom_nav() -> rx.Component:
    return rx.hstack(
        *[_mobile_nav_item(v, i, l) for v, i, l in NAV_ITEMS],
        width="100%",
        align="center",
        # space-evenly, no start: con NAV_ITEMS reducido a cuatro filas, un
        # "justify=start" con overflow_x=auto (pensado para cuando había doce y
        # hacía falta desplazar) dejaba los iconos apelotonados a la izquierda
        # y un hueco vacío enorme a la derecha — "descentrado". space-evenly
        # reparte el mismo hueco entre cada icono Y entre los de los extremos y
        # el borde de la pantalla, que es justo "el mismo espacio entre los
        # objetos que con los laterales".
        # El prop tipado "justify" de Radix solo admite start/center/end/
        # between — "space-evenly" (con hueco también en los extremos, no
        # solo entre iconos) hace falta meterlo como CSS crudo en style.
        # El !important es necesario: igual que con "display" más abajo en
        # este archivo, el HStack de Radix trae su propio justify-content
        # (normal/start) en un CSS estático que Emotion inserta con MENOS
        # prioridad que la que le tocaría — sin !important, a igual
        # especificidad gana la regla de Radix y el menú se queda pegado a
        # la izquierda pase lo que pase en el style.
        style={"justify_content": "space-evenly !important"},
        padding="8px 6px",
        padding_bottom="calc(35px + env(safe-area-inset-bottom))",
        background=theme.BG_SIDEBAR,
        border_top=f"1px solid {theme.BORDER}",
        position="fixed",
        bottom="0",
        left="0",
        right="0",
        z_index="60",
        # !important por el mismo motivo que en sidebar(): .rt-Flex fuerza display:flex
        # incondicional y gana la cascada si no se lo ganamos con !important.
        display=["flex !important", "flex !important", "none !important"],
    )
