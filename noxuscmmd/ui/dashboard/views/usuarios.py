"""Vista "Dispositivos y accesos": quién entra en esta casa y qué puede tocar.

Solo pinta. Quien decide es domains/auth/admin_state.py, que comprueba el
permiso en cada evento — esta pantalla puede estar escondida y sus botones no
pintados, y aun así hay que suponer que alguien puede llamar a sus eventos.
"""
import reflex as rx

from .. import theme
from ..components.form_dialog import select_content
from ..state import DashboardState
from ....domains.auth.admin_state import ICONOS_DISPOSITIVO, AuthAdminState
from ....domains.auth.state import AuthState
from ....domains.auth import store
from ....domains.notifications import categorias

_COLOR_ROL = {
    store.ADMIN: theme.ACCENT,
    store.FAMILIA: theme.SUCCESS,
    store.INVITADO: theme.WARNING,
    store.PENDIENTE: theme.MUTED,
    # Rojo, y distinto del gris de «Sin acceso» a propósito: los permisos de los
    # dos son los mismos —ninguno—, pero uno es «todavía no he decidido» y el
    # otro es «he dicho que no». Que se distingan de un vistazo es justo el
    # motivo de que el rol exista.
    store.BLOQUEADO: theme.DANGER,
}

# Un icono por rol, para que se lea de un vistazo sin tener que fiarse solo
# del color — el mismo criterio en el badge de la fila y en cada opción del
# desplegable, así los dos sitios enseñan lo mismo.
_ICONO_ROL = {
    store.ADMIN: "shield-check",
    store.FAMILIA: "users",
    store.INVITADO: "user",
    store.PENDIENTE: "shield-question",
    store.BLOQUEADO: "ban",
}

# Un icono por categoría de aviso — ver notifications/categorias.py. El de
# «desconocido» es el mismo que el del banner de arriba (components/
# desconocidos.py): el mismo suceso no debería tener dos caras según dónde
# se mire.
_ICONO_CATEGORIA = {
    categorias.MOVIMIENTO: "scan-eye",
    categorias.ALARMA: "siren",
    categorias.DESCONOCIDO: "circle-help",
}


def _color_rol(item: rx.Var):
    """El color de fondo de ESTE aparato, según su rol — mismo criterio que
    _COLOR_ROL pero como Var, para usarlo en el marco de la tarjeta grande."""
    return rx.match(
        item["rol"],
        (store.ADMIN, theme.ACCENT),
        (store.FAMILIA, theme.SUCCESS),
        (store.INVITADO, theme.WARNING),
        (store.BLOQUEADO, theme.DANGER),
        theme.MUTED,
    )


def _etiqueta_rol(item: rx.Var) -> rx.Component:
    """La píldora con el rol, icono más texto. El color y el icono se eligen
    con rx.match y no con un diccionario de Python: dentro de un foreach el
    rol es una Var, no una cadena, y no se puede usar como clave."""
    color = rx.match(
        item["rol"],
        (store.ADMIN, theme.ACCENT),
        (store.FAMILIA, theme.SUCCESS),
        (store.INVITADO, theme.WARNING),
        theme.MUTED,
    )
    icono = rx.match(
        item["rol"],
        (store.ADMIN, _ICONO_ROL[store.ADMIN]),
        (store.FAMILIA, _ICONO_ROL[store.FAMILIA]),
        (store.INVITADO, _ICONO_ROL[store.INVITADO]),
        (store.BLOQUEADO, _ICONO_ROL[store.BLOQUEADO]),
        _ICONO_ROL[store.PENDIENTE],
    )
    return rx.hstack(
        rx.icon(icono, size=11, color=color),
        rx.text(item["rol_nombre"], size="1", weight="bold", color=color),
        spacing="1", align="center", flex_shrink="0",
        background=rx.match(
            item["rol"],
            (store.ADMIN, theme.alpha(theme.ACCENT, 0.12)),
            (store.FAMILIA, theme.alpha(theme.SUCCESS, 0.12)),
            (store.INVITADO, theme.alpha(theme.WARNING, 0.12)),
            theme.alpha(theme.MUTED, 0.12),
        ),
        padding="3px 10px", border_radius="999px",
    )


