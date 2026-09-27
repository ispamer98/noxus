"""Pantalla-kiosco de UNA habitación: la tablet fija de pared que sustituye a los
interruptores físicos.

Va en /estancia/<id> y es una página sola: no monta la barra lateral, la barra
superior, el dock móvil, la paleta de comandos ni las ventanas flotantes del
panel, y no tiene ni un enlace hacia el resto. Que un dispositivo no pueda
salir NO depende solo de eso: lo hace cumplir el servidor (rol `kiosco` con
capacidades mínimas, estancia fijada en su ficha, y cada control comprobado
contra los miembros de SU estancia; ver domains/auth/permisos.py y
domains/nodes/kiosco_state.py).

Diseño (centro de control: controles, nunca información de estado):
- Cabecera mínima: nombre de la habitación y hora.
- A la izquierda, el plano de la planta con SOLO los marcadores de la estancia.
  A la derecha, los controles en tarjetas: luces y aparatos, puertas, mandos y
  los equipos sobre los que hay algo que hacer, en baldosas compactas.
- El botón «Cámaras» de la cabecera despliega, bajo el plano, un Mural de 1/2/4/6/8
  huecos donde se coloca CUALQUIER cámara del sistema, para mirar fuera de la
  habitación de un vistazo. Reparto, cámaras y si está desplegado se recuerdan
  por estancia (KioscoState.mural_*).
- Nada de estados de conexión, sensores ni el estado de la casa.
- Mandos y equipos se abren en una hoja a pantalla completa DENTRO de la misma
  página (KioscoState.overlay_*), con un botón «Cerrar».
- Sirena: la tablet puede sonar mientras haya una alerta de alarma sin confirmar
  (sonido y volumen a elegir; se guarda por estancia). El sonido lo genera
  assets/nx.js con Web Audio.
- Modo permanente: pantalla siempre encendida, reposo con reloj a los 90 s (el
  primer toque solo despierta) y despierta sola si salta una alarma. Es
  JavaScript de assets/nx.js (bloque «Kiosco»); aquí solo están los ganchos.
"""
import reflex as rx

from ...domains.auth.state import AuthState
from ...domains.devices.registry_state import RegistryState
from ...domains.infra.state import InfraState
from ...domains.nodes.host_actions_state import HostActionsState
from ...domains.nodes.kiosco_state import KioscoState
from ...domains.nodes.state import NodesState
from ...domains.notifications.alertas_state import AlertasState
from ...domains.security.state import SecurityState
from ..dashboard.components.alertas import banner_alertas
from ..dashboard.views.ir_remotes import ir_remote_kiosco
from ..dashboard.views.overview import _quick_action
from ..dashboard.windows import _accion, _boton_propio, camera_kiosco_content
from ..views.device_list import kiosco_floor_plan_content
from .dashboard import _NX_JS, _comprobando, _sin_acceso

# Lo que hay que hacer al ENTRAR: solo lo que usa esta pantalla. Los primeros
# tres identifican a la tablet y KioscoState.entrar los ejecuta ANTES de decidir
# si se puede cargar nada más (una sesión sin acceso no recibe datos de la casa;
# ver la nota de Reflex sobre vars públicas en ui/pages/dashboard.py).
EVENTOS_KIOSCO_IDENTIFICACION = [
    AuthState.identificar,
    AuthState.canjear_de_la_url,
    AuthState.vigilar_acceso,
]
EVENTOS_KIOSCO = EVENTOS_KIOSCO_IDENTIFICACION + [
    SecurityState.on_load,
    InfraState.on_load,
    RegistryState.on_load,
    NodesState.on_load,
    AlertasState.on_load,
]


# ── Baldosas de cada tipo ─────────────────────────────────────────────────────
def _luz(luz: rx.Var) -> rx.Component:
    return _quick_action(
        rx.cond(luz["floor_icon"], luz["floor_icon"].to(str), "lightbulb"),
        luz["name"].to(str), NodesState.toggle_light(luz["id"].to(str)),
        tono="lamp", activo=luz["is_on"].to(bool), interruptor=True,
    )


def _puerta(puerta: rx.Var) -> rx.Component:
    return _quick_action(
        "door-open", "Abrir " + puerta["name"].to(str),
        NodesState.open_door(puerta["id"].to(str)),
    )


