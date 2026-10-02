"""
La barra superior, siempre visible: dice en qué vista se está (`VIEW_TITLES`,
la tabla completa de TODAS las vistas — la hermana `NAV_ITEMS` de sidebar.py
solo tiene las cinco que además aparecen en el menú), deja armar/desarmar de
un vistazo, y agrupa lo que hace falta poder alcanzar desde cualquier pantalla:
la paleta de comandos, enviar un aviso, registros, métricas y el chip de
"este dispositivo".

QUÉ NO HAY AQUÍ Y POR QUÉ: nada que se toque una vez y no se vuelva a tocar
vive en esta barra — eso es Ajustes (ver settings_hub.py). Esta barra se ve
todo el rato, así que solo lleva lo que de verdad se usa todo el rato.
"""
import reflex as rx

from ...domains.security.state import SecurityState
from ...domains.notifications.state import PushState
from ...domains.auth.state import AuthState
from ...domains.security.arming_state import ArmingState
from .components.form_dialog import styled_input
from .components.paleta import boton_paleta
from .components.enviar_alerta import dialogo_enviar_alerta
from . import theme
from .state import DashboardState

# Las cinco de Alarma/Grupos/Equipos/Mandos/Automatizaciones ya no tienen fila
# propia en el menú (viven detrás de "Ajustes", ver dashboard/views/
# settings_hub.py), pero SIGUEN siendo vistas de verdad — un widget "Ir a
# Equipos" o un enlace directo caen igual en ellas — así que su título entero
# se queda aquí para que la barra superior diga dónde se está.
VIEW_TITLES = {
    "overview": ("Resumen", "layout-dashboard"),
    "alarm": ("Alarma", "siren"),
    "groups": ("Grupos de Armado", "layers"),
    "floor_plan": ("Plano de Planta", "map"),
    "video_wall": ("Mural", "grid-2x2"),
    "cctv": ("CCTV", "video"),
    "access": ("Control de Accesos", "door-open"),
    "lights": ("Luces", "lightbulb"),
    "ir_remotes": ("Mandos", "gamepad-2"),
    "automations": ("Automatizaciones", "workflow"),
    "equipment": ("Equipos", "server"),
    "settings_hub": ("Ajustes", "settings"),
    "system": ("Copias de seguridad", "hard-drive-download"),
    "logs": ("Registros", "clipboard-list"),
    "metricas": ("Métricas", "chart-line"),
    "voz": ("Alexa y voz", "audio-lines"),
    "instalador": ("Modo instalador", "ear"),
    "presencia": ("Simulación de presencia", "user-round-check"),
    "accesorios": ("Accesorios", "toggle-right"),
    "movimiento": ("Detección de movimiento", "scan-eye"),
    "pruebas": ("Pruebas", "flask-conical"),
    "estancias": ("Estancias", "layout-panel-left"),
}


def _view_title() -> rx.Component:
    # Un h1 de verdad (uno por página): el título de la vista es lo que dice
    # dónde se está, y así lo leen igual un lector de pantalla y una persona.
    return rx.el.h1(
        rx.match(
            DashboardState.active_view,
            *[(view_id, title) for view_id, (title, _) in VIEW_TITLES.items()],
            "Resumen",
        ),
        class_name="nx-title",
    )


def _arm_toggle_icon() -> rx.Component:
    """Escudo clicable: arma/desarma el sistema. Sustituye al badge de texto
    ARMADO/DESARMADO — más compacto (cabe en móvil) y además es un atajo.

    A quien no puede armar no se le enseña. Es solo la cara visible: quien
    decide de verdad es el manejador (domains/security/state.py), porque el
    evento se puede invocar sin que el botón esté pintado."""
    return rx.cond(AuthState.puede_armar, _arm_toggle_boton())