def _item_rol(rol: str, texto: str) -> rx.Component:
    return rx.select.item(
        rx.hstack(rx.icon(_ICONO_ROL[rol], size=14), rx.text(texto),
                  spacing="2", align="center"),
        value=rol,
    )


def _selector_rol(item: rx.Var) -> rx.Component:
    """El rol, en un desplegable en vez de cinco botones sueltos.

    Bloquear sigue siendo una opción más de la lista, no un botón aparte: se
    puede deshacer desde el mismo sitio en que se puso, y un bloqueo del que
    no se sabe cómo se sale no es un bloqueo, es un aparato perdido. La
    diferencia con «Sin acceso» es solo que un bloqueado deja de salir en el
    aviso de «alguien pide entrar» — los permisos de los dos son ninguno."""
    return rx.select.root(
        rx.select.trigger(size="2", width="100%"),
        select_content(
            _item_rol(store.ADMIN, "Administrador"),
            _item_rol(store.FAMILIA, "Familia"),
            _item_rol(store.INVITADO, "Invitado"),
            _item_rol(store.PENDIENTE, "Sin acceso"),
            _item_rol(store.BLOQUEADO, "Bloqueado"),
        ),
        value=item["rol"],
        on_change=lambda v: AuthAdminState.cambiar_rol(item["id"], v),
    )


def _fila_categoria(item: rx.Var, cat: rx.Var) -> rx.Component:
    icono = rx.match(
        cat["id"],
        (categorias.MOVIMIENTO, _ICONO_CATEGORIA[categorias.MOVIMIENTO]),
        (categorias.ALARMA, _ICONO_CATEGORIA[categorias.ALARMA]),
        _ICONO_CATEGORIA[categorias.DESCONOCIDO],
    )
    return rx.hstack(
        rx.checkbox(
            checked=cat["activa"],
            on_change=lambda _: AuthAdminState.alternar_categoria(item["id"], cat["id"]),
        ),
        rx.icon(icono, size=13, color=theme.MUTED, flex_shrink="0"),
        rx.text(cat["nombre"], size="2", color=theme.TEXT),
        spacing="2", align="center", width="100%",
    )


def _etiqueta_seccion(texto: str) -> rx.Component:
    return rx.text(texto, size="1", weight="bold", color=theme.MUTED,
                   letter_spacing="0.05em", text_transform="uppercase",
                   margin_top="8px")


def _celda_icono(item: rx.Var, icono: str) -> rx.Component:
    """Una casilla de la rejilla de iconos elegibles. Rejilla propia y no
    icon_grid (components/icon_picker.py): icon_grid ya trae su propio
    popover dentro, y esto vive DENTRO del popover de permisos — anidar un
    popover en otro es justo lo que Radix no lleva bien."""
    selected = item["icono"] == icono
    return rx.box(
        rx.icon(icono, size=15, color=rx.cond(selected, theme.ACCENT, theme.TEXT)),
        on_click=AuthAdminState.elegir_icono(item["id"], icono),
        cursor="pointer", display="flex", align_items="center", justify_content="center",
        padding="7px", border_radius="8px",
        background=rx.cond(selected, theme.alpha(theme.ACCENT, 0.16), "transparent"),
        border=rx.cond(selected, f"1px solid {theme.ACCENT}", f"1px solid {theme.BORDER}"),
        _hover={"background": theme.alpha(theme.ACCENT, 0.10)},
    )