def _mando(mando: rx.Var) -> rx.Component:
    return _quick_action(
        rx.cond(mando["icon"], mando["icon"].to(str), "gamepad-2"),
        mando["name"].to(str),
        KioscoState.abrir_overlay("mando", mando["id"].to(str)),
    )


def _equipo(host: rx.Var) -> rx.Component:
    return _quick_action(
        rx.cond(host["floor_icon"], host["floor_icon"].to(str),
                rx.cond(host["icon"], host["icon"].to(str), "server")),
        host["name"].to(str),
        KioscoState.abrir_overlay("equipo", host["id"].to(str)),
    )


def _seccion(titulo: str, icono: str, items: rx.Var, render,
             visible=None, clase_items: str = "nx-kiosco-tiles") -> rx.Component:
    """Un grupo con su encabezado. Sin controles de ese tipo no pinta nada."""
    cuerpo = rx.cond(
        items.length() > 0,
        rx.el.section(
            rx.el.h2(rx.icon(icono, size=18), rx.el.span(titulo),
                     class_name="nx-kiosco-h2"),
            rx.el.div(rx.foreach(items, render), class_name=clase_items),
            class_name="nx-kiosco-seccion",
        ),
    )
    return cuerpo if visible is None else rx.cond(visible, cuerpo)


def _controles() -> rx.Component:
    vacia = (
        NodesState.kiosco_lights.length() + NodesState.kiosco_doors.length()
        + NodesState.kiosco_remotes.length() + NodesState.kiosco_hosts.length()
    ) == 0
    return rx.el.div(
        _seccion("Luces y aparatos", "lightbulb", NodesState.kiosco_lights, _luz),
        _seccion("Puertas", "door-open", NodesState.kiosco_doors, _puerta),
        _seccion("Mandos", "gamepad-2", NodesState.kiosco_remotes, _mando,
                 visible=AuthState.puede_mandos),
        _seccion("Equipos", "server", NodesState.kiosco_hosts, _equipo,
                 visible=AuthState.puede_equipos),
        rx.cond(
            vacia,
            rx.el.p("Esta habitación aún no tiene controles. Se añaden en "
                    "Ajustes → Estancias.", class_name="nx-kiosco-vacio"),
        ),
        class_name="nx-kiosco-controles",
        custom_attrs={"data-baldosas": NodesState.kiosco_pantalla["baldosas"]},
    )


# ── Plano en la esquina ───────────────────────────────────────────────────────
def _plano() -> rx.Component:
    """El plano grande, con el mismo marco de cristal, halo y viñeta que la
    pestaña Plano del panel (nx.css, .nx-kiosco-marco), y la copia difuminada de
    la propia imagen detrás para que se funda con el fondo."""
    return rx.el.section(
        rx.image(src=NodesState.plano_imagen_url, alt="", aria_hidden="true",
                 class_name="nx-kiosco-fondo", draggable=False),
        rx.el.button(
            rx.icon("chevrons-up-down", size=18), rx.el.span("Plano"),
            on_click=KioscoState.alternar_plano_colapsado,
            class_name="nx-kiosco-btn nx-kiosco-solo-vertical",
            type="button", aria_label="Mostrar u ocultar el plano",
        ),
        rx.el.div(
            kiosco_floor_plan_content(),
            rx.el.button(
                rx.icon("maximize-2", size=20),
                on_click=KioscoState.ampliar_plano,
                class_name="nx-kiosco-btn nx-kiosco-ampliar", type="button",
                aria_label="Ampliar el plano", title="Ampliar el plano",
            ),
            class_name="nx-kiosco-marco",
        ),
        class_name="nx-kiosco-plano",
        custom_attrs={"data-colapsado": KioscoState.plano_colapsado},
    )


# ── Hojas a pantalla completa (dentro de la misma página) ─────────────────────
def _hoja(titulo, contenido: rx.Component, al_cerrar, clase: str = "",
          extra: rx.Component | None = None) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.h2(titulo, class_name="nx-kiosco-hoja-titulo"),
            extra if extra is not None else rx.fragment(),
            rx.el.button(rx.icon("x", size=24), rx.el.span("Cerrar"),
                         on_click=al_cerrar, class_name="nx-kiosco-btn nx-kiosco-cerrar",
                         type="button"),
            class_name="nx-kiosco-hoja-cab",
        ),
        rx.el.div(contenido, class_name="nx-kiosco-hoja-cuerpo " + clase),
        class_name="nx-kiosco-hoja", role="dialog", aria_modal="true",
    )


