"""
Vista "Equipos": lista única de TODOS los equipos de la casa, sin distinción
de origen. Da igual que el equipo venga de siempre (server, pc, raspberry...)
o se haya dado de alta hace un minuto: una sola tarjeta, un solo formulario y
exactamente los mismos ocho campos (nombre, IP, usuario SSH, usuario de
escritorio remoto, sistema, MAC, reintentos de ping, icono) tanto al crear como
al editar.

Tarjeta MÍNIMA en reposo: solo icono (coloreado según en línea/sin conexión —
ya dice lo que decía la antigua etiqueta de texto, sin repetirlo) y nombre. La
IP y todo lo accionable viven dentro, al desplegar, para que la lista completa
quepa de un vistazo sin ruido.

Dentro, TODAS las acciones —las tres de siempre (apagar/reiniciar/
temperatura), las cableadas (RDP/WOL/relés) y las personalizables (comando
SSH / pin)— son botones con el MISMO formato (`_chip`): mismo tamaño, misma
forma, en una sola fila que se ajusta sola. Solo cambia el color, y con
significado (rojo = apaga algo, verde = enciende, gris = neutro) — no hay ya
tres estéticas distintas para tres orígenes distintos del mismo tipo de cosa.

La consola SSH libre es la única pieza que NO es un botón de una acción
concreta, así que se queda recogida hasta que se pide con su propio botón
"Consola" — es lo que más sitio ocupa y lo que menos se usa.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from ....domains.nodes.host_actions_state import HostActionsState
from ....domains.infra.state import InfraState
from .. import theme
from ..state import DashboardState
from ..components.actions_menu import actions_menu, confirm_delete, confirm_delete_dialog
from ..components.form_dialog import form_dialog_content, field, dialog_footer, styled_input, styled_select, select_content
from ..components.icon_picker import icon_field

_HOST_ICONS = ["server", "monitor", "laptop", "smartphone", "tablet", "router", "printer", "hard-drive", "cpu"]

_BUTTON_KIND_OPTIONS = [
    ("ssh_command", "Comando SSH (muestra la salida)"),
    ("pin_write_on", "Poner un pin a ON"),
    ("pin_write_off", "Poner un pin a OFF"),
    ("pin_read", "Leer un pin (muestra la salida)"),
]

_NODE_KIND_OPTIONS = [("esp32", "ESP32 (MQTT)"), ("ssh", "SSH (tipo Raspberry)")]

# El sistema decide qué comando de apagado/reinicio se manda por SSH (ver
# domains/devices/ssh_bus.py) — por eso es un campo del equipo y no un detalle.
_OS_OPTIONS = [("linux", "Linux"), ("windows", "Windows")]


def _chip(icon, label, on_click, *, color: str = "gray", loading=False) -> rx.Component:
    """UNA acción, siempre con el mismo formato — da igual si es de las tres
    de siempre, una cableada (RDP/WOL/relé) o un botón que alguien se montó a
    medida: mismo tamaño, misma forma, mismo tipo de letra. Solo el color
    cambia, y con significado (ver los usos más abajo), no por decoración."""
    return rx.button(
        rx.icon(icon, size=13), label,
        on_click=on_click,
        size="1",
        variant="soft",
        color_scheme=color,
        loading=loading,
        flex_shrink="0",
    )


def _console_panel(host_id) -> rx.Component:
    """Recogida por defecto — ver toggle_console. Solo el contenido; el botón
    que la muestra/oculta vive en la fila de chips, junto a las demás
    acciones, con el mismo formato que ellas."""
    return rx.cond(
        HostActionsState.console_shown.get(host_id, False),
        rx.vstack(
            rx.hstack(
                rx.input(
                    value=HostActionsState.console_input.get(host_id, ""),
                    on_change=lambda v: HostActionsState.set_console_input(host_id, v),
                    placeholder="ls -la",
                    size="2",
                    width="100%",
                    auto_complete=False,
                    style={"font_family": theme.FONT_MONO},
                ),
                rx.button(
                    rx.icon("terminal", size=14),
                    "Ejecutar",
                    on_click=HostActionsState.run_console_command(host_id),
                    size="2",
                    variant="surface",
                    loading=HostActionsState.running.get(host_id, False),
                ),
                spacing="2",
                width="100%",
            ),
            rx.cond(
                HostActionsState.console_output.get(host_id, "") != "",
                rx.box(
                    rx.code(
                        HostActionsState.console_output.get(host_id, ""),
                        white_space="pre-wrap",
                        width="100%",
                    ),
                    width="100%",
                    max_height="200px",
                    overflow_y="auto",
                    background="#0b0f17",
                    padding="10px",
                    border_radius="8px",
                    border=f"1px solid {theme.BORDER}",
                ),
            ),
            spacing="2",
            width="100%",
            padding_top="2",
        ),
    )


def _default_action_chips(host_id) -> list[rx.Component]:
    # UNA clave de carga por acción (host_id + ":" + acción), no por equipo:
    # con una sola bandera para las tres, pulsar "Temperatura" encendía
    # también el aro de "Apagar" y "Reiniciar" — los tres leían lo mismo.
    return [
        _chip("power", "Apagar", HostActionsState.accion_generica(host_id, "apagar"),
              color="red", loading=HostActionsState.running.get(host_id + ":apagar", False)),
        _chip("rotate-cw", "Reiniciar", HostActionsState.accion_generica(host_id, "reiniciar"),
              color="amber", loading=HostActionsState.running.get(host_id + ":reiniciar", False)),
        _chip("thermometer", "Temperatura", HostActionsState.accion_generica(host_id, "temperatura"),
              color="blue", loading=HostActionsState.running.get(host_id + ":temperatura", False)),
    ]


def _custom_button_chip(b, host_id) -> rx.Component:
    return rx.cond(
        b["host_id"] == host_id,
        rx.hstack(
            # Cargado por el ID DEL BOTÓN, no del equipo: dos botones en el
            # mismo equipo no deben encenderse el aro el uno al otro.
            _chip("zap", b["label"], HostActionsState.run_button(b["id"]),
                  color="cyan", loading=HostActionsState.running.get(b["id"].to(str), False)),
            confirm_delete_dialog(
                rx.icon("x", size=11, color=theme.MUTED, cursor="pointer",
                        _hover={"color": theme.DANGER}, title="Quitar este botón"),
                title="¿Eliminar botón?", tipo="el botón", nombre=b["label"],
                on_confirm=HostActionsState.delete_button(b["id"]),
            ),
            spacing="1", align="center", flex_shrink="0",
        ),
        rx.fragment(),
    )


def _add_button_dialog(host_id) -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(_chip("plus", "Botón nuevo", rx.noop(), color="gray")),
        form_dialog_content(
            icon="zap",
            title="Nuevo botón de acción",
            accent=theme.ACCENT,
            max_width="380px",
            form=rx.form.root(
                rx.vstack(
                    rx.input(name="host_id", value=host_id, type="hidden"),
                    field("Nombre del botón", styled_input(name="label", placeholder="Reiniciar router")),
                    field("Tipo de acción", styled_select(
                        "Tipo de acción",
                        rx.select.content(*[rx.select.item(label, value=val) for val, label in _BUTTON_KIND_OPTIONS]),
                        name="kind", default_value="ssh_command",
                    )),
                    field(
                        "Comando SSH o número de pin",
                        styled_input(name="value", placeholder="17"),
                        hint="Comando SSH: se ejecuta tal cual. Pin ON/OFF/Leer: número de pin GPIO.",
                    ),
                    dialog_footer(confirm_label="Añadir", color_scheme="cyan"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=HostActionsState.submit_add_button,
                reset_on_submit=True,
            ),
        ),
    )


def _rdp_chips(e) -> list[rx.Component]:
    """Uno o dos chips según lo que tenga configurado el equipo — mismo
    formato que cualquier otro, solo que aquí puede haber un segundo chip de
    respaldo (ver el porqué en el docstring viejo de _rdp_buttons, que sigue
    aplicando: sin lanzador por SSH, el navegador no siempre sabe abrir
    rdp://, así que la descarga manda y "abrir directo" queda al lado)."""
    directo = _chip("monitor-play", e["label"], HostActionsState.open_rdp(e["target"]), color="cyan")
    respaldo = rx.fragment(
        _chip("download", e["label"], HostActionsState.download_rdp(e["target"]), color="cyan"),
        _chip("monitor-play", "Abrir directo", HostActionsState.open_rdp(e["target"]), color="gray"),
    )
    return [rx.cond(e["directo"], directo, respaldo)]


def _extra_chips(host) -> rx.Component:
    """Relés GPIO + acciones cableadas del equipo (RDP/WOL/foto), en el MISMO
    formato que el resto — pintadas desde los datos que NodesState ya dejó
    resueltos en host["extras"]: dentro de un rx.foreach no se puede
    consultar el registry ni elegir el manejador en Python, así que cada
    entrada viaja con su `kind` y su `target` y es el servidor quien resuelve
    la acción (ver InfraState.run_accion_extra)."""
    extras = host["extras"].to(list[dict])
    return rx.foreach(
        extras,
        lambda e: rx.cond(
            e["kind"] == "relay",
            rx.fragment(
                _chip("zap", e["label"], InfraState.accion_gpio(e["target"], "on"), color="green"),
                _chip("power-off", e["label"], InfraState.accion_gpio(e["target"], "off"), color="gray"),
            ),
            rx.cond(
                e["kind"] == "rdp",
                _rdp_chips(e)[0],
                _chip("zap", e["label"], InfraState.run_accion_extra(e["target"]),
                      color=rx.cond(e["target"] == "wake_pc", "green", "purple")),
            ),
        ),
    )


def _expand_panel(host) -> rx.Component:
    """Panel desplegable, idéntico para cualquier equipo. `host` es siempre un
    elemento de NodesState.hosts, así que todo lo de aquí es reactivo: quitarle
    el usuario SSH a un equipo apaga sus chips en el acto, sin reiniciar."""
    host_id = host["id"].to(str)
    return rx.vstack(
        rx.divider(border_color=theme.BORDER),
        rx.text(host["ip"], size="1", color=theme.MUTED, font_family=theme.FONT_MONO),
        rx.hstack(
            rx.cond(
                host["ssh_capable"],
                rx.fragment(*_default_action_chips(host_id)),
                rx.fragment(),
            ),
            _extra_chips(host),
            rx.foreach(HostActionsState.buttons, lambda b: _custom_button_chip(b, host_id)),
            _add_button_dialog(host_id),
            rx.cond(
                host["ssh_capable"],
                _chip("terminal", "Consola", HostActionsState.toggle_console(host_id), color="gray"),
                rx.fragment(),
            ),
            spacing="2", wrap="wrap", width="100%",
        ),
        rx.cond(
            ~host["ssh_capable"],
            rx.text(
                "Sin usuario SSH configurado — solo ping y lo cableado de la ficha.",
                size="1", color=theme.MUTED, italic=True,
            ),
        ),
        _console_panel(host_id),
        rx.hstack(
            rx.spacer(),
            actions_menu(
                edit_content=_edit_host_dialog(host),
                on_remove=NodesState.delete_host(host["id"]),
                remove_style="destructive",
                remove_label="Eliminar",
                remove_icon="trash-2",
                remove_confirm_title="¿Eliminar equipo?",
                remove_confirm_description=confirm_delete("el equipo", host["name"]),
            ),
            width="100%", padding_top="2",
        ),
        spacing="3", width="100%", padding_top="2",
    )


def _host_form_fields(host=None) -> list[rx.Component]:
    """Los OCHO campos de un equipo, en el mismo orden y con el mismo aspecto
    tanto al crear (host=None) como al editar. Tenerlos en una sola función es
    lo que garantiza que no vuelvan a divergir: antes el formulario de alta no
    ofrecía MAC ni sistema, así que un equipo creado desde la web nacía sin
    Wake on LAN y apagándose siempre con el comando de Linux."""
    editando = host is not None
    return [
        field("Nombre", styled_input(
            name="name", placeholder="NAS",
            **({"default_value": host["name"]} if editando else {}),
        )),
        field("IP", styled_input(
            name="ip", placeholder="192.168.1.20",
            **({"default_value": host["ip"]} if editando else {}),
        )),
        field(
            "Usuario SSH", styled_input(
                name="user",
                **({"default_value": host["user"]} if editando else {}),
            ),
            hint="Vacío = solo ping, sin acciones ni consola.",
        ),
        field(
            "Usuario de escritorio remoto (RDP)", styled_input(
                name="rdp_user", placeholder="usuario",
                **({"default_value": host["rdp_user"]} if editando else {}),
            ),
            hint="Vacío = este equipo no ofrece escritorio remoto. No tiene por qué ser "
                 "el mismo usuario que el de SSH: es la cuenta de Windows con la que se "
                 "abre la sesión remota.",
        ),
        field(
            "Lanzar el escritorio remoto desde", rx.select.root(
                rx.select.trigger(placeholder="El navegador de quien pulse", width="100%", size="3"),
                select_content(
                    rx.select.item("El navegador de quien pulse", value="navegador"),
                    rx.select.group(
                        rx.select.label("Abrirlo por SSH en..."),
                        rx.foreach(
                            NodesState.ssh_hosts,
                            lambda h: rx.select.item(h["name"], value=h["id"]),
                        ),
                    ),
                ),
                name="rdp_launch_host",
                default_value=host["rdp_launch_host"] if editando else "navegador",
            ),
            hint="Por el navegador solo funciona si el sistema de quien pulsa tiene "
                 "asociado el esquema rdp://; si no, se baja el .rdp. Eligiendo un equipo, "
                 "el servidor entra por SSH y abre el cliente allí — un clic y listo.",
        ),
        field("Sistema", styled_select(
            "Sistema",
            rx.select.content(*[rx.select.item(label, value=val) for val, label in _OS_OPTIONS]),
            name="os",
            default_value=host["os"] if editando else "linux",
        ), hint="Decide el comando de apagado y reinicio."),
        field("MAC (Wake on LAN, opcional)", styled_input(
            name="mac", placeholder="08-BF-B8-30-4E-1B",
            **({"default_value": host["mac"]} if editando else {}),
        )),
        field("Reintentos de ping", styled_input(
            name="ping_retries", type="number", min="1",
            **({"default_value": host["ping_retries"].to(str)} if editando else {"default_value": "1"}),
        ), hint="Súbelo si el equipo tarda en responder y sale offline sin estarlo."),
        field("Icono", icon_field(
            name="icon",
            key=(host["id"].to(str) + ":icon") if editando else "nuevo_equipo:icon",
            default_value=host["icon"].to(str) if editando else "server",
            options=_HOST_ICONS,
        )),
    ]


def _edit_host_dialog(host) -> rx.Component:
    return form_dialog_content(
        icon="server",
        title="Editar equipo",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=host["id"], type="hidden"),
                *_host_form_fields(host),
                dialog_footer(confirm_label="Guardar"),
                spacing="3",
                width="100%",
            ),
            on_submit=NodesState.submit_edit_host,
        ),
    )