def _icono_grande(item: rx.Var) -> rx.Component:
    """El icono de la tarjeta, grande y con el marco del color de su rol —
    azul admin, verde familia, naranja invitado, gris sin acceso, rojo
    bloqueado. Con un punto naranja encima si está pidiendo acceso AHORA: eso
    no depende del rol —puede llevar cualquiera, hasta bloqueado— así que no
    podía compartir el mismo color sin confundirse con «es invitado»."""
    color = _color_rol(item)
    return rx.box(
        rx.icon(item["icono"].to(str), size=22, color=color),
        rx.cond(
            item["pide_acceso"],
            rx.box(
                rx.icon("door-open", size=10, color="white"),
                position="absolute", top="-5px", right="-5px",
                background=theme.WARNING, border_radius="999px",
                padding="3px", display="flex", align_items="center",
                justify_content="center",
                border=f"2px solid {theme.BG_CARD}",
            ),
        ),
        position="relative", padding="11px", border_radius="12px",
        background=rx.match(
            item["rol"],
            (store.ADMIN, theme.alpha(theme.ACCENT, 0.14)),
            (store.FAMILIA, theme.alpha(theme.SUCCESS, 0.14)),
            (store.INVITADO, theme.alpha(theme.WARNING, 0.14)),
            (store.BLOQUEADO, theme.alpha(theme.DANGER, 0.14)),
            theme.alpha(theme.MUTED, 0.12),
        ),
        # La regla CSS entera en cada rama, no "2px solid " + rx.match(...):
        # un rx.match devuelve una Var, y concatenarla con un str por delante
        # revienta al compilar la página (y tiró el servicio una vez).
        border=rx.match(
            item["rol"],
            (store.ADMIN, f"2px solid {theme.alpha(theme.ACCENT, 0.5)}"),
            (store.FAMILIA, f"2px solid {theme.alpha(theme.SUCCESS, 0.5)}"),
            (store.INVITADO, f"2px solid {theme.alpha(theme.WARNING, 0.5)}"),
            (store.BLOQUEADO, f"2px solid {theme.alpha(theme.DANGER, 0.5)}"),
            f"2px solid {theme.alpha(theme.MUTED, 0.4)}",
        ),
        flex_shrink="0",
    )


def _panel_permisos(item: rx.Var) -> rx.Component:
    """Todo lo que se puede tocar de un aparato, en un solo bocadillo — icono,
    rol y avisos, que antes eran hasta ocho controles sueltos pintados siempre
    en la tarjeta, y la mayor parte del tiempo nadie los estaba tocando."""
    return rx.vstack(
        _etiqueta_seccion("Icono"),
        rx.grid(
            *[_celda_icono(item, ic) for ic in ICONOS_DISPOSITIVO],
            columns="5", spacing="2", width="100%",
        ),
        _etiqueta_seccion("Rol"),
        _selector_rol(item),
        rx.cond(
            item["tiene_avisos"] == "sí",
            rx.fragment(
                _etiqueta_seccion("Avisos que recibe"),
                rx.foreach(item["categorias"].to(list[dict]),
                          lambda cat: _fila_categoria(item, cat)),
            ),
        ),
        rx.divider(border_color=theme.BORDER, margin_top="4px"),
        rx.button(
            rx.icon("trash-2", size=13), "Eliminar dispositivo",
            size="1", variant="soft", color_scheme="red", width="100%",
            on_click=AuthAdminState.eliminar_dispositivo(item["id"]),
        ),
        spacing="2", width="230px",
    )