def _equipo_contenido(host: rx.Var) -> rx.Component:
    """Las mismas acciones que la ventana de equipo del plano (windows.py), con
    sus mismos eventos: el permiso y el registro los pone HostActionsState."""
    hid = host["id"].to(str)
    return rx.vstack(
        rx.cond(host["mac"], _accion("power", "Encender por red",
                                     HostActionsState.encender_wol(hid), "green")),
        rx.cond(
            host["user"],
            rx.fragment(
                _accion("power-off", "Apagar",
                        HostActionsState.accion_rapida(hid, "apagar"), "red"),
                _accion("rotate-ccw", "Reiniciar",
                        HostActionsState.accion_rapida(hid, "reiniciar"), "amber"),
            ),
        ),
        rx.foreach(host["botones"].to(list[dict]), _boton_propio),
        spacing="3", width="min(420px, 100%)",
    )


def _celda_mural(c: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.cond(
            c["vacia"].to(bool),
            rx.el.button(
                rx.icon("plus", size=36), rx.el.span("Añadir cámara"),
                on_click=KioscoState.mural_elegir_hueco(c["slot"].to(str)),
                class_name="nx-mural-vacia", type="button",
            ),
            rx.fragment(
                rx.cond(
                    c["visible"].to(bool),
                    rx.cond(
                        c["jugable"].to(bool),
                        rx.el.iframe(src=c["url"].to(str), allow="autoplay; fullscreen"),
                        rx.el.div("Este origen no se puede ver aquí.",
                                  class_name="nx-mural-espera"),
                    ),
                    rx.el.div(rx.spinner(size="3"), class_name="nx-mural-espera"),
                ),
                rx.el.div(
                    rx.el.span(c["nombre"].to(str)),
                    rx.el.button(rx.icon("volume-x", size=20, class_name="nx-mural-mudo"),
                                 rx.icon("volume-2", size=20, class_name="nx-mural-suena"),
                                 class_name="nx-mural-audio", type="button",
                                 aria_label="Activar o silenciar el sonido"),
                    rx.el.button(rx.icon("rotate-cw", size=20),
                                 on_click=KioscoState.mural_recargar(c["slot"].to(str)),
                                 type="button", aria_label="Recargar"),
                    rx.el.button(rx.icon("replace", size=20),
                                 on_click=KioscoState.mural_elegir_hueco(c["slot"].to(str)),
                                 type="button", aria_label="Cambiar cámara"),
                    rx.el.button(rx.icon("x", size=20),
                                 on_click=KioscoState.mural_quitar(c["slot"].to(str)),
                                 type="button", aria_label="Quitar"),
                    class_name="nx-mural-barra",
                ),
            ),
        ),
        class_name="nx-mural-celda",
    )


def _mural() -> rx.Component:
    """El panel del mural, desplegado bajo el plano: reparto 1/2/4/6/8 y sus
    huecos. Ocupa el espacio que deja el plano; se activa desde la cabecera."""
    reparto = rx.el.div(
        *[rx.el.button(
            n, on_click=KioscoState.mural_repartir(n),
            class_name="nx-kiosco-btn nx-mural-reparto", type="button",
            custom_attrs={"data-activo": KioscoState.mural_layout == n},
        ) for n in ("1", "2", "4", "6", "8")],
        class_name="nx-mural-repartos",
    )
    return rx.el.section(
        rx.el.div(
            rx.el.h2(rx.icon("video", size=18), rx.el.span("Cámaras"),
                     class_name="nx-kiosco-h2"),
            reparto,
            class_name="nx-mural-cab",
        ),
        rx.el.div(rx.foreach(KioscoState.mural_celdas, _celda_mural),
                  class_name="nx-mural",
                  custom_attrs={"data-reparto": KioscoState.mural_layout}),
        class_name="nx-mural-panel",
    )