def _arm_toggle_boton() -> rx.Component:
    armado = SecurityState.sistema_armado
    return rx.el.button(
        rx.icon(
            rx.cond(armado, "shield-check", "shield-off"), size=20,
            color=rx.cond(armado, "#ff4d5e", "#2ee6a6"),
        ),
        on_click=ArmingState.pedir_armar(""),
        class_name="nx-arm-icon",
        custom_attrs={"data-armado": armado},
        title=rx.cond(armado, "Casa armada — pulsa para desarmar",
                      "Casa desarmada — pulsa para armar"),
        aria_label=rx.cond(armado, "Casa armada. Pulsa para desarmar",
                           "Casa desarmada. Pulsa para armar"),
        type="button",
    )



# El nombre que sale en los avisos ("Ajustes de las notificaciones") vivía
# aquí, en un engranaje suelto siempre visible — se ha movido dentro de
# "Ajustes" (ver dashboard/views/settings_hub.py:_ajustes_avisos_dialog). Es
# exactamente el tipo de cosa que se toca una vez y no debía estar tentando a
# quien no debería tocarla en una barra que se ve todo el rato.
_MUESTRAS_ACENTO = {
    "blue": "#3b82f6", "cyan": "#06b6d4", "jade": "#10b981",
    "violet": "#8b5cf6", "amber": "#f59e0b", "orange": "#f97316",
}


def _apariencia() -> rx.Component:
    """Cómo se ve ESTE accesorio: densidad y color de acento.

    Va en la ventanita del dispositivo y no en Ajustes a propósito. Son
    preferencias del accesorio, no de la casa: el televisor del salón quiere
    botones grandes y el portátil de administrar quiere que quepa el doble. Por
    eso tampoco pide permiso de ajustes — un invitado con una tablet tiene el
    mismo derecho a ver los botones grandes."""
    return rx.vstack(
        rx.text("Cómo se ve este aparato", size="1", color=theme.MUTED,
                weight="medium"),
        rx.hstack(
            rx.foreach(
                AuthState.densidades_ui,
                lambda d: rx.vstack(
                    rx.text(d["nombre"], size="2", weight="bold",
                            color=rx.cond(d["activa"], theme.TEXT, theme.MUTED)),
                    rx.text(d["detalle"], size="1", color=theme.MUTED,
                            style={"font-size": "0.65rem"}),
                    on_click=AuthState.poner_densidad(d["id"]),
                    cursor="pointer", spacing="0", align="start", flex="1",
                    padding="7px 9px", border_radius="9px",
                    background=rx.cond(d["activa"],
                                       theme.alpha(theme.ACCENT, 0.12),
                                       theme.BG_CARD),
                    border=rx.cond(
                        d["activa"],
                        f"1px solid {theme.alpha(theme.ACCENT, 0.55)}",
                        f"1px solid {theme.BORDER}"),
                ),
            ),
            spacing="2", width="100%",
        ),
        rx.hstack(
            rx.foreach(
                AuthState.acentos_ui,
                lambda a: rx.box(
                    width="22px", height="22px", border_radius="50%",
                    background=rx.match(
                        a["id"].to(str),
                        *[(k, v) for k, v in _MUESTRAS_ACENTO.items()],
                        _MUESTRAS_ACENTO["blue"],
                    ),
                    cursor="pointer", flex_shrink="0",
                    on_click=AuthState.poner_acento(a["id"]),
                    # El elegido se marca con un aro, no solo con el color: dos
                    # colores parecidos no dicen cuál está puesto.
                    border=rx.cond(a["activo"], f"2px solid {theme.TEXT}",
                                   f"1px solid {theme.BORDER_STRONG}"),
                ),
            ),
            spacing="2", wrap="wrap", width="100%",
        ),
        spacing="2", width="100%",
    )


