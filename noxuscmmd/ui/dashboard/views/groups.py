"""
Vista "Grupos": único mecanismo de armado de todo el sistema. Cada grupo
agrupa sensores (del registry clásico o dados de alta en caliente sobre
nodos) y se arma/desarma de forma independiente. Uno de los grupos está
marcado como "principal" — es el que controla el botón de armado general de
siempre (vista clásica y tarjeta superior de Alarma); puedes elegir cuál
mediante el botón ☆ de cada tarjeta.
"""
import reflex as rx

from ....domains.auth.state import AuthState
from ....domains.security.arming_state import ArmingState
from ....domains.security.groups_state import GroupsState
from .. import theme
from ..components.sensor_select import sensor_select
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input


def _member_chip(group_id: str, member: dict) -> rx.Component:
    return rx.hstack(
        rx.text(member["name"], size="1", color=theme.TEXT),
        rx.icon(
            "x",
            size=11,
            color=theme.MUTED,
            cursor="pointer",
            on_click=GroupsState.remove_sensor_from_group(group_id, member["id"]),
            _hover={"color": theme.DANGER},
        ),
        spacing="1",
        align="center",
        padding="4px 8px",
        border_radius="999px",
        background=theme.alpha(theme.PURPLE, 0.14),
        border=f"1px solid {theme.alpha(theme.PURPLE, 0.3)}",
    )


def _edit_group_dialog(group: dict) -> rx.Component:
    return form_dialog_content(
        icon="layers",
        title="Editar grupo",
        accent=theme.PURPLE,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=group["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=group["name"])),
                dialog_footer(confirm_label="Guardar", color_scheme="purple"),
                spacing="3",
                width="100%",
            ),
            on_submit=GroupsState.submit_edit_group,
        ),
    )


def _group_card(group: dict) -> rx.Component:
    armed = group["armed"]
    is_principal = group["is_principal"]
    members = group["members"].to(list[dict])
    return rx.vstack(
        rx.hstack(
            rx.icon(
                rx.cond(armed, "shield-check", "shield-off"),
                size=20,
                color=rx.cond(armed, theme.DANGER, theme.SUCCESS),
            ),
            rx.text(group["name"], size="3", weight="bold", color=theme.TEXT),
            rx.cond(
                is_principal,
                rx.badge(
                    rx.hstack(rx.icon("star", size=11), rx.text("PRINCIPAL"), spacing="1", align="center"),
                    variant="solid", color_scheme="purple", size="1",
                ),
                rx.icon(
                    "star",
                    size=15,
                    color=theme.MUTED,
                    cursor="pointer",
                    on_click=GroupsState.set_principal_group(group["id"]),
                    title="Marcar como grupo principal (armado general)",
                    _hover={"color": theme.PURPLE},
                ),
            ),
            rx.spacer(),
            rx.cond(
                AuthState.puede_armar,
                rx.button(
                    rx.cond(armed, "DESARMAR", "ARMAR"),
                    on_click=ArmingState.pedir_armar(group["id"]),
                    color_scheme=rx.cond(armed, "red", "green"),
                    variant=rx.cond(armed, "solid", "surface"),
                    size="2",
                ),
            ),
            actions_menu(
                edit_content=_edit_group_dialog(group),
                on_remove=GroupsState.delete_group(group["id"]),
                remove_confirm_title="¿Eliminar grupo?",
                remove_confirm_description=confirm_delete(
                    "el grupo", group["name"],
                    "Sus sensores no se borran, solo dejan de pertenecer a él."),
            ),
            width="100%",
            align="center",
            spacing="3",
            wrap="wrap",
        ),
        rx.cond(
            members.length() == 0,
            rx.text("Sin sensores todavía.", size="1", color=theme.MUTED, italic=True),
            rx.hstack(
                rx.foreach(members, lambda m: _member_chip(group["id"], m)),
                spacing="2",
                wrap="wrap",
                width="100%",
            ),
        ),
        sensor_select(lambda sid: GroupsState.add_sensor_to_group(group["id"], sid)),
        spacing="3",
        width="100%",
        background=theme.BG_CARD,
        border=rx.cond(
            is_principal,
            f"1px solid {theme.alpha(theme.PURPLE, 0.5)}",
            rx.cond(armed, f"1px solid {theme.alpha(theme.DANGER, 0.4)}", f"1px solid {theme.BORDER}"),
        ),
        border_radius="12px",
        padding="16px",
        backdrop_filter="blur(10px)",
    )


def _add_group_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Nuevo grupo", size="2", variant="surface"),
        ),
        form_dialog_content(
            icon="layers",
            title="Nuevo grupo de armado",
            accent=theme.PURPLE,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Garaje, Noche, Perímetro")),
                    dialog_footer(confirm_label="Crear", color_scheme="purple"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=GroupsState.submit_add_group,
                reset_on_submit=True,
            ),
        ),
    )


def groups_view() -> rx.Component:
    # Todo sensor se arma exclusivamente por pertenecer a un grupo armado — no hay excepciones.
    # El grupo con la ⭐ es el "principal": es el que controla el botón de armado general de
    # siempre (y la vista clásica). Pulsa la estrella de cualquier grupo para convertirlo en el principal.
    return rx.vstack(
        rx.hstack(
            rx.text("GRUPOS", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_group_dialog(),
            width="100%",
            align="center",
        ),
        rx.cond(
            GroupsState.groups.length() == 0,
            rx.text("Aún no hay grupos creados.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(GroupsState.groups, _group_card), spacing="3", width="100%"),
        ),
        spacing="3",
        width="100%",
    )
