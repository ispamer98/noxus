"""Ventanas flotantes del dashboard, incluido el visor único de cámaras."""
import reflex as rx

from ..views.camera_view import video_embed_safe, open_in_browser_button
from ...domains.auth.state import AuthState
from ...domains.nodes.host_actions_state import HostActionsState
from ...domains.nodes.state import NodesState
from . import theme
from .components.floating_window import floating_window
from .components.icono_propio import icono
from .components.panel_control import boton_control, panel, panel_cabecera
from .components.electro_panel import electro_panel
from ...domains.electro.state import ElectroState
from .state import DashboardState
from .components.form_dialog import select_content


_STREAM_MODES = "webrtc,mse,hls,mp4"


def _dynamic_camera_window(cam: dict) -> rx.Component:
    go2rtc_url = f"/cam/stream.html?src={cam['url']}&mode={_STREAM_MODES}"
    content = rx.match(
        cam["kind"],
        (
            "go2rtc",
            rx.vstack(
                open_in_browser_button(go2rtc_url),
                video_embed_safe(go2rtc_url),
                spacing="3",
                width="100%",
            ),
        ),
        (
            "rtsp",
            rx.vstack(
                # Los navegadores no reproducen RTSP directamente: se guarda solo para copiarla y
                # abrirla en VLC u otro reproductor compatible.
                rx.hstack(
                    rx.code(cam["url"], size="1", style={"word_break": "break-all"}),
                    rx.icon(
                        "copy",
                        size=15,
                        cursor="pointer",
                        on_click=rx.set_clipboard(cam["url"]),
                        title="Copiar URL RTSP",
                        _hover={"color": theme.ACCENT},
                    ),
                    align="start",
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
        ),
        rx.vstack(
            open_in_browser_button(cam["url"]),
            video_embed_safe(cam["url"]),
            spacing="3",
            width="100%",
        ),
    )
    return floating_window(
        content,
        window_id=cam["id"],
        title=cam["name"],
        icon=cam["icon"].to(str),
        is_open=DashboardState.open_windows.contains(cam["id"].to(str)),
        on_close=DashboardState.close_window(cam["id"]),
        accent=theme.ACCENT,
        top="10%",
        left="15%",
        width="620px",
    )


def floating_windows_layer() -> rx.Component:
    return rx.fragment(rx.foreach(NodesState.window_cameras, _dynamic_camera_window))


def camera_kiosco_content(cam: rx.Var) -> rx.Component:
    """Visor embebido para la hoja del kiosco, sin enlace a otra pestaña."""
    return rx.match(
        cam["kind"],
        ("go2rtc", video_embed_safe(
            "/cam/stream.html?src=" + cam["url"].to(str)
            + f"&mode={_STREAM_MODES}")),
        ("rtsp", rx.text(
            "Este origen RTSP no se puede reproducir en el navegador.",
            color=theme.MUTED)),
        video_embed_safe(cam["url"].to(str)),
    )


# ── Equipos en el plano ──────────────────────────────────────────────────────
# Un ordenador colocado en el plano abre SU BOTONERA al pulsarlo, en vez de
# encenderse o apagarse de un toque como hace una luz. El motivo es que apagar
# un equipo por un roce en la pantalla del móvil es un destrozo que no se
# deshace: lo que estuviera abierto sin guardar, se pierde. Un panel con sus
# botones cuesta un toque más y no se dispara sin querer.
#
# Lo que sale aquí es lo mismo que ya vive en la pestaña Equipos, no una copia:
# los eventos son los de HostActionsState, con sus permisos y su registro. Aquí
# solo se presentan al lado del sitio de la casa donde está el aparato.
def _accion(icono: str, texto: str, al_pulsar, color: str = "gray") -> rx.Component:
    return rx.button(
        rx.icon(icono, size=14), texto,
        on_click=al_pulsar, size="2", variant="soft", color_scheme=color,
        width="100%", justify="start",
    )


def _boton_propio(boton: rx.Var) -> rx.Component:
    """Uno de los botones que el equipo tenga dados de alta (un comando SSH,
    poner un pin, leer un pin). El icono es fijo porque lo que cambia es lo que
    hace, no de qué tipo es: el nombre que le puso el usuario ya lo dice."""
    return _accion("play", boton["label"].to(str),
                   HostActionsState.run_button(boton["id"].to(str)))


def equipo_contenido(host: rx.Var) -> rx.Component:
    """Botonera de un equipo (PC, servidor): la misma en el plano y en la tablet.
    Encender solo si hay MAC (Wake-on-LAN); apagar/reiniciar solo si hay usuario
    SSH. Lo comprueban también los eventos (HostActionsState)."""
    hid = host["id"].to(str)
    online = host["online"].to(bool)
    return panel(
        panel_cabecera(rx.cond(host["floor_icon"], host["floor_icon"].to(str), host["icon"].to(str)),
                       host["name"], rx.cond(online, "En línea", "Sin respuesta"), online),
        rx.el.div(
            rx.cond(host["mac"], boton_control("power", "Encender",
                                               HostActionsState.encender_wol(hid), "safe")),
            rx.cond(host["user"], rx.fragment(
                boton_control("power-off", "Apagar",
                              HostActionsState.accion_rapida(hid, "apagar"), "guard"),
                boton_control("rotate-ccw", "Reiniciar",
                              HostActionsState.accion_rapida(hid, "reiniciar"), "warn"),
            )),
            class_name="nx-control-acciones",
        ),
        # `.to(list[dict])`: dentro de un foreach los campos son `Any`.
        rx.cond(host["botones"].to(list[dict]).length() > 0, rx.el.div(
            rx.foreach(host["botones"].to(list[dict]), lambda b: boton_control(
                "play", b["label"].to(str), HostActionsState.run_button(b["id"].to(str)))),
            class_name="nx-control-rejilla",
        )),
    )


def _equipo_window(host: rx.Var) -> rx.Component:
    hid = host["id"].to(str)
    return floating_window(
        equipo_contenido(host),
        window_id=host["id"],
        title=host["name"],
        icon=rx.cond(host["floor_icon"], host["floor_icon"].to(str),
                     host["icon"].to(str)),
        is_open=DashboardState.open_windows.contains(hid),
        on_close=DashboardState.close_window(host["id"]),
        accent=theme.ACCENT, top="12%", left="22%", width="340px",
        fullscreen_on_mobile=False,
        # Se cierra tocando fuera: se saca un momento desde el plano.
        dismiss_on_outside="1",
    )


def _chip(nombre_icono, texto, alerta, titulo) -> rx.Component:
    """Estado en una palabra con su icono; el detalle va en el tooltip."""
    color = rx.cond(alerta, theme.WARNING, theme.SUCCESS)
    return rx.hstack(
        icono(nombre_icono, 15, color),
        rx.text(texto, size="2", weight="medium", color=theme.TEXT),
        spacing="1", align="center", padding="5px 9px", border_radius="999px",
        background=theme.alpha(theme.TEXT, 0.05), title=titulo, flex="1",
        justify="center",
    )


def _boton_icono(icono: str, titulo: str, al_pulsar, color: str = "gray") -> rx.Component:
    return rx.icon_button(
        rx.icon(icono, size=18), on_click=al_pulsar, size="3", variant="soft",
        color_scheme=color, title=titulo, aria_label=titulo, flex="1",
    )


def _anclado(a: rx.Var) -> rx.Component:
    """Un elemento anclado a la puerta (las persianas, una luz): su nombre y sus
    botones. Un mando enseña sus teclas; una luz o aparato, su interruptor."""
    rid = a["id"].to(str)
    return rx.hstack(
        rx.icon(a["icon"].to(str), size=15, color=theme.MUTED, flex_shrink="0"),
        rx.vstack(
            rx.text(a["name"], size="1", color=theme.TEXT, overflow="hidden",
                    text_overflow="ellipsis", white_space="nowrap", width="100%"),
            # Subiendo… / Bajando… / Subida / Bajada / Parada (ver NodesState
            # ._estado_persiana): lo que se quería ver sin tener que adivinar.
            rx.cond(a["estado"].to(str) != "",
                    rx.text(a["estado"].to(str), size="1", color=theme.WARNING)),
            spacing="0", flex="1", min_width="0", align="start",
        ),
        rx.match(
            a["tipo"].to(str),
            ("mando", rx.hstack(rx.foreach(a["botones"].to(list[dict]), lambda b: rx.icon_button(
                rx.icon(b["icon"].to(str), size=15), size="2", variant="soft",
                title=b["label"].to(str), aria_label=b["label"].to(str),
                on_click=NodesState.send_ir_button(rid, b["id"].to(str)))), spacing="1")),
            # Persiana: una señal por sentido (y parar si el mando la tiene).
            ("persiana", rx.hstack(rx.foreach(a["botones"].to(list[dict]), lambda b: rx.icon_button(
                rx.icon(b["icon"].to(str), size=16), size="2", variant="soft", color_scheme="blue",
                title=b["label"].to(str), aria_label=b["label"].to(str),
                on_click=NodesState.mover_persiana(rid, b["id"].to(str)))), spacing="1")),
            rx.icon_button(
                rx.icon("power", size=15), size="2",
                variant=rx.cond(a["activo"].to(bool), "solid", "soft"),
                color_scheme=rx.cond(a["activo"].to(bool), "amber", "gray"),
                title="Encender / apagar", aria_label="Encender / apagar",
                on_click=NodesState.toggle_light(rid)),
        ),
        spacing="2", align="center", width="100%",
        padding="6px 8px", border_radius="10px", background=theme.alpha(theme.TEXT, 0.04),
    )


def _ajustes_grupo(door: rx.Var) -> rx.Component:
    """Qué forma la puerta: magnético, si tiene cerradura y qué va anclado.
    Escondido tras un icono para que el bocadillo quede limpio."""
    did = door["id"].to(str)
    tiene_mag = door["magnetico_id"].to(str) != ""
    return rx.popover.root(
        rx.popover.trigger(rx.icon_button(
            rx.icon("settings-2", size=15), size="1", variant="ghost", color_scheme="gray",
            title="Qué forma esta puerta", aria_label="Qué forma esta puerta")),
        rx.popover.content(
            rx.vstack(
                rx.hstack(rx.icon("magnet", size=14, color=theme.MUTED),
                          rx.text("Magnético", size="1", color=theme.MUTED, weight="bold"),
                          spacing="1", align="center"),
                rx.select.root(
                    rx.select.trigger(placeholder="Elegir magnético…", width="100%"),
                    select_content(
                        rx.select.item("Sin magnético", value="_ninguno"),
                        rx.foreach(NodesState.opciones_magnetico,
                                   lambda o: rx.select.item(o["nombre"], value=o["id"])),
                    ),
                    value=rx.cond(tiene_mag, door["magnetico_id"].to(str), "_ninguno"),
                    on_change=lambda v: NodesState.asociar_magnetico(did, v),
                    size="2",
                ),
                rx.hstack(rx.icon("lock", size=14, color=theme.MUTED),
                          rx.text("Cerradura", size="1", color=theme.MUTED, weight="bold"),
                          spacing="1", align="center"),
                rx.select.root(
                    rx.select.trigger(width="100%"),
                    select_content(
                        rx.select.item("Sin cerradura", value="_ninguna"),
                        rx.foreach(NodesState.opciones_cerradura,
                                   lambda o: rx.select.item(o["nombre"], value=o["id"])),
                    ),
                    value=door["cerradura_sel"].to(str),
                    on_change=lambda v: NodesState.elegir_cerradura(did, v),
                    size="2",
                ),
                rx.hstack(rx.icon("link", size=14, color=theme.MUTED),
                          rx.text("Anclados a esta puerta", size="1", color=theme.MUTED, weight="bold"),
                          spacing="1", align="center"),
                rx.foreach(door["anclados_ui"].to(list[dict]), lambda a: rx.hstack(
                    rx.icon(a["icon"].to(str), size=14, color=theme.MUTED),
                    rx.text(a["name"], size="2", color=theme.TEXT, flex="1"),
                    rx.icon("x", size=14, color=theme.DANGER, cursor="pointer",
                            on_click=NodesState.soltar_de_puerta(did, a["ref"].to(str))),
                    align="center", width="100%", spacing="2")),
                rx.select.root(
                    rx.select.trigger(placeholder="Anclar elemento…", width="100%"),
                    select_content(rx.foreach(
                        NodesState.opciones_anclar,
                        lambda o: rx.select.item(o["nombre"], value=o["ref"]))),
                    value="",
                    on_change=lambda v: NodesState.anclar_a_puerta(did, v),
                    size="2",
                ),
                spacing="2", width="240px",
            ),
            side="bottom", align="end",
        ),
    )


def puerta_contenido(door: rx.Var, con_anclados: bool = True) -> rx.Component:
    """La puerta: estado (magnético y maniobra), cerradura y sus tres órdenes.
    La misma en el plano y en la tablet; los eventos son los de siempre."""
    lock = door["lock_id"].to(str)
    tiene_mag = door["magnetico_id"].to(str) != ""
    abriendo = NodesState.pulsing_doors[lock]
    liberada = door["cerradura_abierta"].to(bool) | abriendo
    estado = rx.match(door["transito"].to(str),
                      ("abriendo", "Abriendo…"), ("abierta", "Abierta"),
                      ("cerrando", "Cerrando…"),
                      rx.cond(door["is_open"].to(bool), "Abierta", "Cerrada"))
    return panel(
        panel_cabecera(door["icono_plano"].to(str), door["name"], estado,
                       door["is_open"].to(bool) | door["ambar"].to(bool),
                       subtitulo=rx.cond(tiene_mag, "Magnético: " + door["magnetico_nombre"].to(str),
                                         "Sin magnético: según la cerradura")),
        rx.cond(
            ~door["sin_cerradura"].to(bool),
            rx.fragment(
                rx.el.div(
                    rx.el.span(icono(rx.cond(liberada, "lock-open", "lock"), 16),
                               rx.cond(abriendo, "Abriendo", rx.cond(liberada, "Desbloqueada", "Bloqueada")),
                               class_name="nx-control-pastilla",
                               custom_attrs={"data-activo": liberada}),
                    rx.el.span(rx.cond(door["modo"].to(str) == "dos_pulsos", "Dos pulsos", "Un pulso")
                               + " · " + door["pulse_seconds"].to(str) + " s",
                               class_name="nx-control-pastilla"),
                    class_name="nx-control-pastillas",
                ),
                rx.cond(door["nodo_caido"].to(bool), rx.el.p(
                    icono("wifi-off", 14), door["nodo_nombre"].to(str) + " sin conexión: no recibirá órdenes",
                    class_name="nx-control-aviso")),
                rx.el.div(
                    boton_control("door-open", "Abrir", NodesState.open_door(lock), "safe"),
                    boton_control("lock-open", "Mantener abierta",
                                  NodesState.set_door_hold(lock, True), "warn",
                                  door["cerradura_abierta"].to(bool)),
                    boton_control("lock", "Mantener cerrada",
                                  NodesState.set_door_hold(lock, False), "info",
                                  ~door["cerradura_abierta"].to(bool)),
                    class_name="nx-control-acciones nx-control-tres",
                ),
            ),
        ),
        *([rx.foreach(door["anclados_ui"].to(list[dict]), lambda a: _anclado(a)),
           rx.cond(AuthState.puede_ajustes, rx.hstack(rx.spacer(), _ajustes_grupo(door), width="100%"))]
          if con_anclados else []),
    )


def _puerta_window(door: rx.Var) -> rx.Component:
    did = door["id"].to(str)
    return floating_window(
        puerta_contenido(door),
        window_id=door["id"],
        title=door["name"],
        icon=rx.cond(door["floor_icon"], door["floor_icon"].to(str), "door-closed"),
        is_open=DashboardState.open_windows.contains(did),
        on_close=DashboardState.close_window(door["id"]),
        accent=theme.ACCENT, top="12%", left="22%", width="360px",
        fullscreen_on_mobile=False,
        dismiss_on_outside="1",
    )


def _tecla_aparato(aparato: rx.Var, b: rx.Var) -> rx.Component:
    lid = aparato["id"].to(str)
    return boton_control(
        b["icon"].to(str), b["label"].to(str),
        rx.cond(
            b["tipo"].to(str) == "persiana",
            NodesState.mover_persiana(lid, b["id"].to(str)),
            NodesState.send_ir_button(aparato["remote_id"].to(str), b["id"].to(str)),
        ),
        rx.cond(b["tipo"].to(str) == "persiana", "info", ""),
    )


def _aparato_window(aparato: rx.Var) -> rx.Component:
    """Un aparato (la tele, una persiana) en su panel: estado, encender/apagar,
    sus teclas y el mando completo si lo tiene."""
    lid = aparato["id"].to(str)
    persiana = aparato["persiana"].to(bool)
    encendido = aparato["is_on"].to(bool)
    content = panel(
        panel_cabecera(rx.cond(aparato["floor_icon"], aparato["floor_icon"].to(str),
                               rx.cond(persiana, "blinds", "toggle-right")),
                       aparato["name"], aparato["estado"].to(str), encendido),
        rx.cond(~persiana, rx.el.div(
            boton_control("power", rx.cond(encendido, "Apagar", "Encender"),
                          NodesState.toggle_light(lid), "lamp", encendido),
            class_name="nx-control-acciones")),
        rx.el.div(rx.foreach(aparato["botones"].to(list[dict]),
                             lambda b: _tecla_aparato(aparato, b)),
                  class_name="nx-control-rejilla"),
        rx.cond(
            aparato["remote_id"].to(str) != "",
            rx.el.button(icono("gamepad-2", 15), "Mando completo", type="button",
                         class_name="nx-control-enlace",
                         on_click=DashboardState.open_window_compact(aparato["remote_id"].to(str))),
        ),
    )
    return floating_window(
        content,
        window_id=aparato["id"],
        title=aparato["name"],
        icon=rx.cond(aparato["floor_icon"], aparato["floor_icon"].to(str), "toggle-right"),
        is_open=DashboardState.open_windows.contains(lid),
        on_close=DashboardState.close_window(aparato["id"]),
        accent=theme.ACCENT, top="12%", left="22%", width="340px",
        fullscreen_on_mobile=False,
        dismiss_on_outside="1",
    )


def aparato_windows_layer() -> rx.Component:
    return rx.cond(
        AuthState.puede_luces,
        rx.foreach(NodesState.aparatos_on_floor, _aparato_window),
    )


def puerta_windows_layer() -> rx.Component:
    """Una ventanita por puerta COLOCADA EN EL PLANO, para quien puede abrirlas."""
    return rx.cond(
        AuthState.puede_puertas,
        rx.foreach(NodesState.doors_on_floor, _puerta_window),
    )


def equipo_windows_layer() -> rx.Component:
    """Una ventana por equipo COLOCADO EN EL PLANO. Solo para quien puede
    accionarlos: los eventos lo comprueban igual (permisos.EQUIPOS), pero
    tampoco hay por qué montarle la botonera a quien no va a poder usarla."""
    return rx.cond(
        AuthState.puede_equipos,
        rx.foreach(NodesState.hosts_on_floor, _equipo_window),
    )


def _electro_window(e: rx.Var) -> rx.Component:
    eid = e["id"].to(str)
    return floating_window(
        electro_panel(e),
        window_id=e["id"],
        title=e["name"],
        icon=e["floor_icon"].to(str),
        is_open=DashboardState.open_windows.contains(eid),
        on_close=DashboardState.close_window(e["id"]),
        accent=theme.ACCENT, top="8%", left="24%", width="440px",
        dismiss_on_outside="1",
    )


def electro_windows_layer() -> rx.Component:
    """Un panel por electrodoméstico (simulados, ver domains/electro)."""
    return rx.cond(
        AuthState.puede_equipos,
        rx.foreach(ElectroState.electrodomesticos, _electro_window),
    )