def _selector_camara() -> rx.Component:
    """Elegir qué cámara va en un hueco: hoja a pantalla completa."""
    return rx.cond(
        KioscoState.mural_elegir != "",
        rx.el.div(
            rx.el.div(
                rx.el.h2("Elegir cámara", class_name="nx-kiosco-hoja-titulo"),
                rx.el.button(rx.icon("x", size=24), rx.el.span("Cancelar"),
                             on_click=KioscoState.mural_cancelar,
                             class_name="nx-kiosco-btn nx-kiosco-cerrar", type="button"),
                class_name="nx-kiosco-hoja-cab",
            ),
            rx.el.div(
                rx.foreach(KioscoState.mural_catalogo, lambda cam: _quick_action(
                    "video", cam["name"].to(str),
                    KioscoState.mural_poner(cam["id"].to(str)))),
                class_name="nx-kiosco-tiles nx-mural-lista",
            ),
            class_name="nx-kiosco-hoja", role="dialog", aria_modal="true",
        ),
    )


def _hoja_sirena() -> rx.Component:
    def opcion(valor: str, texto: str, activo, evento) -> rx.Component:
        return rx.el.button(texto, on_click=evento(valor), type="button",
                            class_name="nx-kiosco-btn nx-opcion",
                            custom_attrs={"data-activo": activo == valor})

    sonidos = [("sirena", "Sirena"), ("pitido", "Pitido"), ("alarma", "Alarma"),
               ("timbre", "Timbre")]
    volumenes = [("25", "Suave"), ("50", "Medio"), ("75", "Alto"), ("100", "Máximo")]
    contenido = rx.el.div(
        _quick_action("siren", "Sirena en esta tablet", KioscoState.alternar_sirena,
                      tono="lamp", activo=_sirena("activa") == "1", interruptor=True),
        rx.el.p("Si salta la alarma, esta tablet suena hasta que alguien confirme "
                "o silencie el aviso.", class_name="nx-kiosco-nota"),
        rx.el.h3("Sonido", class_name="nx-kiosco-h3"),
        rx.el.div(*[opcion(v, t, _sirena("sonido"), KioscoState.elegir_sonido)
                    for v, t in sonidos], class_name="nx-opciones"),
        rx.el.h3("Volumen", class_name="nx-kiosco-h3"),
        rx.el.div(*[opcion(v, t, _sirena("volumen"), KioscoState.elegir_volumen)
                    for v, t in volumenes], class_name="nx-opciones"),
        rx.el.button(rx.icon("play", size=20), rx.el.span("Probar"), type="button",
                     class_name="nx-kiosco-btn nx-sirena-probar"),
        rx.el.p("Si suena bajo o no suena: toca una vez la pantalla; el navegador "
                "no deja sonar hasta que alguien la toca.", class_name="nx-kiosco-nota",
                custom_attrs={"data-solo-bloqueado": "1"}),
        class_name="nx-sirena-panel",
    )
    return _hoja("Sirena", contenido, KioscoState.cerrar_sirena_ajustes)


def _hojas() -> rx.Component:
    return rx.fragment(
        rx.cond(
            KioscoState.overlay_kind == "mando",
            rx.foreach(NodesState.kiosco_remotes, lambda r: rx.cond(
                r["id"].to(str) == KioscoState.overlay_id,
                _hoja(r["name"].to(str), ir_remote_kiosco(r),
                      KioscoState.cerrar_overlay))),
        ),
        rx.cond(
            KioscoState.overlay_kind == "equipo",
            rx.foreach(NodesState.kiosco_hosts, lambda h: rx.cond(
                h["id"].to(str) == KioscoState.overlay_id,
                _hoja(h["name"].to(str), _equipo_contenido(h),
                      KioscoState.cerrar_overlay))),
        ),
        rx.cond(
            KioscoState.overlay_kind == "camara",
            rx.foreach(NodesState.kiosco_cameras, lambda c: rx.cond(
                c["id"].to(str) == KioscoState.overlay_id,
                _hoja(c["name"].to(str), camera_kiosco_content(c),
                      KioscoState.cerrar_overlay))),
        ),
        _selector_camara(),
        rx.cond(KioscoState.sirena_ajustes, _hoja_sirena()),
        rx.cond(
            KioscoState.plano_ampliado,
            _hoja("Plano", kiosco_floor_plan_content(), KioscoState.cerrar_plano,
                  clase="nx-kiosco-hoja-plano"),
        ),
    )


