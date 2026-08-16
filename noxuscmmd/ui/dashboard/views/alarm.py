"""
Vista "Alarma": todos los sensores binarios en un único sitio — los que ya
existían en el registry (puerta principal, tampers, cableados a la
Raspberry/Pi Zero) tratados exactamente igual que los que se dan de alta en
caliente sobre un nodo ESP32. Mismo diseño de tarjeta, mismo menú de acciones
(⋮ Editar/Aislar/Ocultar-o-Eliminar), un único listado — no hay "sensores de
primera" y "sensores de segunda".
"""
import reflex as rx

from ....domains.security.state import SecurityState
from ....domains.security.groups_state import GroupsState
from ....domains.devices import registry
from ....domains.devices.registry_state import RegistryState
from ....domains.nodes.state import NodesState
from .. import theme
from ..components.node_select import node_select
from ..components.edit_entity_dialog import edit_entity_dialog
from ..components.hidden_card import hidden_entities_card
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select
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

_NODE_KIND_OPTIONS = [
    ("esp32", "ESP32 (MQTT)"),
    ("ssh", "SSH (tipo Raspberry)"),
]

def _edit_static_sensor_dialog(sid: str, name: str, kind: str, node_id: str | None, topic: str,
                                show_on_floor: bool, floor_icon: str) -> rx.Component:
    """Mismos campos que el editor de un sensor dado de alta en caliente
    (_edit_sensor_dialog) — tipo, nodo (selector real) y topic/pin — para que
    editar un sensor de fábrica se sienta exactamente igual."""
    return form_dialog_content(
        icon="pencil",
        title=f"Editar {name}",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=sid, type="hidden"),
                field("Nombre", styled_input(name="name", default_value=name)),
                field("Tipo de sensor", styled_select(
                    "Tipo de sensor",
                    rx.select.content(*[rx.select.item(label, value=val) for val, label in _KIND_OPTIONS]),
                    name="kind", default_value=kind,
                )),
                field("Nodo", node_select(name="node", default_value=node_id)),
                field("Topic MQTT", styled_input(name="topic", default_value=topic)),
                *floor_plan_fields(show_on_floor, floor_icon, key=sid),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=RegistryState.submit_edit_entity,
        ),
    )


def _sensor_card(sid: str, kind: str, node_id: str | None, topic: str,
                  floor_top: str | None = None, floor_icon: str | None = None) -> rx.Component:
    """Misma tarjeta para TODOS los sensores — vengan de registry.py (puerta
    principal, tampers...) o dados de alta en caliente. Ninguno tiene ya un
    mecanismo de armado propio: el armado se decide exclusivamente por
    pertenencia a un grupo (pestaña Grupos), incluido el "grupo principal"
    que hace de armado general."""
    meta = _KIND_META.get(kind, _KIND_META["generic"])
    is_open = SecurityState.sensor_abierto[sid]
    accent_open = meta["accent_open"]
    name = RegistryState.names[sid]
    node_label = RegistryState.names[node_id] if node_id else "Sin nodo"
    # Var reactiva (RegistryState.isolated), no un bool de Python — así el
    # icono/color/badge se repintan al instante al aislar/reactivar, en vez
    # de necesitar reiniciar el servicio para verse (ver registry_state.py).
    isolated = RegistryState.isolated.get(sid, False)

    return rx.hstack(
        rx.box(
            rx.icon(
                rx.cond(is_open, meta["icon_open"], meta["icon_closed"]),
                size=20,
                color=rx.cond(isolated, theme.MUTED, rx.cond(is_open, accent_open, theme.SUCCESS)),
            ),
            padding="10px",
            border_radius="10px",
            background=rx.cond(
                isolated,
                theme.alpha(theme.MUTED, 0.10),
                rx.cond(is_open, theme.alpha(accent_open, 0.14), theme.alpha(theme.SUCCESS, 0.14)),
            ),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(name, size="3", weight="bold", color=rx.cond(isolated, theme.MUTED, theme.TEXT)),
                rx.badge(meta["label"], variant="soft", size="1", color_scheme="gray"),
                rx.badge(node_label, variant="outline", size="1", color_scheme="purple"),
                rx.cond(isolated, rx.badge("AISLADO", variant="soft", size="1", color_scheme="gray")),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.badge(
                rx.cond(is_open, meta["text_open"], meta["text_closed"]),
                color_scheme=rx.cond(is_open, "orange", "green"),
                variant="surface",
                size="1",
            ),
            rx.cond(
                isolated,
                rx.text("Aislado: no dispara alerta aunque su grupo esté armado", size="1", color=theme.MUTED),
                _group_membership(sid),
            ),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        actions_menu(
            edit_content=_edit_static_sensor_dialog(
                sid, name, kind, node_id, topic, bool(floor_top), floor_icon or "",
            ),
            on_isolate=RegistryState.toggle_isolated(sid),
            isolate_label=rx.cond(isolated, "Reactivar", "Aislar"),
            isolate_icon=rx.cond(isolated, "eye", "eye-off"),
            on_remove=RegistryState.delete_factory_entity(sid),
            remove_confirm_title="¿Eliminar sensor?",
            remove_confirm_description=confirm_delete("el sensor", name),
        ),
        spacing="3",
        align="start",
        width="100%",
        background=rx.cond(isolated, theme.alpha(theme.MUTED, 0.04), theme.BG_CARD),
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
        opacity=rx.cond(isolated, "0.7", "1"),
    )


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
        rx.button(
            rx.cond(armed, "DESARMAR", "ARMAR"),
            on_click=GroupsState.toggle_group_armed(principal["id"]),
            color_scheme=rx.cond(armed, "red", "green"),
            variant=rx.cond(armed, "solid", "surface"),
            size="3",
        ),
        width="100%",
        align="center",
        spacing="3",
        background=theme.BG_CARD,
        border=rx.cond(
            armed,
            f"1px solid {theme.alpha(theme.DANGER, 0.4)}",
            f"1px solid {theme.BORDER}",
        ),
        border_radius="12px",
        padding="16px",
        backdrop_filter="blur(10px)",
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
        background=rx.cond(isolated, theme.alpha(theme.MUTED, 0.04), theme.BG_CARD),
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        backdrop_filter="blur(10px)",
        opacity=rx.cond(isolated, "0.7", "1"),
    )