def _panel_dispositivo() -> rx.Component:
    """El chip de la barra: dice qué dispositivo es este y deja arreglarlo.

    Antes era un botón que lanzaba el alta directamente, así que si algo no
    cuadraba (el nombre mal, los avisos dejaron de llegar, se dio de alta dos
    veces) no había ningún sitio donde mirarlo ni arreglarlo. Ahora abre una
    ventanita con lo que hay y las tres cosas que se pueden hacer.

    Sin jerga a propósito: ni "suscripción", ni "endpoint", ni "service
    worker". Aquí se habla de "este dispositivo" y de "avisos"."""
    vinculado = PushState.current_user != ""
    return rx.popover.root(
        rx.popover.trigger(
            # El icono entero expresa el estado: no se reduce a un punto que se
            # pierde de vista en la barra. La pastilla sigue siendo el ancla
            # del mismo popover; su contenido no cambia.
            rx.el.button(
                rx.icon(
                    rx.cond(vinculado, "circle-user-round", "circle-user"),
                    size=20,
                    color=rx.cond(vinculado, "#2ee6a6", "#ffa31a"),
                    flex_shrink="0",
                ),
                rx.el.span(
                    rx.cond(vinculado, PushState.current_user, "Sin vincular"),
                    class_name="nx-chip-nombre",
                ),
                class_name="nx-chip",
                custom_attrs={"data-vinculado": vinculado},
                title="Este dispositivo",
                aria_label="Este dispositivo",
                type="button",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.hstack(
                    rx.icon(rx.cond(vinculado, "bell-ring", "bell-off"), size=16,
                            color=rx.cond(vinculado, theme.SUCCESS, theme.WARNING),
                            flex_shrink="0"),
                    rx.text(
                        rx.cond(vinculado, "Este dispositivo recibe avisos",
                                "Este dispositivo no recibe avisos"),
                        size="2", weight="bold", color=theme.TEXT,
                    ),
                    spacing="2", align="center",
                ),
                rx.text(
                    rx.cond(
                        vinculado,
                        "Su nombre es el que aparece en los registros junto a todo lo "
                        "que se hace desde aquí.",
                        "Actívalo para recibir avisos y para que lo que hagas desde este "
                        "accesorio quede identificado en los registros.",
                    ),
                    size="1", color=theme.MUTED,
                ),
                rx.cond(
                    PushState.aviso != "",
                    rx.text(PushState.aviso, size="1", color=theme.WARNING,
                            padding="8px", border_radius="8px", width="100%",
                            background=theme.alpha(theme.WARNING, 0.08)),
                ),
                rx.divider(border_color=theme.BORDER),
                rx.cond(
                    vinculado,
                    rx.vstack(
                        rx.text("Nombre de este dispositivo", size="1", color=theme.MUTED,
                                weight="medium"),
                        rx.hstack(
                            styled_input(
                                value=PushState.nombre_nuevo,
                                on_change=PushState.set_nombre_nuevo,
                                placeholder="Mi iPhone",
                                max_length=30, size="2",
                            ),
                            rx.button("Guardar", on_click=PushState.renombrar,
                                      size="2", variant="surface", flex_shrink="0"),
                            spacing="2", width="100%",
                        ),
                        rx.divider(border_color=theme.BORDER),
                        _apariencia(),
                        rx.divider(border_color=theme.BORDER),
                        rx.button(
                            rx.icon("refresh-cw", size=14), "¿No te llegan los avisos?",
                            on_click=PushState.reactivar,
                            size="2", variant="soft", width="100%",
                        ),
                        rx.text("Vuelve a activarlos desde cero, sin perder el nombre.",
                                size="1", color=theme.MUTED),
                        rx.button(
                            rx.icon("log-out", size=14), "Desvincular este dispositivo",
                            on_click=PushState.desvincular,
                            size="2", variant="soft", color_scheme="red", width="100%",
                        ),
                        spacing="2", width="100%",
                    ),
                    rx.button(
                        rx.icon("bell-ring", size=14), "Activar los avisos aquí",
                        on_click=PushState.suscribir,
                        size="2", color_scheme="orange", width="100%",
                    ),
                ),
                spacing="3", width="100%",
            ),
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.BORDER_STRONG}",
            border_radius="12px",
            padding="16px",
            width="min(330px, 92vw)",
        ),
        on_open_change=PushState.abrir_panel,
    )


