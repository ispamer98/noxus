"""Vista "Dispositivos y accesos": quién entra en esta casa y qué puede tocar.

Solo pinta. Quien decide es domains/auth/admin_state.py, que comprueba el
permiso en cada evento — esta pantalla puede estar escondida y sus botones no
pintados, y aun así hay que suponer que alguien puede llamar a sus eventos.
"""
import reflex as rx

from .. import theme
from ..state import DashboardState
from ....domains.auth.admin_state import AuthAdminState
from ....domains.auth.state import AuthState
from ....domains.auth import store

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


def _etiqueta_rol(item: rx.Var) -> rx.Component:
    """La píldora con el rol. El color se elige con rx.match y no con un
    diccionario de Python: dentro de un foreach el rol es una Var, no una
    cadena, y no se puede usar como clave."""
    color = rx.match(
        item["rol"],
        (store.ADMIN, theme.ACCENT),
        (store.FAMILIA, theme.SUCCESS),
        (store.INVITADO, theme.WARNING),
        theme.MUTED,
    )
    return rx.text(
        item["rol_nombre"], size="1", weight="bold", color=color,
        background=rx.match(
            item["rol"],
            (store.ADMIN, theme.alpha(theme.ACCENT, 0.12)),
            (store.FAMILIA, theme.alpha(theme.SUCCESS, 0.12)),
            (store.INVITADO, theme.alpha(theme.WARNING, 0.12)),
            theme.alpha(theme.MUTED, 0.12),
        ),
        padding="3px 10px", border_radius="999px", flex_shrink="0",
    )


def _boton_rol(item: rx.Var, rol: str, texto: str) -> rx.Component:
    return rx.button(
        texto, size="1", variant="soft",
        color_scheme=rx.cond(item["rol"] == rol, "blue", "gray"),
        on_click=AuthAdminState.cambiar_rol(item["id"], rol),
    )


def _fila_dispositivo(item: rx.Var) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("smartphone", size=16, color=theme.MUTED, flex_shrink="0"),
            rx.text(item["nombre"], size="2", weight="bold", color=theme.TEXT),
            _etiqueta_rol(item),
            rx.spacer(),
            rx.text(item["visto"], size="1", color=theme.MUTED, flex_shrink="0"),
            align="center", spacing="2", width="100%",
        ),
        rx.cond(
            item["caduca"] != "",
            rx.text(item["caduca"], size="1", color=theme.WARNING),
        ),
        rx.hstack(
            _boton_rol(item, store.ADMIN, "Administrador"),
            _boton_rol(item, store.FAMILIA, "Familia"),
            _boton_rol(item, store.INVITADO, "Invitado"),
            _boton_rol(item, store.PENDIENTE, "Sin acceso"),
            # Bloquear se puede DESHACER desde aquí, y por eso el botón está en
            # la misma fila que los demás roles y no escondido en otro sitio: un
            # bloqueo del que no se sabe cómo se sale no es un bloqueo, es un
            # aparato perdido. La diferencia con «Sin acceso» es solo que un
            # bloqueado deja de salir en el aviso de «hay alguien pidiendo
            # entrar» — los permisos de los dos son los mismos: ninguno.
            _boton_rol(item, store.BLOQUEADO, "Bloqueado"),
            rx.spacer(),
            rx.button(
                rx.icon("trash-2", size=14), size="1", variant="soft",
                color_scheme="red",
                on_click=AuthAdminState.eliminar_dispositivo(item["id"]),
            ),
            spacing="2", width="100%", wrap="wrap", align="center",
        ),
        spacing="2", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
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