def _add_host_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=13), "Añadir equipo", size="2", variant="surface"),
        ),
        form_dialog_content(
            icon="server",
            title="Nuevo equipo",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    *_host_form_fields(),
                    rx.divider(border_color=theme.BORDER),
                    rx.hstack(
                        rx.checkbox(name="es_nodo"),
                        rx.text("También es un nodo (ESP32/Raspberry) para sensores/puertas/luces", size="1", color=theme.MUTED),
                        spacing="2", align="center",
                    ),
                    field("Tipo de nodo (si aplica)", styled_select(
                        "Tipo de nodo",
                        rx.select.content(*[rx.select.item(label, value=val) for val, label in _NODE_KIND_OPTIONS]),
                        name="node_kind", default_value="esp32",
                    )),
                    dialog_footer(confirm_label="Añadir"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=NodesState.submit_add_host,
                reset_on_submit=True,
            ),
        ),
    )


def _reorder_controls(host) -> rx.Component:
    """Flechas de subir/bajar, solo en modo organizar. stop_propagation es
    imprescindible: sin él, el clic llega también a la fila y despliega la
    ficha del equipo justo cuando lo estabas recolocando."""
    return rx.hstack(
        rx.icon(
            "chevron-up", size=15, color=theme.MUTED, cursor="pointer",
            _hover={"color": theme.ACCENT},
            on_click=NodesState.move_host_up(host["id"].to(str)).stop_propagation,
            title="Subir",
        ),
        rx.icon(
            "chevron-down", size=15, color=theme.MUTED, cursor="pointer",
            _hover={"color": theme.ACCENT},
            on_click=NodesState.move_host_down(host["id"].to(str)).stop_propagation,
            title="Bajar",
        ),
        spacing="2", align="center", flex_shrink="0",
    )