def _boton_atras_ajustes() -> rx.Component:
    """Flecha de volver al menu de Ajustes, en TODAS las pestañas de dentro de Ajustes.

    Vive aqui, en la barra de arriba, y no en cada vista: asi sale en las pestañas que
    decide state._EN_AJUSTES, siempre en el mismo sitio, y una pestaña nueva la tiene
    sin acordarse de ponerla. El "atras" propio de un flujo interno (el editor de Auto,
    el instalador) sigue siendo suyo: esta flecha va siempre al menu de Ajustes.
    """
    return rx.cond(
        DashboardState.en_subajustes,
        rx.button(
            rx.icon("arrow-left", size=16),
            rx.text("Ajustes", display=rx.breakpoints(initial="none", sm="inline")),
            size="2",
            variant="soft",
            on_click=DashboardState.set_view("settings_hub"),
            aria_label="Volver a Ajustes",
            title="Volver a Ajustes",
            flex_shrink="0",
        ),
    )


def _icono_barra(icono: str, titulo: str, **props) -> rx.Component:
    return rx.el.button(
        rx.icon(icono, size=18),
        class_name="nx-icon-btn",
        title=titulo,
        aria_label=titulo,
        type="button",
        **props,
    )


def topbar() -> rx.Component:
    # Vive FUERA del contenedor que se desplaza (ver _panel en
    # ui/pages/dashboard.py): por eso no se mueve nunca, ni al hacer scroll ni
    # con el rebote elástico de iOS, que antes la arrastraba a media pantalla.
    return rx.el.header(
        # La marca solo sale en el móvil, donde no hay barra lateral (nx.css).
        rx.el.img(src="/noxus-marca.svg", alt="", class_name="nx-title-mark",
                  width="26", height="26"),
        _boton_atras_ajustes(),
        _view_title(),
        _arm_toggle_icon(),
        rx.badge(
            rx.cond(SecurityState.puerta_abierta, "Puerta abierta", "Puerta cerrada"),
            color_scheme=rx.cond(SecurityState.puerta_abierta, "orange", "gray"),
            variant="surface",
            size="2",
            class_name="nx-solo-escritorio nx-solo-ancho",
            flex_shrink="0",
        ),
        # Piloto «en vivo» junto al reloj: late mientras el panel está conectado.
        rx.el.span(class_name="nx-vivo nx-solo-escritorio nx-solo-ancho", aria_hidden="true"),
        rx.el.span(id="nx-clock", class_name="nx-clock nx-solo-escritorio nx-solo-ancho"),
        # La paleta de comandos: la forma rápida de llegar a CUALQUIER sitio.
        boton_paleta(),
        # Mandar un aviso a los móviles de la casa sin pasar por el Resumen.
        # Pesa lo mismo que sus vecinas: aquí no está pasando nada, es una
        # herramienta.
        dialogo_enviar_alerta(_icono_barra("bell-ring", "Enviar una alerta")),
        _icono_barra("clipboard-list", "Ver registros",
                     on_click=DashboardState.set_view("logs")),
        # Métricas al lado de Registros: son las dos caras del mismo histórico
        # —los hechos uno a uno y los hechos contados—. Se ve TAMBIÉN en el
        # móvil: una vista a la que solo se llega escribiendo ?vista=metricas
        # en la barra de direcciones es una vista que no existe.
        _icono_barra("chart-line", "Ver métricas",
                     on_click=DashboardState.set_view("metricas")),
        # La terminal del despliegue: solo en los aparatos que la tienen
        # marcada en Dispositivos. La ventana es JavaScript puro (ver
        # pages/dashboard.py) para que siga viva mientras el servicio reinicia.
        rx.cond(
            AuthState.ve_despliegue,
            _icono_barra("square-terminal", "Estado del despliegue",
                         on_click=rx.call_script("window.__nxTerminal && window.__nxTerminal.toggle()")),
        ),
        _panel_dispositivo(),
        class_name="nx-topbar",
    )
