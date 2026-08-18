"""
Vista "Accesos": puertas/cerraduras eléctricas colgando de un nodo — la
Raspberry/Pi Zero (SSH + raspi-gpio, siempre disponibles) o un nodo ESP32
dado de alta en la pestaña Alarma (MQTT).

Cada puerta define su propio tiempo de pulso (pulse_seconds) y admite 4
acciones sobre el relé: abrir a pulso (se cierra sola), cortar un pulso en
marcha, y mantener el relé abierto o cerrado de forma indefinida — ver
domains/nodes/state.py (open_door / cut_door_pulse / set_door_hold).

Además: control de accesos por tarjeta/tag (domains/access) — niveles que
agrupan puertas (igual que un grupo de armado agrupa sensores) y credenciales
(tarjeta/tag + titular) que pertenecen a un nivel. Es solo la gestión por
ahora; conectarlo a un lector RFID/NFC real (ESP32 por MQTT) es el siguiente
paso natural cuando haya ese hardware — ver el docstring de domains/access/
store.py.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from ....domains.access.state import AccessControlState
from .. import theme
from ..components.node_select import node_select
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select, select_content
from ..components.floor_fields import floor_plan_fields


def _door_select(on_change) -> rx.Component:
    return rx.select.root(
        rx.select.trigger(placeholder="Añadir puerta al nivel...", width="100%", size="3"),
        select_content(
            rx.foreach(NodesState.doors, lambda d: rx.select.item(d["name"], value=d["id"])),
        ),
        on_change=on_change,
        value="",
    )


def _level_select(name: str = "level_id", default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Nivel de acceso (opcional)",
        select_content(
            rx.select.item("Sin nivel", value=""),
            rx.foreach(AccessControlState.levels, lambda lv: rx.select.item(lv["name"], value=lv["id"])),
        ),
        name=name,
        **kwargs,
    )


def _pulse_field(default_value: str = "2") -> rx.Component:
    return field(
        "Tiempo de pulso (segundos)",
        styled_input(name="pulse_seconds", default_value=default_value, type="number", min=1, max=60),
    )


def _edit_door_dialog(door: dict) -> rx.Component:
    return form_dialog_content(
        icon="door-closed",
        title="Editar puerta",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=door["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=door["name"])),
                field("Nodo", node_select(default_value=door["node_id"])),
                field("Pin GPIO (SSH) o señal MQTT (ESP32)", styled_input(name="pin", default_value=door["pin"])),
                _pulse_field(door["pulse_seconds"].to(str)),
                *floor_plan_fields(
                    door["floor_top"],
                    rx.cond(door["floor_icon"], door["floor_icon"].to(str), "door-closed"),
                    key=door["id"].to(str),
                ),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_door,
        ),
    )


def _door_card(door: dict) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.box(
                rx.icon("door-closed", size=20, color=theme.ACCENT),
                padding="10px",
                border_radius="10px",
                background=theme.alpha(theme.ACCENT, 0.14),
                flex_shrink="0",
            ),
            rx.vstack(
                rx.hstack(
                    rx.text(door["name"], size="3", weight="bold", color=theme.TEXT),
                    rx.badge(door["node_name"], variant="outline", size="1", color_scheme="purple"),
                    rx.badge(f"Pulso {door['pulse_seconds']}s", variant="soft", size="1", color_scheme="gray"),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(f"Pin {door['pin']} · {door['topic_cmd']}", size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            actions_menu(
                edit_content=_edit_door_dialog(door),
                on_remove=NodesState.delete_door(door["id"]),
                remove_confirm_title="¿Eliminar puerta?",
                remove_confirm_description=confirm_delete("la puerta", door["name"]),
            ),
            spacing="3",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        rx.hstack(
            rx.button(
                rx.icon("lock-open", size=14),
                "Abrir (pulso)",
                on_click=NodesState.open_door(door["id"]),
                color_scheme="blue",
                variant="surface",
                size="2",
            ),
            rx.button(
                rx.icon("ban", size=14),
                "Cortar pulso",
                on_click=NodesState.cut_door_pulse(door["id"]),
                color_scheme="orange",
                variant="surface",
                size="2",
            ),
            rx.button(
                rx.icon("door-open", size=14),
                "Mantener abierto",
                on_click=NodesState.set_door_hold(door["id"], True),
                color_scheme="amber",
                variant="surface",
                size="2",
            ),
            rx.button(
                rx.icon("lock", size=14),
                "Mantener cerrado",
                on_click=NodesState.set_door_hold(door["id"], False),
                color_scheme="gray",
                variant="surface",
                size="2",
            ),
            spacing="2",
            wrap="wrap",
            width="100%",
        ),
        spacing="3",
        align="start",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
    )


def _add_door_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Añadir puerta", size="2", variant="surface", color_scheme="blue"),
        ),
        form_dialog_content(
            icon="door-closed",
            title="Nueva puerta / cerradura",
            accent=theme.ACCENT,
            # Raspberry/Pi Zero actúan por SSH (pin GPIO, como el ventilador); un nodo ESP32 actúa
            # por MQTT (nombre de señal — el topic se arma solo como casa/<nombre del nodo>/<señal>).
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Puerta Garaje")),
                    field("Nodo", node_select()),
                    field("Pin GPIO (SSH) o señal MQTT (ESP32)", styled_input(name="pin", placeholder="27 · puerta_garaje")),
                    _pulse_field(),
                    dialog_footer(confirm_label="Añadir"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_door,
                reset_on_submit=True,
            ),
        ),
    )


def _door_chip(level_id: str, door: dict) -> rx.Component:
    return rx.hstack(
        rx.text(door["name"], size="1", color=theme.TEXT),
        rx.icon(
            "x", size=11, color=theme.MUTED, cursor="pointer",
            on_click=AccessControlState.remove_door_from_level(level_id, door["id"]),
            _hover={"color": theme.DANGER},
        ),
        spacing="1", align="center", padding="4px 8px", border_radius="999px",
        background=theme.alpha(theme.PURPLE, 0.14),
        border=f"1px solid {theme.alpha(theme.PURPLE, 0.3)}",
    )


def _edit_level_dialog(level: dict) -> rx.Component:
    return form_dialog_content(
        icon="key",
        title="Editar nivel de acceso",
        accent=theme.PURPLE,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=level["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=level["name"])),
                dialog_footer(confirm_label="Guardar", color_scheme="purple"),
                spacing="3",
                width="100%",
            ),
            on_submit=AccessControlState.submit_edit_level,
        ),
    )


def _level_card(level: dict) -> rx.Component:
    doors = level["doors"].to(list[dict])
    return rx.vstack(
        rx.hstack(
            rx.icon("key", size=18, color=theme.PURPLE),
            rx.text(level["name"], size="3", weight="bold", color=theme.TEXT),
            rx.spacer(),
            actions_menu(
                edit_content=_edit_level_dialog(level),
                on_remove=AccessControlState.delete_level(level["id"]),
                remove_confirm_title="¿Eliminar nivel de acceso?",
                remove_confirm_description=confirm_delete(
                    "el nivel", level["name"],
                    "Las tarjetas/tags que lo tengan asignado se quedan sin nivel."),
            ),
            width="100%", align="center", spacing="3",
        ),
        rx.cond(
            doors.length() == 0,
            rx.text("Sin puertas asignadas.", size="1", color=theme.MUTED, italic=True),
            rx.hstack(rx.foreach(doors, lambda d: _door_chip(level["id"], d)), spacing="2", wrap="wrap", width="100%"),
        ),
        _door_select(lambda did: AccessControlState.add_door_to_level(level["id"], did)),
        spacing="3",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="16px",
        backdrop_filter="blur(10px)",
    )


def _add_level_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Nivel de acceso", size="2", variant="surface", color_scheme="purple"),
        ),
        form_dialog_content(
            icon="key",
            title="Nuevo nivel de acceso",
            accent=theme.PURPLE,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Familia, Limpieza, Visitas")),
                    dialog_footer(confirm_label="Crear", color_scheme="purple"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=AccessControlState.submit_add_level,
                reset_on_submit=True,
            ),
        ),
    )


def _edit_credential_dialog(cred: dict) -> rx.Component:
    return form_dialog_content(
        icon="id-card",
        title="Editar tarjeta / tag",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=cred["id"], type="hidden"),
                field("Nombre del titular", styled_input(name="holder_name", default_value=cred["holder_name"])),
                field("ID de tarjeta/tag", styled_input(name="tag_id", default_value=cred["tag_id"])),
                field("Nivel de acceso", _level_select(default_value=cred["level_id"])),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=AccessControlState.submit_edit_credential,
        ),
    )


def _credential_card(cred: dict) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("id-card", size=20, color=theme.ACCENT),
            padding="10px",
            border_radius="10px",
            background=theme.alpha(theme.ACCENT, 0.14),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(cred["holder_name"], size="3", weight="bold", color=theme.TEXT),
                rx.cond(
                    cred["level_name"] != "",
                    rx.badge(cred["level_name"], variant="soft", size="1", color_scheme="purple"),
                    rx.badge("Sin nivel", variant="soft", size="1", color_scheme="gray"),
                ),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.text(cred["tag_id"], size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
            spacing="1", align="start",
        ),
        rx.spacer(),
        actions_menu(
            edit_content=_edit_credential_dialog(cred),
            on_remove=AccessControlState.delete_credential(cred["id"]),
            remove_confirm_title="¿Eliminar tarjeta/tag?",
            remove_confirm_description=confirm_delete("la tarjeta/tag de", cred["holder_name"]),
        ),
        spacing="3",
        align="center",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
        wrap="wrap",
    )


def _add_credential_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Tarjeta / tag", size="2", variant="surface", color_scheme="blue"),
        ),
        form_dialog_content(
            icon="id-card",
            title="Nueva tarjeta / tag",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre del titular", styled_input(name="holder_name", placeholder="Nombre")),
                    field("ID de tarjeta/tag", styled_input(name="tag_id", placeholder="04A3F2B1")),
                    field("Nivel de acceso", _level_select()),
                    dialog_footer(confirm_label="Añadir"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=AccessControlState.submit_add_credential,
                reset_on_submit=True,
            ),
        ),
    )


def access_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("PUERTAS", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_door_dialog(),
            width="100%",
            align="center",
        ),
        rx.cond(
            NodesState.doors.length() == 0,
            rx.text("Aún no hay puertas dadas de alta.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(NodesState.doors, _door_card), spacing="2", width="100%"),
        ),
        rx.divider(border_color=theme.BORDER),
        rx.hstack(
            rx.text("NIVELES DE ACCESO", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_level_dialog(),
            width="100%",
            align="center",
        ),
        rx.cond(
            AccessControlState.levels.length() == 0,
            rx.text("Aún no hay niveles creados.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(AccessControlState.levels, _level_card), spacing="3", width="100%"),
        ),
        rx.divider(border_color=theme.BORDER),
        rx.hstack(
            rx.text("TARJETAS / TAGS", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_credential_dialog(),
            width="100%",
            align="center",
        ),
        rx.cond(
            AccessControlState.credentials.length() == 0,
            rx.text("Aún no hay tarjetas dadas de alta.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(AccessControlState.credentials, _credential_card), spacing="2", width="100%"),
        ),
        spacing="3",
        width="100%",
    )