# ── Cabecera y reposo ─────────────────────────────────────────────────────────
def _cabecera() -> rx.Component:
    return rx.el.header(
        rx.el.h1(NodesState.kiosco_room_name, class_name="nx-kiosco-nombre"),
        rx.el.div(
            rx.cond(_op("sirena"), rx.el.button(
                rx.icon("siren", size=20), rx.el.span("Sirena"),
                on_click=KioscoState.abrir_sirena_ajustes,
                class_name="nx-kiosco-btn nx-kiosco-alterna nx-kiosco-sirena",
                type="button",
                custom_attrs={"data-activo": _sirena("activa") == "1"},
            )),
            rx.cond(
                AuthState.puede_camaras & _op("camaras"),
                rx.el.button(
                    rx.icon("video", size=20), rx.el.span("Cámaras"),
                    on_click=KioscoState.alternar_mural,
                    class_name="nx-kiosco-btn nx-kiosco-alterna", type="button",
                    custom_attrs={"data-activo": KioscoState.mural_abierto},
                ),
            ),
            class_name="nx-kiosco-acciones",
        ),
        rx.cond(_op("hora"), rx.el.div(class_name="nx-kiosco-hora")),
        class_name="nx-kiosco-cab",
    )


def _reposo() -> rx.Component:
    """La pantalla casi negra de las noches. La enciende y apaga el JS (nx.js)
    con data-reposo en .nx-kiosco; sin JS simplemente no aparece."""
    return rx.el.div(
        rx.el.div(class_name="nx-kiosco-hora nx-kiosco-reposo-hora"),
        rx.el.div(class_name="nx-kiosco-fecha nx-kiosco-reposo-fecha"),
        rx.el.i(class_name="nx-kiosco-reposo-armado",
                custom_attrs={"data-armado": SecurityState.sistema_armado}),
        class_name="nx-kiosco-reposo", aria_hidden="true",
    )


def _sirena(clave: str):
    """La sirena de esta estancia (ficha de la estancia, en vivo)."""
    return NodesState.kiosco_sirena[clave]


def _op(clave: str):
    """Una opción de pantalla de esta estancia (pestaña «Estancias»)."""
    return NodesState.kiosco_pantalla[clave] == "1"


def _kiosco() -> rx.Component:
    return rx.el.div(
        _cabecera(),
        rx.el.main(
            rx.cond(_op("plano"), _plano()),
            rx.el.div(rx.cond(KioscoState.mural_abierto, _mural()), _controles(),
                      class_name="nx-kiosco-der"),
            class_name="nx-kiosco-cuerpo",
            custom_attrs={"data-sin-plano": ~_op("plano")}),
        _hojas(),
        # El banner de alarma de siempre; el JS despierta la pantalla si aparece.
        rx.el.div(banner_alertas(), class_name="nx-kiosco-alertas"),
        _reposo(),
        class_name="nx-kiosco",
        custom_attrs={
            "data-kiosco": "1",
            "data-sirena": _sirena("activa") == "1",
            "data-sonido": _sirena("sonido"),
            "data-volumen": _sirena("volumen"),
            "data-prueba": _sirena("prueba"),
            "data-alarma": AlertasState.hay_pendientes,
        },
    )


def _espera() -> rx.Component:
    """Una tablet que todavía no tiene acceso: la pantalla de siempre para pedirlo
    y, en cuanto un administrador la apruebe, el JS recarga sola (data-kiosco-espera)."""
    return rx.fragment(_sin_acceso(), rx.el.div(custom_attrs={"data-kiosco-espera": "1"}))


def kiosco_page() -> rx.Component:
    return rx.box(
        rx.script(src=_NX_JS),
        rx.theme(
            rx.cond(
                AuthState.comprobando,
                _comprobando(),
                rx.cond(AuthState.tiene_acceso, _kiosco(), _espera()),
            ),
            appearance="dark",
            accent_color=AuthState.acento,
        ),
        min_height="100vh", width="100%", background="transparent",
        # El mismo tinte de armado que el panel (aurora y nodos), pero solo con acceso.
        custom_attrs={"data-nx-armado": rx.cond(
            AuthState.tiene_acceso, SecurityState.sistema_armado, False)},
    )
