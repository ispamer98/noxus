"""
Vista "Alarma": todos los sensores binarios en un único sitio — los que ya
existían en el registry (puerta principal, tampers, cableados a la
Raspberry/Pi Zero) tratados exactamente igual que los que se dan de alta en
caliente sobre un nodo ESP32. Mismo diseño de tarjeta, mismo menú de acciones
(⋮ Editar/Aislar/Ocultar-o-Eliminar), un único listado — no hay "sensores de
primera" y "sensores de segunda".
"""
import reflex as rx

from ....domains.auth.state import AuthState
from ....domains.security.arming_state import ArmingState
from ....domains.security.groups_state import GroupsState
from ....domains.nodes.state import NodesState
from .. import theme
from ..components.node_select import node_select
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import (form_dialog_content, field, dialog_footer,
                                      styled_input, styled_select, select_content)
from ..components.floor_fields import floor_plan_fields


def _group_membership(sid) -> rx.Component:
    """Badges con los grupos a los que pertenece el sensor — sustituye al
    antiguo texto fijo "sigue el armado del grupo al que pertenezca"."""
    grupos = GroupsState.groups_by_sensor.get(sid, [])
    return rx.cond(
        grupos.length() > 0,
        rx.hstack(
            rx.text("Grupos:", size="1", color=theme.MUTED),
            rx.foreach(grupos, lambda n: rx.badge(n, variant="soft", size="1", color_scheme="purple")),
            spacing="1",
            align="center",
            wrap="wrap",
        ),
        rx.text("Sin grupo asignado", size="1", color=theme.MUTED),
    )

_KIND_META = {
    "door": {
        "label": "Magnético",
        "icon_open": "door-open",
        "icon_closed": "door-closed",
        "text_open": "ABIERTA",
        "text_closed": "CERRADA",
        "accent_open": theme.WARNING,
    },
    "tamper": {
        "label": "Tamper",
        "icon_open": "lock-open",
        "icon_closed": "lock",
        "text_open": "ABIERTO",
        "text_closed": "CERRADO",
        "accent_open": theme.DANGER,
    },
    "pir": {
        "label": "Volumétrico (PIR)",
        "icon_open": "radar",
        "icon_closed": "radar",
        "text_open": "MOVIMIENTO",
        "text_closed": "SIN MOVIMIENTO",
        "accent_open": theme.DANGER,
    },
    "generic": {
        "label": "Sensor",
        "icon_open": "circle-dot",
        "icon_closed": "circle",
        "text_open": "ACTIVO",
        "text_closed": "INACTIVO",
        "accent_open": theme.WARNING,
    },
}

_KIND_OPTIONS = [
    ("door", "Magnético (puerta/ventana)"),
    ("pir", "Volumétrico (PIR)"),
    ("tamper", "Tamper"),
    ("generic", "Genérico"),
]

# Un NODO es lo que mueve relés y lee sensores de una estancia, y habla SOLO
# MQTT (casa/<nodo>/<pin>/set · casa/<nodo>/<pin>), sea un ESP32 o una Pi (su
# servicio gpio-mqtt). La gestión del ordenador (apagar, SSH...) es de Equipos.
_NODE_KIND_OPTIONS = [
    ("esp32", "ESP32"),
    ("raspberry", "Raspberry Pi"),
]

