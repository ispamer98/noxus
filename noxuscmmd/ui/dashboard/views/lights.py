"""
Vista "Luces": relés de iluminación colgando de un nodo (Raspberry/Pi Zero
por SSH, o ESP32 por MQTT). Mismo patrón que Accesos, pero con toggle ON/OFF
en vez de pulso momentáneo. Las luces se agrupan opcionalmente por estancia
(NodesState.rooms) — puramente organizativo, no afecta a cómo se controlan.
"""
import reflex as rx

from ....domains.nodes import store as nodes_store
from ....domains.nodes.state import NodesState
from .. import theme
from ..components.node_select import node_select
from ..components.actions_menu import actions_menu, confirm_delete, confirm_delete_dialog
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select, select_content
from ..components.floor_fields import floor_plan_fields


def _room_select(name: str = "room_id", default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Estancia (opcional)",
        select_content(
            rx.select.item("Sin estancia", value=""),
            rx.foreach(NodesState.rooms, lambda r: rx.select.item(r["name"], value=r["id"])),
        ),
        name=name,
        **kwargs,
    )


# Qué icono lleva cada aparato. La mecánica es la misma para todos (encender y
# apagar), lo que cambia es qué es: una luz, el ventilador de techo, la tele.
# El mapa vive en el dominio (store.ICONO_ASPECTO): lo comparten esta pantalla,
# el plano y el catálogo de widgets.
ICONO_ASPECTO = nodes_store.ICONO_ASPECTO
NOMBRE_ASPECTO = {
    "luz": "Luz", "ventilador": "Ventilador", "tv": "Televisión",
    "enchufe": "Enchufe", "otro": "Otro aparato",
}


def _aspecto_select(default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Qué es",
        select_content(
            *[rx.select.item(NOMBRE_ASPECTO[a], value=a) for a in ICONO_ASPECTO],
        ),
        name="aspecto",
        **kwargs,
    )


def _kind_select(default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Cómo se enciende",
        select_content(
            rx.select.item("Por relé (nodo con GPIO o MQTT)", value="rele"),
            rx.select.item("Por mando (infrarrojos)", value="mando"),
        ),
        name="light_kind",
        **kwargs,
    )


def _modo_mando_select(default_value=None) -> rx.Component:
    """Una tecla o dos. El ventilador de techo tiene «Luz ON» y «Luz OFF»
    separadas; la tele, una sola tecla de encendido que hace las dos cosas."""
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Teclas del mando",
        select_content(
            rx.select.item("Dos teclas: una enciende y otra apaga", value="dos"),
            rx.select.item("Una sola tecla para encender y apagar", value="una"),
        ),
        name="mando_modo",
        **kwargs,
    )


def _tecla_select(name: str, etiqueta: str, default_value=None) -> rx.Component:
    """Un solo desplegable con las teclas de TODOS los mandos, ya etiquetadas
    "Mando · Tecla". El mando se deduce de la tecla elegida (ver
    NodesState.teclas_de_mando)."""
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        etiqueta,
        select_content(
            rx.foreach(
                NodesState.teclas_de_mando,
                lambda t: rx.select.item(t["etiqueta"], value=t["valor"]),
            ),
        ),
        name=name,
        **kwargs,
    )