def _edit_sensor_dialog(sensor: dict) -> rx.Component:
    return form_dialog_content(
        icon="pencil",
        title="Editar sensor",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=sensor["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=sensor["name"])),
                field("Tipo de sensor", styled_select(
                    "Tipo de sensor",
                    rx.select.content(*[rx.select.item(label, value=val) for val, label in _KIND_OPTIONS]),
                    name="kind", default_value=sensor["kind"],
                )),
                field("Nodo", node_select(default_value=sensor["node_id"])),
                field("Pin GPIO (SSH) o señal MQTT (ESP32)", styled_input(name="pin", default_value=sensor["pin"])),
                *floor_plan_fields(
                    sensor["floor_top"],
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


def _host_node_card(host_id: str, ip: str) -> rx.Component:
    """Raspberry/Pi Zero: siempre disponibles como nodo (vienen del registry,
    no se dan de alta desde aquí), pero editables y con el mismo menú de
    acciones que cualquier otro nodo — "Ocultar" en vez de "Eliminar" porque
    son hardware fijo (se restauran desde la tarjeta de ocultos, igual que en
    la pestaña Equipos)."""
    name = RegistryState.names[host_id]
    return rx.hstack(
        rx.icon("cpu", size=18, color=theme.ACCENT),
        rx.vstack(
            rx.text(name, size="2", weight="bold", color=theme.TEXT),
            rx.text(ip or "—", size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        rx.badge("SSH", variant="soft", size="1", color_scheme="blue"),
        actions_menu(
            edit_content=edit_entity_dialog(
                entity_id=host_id,
                title=f"Editar {name}",
                fields=[
                    ("name", "Nombre", name),
                    ("host", "IP", ip),
                ],
            ),
            on_remove=RegistryState.hide_entity(host_id),
            remove_style="reversible",
            remove_label="Ocultar",
            remove_icon="archive",
        ),
        spacing="3",
        align="center",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="10px",
        padding="10px 14px",
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
        rx.badge(
            rx.cond(node["kind"] == "ssh", "SSH", "ESP32 · MQTT"),
            variant="soft", size="1", color_scheme="blue",
        ),
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
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="10px",
        padding="10px 14px",
    )


def _edit_node_dialog(node: dict) -> rx.Component:
    return form_dialog_content(
        icon="pencil",
        title="Editar nodo",
        accent=theme.PURPLE,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=node["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=node["name"])),
                field("Tipo de nodo", styled_select(
                    "Tipo de nodo",
                    rx.select.content(*[rx.select.item(label, value=val) for val, label in _NODE_KIND_OPTIONS]),
                    name="kind", default_value=node["kind"],
                )),
                field("IP", styled_input(name="ip", default_value=node["ip"])),
                field("Usuario SSH", styled_input(name="user", default_value=node["user"]), hint="Solo aplica si el tipo es SSH."),
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
                        rx.select.content(*[rx.select.item(label, value=val) for val, label in _NODE_KIND_OPTIONS]),
                        name="kind", default_value="esp32",
                    )),
                    field("IP", styled_input(name="ip", placeholder="192.168.1.50")),
                    field("Usuario SSH", styled_input(name="user", placeholder="Solo si el tipo es SSH")),
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
                        rx.select.content(*[rx.select.item(label, value=val) for val, label in _KIND_OPTIONS]),
                        name="kind", default_value="door",
                    )),
                    field("Nodo", node_select()),
                    field(
                        "Pin GPIO (SSH) o señal MQTT (ESP32)",
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


def alarm_view() -> rx.Component:
    hidden = registry.hidden_ids()
    sensors = {sid: s for sid, s in registry.binary_sensors().items() if sid not in hidden}
    gpio_hosts = {hid: h for hid, h in registry.gpio_hosts().items() if hid not in hidden}
    hidden_sensors = {sid: s.name for sid, s in registry.binary_sensors().items() if sid in hidden}
    return rx.vstack(
        _master_arm_card(),
        rx.hstack(
            rx.text("NODOS", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_node_dialog(),
            width="100%",
            align="center",
            padding_top="2",
        ),
        rx.vstack(
            *[_host_node_card(hid, h.ssh.host) for hid, h in gpio_hosts.items()],
            rx.foreach(NodesState.nodes, _node_card),
            spacing="2",
            width="100%",
        ),
        rx.hstack(
            rx.text("SENSORES", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_sensor_dialog(),
            width="100%",
            align="center",
            padding_top="3",
        ),
        *[
            _sensor_card(sid, s.kind, s.node, s.mqtt.topic if s.mqtt else "", s.floor_top, s.floor_icon)
            for sid, s in sensors.items()
        ],
        rx.foreach(NodesState.sensors, _dynamic_sensor_card),
        hidden_entities_card("SENSORES", hidden_sensors),
        spacing="3",
        width="100%",
    )