def _master_arm_card() -> rx.Component:
    """El "armado general" ya no es un mecanismo aparte: es el grupo marcado
    como principal (por defecto "Sistema"). Arma/desarma ese grupo — que a su
    vez mantiene sincronizado SecurityState.sistema_armado para que la vista
    clásica siga funcionando igual. Puedes elegir otro grupo como principal
    desde la pestaña Grupos."""
    principal = GroupsState.principal
    armed = principal["armed"]
    return rx.hstack(
        rx.icon(
            rx.cond(armed, "shield-check", "shield-off"),
            size=24,
            color=rx.cond(armed, theme.DANGER, theme.SUCCESS),
        ),
        rx.vstack(
            rx.hstack(
                rx.text("Grupo principal:", size="3", weight="bold", color=theme.TEXT),
                rx.text(principal["name"], size="3", weight="bold", color=theme.PURPLE),
                spacing="2",
            ),
            rx.text(
                rx.cond(armed, "ARMADO — cualquier miembro abierto dispara alerta", "DESARMADO"),
                size="1",
                color=theme.MUTED,
            ),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        rx.cond(
            AuthState.puede_armar,
            rx.button(
                rx.cond(armed, "DESARMAR", "ARMAR"),
                on_click=ArmingState.pedir_armar(principal["id"]),
                color_scheme=rx.cond(armed, "red", "green"),
                variant=rx.cond(armed, "solid", "surface"),
                size="3",
            ),
        ),
        width="100%",
        align="center",
        spacing="3",
        background=theme.BG_CARD, class_name="nx-card",
        border=rx.cond(
            armed,
            f"1px solid {theme.alpha(theme.DANGER, 0.4)}",
            f"1px solid {theme.BORDER}",
        ),
        border_radius="12px",
        padding="16px",
        wrap="wrap",
    )


def _kind_icon(kind, is_open) -> rx.Component:
    return rx.match(
        kind,
        ("door", rx.icon(rx.cond(is_open, "door-open", "door-closed"), size=20, color=rx.cond(is_open, theme.WARNING, theme.SUCCESS))),
        ("tamper", rx.icon(rx.cond(is_open, "lock-open", "lock"), size=20, color=rx.cond(is_open, theme.DANGER, theme.SUCCESS))),
        ("pir", rx.icon("radar", size=20, color=rx.cond(is_open, theme.DANGER, theme.SUCCESS))),
        rx.icon(rx.cond(is_open, "circle-dot", "circle"), size=20, color=rx.cond(is_open, theme.WARNING, theme.SUCCESS)),
    )


def _kind_label(kind) -> rx.Component:
    return rx.match(
        kind,
        ("door", rx.text("Magnético", size="1")),
        ("tamper", rx.text("Tamper", size="1")),
        ("pir", rx.text("Volumétrico (PIR)", size="1")),
        rx.text("Sensor", size="1"),
    )


def _dynamic_sensor_card(sensor: dict) -> rx.Component:
    is_open = NodesState.sensor_state[sensor["id"].to(str)]
    isolated = sensor["isolated"]
    return rx.hstack(
        rx.box(
            _kind_icon(sensor["kind"], is_open),
            padding="10px",
            border_radius="10px",
            background=rx.cond(
                isolated,
                theme.alpha(theme.MUTED, 0.10),
                rx.cond(is_open, theme.alpha(theme.WARNING, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
            ),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(sensor["name"], size="3", weight="bold", color=rx.cond(isolated, theme.MUTED, theme.TEXT)),
                rx.badge(_kind_label(sensor["kind"]), variant="soft", size="1", color_scheme="gray"),
                rx.badge(sensor["node_name"], variant="outline", size="1", color_scheme="purple"),
                rx.cond(isolated, rx.badge("AISLADO", variant="soft", size="1", color_scheme="gray")),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.badge(
                rx.cond(is_open, "ABIERTO / ACTIVO", "CERRADO / INACTIVO"),
                color_scheme=rx.cond(is_open, "orange", "green"),
                variant="surface",
                size="1",
            ),
            rx.cond(
                isolated,
                rx.text("Aislado: no dispara alerta aunque su grupo esté armado", size="1", color=theme.MUTED),
                _group_membership(sensor["id"].to(str)),
            ),
            rx.text(f"Pin {sensor['pin']} · {sensor['topic']}", size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        actions_menu(
            edit_content=_edit_sensor_dialog(sensor),
            on_isolate=NodesState.toggle_sensor_isolated(sensor["id"]),
            isolate_label=rx.cond(isolated, "Reactivar", "Aislar"),
            isolate_icon=rx.cond(isolated, "eye", "eye-off"),
            on_remove=NodesState.delete_sensor(sensor["id"]),
            remove_confirm_title="¿Eliminar sensor?",
            remove_confirm_description=confirm_delete(
                "el sensor", sensor["name"], "Se borra su configuración por completo."),
        ),
        spacing="3",
        align="start",
        width="100%",
        background=rx.cond(isolated, theme.alpha(theme.MUTED, 0.04), theme.BG_CARD), class_name="nx-card",
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        opacity=rx.cond(isolated, "0.7", "1"),
    )


def _edit_sensor_dialog(sensor: dict) -> rx.Component:
    return form_dialog_content(
        icon="settings",
        title="Ajustes del sensor",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.el.input(name="entity_id", value=sensor["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=sensor["name"])),
                field("Tipo de sensor", styled_select(
                    "Tipo de sensor",
                    select_content(*[rx.select.item(label, value=val) for val, label in _KIND_OPTIONS]),
                    name="kind", default_value=sensor["kind"],
                )),
                field("Nodo", node_select(default_value=sensor["node_id"])),
                field("Pin o señal MQTT", styled_input(name="pin", default_value=sensor["pin"])),
                *floor_plan_fields(
                    False,
                    rx.cond(sensor["floor_icon"], sensor["floor_icon"].to(str), "circle-dot"),
                    key=sensor["id"].to(str),
                ),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_sensor,
        ),
    )


def _node_card(node: dict) -> rx.Component:
    return rx.hstack(
        rx.icon("cpu", size=18, color=theme.ACCENT),
        rx.vstack(
            rx.text(node["name"], size="2", weight="bold", color=theme.TEXT),
            rx.text(node["ip"], size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        actions_menu(
            edit_content=_edit_node_dialog(node),
            on_remove=NodesState.delete_node(node["id"]),
            remove_confirm_title="¿Eliminar nodo?",
            remove_confirm_description=confirm_delete(
                "el nodo", node["name"],
                "Dejarán de funcionar los sensores, puertas y luces que dependan de él."),
        ),
        spacing="3",
        align="center",
        width="100%",
        background=theme.BG_CARD, class_name="nx-card",
        border=f"1px solid {theme.BORDER}",
        border_radius="10px",
        padding="10px 14px",
    )


def _edit_node_dialog(node: dict) -> rx.Component:
    return form_dialog_content(
        icon="settings",
        title="Ajustes del nodo",
        accent=theme.PURPLE,
        form=rx.form.root(
            rx.vstack(
                rx.el.input(name="entity_id", value=node["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=node["name"])),
                field("Tipo de nodo", styled_select(
                    "Tipo de nodo",
                    select_content(*[rx.select.item(label, value=val) for val, label in _NODE_KIND_OPTIONS]),
                    name="kind", default_value=node["kind"],
                )),
                field("IP", styled_input(name="ip", default_value=node["ip"])),
                dialog_footer(confirm_label="Guardar", color_scheme="purple"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_node,
        ),
    )


def _add_node_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Nodo", size="2", variant="surface", color_scheme="purple"),
        ),
        form_dialog_content(
            icon="cpu",
            title="Nuevo nodo",
            accent=theme.PURPLE,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Nodo Garaje")),
                    field("Tipo de nodo", styled_select(
                        "Tipo de nodo",
                        select_content(*[rx.select.item(label, value=val) for val, label in _NODE_KIND_OPTIONS]),
                        name="kind", default_value="esp32",
                    )),
                    field("IP", styled_input(name="ip", placeholder="192.168.1.50")),
                    dialog_footer(confirm_label="Añadir", color_scheme="purple"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_node,
                reset_on_submit=True,
            ),
        ),
    )


def _add_sensor_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Sensor", size="2", variant="surface", color_scheme="blue"),
        ),
        form_dialog_content(
            icon="radar",
            title="Nuevo sensor",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Ventana Cocina")),
                    field("Tipo de sensor", styled_select(
                        "Tipo de sensor",
                        select_content(*[rx.select.item(label, value=val) for val, label in _KIND_OPTIONS]),
                        name="kind", default_value="door",
                    )),
                    field("Nodo", node_select()),
                    field(
                        "Pin o señal MQTT",
                        styled_input(name="pin", placeholder="17 · tamper1"),
                    ),
                    dialog_footer(confirm_label="Añadir"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_sensor,
                reset_on_submit=True,
            ),
        ),
    )


def _elemento_vigilado(e: rx.Var) -> rx.Component:
    """Una línea: elemento y el desplegable de qué cámara lo mira."""
    return rx.hstack(
        rx.icon("radar", size=15, color=theme.MUTED, flex_shrink="0"),
        rx.vstack(
            rx.text(e["nombre"], size="2", color=theme.TEXT),
            rx.cond(
                e["aviso"] != "",
                rx.text(e["aviso"], size="1", color=theme.WARNING),
            ),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.select.root(
            rx.select.trigger(placeholder="Sin cámara", variant="surface"),
            select_content(
                rx.foreach(
                    NodesState.camaras_vigilancia,
                    lambda c: rx.select.item(c["nombre"], value=c["id"]),
                ),
            ),
            value=e["camara"],
            on_change=lambda v: NodesState.asignar_camara(e["id"], v),
            size="1",
        ),
        align="center", spacing="3", width="100%",
        padding="8px 10px", border_radius="10px",
        background=theme.BG_CARD, class_name="nx-card",
        border=f"1px solid {theme.BORDER}",
    )


def _camaras_de_los_elementos() -> rx.Component:
    """Qué cámara mira a cada elemento de la alarma.

    Va en una sección propia y no dentro de la ficha de cada sensor: los
    elementos que disparan están repartidos entre los de fábrica y los dados de
    alta, con dos tarjetas y dos diálogos distintos, y esto se entiende mucho
    mejor visto todo junto — es una tabla de «quién mira a qué».

    Solo para quien puede tocar ajustes: es configuración de la instalación.
    Esconderlo no es el permiso, que se comprueba dentro del manejador
    (NodesState.asignar_camara); esto es para no ofrecer lo que no se va a
    poder usar."""
    return rx.cond(
        AuthState.puede_ajustes,
        rx.vstack(
            rx.hstack(
                rx.text("Cámara por elemento", size="1", color=theme.MUTED,
                        class_name="nx-label", weight="bold"),
                rx.spacer(),
                width="100%", align="center", padding_top="3",
            ),
            rx.text(
                "Al saltar la alarma se guarda un fotograma de la cámara "
                "elegida y queda dentro del evento, en Registros.",
                size="1", color=theme.MUTED,
            ),
            rx.foreach(NodesState.elementos_vigilados, _elemento_vigilado),
            spacing="2", width="100%",
        ),
    )


def alarm_view() -> rx.Component:
    return rx.vstack(
        _master_arm_card(),
        rx.hstack(
            rx.text("Nodos", size="1", color=theme.MUTED, weight="bold", class_name="nx-label"),
            rx.spacer(),
            _add_node_dialog(),
            width="100%",
            align="center",
            padding_top="2",
        ),
        rx.vstack(
            rx.foreach(NodesState.nodes, _node_card),
            spacing="2",
            width="100%",
        ),
        rx.hstack(
            rx.text("Sensores", size="1", color=theme.MUTED, weight="bold", class_name="nx-label"),
            rx.spacer(),
            _add_sensor_dialog(),
            width="100%",
            align="center",
            padding_top="3",
        ),
        rx.foreach(NodesState.sensors, _dynamic_sensor_card),
        _camaras_de_los_elementos(),
        spacing="3",
        width="100%",
    )
