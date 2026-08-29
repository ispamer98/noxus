"""
Vista "Mandos IR": mandos virtuales sobre el Broadlink (ver
domains/devices/ir_bus.py) — cada uno es un aparato real (TV, ventilador,
aire...) con los botones de su mando físico, aprendidos uno a uno.

Dos piezas:
- ir_remotes_view(): la lista de mandos (alta/edición/borrado, como
  Luces/Accesos) — se abre desde el sidebar.
- ir_remote_window(): el mando virtual en sí, una ventana flotante (ver
  windows.py) con la rejilla de botones — se abre desde aquí o pulsando el
  marcador del mando en el Plano.

"Añadir botón" aprende una señal física por IR/RF o crea directamente una
acción de red webOS (Home, apps, HDMI...) sin contactar con el Broadlink (ver
NodesState.submit_learn_ir_button).
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from ....domains.devices import remote_templates, webos_bus
from .. import theme
from ..state import DashboardState
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.form_dialog import (
    form_dialog_content, field, dialog_footer, styled_input, styled_select, select_content,
)
from ..components.icon_picker import icon_field, icon_grid
from ..components.floor_fields import floor_plan_fields
from ..components.floating_window import floating_window

_REMOTE_ICONS = ["tv", "fan", "air-vent", "gamepad-2", "speaker", "monitor", "radio", "lamp"]

# Todos los iconos que puede llevar un botón — incluye los que usan las
# plantillas (ver ../../domains/devices/remote_templates.py), para que al
# editar un botón de plantilla su propio icono salga marcado en la rejilla.
_BUTTON_ICONS = [
    # Encendido y fuente
    "power", "power-off", "monitor", "tv", "circle", "square",
    # Volumen y canales
    "volume-2", "volume-1", "volume-x", "chevron-up", "chevron-down",
    "chevron-left", "chevron-right", "check", "corner-up-left",
    # Navegación y menús
    "house", "settings", "list", "calendar", "ellipsis", "zap", "captions",
    "mic", "info", "layout-grid",
    # Reproducción
    "play", "pause", "rewind", "fast-forward",
    # Apps y asistentes
    "clapperboard", "film", "sparkles", "disc", "message-circle", "bot",
    # Clima, luz y ventilador
    "wind", "fan", "snowflake", "flame", "sun", "sun-dim", "moon", "moon-star",
    "lightbulb", "lamp", "heart", "timer", "hourglass", "rotate-ccw", "rotate-cw",
    "thermometer", "droplet",
]


# ── Lista de mandos (pestaña del sidebar) ─────────────────────────────────
def _remote_card(remote: dict) -> rx.Component:
    n_botones = remote["buttons"].to(list[dict]).length()
    return rx.hstack(
        rx.box(
            rx.icon(remote["icon"].to(str), size=20, color=theme.ACCENT),
            padding="10px",
            border_radius="10px",
            background=theme.alpha(theme.ACCENT, 0.12),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(remote["name"], size="3", weight="bold", color=theme.TEXT),
            rx.text(
                rx.cond(n_botones == 1, "1 botón aprendido", f"{n_botones} botones aprendidos"),
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("gamepad-2", size=14), "Abrir mando",
            on_click=DashboardState.open_window(remote["id"]),
            size="2", variant="surface", color_scheme="cyan",
        ),
        actions_menu(
            edit_content=_edit_remote_dialog(remote),
            on_remove=NodesState.delete_ir_remote(remote["id"]),
            remove_confirm_title="¿Eliminar mando?",
            remove_confirm_description=confirm_delete(
                "el mando", remote["name"], extra="Se pierden todos sus botones aprendidos.",
            ),
        ),
        spacing="3", align="center", width="100%",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        border_radius="12px", padding="14px", backdrop_filter="blur(10px)", wrap="wrap",
    )


def _edit_remote_dialog(remote: dict) -> rx.Component:
    return form_dialog_content(
        icon="tv",
        title="Editar mando",
        accent=theme.ACCENT,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=remote["id"], type="hidden"),
                field("Nombre", styled_input(name="name", default_value=remote["name"], placeholder="TV Salón")),
                field("Icono", icon_field(
                    name="icon", key=remote["id"].to(str) + ":icon",
                    default_value=remote["icon"].to(str), options=_REMOTE_ICONS,
                )),
                # Sin selector de icono para el plano: el mando usa allí el
                # mismo icono que se ha elegido arriba (ver store.update_ir_remote).
                *floor_plan_fields(
                    remote["floor_top"],
                    remote["icon"].to(str),
                    key=remote["id"].to(str),
                    con_icono=False,
                ),
                dialog_footer(confirm_label="Guardar", color_scheme="cyan"),
                spacing="3", width="100%",
            ),
            on_submit=NodesState.submit_edit_ir_remote,
        ),
    )


def _add_remote_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=14), "Añadir mando", size="2", variant="surface", color_scheme="cyan"),
        ),
        form_dialog_content(
            icon="tv",
            title="Nuevo mando IR",
            accent=theme.ACCENT,
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="TV Salón, Ventilador...")),
                    field("Icono", icon_field(name="icon", key="new_ir_remote", default_value="tv", options=_REMOTE_ICONS)),
                    field(
                        "Plantilla",
                        styled_select(
                            "Plantilla",
                            select_content(
                                *[rx.select.item(etiqueta, value=pid)
                                  for pid, etiqueta in remote_templates.opciones()],
                            ),
                            name="plantilla", default_value="vacio",
                        ),
                        hint="Una plantilla crea de golpe todos los botones del mando real, "
                             "colocados en su sitio pero sin señal — luego le enseñas la señal "
                             "a cada uno y borras los que no uses.",
                    ),
                    dialog_footer(confirm_label="Crear", color_scheme="cyan"),
                    spacing="3", width="100%",
                ),
                on_submit=NodesState.submit_add_ir_remote,
                reset_on_submit=True,
            ),
        ),
    )


def ir_remotes_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("MANDOS IR", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
            rx.spacer(),
            _add_remote_dialog(),
            width="100%", align="center", wrap="wrap",
        ),
        rx.cond(
            NodesState.ir_remotes.length() == 0,
            rx.text("Aún no hay ningún mando IR dado de alta.", size="1", color=theme.MUTED, italic=True),
            rx.vstack(rx.foreach(NodesState.ir_remotes, _remote_card), spacing="2", width="100%"),
        ),
        spacing="3", width="100%",
    )


# ── Mando virtual (ventana flotante) ──────────────────────────────────────
# El cuerpo del mando es un "plano" en miniatura: mismo mecanismo de arrastre
# que el plano de planta (ver _PLAN_DRAG_SCRIPT en ui/views/device_list.py),
# pero acotado a los botones de UN mando en vez de a toda la casa — un
# acumulador aparte (window.__nxRemotePending) y un botón "Guardar
# disposición" propio en vez de "Listo". Los botones nacen ya colocados en
# rejilla (ver store._default_button_pos), así que no hace falta una lista de
# "sin colocar": lo único que hace el modo edición es permitir arrastrarlos.
_REMOTE_DRAG_SCRIPT = """
(function(){
    if (window.__nxRemoteDragInit) return;
    window.__nxRemoteDragInit = true;
    window.__nxRemotePending = window.__nxRemotePending || {};

    function editingContainer(el){
        var c = el.closest('.nx-remote-container');
        return c && c.classList.contains('nx-remote-editing') ? c : null;
    }

    // ── Vibración al pulsar una tecla ────────────────────────────────────
    // Se dispara en pointerdown (no en click) para que llegue en el instante
    // del toque, como el teclado del móvil, y no tras el viaje al servidor.
    //
    // Solo funciona donde el navegador expone la Vibration API (Android). En
    // iPhone NO hay forma: Apple no se la da a las páginas web. Se probó el
    // truco del <input switch> de iOS 17.4 y no funciona en la práctica, así
    // que no se deja código muerto intentándolo — en iPhone la confirmación
    // de que la tecla ha entrado es la visual (ver _active en la tecla).
    // ── Cerrar al tocar fuera ────────────────────────────────────────────
    // Solo las ventanas marcadas con data-nx-dismiss (el mando abierto desde
    // el plano). Se hace pulsando su propia aspa en vez de con un evento
    // nuevo: así el cierre pasa por el mismo sitio que el botón de cerrar y
    // no hay dos caminos que mantener.
    document.addEventListener('pointerdown', function(e){
        if (!e.target.closest) return;
        // Los diálogos y desplegables de Radix se dibujan FUERA de la
        // ventana (en un portal al final del body): sin esta excepción,
        // abrir cualquiera de ellos contaría como "tocar fuera" y cerraría
        // el mando por debajo.
        if (e.target.closest('[role="dialog"], [role="alertdialog"], [data-radix-popper-content-wrapper]')) return;
        // Tampoco cuenta pulsar el marcador del plano que lo acaba de abrir.
        if (e.target.closest('.nx-plan-marker')) return;
        var dentro = e.target.closest('.nx-window');
        document.querySelectorAll('.nx-window[data-nx-dismiss="1"]').forEach(function(win){
            if (win !== dentro) {
                var aspa = win.querySelector('.nx-window-close');
                if (aspa) aspa.click();
            }
        });
    }, true);

    document.addEventListener('pointerdown', function(e){
        if (!navigator.vibrate || !e.target.closest) return;
        if (e.target.closest('.nx-remote-btn-delete')) return;
        var marker = e.target.closest('.nx-remote-marker');
        // Solo al USAR el mando: recolocando botones el toque no manda
        // ninguna señal, así que vibrar ahí engañaría.
        if (marker && !editingContainer(marker)) {
            try { navigator.vibrate(8); } catch (err) {}
        }
    }, true);

    document.addEventListener('click', function(e){
        // La "x" de borrar vive DENTRO del marcador y solo se ve en modo
        // edición — sin esta excepción, el propio bloqueo de clics que evita
        // disparar el botón al arrastrar también bloqueaba su única forma de
        // borrarse.
        if (e.target.closest && e.target.closest('.nx-remote-btn-delete')) return;
        var marker = e.target.closest && e.target.closest('.nx-remote-marker');
        if (marker && editingContainer(marker)) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);

    document.addEventListener('pointerdown', function(e){
        if (e.target.closest && e.target.closest('.nx-remote-btn-delete')) return;
        var marker = e.target.closest('.nx-remote-marker');
        if (!marker) return;
        var container = editingContainer(marker);
        if (!container) return;
        var id = marker.getAttribute('data-nx-id');
        if (!id) return;
        try { marker.setPointerCapture(e.pointerId); } catch (err) {}
        marker.style.transition = 'none';

        var rect = container.getBoundingClientRect();

        function onMove(ev){
            var left = Math.max(0, Math.min(100, (ev.clientX - rect.left) / rect.width * 100));
            var top = Math.max(0, Math.min(100, (ev.clientY - rect.top) / rect.height * 100));
            marker.style.left = left.toFixed(1) + '%';
            marker.style.top = top.toFixed(1) + '%';
            window.__nxRemotePending[id] = {top: top.toFixed(1) + '%', left: left.toFixed(1) + '%'};
        }
        function onUp(ev){
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
            document.removeEventListener('pointercancel', onUp);
            marker.style.transition = '';
            try { marker.releasePointerCapture(ev.pointerId); } catch (err) {}
        }
        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
        document.addEventListener('pointercancel', onUp);
    });
})();
"""

# Lado de una tecla. Las plantillas calculan sus separaciones contra esta
# medida (ver remote_templates.py): subirla sin recalcular allí las solapa.
_BTN = 44

REMOTE_COMMIT_SCRIPT = (
    "(function(){var p = window.__nxRemotePending || {};"
    " window.__nxRemotePending = {}; return JSON.stringify(p);})()"
)
REMOTE_RESET_SCRIPT = "window.__nxRemotePending = {};"


# Las cuatro teclas de color de la TV: son las únicas que llevan color propio
# impreso en el mando real, así que se pintan tal cual en vez de en gris.
_KEY_COLORS = {
    # Las cuatro teclas de color de la TV
    "rojo": theme.DANGER, "verde": theme.SUCCESS,
    "amarillo": "#eab308", "azul": theme.ACCENT,
    # Colores de marca de los accesos a apps: no se puede poner el logo, pero
    # la inicial en su color se reconoce de un vistazo igual que en el mando.
    "netflix": "#e50914", "prime": "#00a8e1",
    "disney": "#4b6bfb", "rakuten": "#bf0000",
    "alexa": "#00caff", "google": "#ea4335",
}


def _key_color(clave):
    """rx.match y no un dict: dentro de un rx.foreach la clave es una Var."""
    return rx.match(clave, *[(k, v) for k, v in _KEY_COLORS.items()], theme.TEXT)


# Tamaño del rótulo de una tecla (los números, las iniciales de las apps),
# en proporción al ancho del cuerpo del mando — así encoge con él en vez de
# quedarse grande y desbordar la tecla. Con topes por los dos lados para que
# siga siendo legible en un mando pequeño y no se dispare en uno grande.
_BTN_FONT = "clamp(11px, 7cqw, 20px)"


def _remote_group_plate(grupo: dict) -> rx.Component:
    """Una placa serigrafiada del mando real: el balancín del volumen, el aro
    de la rueda, la tira de colores, el pad de la luz... Puramente decorativa
    (pointer-events a ninguno, para no robarle el toque a las teclas que van
    encima), pero es lo que hace que el mando virtual se lea de un vistazo
    como el físico en vez de como una nube de círculos sueltos."""
    hundido = grupo["tono"].to(str) == "hundido"
    return rx.box(
        position="absolute",
        top=grupo["pos_top"].to(str),
        left=grupo["pos_left"].to(str),
        width=grupo["width"].to(str),
        height=grupo["height"].to(str),
        transform="translate(-50%, -50%)",
        border_radius=grupo["radius"].to(str),
        background=rx.cond(hundido, "rgba(0,0,0,0.28)", "rgba(255,255,255,0.045)"),
        border=rx.cond(
            hundido,
            "1px solid rgba(0,0,0,0.35)",
            "1px solid rgba(255,255,255,0.07)",
        ),
        box_shadow=rx.cond(
            hundido,
            "inset 0 2px 6px rgba(0,0,0,0.5)",
            "inset 0 1px 0 rgba(255,255,255,0.05)",
        ),
        pointer_events="none",
        z_index="1",
    )


def _remote_button_marker(remote_id, editing, boton: dict, boton_w) -> rx.Component:
    """Un botón físico del mando virtual: círculo con solo el icono (como un
    mando real — el nombre va en el `title`, no impreso debajo) colocado por
    posición absoluta dentro del cuerpo. Fuera de modo edición, tocarlo
    dispara la señal; en modo edición se arrastra (ver _REMOTE_DRAG_SCRIPT) y
    aparecen el lápiz (editar/aprender) y la "x" (borrar).

    Un botón SIN señal (los recién creados desde una plantilla) se pinta
    apagado y con el borde punteado: se ve de un vistazo lo que queda por
    enseñarle al mando."""
    sin_senal = boton["code"].to(str) == ""
    return rx.box(
        rx.cond(
            editing,
            rx.fragment(
                rx.icon(
                    "pencil", size=10, color="white", cursor="pointer",
                    class_name="nx-remote-btn-delete",
                    on_click=NodesState.open_button_editor(remote_id, boton["id"]).stop_propagation,
                    position="absolute", top="-5px", left="-5px", z_index="6",
                    background=theme.ACCENT, border_radius="50%", padding="3px",
                    border=f"1px solid {theme.BG_WINDOW}",
                    title="Editar / aprender señal",
                ),
                rx.icon(
                    "x", size=10, color="white", cursor="pointer",
                    class_name="nx-remote-btn-delete",
                    on_click=NodesState.delete_ir_button(remote_id, boton["id"]).stop_propagation,
                    position="absolute", top="-5px", right="-5px", z_index="6",
                    background=theme.DANGER, border_radius="50%", padding="3px",
                    border=f"1px solid {theme.BG_WINDOW}",
                    title="Borrar botón",
                ),
            ),
        ),
        # Sin marca de "va por red": por dónde sale la orden (Broadlink o
        # webOS) es cosa del sistema, no algo que haya que estar viendo al
        # usar el mando. La vía se sigue eligiendo por botón en su ficha.
        # Rótulo impreso (los números) o icono. Diez teclas con el mismo
        # icono de círculo no se distinguen entre sí — ver remote_templates.
        rx.cond(
            boton["text"].to(str) != "",
            rx.text(
                boton["text"].to(str), weight="bold",
                color=rx.cond(
                    boton["color"].to(str) != "", _key_color(boton["color"]),
                    rx.cond(sin_senal, theme.MUTED, theme.TEXT),
                ),
                # Hereda el font-size de la tecla (_BTN_FONT), que va en
                # proporción al cuerpo — con un size fijo de Radix, el número
                # se salía de la tecla al encogerse el mando.
                font_size="1em",
                line_height="1",
            ),
            rx.icon(
                boton["icon"].to(str), size=20,
                color=rx.cond(
                    boton["color"].to(str) != "", _key_color(boton["color"]),
                    rx.cond(sin_senal, theme.MUTED, theme.TEXT),
                ),
            ),
        ),
        on_click=NodesState.send_ir_button(remote_id, boton["id"]),
        title=rx.cond(
            sin_senal,
            boton["label"].to(str) + " — sin señal todavía",
            boton["label"].to(str),
        ),
        cursor=rx.cond(editing, "grab", "pointer"),
        position="absolute",
        top=boton["render_top"].to(str),
        left=boton["render_left"].to(str),
        transform="translate(-50%, -50%)",
        # En % del cuerpo (no en px) para que la tecla encoja con él; el
        # aspect-ratio la mantiene redonda a cualquier tamaño.
        width=boton_w, height="auto", aspect_ratio="1", flex_shrink="0",
        font_size=_BTN_FONT,
        # !important obligatorio, mismo motivo que en sidebar.py: .rt-Box trae
        # display:block incondicional en el CSS base de Radix, con más
        # prioridad de cascada que el estilo que genera Emotion. Sin él este
        # flex no se aplicaba y el icono se iba a la esquina superior
        # izquierda de la tecla en vez de quedar centrado.
        display="flex !important", align_items="center", justify_content="center",
        border_radius="50%",
        background=rx.cond(
            sin_senal,
            "rgba(255,255,255,0.03)",
            "linear-gradient(155deg, rgba(255,255,255,0.14), rgba(255,255,255,0.02))",
        ),
        border=rx.cond(
            sin_senal,
            "1px dashed rgba(255,255,255,0.22)",
            "1px solid rgba(255,255,255,0.16)",
        ),
        box_shadow=rx.cond(
            sin_senal,
            "none",
            "0 3px 8px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.10)",
        ),
        transition="transform 0.07s ease, background 0.12s ease, box-shadow 0.12s ease",
        _hover={"background": "linear-gradient(155deg, rgba(255,255,255,0.20), rgba(255,255,255,0.05))"},
        # Respuesta al tacto: se hunde y se ilumina. Es la única confirmación
        # que llega SIEMPRE — la vibración depende del sistema (en iPhone,
        # Apple no da acceso a ella a las webs), así que la pulsación tiene
        # que notarse por la vista aunque no vibre nada.
        _active={
            "transform": "translate(-50%, -50%) scale(0.88)",
            "background": "linear-gradient(155deg, rgba(255,255,255,0.34), rgba(255,255,255,0.12))",
            "box-shadow": f"0 0 0 3px {theme.alpha(theme.ACCENT, 0.35)}",
        },
        touch_action="none",
        user_select="none",
        class_name="nx-remote-marker",
        data_nx_id=boton["id"],
        z_index="5",
        # Lo lee la regla de .nx-remote-marker > svg (ver noxuscmmd.py) para
        # dibujar el icono más grande o más pequeño según la tecla.
        style={"--nx-ico": boton["icon_size"].to(str)},
    )


def _remote_body(remote: dict) -> rx.Component:
    """La silueta del mando: cuerpo oscuro tipo plástico/metal (mismo
    lenguaje que el mando de la app Home de Apple), altura fija con hueco de
    sobra para una rejilla de botones generosa."""
    botones = remote["buttons_render"].to(list[dict])
    editing = NodesState.remote_layout_editing == remote["id"]
    return rx.box(
        rx.script(_REMOTE_DRAG_SCRIPT),
        rx.cond(
            botones.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("radio-tower", size=24, color=theme.MUTED),
                    rx.text("Sin botones todavía", size="1", color=theme.MUTED, text_align="center"),
                    spacing="2", align="center",
                ),
                height="100%", width="100%", position="absolute", inset="0",
            ),
            rx.fragment(),
        ),
        # Las placas se calculan a partir de dónde están sus teclas (ver
        # _placa_de_grupo), así que siguen a los botones al arrastrarlos.
        rx.foreach(remote["group_plates"].to(list[dict]), _remote_group_plate),
        rx.foreach(
            botones,
            lambda b: _remote_button_marker(
                remote["id"], editing, b, remote["btn_css_width"].to(str),
            ),
        ),
        class_name=rx.cond(editing, "nx-remote-container nx-remote-editing", "nx-remote-container"),
        position="relative",
        # Cada mando trae su propia forma (ver store.add_ir_remote): el de la
        # TV es alto y estrecho, el del ventilador apaisado. El tamaño no es
        # fijo: se encoge con la altura de la ventana manteniendo la
        # proporción, para que el mando quepa entero sin deslizar (ver
        # _remote_para_ui en domains/nodes/state.py). Las teclas van en % del
        # ancho, así que escalan con él y las posiciones siguen cuadrando.
        width=remote["body_css_width"].to(str),
        aspect_ratio=remote["body_aspect"].to(str),
        # Referencia para dimensionar el texto de las teclas (los números y las
        # iniciales de las apps) en proporción al cuerpo — ver _BTN_FONT.
        container_type="inline-size",
        margin="4px auto",
        border_radius="32px",
        background="linear-gradient(165deg, #262f3d 0%, #131922 60%, #0a0e14 100%)",
        border="1px solid rgba(255,255,255,0.10)",
        box_shadow="0 24px 48px -20px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06)",
    )


def _add_button_dialog(remote: dict) -> rx.Component:
    aprendiendo = NodesState.ir_learning != ""
    es_webos = NodesState.new_button_signal == "webos"
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon("plus", size=13), "Añadir botón",
                size="1", variant="soft", color_scheme="green",
                on_click=NodesState.prepare_add_remote_button,
            ),
        ),
        form_dialog_content(
            icon="circle-plus",
            title=f"Añadir botón — {remote['name']}",
            accent=theme.SUCCESS,
            form=rx.vstack(
                rx.form.root(
                    rx.vstack(
                        rx.input(name="remote_id", value=remote["id"], type="hidden"),
                        field("Nombre del botón", styled_input(
                            name="label", placeholder="Encender, Vol +, Canal 1...",
                            disabled=aprendiendo,
                        )),
                        field("Icono", icon_field(
                            name="icon", key=remote["id"].to(str) + ":new_btn",
                            default_value="circle", options=_BUTTON_ICONS,
                        )),
                        field(
                            "Tipo de señal",
                            styled_select(
                                "Tipo de señal",
                                select_content(
                                    rx.select.item("Infrarrojos (IR) — TV, la mayoría de mandos", value="ir"),
                                    rx.select.item("Radiofrecuencia (RF 433MHz) — típico en ventiladores de techo", value="rf"),
                                    rx.select.item("Por red — TV LG (webOS), sin aprendizaje", value="webos"),
                                ),
                                name="signal", value=NodesState.new_button_signal,
                                on_change=NodesState.set_new_button_signal,
                                disabled=aprendiendo,
                            ),
                            hint="IR/RF aprende una tecla del mando físico. webOS crea una acción "
                                 "de red como Home, Netflix o cambiar directamente de HDMI.",
                        ),
                        rx.cond(
                            es_webos,
                            field(
                                "Acción en la TV",
                                styled_select(
                                    "Elige la acción",
                                    select_content(
                                        *[rx.select.item(etiqueta, value=valor)
                                          for valor, etiqueta in webos_bus.comandos_disponibles()],
                                    ),
                                    name="webos_code", default_value="HOME",
                                ),
                            ),
                        ),
                        rx.hstack(
                            rx.spacer(),
                            rx.button(
                                rx.cond(
                                    aprendiendo,
                                    "Escuchando...",
                                    rx.cond(es_webos, "Crear botón", "Empezar a aprender"),
                                ),
                                type="submit", color_scheme="green", size="2",
                                loading=aprendiendo, disabled=aprendiendo,
                            ),
                            width="100%",
                        ),
                        spacing="3", width="100%",
                    ),
                    on_submit=NodesState.submit_learn_ir_button,
                ),
                rx.cond(
                    NodesState.ir_status != "",
                    rx.text(NodesState.ir_status, size="2", color=theme.TEXT,
                            padding="8px 10px", border_radius="8px", width="100%",
                            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}"),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.dialog.close(rx.button("Cerrar", variant="soft", color_scheme="gray", size="2")),
                    width="100%",
                ),
                spacing="3", width="100%",
            ),
        ),
    )


def _button_editor_dialog(remote: dict) -> rx.Component:
    """Editor de UN botón: nombre, icono, y por dónde se manda. Es único por
    mando (no uno por botón) — con 41 botones, un diálogo por botón
    multiplicaría por 41 el árbol de componentes. Se abre con el lápiz de
    cada botón, que rellena los campos desde NodesState.open_button_editor."""
    abierto = (NodesState.editing_button_remote == remote["id"]) & (NodesState.editing_button_id != "")
    aprendiendo = NodesState.ir_learning != ""
    es_red = NodesState.editing_button_kind == "webos"
    return rx.dialog.root(
        form_dialog_content(
            icon="sliders-horizontal",
            title="Editar botón",
            accent=theme.ACCENT,
            form=rx.vstack(
                field("Nombre", styled_input(
                    value=NodesState.editing_button_label,
                    on_change=NodesState.set_editing_button_label,
                    placeholder="Encender, Vol +, Home...",
                )),
                field("Icono", icon_grid(
                    NodesState.editing_button_icon,
                    lambda icono: NodesState.set_editing_button_icon(icono),
                    _BUTTON_ICONS,
                )),
                field(
                    "¿Cómo se manda?",
                    styled_select(
                        "¿Cómo se manda?",
                        select_content(
                            rx.select.item("Infrarrojos / RF — por el Broadlink", value="ir"),
                            rx.select.item("Por red — TV LG (webOS)", value="webos"),
                        ),
                        value=NodesState.editing_button_kind,
                        on_change=NodesState.set_editing_button_kind,
                    ),
                    hint="Usa «por red» solo para lo que el mando NO manda por infrarrojos "
                         "(Home, micro, abrir apps): esos el Broadlink no los puede aprender.",
                ),
                # Botón de red: se elige QUÉ hace de una lista, no se aprende nada.
                rx.cond(
                    es_red,
                    field("Acción en la TV", styled_select(
                        "Elige la acción",
                        select_content(
                            *[rx.select.item(etiqueta, value=valor)
                              for valor, etiqueta in webos_bus.comandos_disponibles()],
                        ),
                        value=NodesState.editing_button_code,
                        on_change=NodesState.set_editing_button_code,
                    )),
                    # Botón de infrarrojos: se (re)aprende la señal del mando real.
                    rx.vstack(
                        rx.text("SEÑAL", size="1", color=theme.MUTED, weight="medium",
                                letter_spacing="0.02em"),
                        rx.hstack(
                            rx.button(
                                rx.icon("radio-tower", size=13),
                                rx.cond(aprendiendo, "Escuchando...", "Aprender por IR"),
                                on_click=NodesState.learn_into_button("ir"),
                                size="2", variant="soft", color_scheme="green",
                                loading=aprendiendo, disabled=aprendiendo,
                            ),
                            rx.button(
                                rx.icon("antenna", size=13),
                                "Aprender por RF",
                                on_click=NodesState.learn_into_button("rf"),
                                size="2", variant="soft", color_scheme="purple",
                                loading=aprendiendo, disabled=aprendiendo,
                            ),
                            spacing="2", wrap="wrap",
                        ),
                        rx.text(
                            "RF para mandos sin lucecita infrarroja (ventiladores de techo).",
                            size="1", color=theme.MUTED, opacity="0.7",
                        ),
                        spacing="1", width="100%", align="start",
                    ),
                ),
                rx.cond(
                    NodesState.ir_status != "",
                    rx.text(NodesState.ir_status, size="2", color=theme.TEXT,
                            padding="8px 10px", border_radius="8px", width="100%",
                            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}"),
                ),
                rx.hstack(
                    rx.button("Cancelar", variant="soft", color_scheme="gray", size="2",
                              on_click=NodesState.close_button_editor),
                    rx.button("Guardar", color_scheme="cyan", size="2",
                              on_click=NodesState.save_button_editor),
                    spacing="2", justify="end", width="100%", padding_top="2",
                ),
                spacing="4", width="100%",
            ),
        ),
        open=abierto,
        on_open_change=lambda abierto_ahora: rx.cond(
            abierto_ahora, rx.noop(), NodesState.close_button_editor,
        ),
    )


def _layout_toggle(remote: dict) -> rx.Component:
    editing = NodesState.remote_layout_editing == remote["id"]
    return rx.cond(
        editing,
        rx.hstack(
            rx.button(
                rx.icon("check", size=13), "Guardar disposición",
                # Handler directo de un solo argumento, igual que el "Listo"
                # del plano de planta: de qué mando son las posiciones lo sabe
                # el propio State (remote_layout_editing), y salir del modo
                # edición lo hace él al terminar. Ver save_ir_button_positions.
                on_click=rx.call_script(
                    REMOTE_COMMIT_SCRIPT,
                    callback=NodesState.save_ir_button_positions,
                ),
                size="1", variant="solid", color_scheme="green",
            ),
            spacing="1", align="center", wrap="wrap",
        ),
        rx.hstack(
            rx.icon("move", size=13, color=theme.MUTED),
            rx.text("Colocar botones", size="1", color=theme.MUTED),
            on_click=[
                rx.call_script(REMOTE_RESET_SCRIPT),
                NodesState.set_remote_layout_editing(remote["id"]),
            ],
            cursor="pointer", spacing="1", align="center",
            padding="5px 9px", border_radius="8px", opacity="0.6",
            transition="opacity 0.15s ease, background 0.15s ease",
            _hover={"opacity": "1", "background": theme.BG_CARD},
        ),
    )


def ir_remote_window(remote: dict) -> rx.Component:
    n_botones = remote["buttons"].to(list[dict]).length()
    # Abierto desde el plano: solo el mando, para usarlo. Abierto desde la
    # pestaña Mandos IR: además el taller (añadir, recolocar, editar).
    compacto = DashboardState.compact_windows.contains(remote["id"].to(str))
    return floating_window(
        rx.vstack(
            rx.cond(
                compacto,
                rx.fragment(),
                rx.vstack(
                    rx.cond(
                        NodesState.remote_layout_editing == remote["id"],
                        rx.hstack(
                            rx.icon("move", size=13, color=theme.WARNING, flex_shrink="0"),
                            rx.text("Arrastra los botones donde quieras y guarda",
                                    size="1", color=theme.WARNING),
                            spacing="2", align="center",
                        ),
                        rx.fragment(),
                    ),
                    rx.hstack(
                        rx.text(f"{n_botones} botones", size="1", color=theme.MUTED),
                        rx.spacer(),
                        _add_button_dialog(remote),
                        _layout_toggle(remote),
                        width="100%", align="center", spacing="2", wrap="wrap",
                    ),
                    spacing="2", width="100%",
                ),
            ),
            _remote_body(remote),
            rx.cond(compacto, rx.fragment(), _button_editor_dialog(remote)),
            spacing="3", width="100%", align="center",
        ),
        window_id=remote["id"],
        title=remote["name"],
        icon=remote["icon"].to(str),
        is_open=DashboardState.open_windows.contains(remote["id"].to(str)),
        on_close=DashboardState.close_window(remote["id"]),
        accent=theme.ACCENT,
        top="8%",
        left="20%",
        # La ventana se ciñe al cuerpo del mando, que a su vez se encoge con
        # la altura de la pantalla — ver _remote_para_ui.
        width=remote["window_css_width"].to(str),
        # Un mando nunca se traga la pantalla entera, tampoco en el móvil:
        # ocupa lo que ocupa y flota centrado.
        fullscreen_on_mobile=False,
        # Abierto desde el plano se cierra tocando fuera, como cualquier cosa
        # que se saca un momento; abierto desde su pestaña se queda hasta que
        # lo cierres, que ahí se está trabajando con él.
        dismiss_on_outside=rx.cond(compacto, "1", ""),
    )


def ir_remote_windows_layer() -> rx.Component:
    return rx.foreach(NodesState.ir_remotes, ir_remote_window)
