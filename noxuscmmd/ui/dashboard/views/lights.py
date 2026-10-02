"""
Vista "Luces": relés de iluminación colgando de un nodo (Raspberry/Pi Zero
o ESP32, siempre por MQTT). Mismo patrón que Accesos, pero con toggle ON/OFF
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
    "enchufe": "Enchufe", "persiana": "Persiana", "otro": "Otro aparato",
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


def _kind_select(default_value=None, on_change=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    if on_change is not None:
        kwargs["on_change"] = on_change
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


def _modo_encendido_select(default_value=None) -> rx.Component:
    kwargs = {"default_value": default_value} if default_value is not None else {}
    return styled_select(
        "Modo de encendido",
        select_content(
            rx.select.item("Sin modo", value=""),
            rx.select.item("Continuo", value="continuo"),
            rx.select.item("1 h", value="1h"),
            rx.select.item("2 h", value="2h"),
            rx.select.item("3 h", value="3h"),
        ), name="modo_encendido", **kwargs,
    )


def _modo_encendido_fields(light=None):
    light = {} if light is None else light
    remote = light.get("remote_id", "")
    def tecla(campo):
        valor = light.get(campo, "")
        if isinstance(remote, str) and isinstance(valor, str):
            return f"{remote}:{valor}" if remote and valor else None
        return None
    return (
        field("Modo de encendido", _modo_encendido_select(light.get("modo_encendido"))),
        field("Tecla Continuo", _tecla_select("btn_continuo", "Tecla Continuo",
                                                tecla("btn_continuo"))),
        field("Tecla Temporizador", _tecla_select("btn_timing", "Tecla Temporizador",
                                                   tecla("btn_timing"))),
        field("Pausa entre teclas (s)", styled_input(
            name="pausa_secuencia_s", default_value=str(light.get("pausa_secuencia_s", 1.0)),
            type="number", min="0", step="0.1")),
    )


def _apagar_luz_fields(light=None):
    light = {} if light is None else light
    remote = light.get("remote_id", "")
    btn_luz = light.get("btn_luz", "")
    if isinstance(remote, str) and isinstance(btn_luz, str):
        tecla_luz = f"{remote}:{btn_luz}" if remote and btn_luz else None
    else:
        tecla_luz = rx.cond((remote != "") & (btn_luz != ""),
                             remote.to(str) + ":" + btn_luz.to(str), "")
    return (
        field("Apagar la luz al encender", rx.switch(
            name="apagar_luz_al_encender",
            default_checked=light.get("apagar_luz_al_encender", False),
        )),
        field("Tecla Luz", _tecla_select("btn_luz", "Tecla Luz", tecla_luz)),
        field("Repeticiones", styled_input(
            name="luz_repeticiones", default_value=str(light.get("luz_repeticiones", 25)),
            type="number", min="1", max="60")),
        field("Intervalo (s)", styled_input(
            name="luz_intervalo_s", default_value=str(light.get("luz_intervalo_s", 0.12)),
            type="number", min="0.05", max="1.0", step="0.01")),
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
        background=theme.BG_CARD, class_name="nx-card",
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px",
        wrap="wrap",
    )


def _edit_light_dialog(light: dict) -> rx.Component:
    return form_dialog_content(
        icon="lightbulb",
        title="Ajustes de la luz",
        accent=theme.WARNING,
        form=rx.form.root(
            rx.vstack(
                rx.el.input(name="entity_id", value=light["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=light["name"])),
                field("Qué es", _aspecto_select(default_value=light["aspecto"])),
                field("Cómo se enciende", _kind_select(default_value=light["kind"])),
                rx.cond(
                    light["kind"] == nodes_store.LUZ_MANDO,
                    field("Apagado automático (minutos)", styled_input(
                        name="auto_apagado_min",
                        default_value=str(light.get("auto_apagado_min", 0)),
                        type="number", min="0")),
                    rx.fragment(),
                ),
                field("Nodo del relé", node_select(default_value=light["node_id"])),
                field("Pin o señal MQTT", styled_input(name="pin", default_value=light["pin"])),
                field("Modo del mando",
                      _modo_mando_select(default_value=light["mando_modo"])),
                field("Tecla de encendido",
                      _tecla_select("btn_on", "Tecla de encender")),
                field("Tecla de apagado",
                      _tecla_select("btn_off", "Tecla de apagar")),
                *_modo_encendido_fields(light),
                *_apagar_luz_fields(light),
                field("Estancia", _room_select(default_value=light["room_id"])),
                *floor_plan_fields(
                    False,
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
            # Todos los nodos (Raspberry, Pi Zero, ESP32) actúan por MQTT: casa/<nodo>/<pin>/set
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
                    field("Nodo del relé", node_select()),
                    field("Pin o señal MQTT", styled_input(name="pin", placeholder="22 · luz_salon")),
                    field("Modo del mando",
                          _modo_mando_select(default_value="dos")),
                    field("Tecla de encendido",
                          _tecla_select("btn_on", "Tecla de encender")),
                    field("Tecla de apagado",
                          _tecla_select("btn_off", "Tecla de apagar")),
                    *_modo_encendido_fields(),
                    *_apagar_luz_fields(),
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
            rx.text("Luces", size="1", color=theme.MUTED, weight="bold", class_name="nx-label"),
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
                        rx.text("Sin estancia", size="2", weight="bold",
                                color=theme.TEXT, class_name="nx-label"),
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
