"""
Barra de «hay un dispositivo desconocido pidiendo entrar».

Va en el flujo, debajo de la barra superior y junto a la de alertas, por el mismo
motivo: una decisión de acceso a la casa no puede quedarse en una lista de una
pantalla de configuración que nadie mira. Se resuelve desde donde aparece, con
los dos botones que hacen falta y nada más — dar acceso o bloquear.

«Dar acceso» pone rol de INVITADO, que es el mínimo: puede mirar el panel y las
cosas lógicas, pero no abre puertas, no arma la casa y no ve las cámaras. Subirlo
a familia es otra decisión, y se toma en Ajustes → Dispositivos con la ficha
delante. Un botón de la barra no debería poder dar el acceso grande de un toque.

Solo la ven los administradores: son los únicos que pueden decidirlo, y a los
demás sería avisarles de algo que no pueden resolver.
"""
import reflex as rx

from ....domains.auth.admin_state import AuthAdminState
from ....domains.auth.state import AuthState
from ....domains.auth import store as auth_store
from .. import theme


def _fila(d: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("circle-help", size=18, color=theme.WARNING, flex_shrink="0"),
        rx.vstack(
            rx.text(d["nombre"], size="2", weight="bold", color=theme.TEXT),
            # .to(str) delante del +: dentro de un foreach el valor de una clave
            # llega sin tipo y el + no sabe si es suma o unión de textos.
            rx.text("Quiere entrar en el panel · visto " + d["visto"].to(str),
                    size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("check", size=14), "Dar acceso",
            on_click=AuthAdminState.cambiar_rol(d["id"], auth_store.INVITADO),
            size="2", color_scheme="green", flex_shrink="0",
        ),
        rx.button(
            rx.icon("ban", size=14), "Bloquear",
            on_click=AuthAdminState.cambiar_rol(d["id"], auth_store.BLOQUEADO),
            size="2", variant="surface", color_scheme="red", flex_shrink="0",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="10px 12px", border_radius="10px",
        background=theme.alpha(theme.WARNING, 0.10),
        border=f"1px solid {theme.WARNING}",
    )


def banner_desconocidos() -> rx.Component:
    return rx.cond(
        AuthState.puede_ajustes & AuthAdminState.hay_desconocidos,
        rx.vstack(
            rx.foreach(AuthAdminState.desconocidos, _fila),
            spacing="2", width="100%",
            padding=["10px 14px 0", "10px 14px 0", "14px 28px 0"],
        ),
    )