def _fila_dispositivo(item: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.popover.root(
            rx.popover.trigger(
                rx.hstack(
                    _icono_grande(item),
                    rx.vstack(
                        rx.text(item["nombre"], size="2", weight="bold", color=theme.TEXT),
                        _etiqueta_rol(item),
                        spacing="1", align="start", min_width="0",
                    ),
                    rx.spacer(),
                    rx.text(item["visto"], size="1", color=theme.MUTED, flex_shrink="0"),
                    rx.icon("chevron-right", size=15, color=theme.MUTED, flex_shrink="0"),
                    align="center", spacing="3", width="100%", cursor="pointer",
                ),
            ),
            rx.popover.content(
                _panel_permisos(item),
                side="bottom", align="start",
                style={
                    "padding": "12px",
                    "background": theme.BG_WINDOW,
                    "border": f"1px solid {theme.BORDER_STRONG}",
                    "border_radius": "12px",
                },
            ),
        ),
        rx.cond(
            item["caduca"] != "",
            rx.text(item["caduca"], size="1", color=theme.WARNING),
        ),
        # Lo que la propia persona escribió para identificarse al pedir acceso
        # — ver AuthState.enviar_nota_acceso. Se queda visible aunque ya se le
        # haya resuelto: es el porqué del rol que tiene.
        rx.cond(
            item["nota_acceso"] != "",
            rx.hstack(
                rx.icon("message-circle", size=12, color=theme.MUTED, flex_shrink="0"),
                rx.text(item["nota_acceso"], size="1", color=theme.MUTED,
                        style={"font-style": "italic"}),
                spacing="1", align="center",
            ),
        ),
        spacing="2", width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {rx.cond(item['pide_acceso'], theme.alpha(theme.WARNING, 0.5), theme.BORDER)}",
        border_radius="12px", padding="12px 14px",
    )


def _fila_invitacion(item: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("ticket", size=15, color=theme.WARNING, flex_shrink="0"),
            rx.text(item["rol_nombre"], size="2", weight="bold", color=theme.TEXT),
            rx.text(item["queda"], size="1", color=theme.WARNING),
            rx.spacer(),
            rx.text(item["usada"], size="1", color=theme.MUTED, flex_shrink="0"),
            align="center", spacing="2", width="100%",
        ),
        rx.cond(
            item["nota"] != "",
            rx.text(item["nota"], size="1", color=theme.MUTED),
        ),
        rx.hstack(
            rx.text(item["caduca"], size="1", color=theme.MUTED,
                    font_family=theme.FONT_MONO),
            rx.spacer(),
            rx.button("Copiar enlace", size="1", variant="soft",
                      on_click=AuthAdminState.copiar_enlace(item["codigo"])),
            rx.button("Retirar", size="1", variant="soft", color_scheme="red",
                      on_click=AuthAdminState.revocar(item["codigo"])),
            spacing="2", width="100%", align="center", wrap="wrap",
        ),
        spacing="2", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="12px 14px",
    )


