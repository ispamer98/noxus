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


def _activo(view_id: str):
    # "Ajustes" se marca activo también estando DENTRO de una de las pantallas
    # de configuración que agrupa (ver DashboardState.settings_hub_active) — si
    # no, entrar en "Alarma" desde ahí dejaría el menú entero sin ninguna fila
    # resaltada.
    return (
        DashboardState.settings_hub_active if view_id == "settings_hub"
        else DashboardState.active_view == view_id
    )


def _nav_item(view_id: str, icon: str, label: str) -> rx.Component:
    # Botones HTML de verdad y no cajas de Radix: se pueden enfocar con el
    # teclado, y su aspecto entero (activo, pulsado, plegado) lo decide
    # assets/nx.css con data-activo, sin pelearse con el display de .rt-Box.
    is_active = _activo(view_id)
    return rx.el.button(
        rx.icon(icon, size=18),
        rx.el.span(label),
        on_click=DashboardState.set_view(view_id),
        class_name="nx-nav-item",
        custom_attrs={"data-activo": is_active},
        aria_current=rx.cond(is_active, "page", "false"),
        title=label,
        type="button",
    )


def _marca() -> rx.Component:
    """La marca: el arco de la «n», que es también un umbral con una luz
    encendida dentro (assets/noxus-marca.svg), y el nombre en minúsculas.

    La marca es un SVG que ya trae su propia pastilla, así que va centrada por
    construcción: antes era un icono dentro de una caja cuyo `display: grid`
    perdía contra el `display: block` de Radix, y el icono se quedaba pegado
    arriba."""
    return rx.el.div(
        # La caja del escudo lleva el brillo neón y el anillo que gira (nx.css,
        # .nx-logo): es un <span> con display grid propio, así que el escudo
        # queda centrado sin depender del display de las cajas de Radix.
        rx.el.span(
            rx.el.img(src="/noxus-marca.svg", alt="", class_name="nx-mark",
                      width="34", height="34"),
            class_name="nx-logo",
        ),
        rx.el.span("noxus", class_name="nx-wordmark nx-grad", translate="no"),
        class_name="nx-brand",
    )


def sidebar() -> rx.Component:
    # En el móvil no se pinta: la navegación pasa a la barra inferior
    # (mobile_bottom_nav). Lo decide nx.css por ancho, no un rx.cond: así no
    # hay que montar y desmontar nada al girar la tablet.
    return rx.el.aside(
        _marca(),
        rx.el.nav(
            *[_nav_item(v, i, l) for v, i, l in NAV_ITEMS],
            class_name="nx-nav",
            aria_label="Secciones",
        ),
        rx.el.div(
            rx.el.button(
                rx.icon(
                    rx.cond(DashboardState.sidebar_collapsed, "chevrons-right", "chevrons-left"),
                    size=18,
                ),
                rx.el.span("Plegar menú"),
                on_click=DashboardState.toggle_sidebar,
                class_name="nx-nav-item",
                title=rx.cond(DashboardState.sidebar_collapsed, "Desplegar menú", "Plegar menú"),
                type="button",
            ),
            class_name="nx-sidebar-pie",
        ),
        class_name="nx-sidebar",
        custom_attrs={"data-plegada": DashboardState.sidebar_collapsed},
    )


# Etiquetas cortas solo para la barra inferior (columnas estrechas); el
# sidebar de escritorio usa la etiqueta completa de NAV_ITEMS.
_MOBILE_SHORT_LABEL = {
    "floor_plan": "Plano",
}


def _mobile_nav_item(view_id: str, icon: str, label: str) -> rx.Component:
    is_active = _activo(view_id)
    return rx.el.button(
        rx.icon(icon, size=20),
        rx.el.span(_MOBILE_SHORT_LABEL.get(view_id, label)),
        on_click=DashboardState.set_view(view_id),
        class_name="nx-dock-item",
        custom_attrs={"data-activo": is_active},
        aria_current=rx.cond(is_active, "page", "false"),
        aria_label=label,
        type="button",
    )


def mobile_bottom_nav() -> rx.Component:
    """La isla flotante de abajo en el móvil: las mismas cinco secciones que el
    menú lateral, repartidas a partes iguales (nx.css, .nx-dock). Es el único
    elemento del panel con backdrop-filter, y por eso se lo puede permitir."""
    return rx.el.nav(
        *[_mobile_nav_item(v, i, l) for v, i, l in NAV_ITEMS],
        class_name="nx-dock",
        aria_label="Secciones",
    )