def _host_card(host) -> rx.Component:
    """Tarjeta única — la misma para todos los equipos. En reposo, solo icono
    (su color YA dice si está en línea) y nombre — la IP y todo lo accionable
    se quedan dentro, para que la lista entera quepa de un vistazo."""
    host_id = host["id"].to(str)
    online = NodesState.host_online[host_id]
    organizando = DashboardState.editing_equipment
    expanded = (HostActionsState.expanded_host == host_id) & ~organizando
    return rx.vstack(
        rx.hstack(
            rx.cond(
                organizando,
                rx.icon("grip-vertical", size=15, color=theme.MUTED, flex_shrink="0"),
                rx.icon(host["icon"].to(str), size=16,
                        color=rx.cond(online, theme.SUCCESS, theme.MUTED), flex_shrink="0"),
            ),
            rx.text(host["name"], size="2", weight="medium", color=theme.TEXT,
                    white_space="nowrap", overflow="hidden", text_overflow="ellipsis"),
            rx.spacer(),
            rx.cond(
                organizando,
                _reorder_controls(host),
                rx.icon(rx.cond(expanded, "chevron-up", "chevron-down"), size=15,
                        color=theme.MUTED, flex_shrink="0"),
            ),
            # El clic se conecta SIEMPRE al mismo manejador (elegir el
            # manejador con un rx.cond compila a JS válido pero retorcido, y
            # aquí no hace falta): en modo organizar la ficha no se abre
            # porque `expanded` ya lleva el "y no estoy organizando".
            on_click=HostActionsState.toggle_expand(host_id),
            cursor=rx.cond(organizando, "default", "pointer"),
            align="center", spacing="2", width="100%",
        ),
        rx.cond(expanded, _expand_panel(host)),
        width="100%", spacing="0",
        background=theme.BG_CARD,
        border=f"1px solid {rx.cond(organizando, theme.ACCENT, theme.BORDER)}",
        border_radius="10px",
        padding="10px 12px",
        transition="border-color 0.15s ease",
    )


def equipment_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.button(
                rx.icon(rx.cond(DashboardState.editing_equipment, "check", "arrow-up-down"), size=13),
                rx.cond(DashboardState.editing_equipment, "Listo", "Organizar"),
                on_click=DashboardState.toggle_editing_equipment,
                size="2",
                variant=rx.cond(DashboardState.editing_equipment, "solid", "surface"),
            ),
            rx.spacer(),
            _add_host_dialog(),
            width="100%", align="center", wrap="wrap", spacing="2",
        ),
        rx.cond(
            DashboardState.editing_equipment,
            rx.text("Usa las flechas para colocar los equipos en el orden que quieras.",
                    size="1", color=theme.MUTED, italic=True),
        ),
        rx.vstack(
            rx.foreach(NodesState.hosts, _host_card),
            spacing="2", width="100%",
        ),
        spacing="4",
        width="100%",
        max_width="720px",
    )