def _aviso_bloqueo() -> rx.Component:
    return rx.hstack(
        rx.icon(
            rx.cond(AuthAdminState.bloqueo_activo, "shield-check", "shield-alert"),
            size=20,
            color=rx.cond(AuthAdminState.bloqueo_activo, theme.SUCCESS, theme.WARNING),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(
                rx.cond(AuthAdminState.bloqueo_activo,
                        "Permisos en vigor", "Permisos en rodaje"),
                size="2", weight="bold", color=theme.TEXT,
            ),
            rx.text(AuthAdminState.resumen_bloqueo, size="1", color=theme.MUTED,
                    style={"line-height": "1.5"}),
            spacing="1", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(
            rx.cond(AuthAdminState.bloqueo_activo, "Volver a rodaje", "Activar"),
            size="2",
            color_scheme=rx.cond(AuthAdminState.bloqueo_activo, "gray", "green"),
            on_click=AuthAdminState.alternar_bloqueo,
            flex_shrink="0",
        ),
        align="center", spacing="3", width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {rx.cond(AuthAdminState.bloqueo_activo, theme.alpha(theme.SUCCESS, 0.4), theme.alpha(theme.WARNING, 0.4))}",
        border_radius="12px", padding="14px 16px",
    )


def _crear_invitacion() -> rx.Component:
    return rx.vstack(
        rx.text("Dejar entrar a alguien un rato", size="2", weight="bold",
                color=theme.TEXT),
        rx.text(
            "Crea un enlace que caduca solo. Quien lo abra entra como invitado "
            "—luces y poco más, nunca la alarma— y pierde el acceso al pasar "
            "las horas que digas, sin que haya que acordarse de quitárselo.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.hstack(
            rx.input(
                value=AuthAdminState.horas_invitacion,
                on_change=AuthAdminState.set_horas_invitacion,
                placeholder="horas", width="90px", type="number",
            ),
            rx.input(
                value=AuthAdminState.nota_invitacion,
                on_change=AuthAdminState.set_nota_invitacion,
                placeholder="para qué (el fontanero, mi madre...)",
                flex="1", min_width="0",
            ),
            rx.button("Crear", on_click=AuthAdminState.crear_invitacion,
                      flex_shrink="0"),
            spacing="2", width="100%", align="center", wrap="wrap",
        ),
        spacing="2", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="14px 16px",
    )


def usuarios_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("users", size=22, color=theme.ACCENT),
            rx.heading("Dispositivos y accesos", size="6", color=theme.TEXT),
            rx.spacer(),
            rx.button(
                rx.icon("arrow-left", size=15), "Ajustes", size="2",
                variant="soft",
                on_click=DashboardState.set_view("settings_hub"),
            ),
            align="center", spacing="3", width="100%",
        ),
        rx.text(
            "Cada aparato que abre el panel queda aquí con un nombre y un rol. "
            "El administrador lo toca todo; la familia, todo menos esta "
            "pantalla; el invitado solo las luces.",
            size="1", color=theme.MUTED, style={"line-height": "1.6"},
        ),

        _aviso_bloqueo(),

        rx.cond(
            ~AuthAdminState.hay_admin,
            rx.hstack(
                rx.icon("triangle-alert", size=18, color=theme.DANGER,
                        flex_shrink="0"),
                rx.text(
                    "No hay ningún administrador. Ponle el rol a tu dispositivo "
                    "antes de activar los permisos, o nadie podrá volver a "
                    "abrir esta pantalla.",
                    size="1", color=theme.TEXT, style={"line-height": "1.5"},
                ),
                align="center", spacing="3", width="100%",
                background=theme.alpha(theme.DANGER, 0.1),
                border=f"1px solid {theme.alpha(theme.DANGER, 0.4)}",
                border_radius="12px", padding="12px 14px",
            ),
        ),

        rx.text("Este dispositivo", size="1", weight="bold", color=theme.MUTED,
                margin_top="6px"),
        rx.hstack(
            rx.icon("monitor-check", size=16, color=theme.ACCENT, flex_shrink="0"),
            rx.text(AuthState.nombre_dispositivo, size="2", weight="bold",
                    color=theme.TEXT),
            rx.text(AuthState.nombre_rol, size="1", color=theme.MUTED),
            align="center", spacing="2", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
            border_radius="12px", padding="12px 14px",
        ),

        rx.text("Dispositivos", size="1", weight="bold", color=theme.MUTED,
                margin_top="6px"),
        rx.cond(
            AuthAdminState.dispositivos.length() > 0,
            rx.vstack(
                rx.foreach(AuthAdminState.dispositivos, _fila_dispositivo),
                spacing="2", width="100%",
            ),
            rx.text("Todavía no ha entrado ningún dispositivo.", size="1",
                    color=theme.MUTED),
        ),

        rx.text("Invitaciones", size="1", weight="bold", color=theme.MUTED,
                margin_top="6px"),
        _crear_invitacion(),
        rx.cond(
            AuthAdminState.invitaciones.length() > 0,
            rx.vstack(
                rx.foreach(AuthAdminState.invitaciones, _fila_invitacion),
                spacing="2", width="100%",
            ),
            rx.text("No hay ninguna invitación activa.", size="1",
                    color=theme.MUTED),
        ),

        spacing="3", width="100%", max_width="900px", align="start",
        on_mount=AuthAdminState.on_load,
    )
