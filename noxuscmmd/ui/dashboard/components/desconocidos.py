"""
Aviso de «hay un dispositivo desconocido pidiendo entrar».

Va en la pila flotante común, visible en todas las vistas. Se resuelve desde
donde aparece con los dos botones que hacen falta: dar acceso o bloquear.

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
            # Lo que la propia persona escribió para decir quién es o a qué
            # viene — ver AuthState.enviar_nota_acceso. Es justo lo que hace
            # falta para decidir "dar acceso" o "bloquear" sin preguntar antes
            # por otro lado.
            rx.cond(
                d["nota_acceso"] != "",
                rx.text("«" + d["nota_acceso"].to(str) + "»", size="1",
                        color=theme.TEXT, style={"font-style": "italic"}),
            ),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        # Mismo nombre que un aparato ya registrado: casi seguro es él mismo
        # tras reinstalar la app. Un toque y vuelve con su rol y sus avisos.
        rx.cond(
            d["sustituye_a"] != "",
            rx.button(
                rx.icon("refresh-cw", size=14),
                "Es «" + d["sustituye_nombre"].to(str) + "» reinstalado",
                on_click=AuthAdminState.sustituir(d["id"], d["sustituye_a"].to(str)),
                size="2", color_scheme="blue", flex_shrink="0",
            ),
        ),
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
        class_name="nx-floating-notice nx-access-notice",
    )


def banner_desconocidos() -> rx.Component:
    return rx.cond(
        AuthState.puede_ajustes & AuthAdminState.hay_desconocidos,
        rx.vstack(
            rx.foreach(AuthAdminState.desconocidos, _fila),
            spacing="2", width="100%",
            class_name="nx-notice-group",
        ),
    )