def _light_card(light: dict) -> rx.Component:
    is_on = NodesState.sensor_state[light["id"].to(str)]
    return rx.hstack(
        rx.box(
            rx.icon(
                rx.match(
                    light["aspecto"],
                    ("ventilador", "fan"),
                    ("tv", "tv"),
                    ("enchufe", "plug"),
                    ("otro", "toggle-right"),
                    "lightbulb",
                ),
                size=20, color=rx.cond(is_on, theme.WARNING, theme.MUTED),
            ),
            padding="10px",
            border_radius="10px",
            background=rx.cond(is_on, theme.alpha(theme.WARNING, 0.16), theme.alpha(theme.MUTED, 0.08)),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(light["name"], size="3", weight="bold", color=theme.TEXT),
                rx.badge(light["node_name"], variant="outline", size="1", color_scheme="purple"),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            # Un accesorio por mando no tiene pin ni topic: enseñar "Pin ·"
            # vacío no dice nada. Se enseña de qué mando depende.
            rx.cond(
                light["kind"] == "mando",
                rx.text("Por mando · " + light["remote_id"].to(str), size="1",
                        color=theme.MUTED, font_family=theme.FONT_MONO),
                rx.text(f"Pin {light['pin']} · {light['topic_cmd']}", size="1",
                        color=theme.MUTED, font_family=theme.FONT_MONO),
            ),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        rx.switch(
            checked=is_on,
            on_change=NodesState.toggle_light(light["id"]),
            color_scheme="orange",
        ),
        actions_menu(
            edit_content=_edit_light_dialog(light),
            on_remove=NodesState.delete_light(light["id"]),
            remove_confirm_title="¿Eliminar luz?",
            remove_confirm_description=confirm_delete("la luz", light["name"]),
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


def _edit_light_dialog(light: dict) -> rx.Component:
    return form_dialog_content(
        icon="lightbulb",
        title="Editar luz",
        accent=theme.WARNING,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=light["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=light["name"])),
                field("Qué es", _aspecto_select(default_value=light["aspecto"])),
                field("Cómo se enciende", _kind_select(default_value=light["kind"])),
                field("Nodo (solo si es por relé)", node_select(default_value=light["node_id"])),
                field("Pin GPIO (SSH) o señal MQTT (ESP32)", styled_input(name="pin", default_value=light["pin"])),
                field("Teclas del mando (solo si es por mando)",
                      _modo_mando_select(default_value=light["mando_modo"])),
                field("Tecla de encender · o la única si es de una sola",
                      _tecla_select("btn_on", "Tecla de encender")),
                field("Tecla de apagar · se ignora si es de una sola",
                      _tecla_select("btn_off", "Tecla de apagar")),
                field("Estancia", _room_select(default_value=light["room_id"])),
                *floor_plan_fields(
                    light["floor_top"],
                    rx.cond(light["floor_icon"], light["floor_icon"].to(str), "lightbulb"),
                    key=light["id"].to(str),
                ),
                dialog_footer(confirm_label="Guardar", color_scheme="orange"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_light,
        ),
    )


def _add_light_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Añadir luz", size="2", variant="surface", color_scheme="orange"),
        ),
        form_dialog_content(
            icon="lightbulb",
            title="Nueva luz",
            accent=theme.WARNING,
            # Raspberry/Pi Zero actúan por SSH (pin GPIO, como el ventilador); un nodo ESP32 actúa por MQTT
            # (nombre de señal — el topic se arma solo como casa/<nombre del nodo>/<señal>).
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Luz Salón")),
                    field("Qué es", _aspecto_select(default_value="luz")),
                    field("Cómo se enciende", _kind_select(default_value="rele")),
                    # Los dos bloques van siempre puestos y se rellena el que
                    # corresponda: el submit se queda solo con los del tipo
                    # elegido (ver NodesState.submit_add_light), y así no hace
                    # falta sacar el formulario entero al estado para esconder
                    # la mitad.
                    field("Nodo (solo si es por relé)", node_select()),
                    field("Pin GPIO (SSH) o señal MQTT (ESP32)", styled_input(name="pin", placeholder="22 · luz_salon")),
                    field("Teclas del mando (solo si es por mando)",
                          _modo_mando_select(default_value="dos")),
                    field("Tecla de encender · o la única si es de una sola",
                          _tecla_select("btn_on", "Tecla de encender")),
                    field("Tecla de apagar · se ignora si es de una sola",
                          _tecla_select("btn_off", "Tecla de apagar")),
                    field("Estancia", _room_select()),
                    dialog_footer(confirm_label="Añadir", color_scheme="orange"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_light,
                reset_on_submit=True,
            ),
        ),
    )


def _add_room_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Estancia", size="2", variant="surface", color_scheme="gray"),
        ),
        form_dialog_content(
            icon="layout-grid",
            title="Nueva estancia",
            accent=theme.MUTED,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Salón, Cocina, Habitación 1")),
                    dialog_footer(confirm_label="Crear", color_scheme="gray"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_room,
                reset_on_submit=True,
            ),
        ),
    )


def _room_section(room: dict) -> rx.Component:
    lights = NodesState.lights_by_room.get(room["id"].to(str), [])
    return rx.vstack(
        rx.hstack(
            rx.text(room["name"], size="2", weight="bold", color=theme.TEXT, letter_spacing="0.03em"),
            rx.spacer(),
            confirm_delete_dialog(
                rx.icon(
                    "trash-2", size=13, color=theme.MUTED, cursor="pointer",
                    _hover={"color": theme.DANGER},
                    title="Eliminar esta estancia",
                ),
                title="¿Eliminar estancia?",
                tipo="la estancia", nombre=room["name"],
                extra="Las luces no se borran, se quedan sin estancia.",
                on_confirm=NodesState.delete_room(room["id"]),
            ),
            width="100%", align="center",
        ),
        rx.cond(
            lights.length() == 0,
            rx.text("Sin luces en esta estancia todavía.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(lights, _light_card), spacing="2", width="100%"),
        ),
        spacing="2",
        width="100%",
    )


def lights_view() -> rx.Component:
    # El estado ON/OFF es el último comando enviado — se corrige solo si el firmware confirma
    # por MQTT en el topic de estado.
    sin_estancia = NodesState.lights_by_room.get("_none", [])
    return rx.vstack(
        rx.hstack(
            rx.text("LUCES", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_room_dialog(),
            _add_light_dialog(),
            width="100%",
            align="center",
            wrap="wrap",
        ),
        rx.cond(
            ~NodesState.hay_luces,
            rx.text("Aún no hay luces dadas de alta.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(
                rx.foreach(NodesState.rooms, _room_section),
                rx.cond(
                    sin_estancia.length() > 0,
                    rx.vstack(
                        rx.text("SIN ESTANCIA", size="2", weight="bold", color=theme.TEXT, letter_spacing="0.03em"),
                        rx.vstack(rx.foreach(sin_estancia, _light_card), spacing="2", width="100%"),
                        spacing="2", width="100%",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
        ),
        spacing="3",
        width="100%",
    )
