"""
Vista "Ajustes": el único sitio al que hay que ir para configurar algo.

Nace de que casi todas las pantallas del panel mezclan dos cosas muy
distintas: lo que se usa a diario (encender una luz, abrir la puerta, ver una
cámara) y lo que se configura UNA vez al instalar algo y casi no se vuelve a
tocar (dar de alta un sensor, definir una zona de armado, aprender un mando,
montar una automatización). Antes las cinco pantallas de configuración
—Alarma, Grupos, Equipos, Mandos, Auto— estaban sueltas en la barra lateral al
mismo nivel que Resumen o Luces, y para un instalador o un tester encontrar
"dónde se añade un sensor nuevo" significaba abrir pestañas una a una.

Esta vista no tiene estado propio ni formularios: es un mapa con enlaces.
Cada tarjeta llama a DashboardState.set_view(...) — la MISMA vista que ya
existía y sigue siendo la misma (mismo id, mismo componente, mismo domain
state); lo único que cambia es desde dónde se llega a ella. Por eso quitarlas
de la barra lateral no rompe nada: los widgets "Ir a Alarma" / "Ir a CCTV"
del Resumen y cualquier automatización que compruebe algo de esas pantallas
siguen funcionando exactamente igual.

Nótese que Equipos NO está aquí: aunque también es una pantalla de gestión,
es la que más se usa día a día (apagar un PC, entrar por RDP) y por eso tiene
fila propia en el menú — ver sidebar.py. Aquí solo va lo que de verdad es
"instalar/configurar una vez y no tocar más" — Luces incluida: encender o
apagar una luz concreta es un acceso rápido del Resumen; dar de alta una luz
nueva, decirle a qué pin va o crear una estancia es esto de aquí.

El nombre que sale en los avisos del móvil (antes un engranaje suelto en la
barra de arriba, visible todo el rato) también vive aquí ahora, como una
tarjeta más: es exactamente el tipo de cosa que se toca una vez al configurar
el dispositivo de cada uno y nunca más — no algo que deba estar siempre a
mano ni tentando a quien no debería tocarlo."""
import reflex as rx

from .. import theme
from ..components.form_dialog import field, form_dialog_content, styled_input
from ..state import DashboardState
from ....domains.notifications.state import PushState

# (id de la vista, icono, título, descripción de una línea con lo que hay
# de verdad dentro — no el nombre bonito, lo que se va a encontrar).
_SEGURIDAD = [
    ("alarm", "siren", "Alarma",
     "Sensores y nodos: dar de alta, cambiar tipo o pin, aislar de la alarma."),
    ("groups", "layers", "Grupos",
     "Zonas de armado: qué sensores arma cada grupo y cuál es el principal."),
    ("access", "door-open", "Accesos",
     "Niveles y tarjetas RFID: quién puede abrir cada puerta."),
]

_VIGILANCIA = [
    ("cctv", "video", "Cámaras",
     "Añadir o editar cámaras — para verlas basta un acceso rápido del Resumen."),
]

_DISPOSITIVOS = [
    ("lights", "lightbulb", "Luces",
     "Dar de alta luces y estancias — para encenderlas basta un acceso rápido."),
    ("ir_remotes", "gamepad-2", "Mandos",
     "Mandos IR/RF virtuales: aprender señales y colocar botones."),
    ("automations", "workflow", "Automatizaciones",
     "Reglas CUÁNDO / Y SI / ENTONCES sobre cualquier equipo de la casa."),
]


def _card(view_id: str, icon: str, title: str, desc: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon(icon, size=19, color=theme.ACCENT),
            padding="11px",
            border_radius="11px",
            background=theme.alpha(theme.ACCENT, 0.14),
            border=f"1px solid {theme.alpha(theme.ACCENT, 0.3)}",
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(title, size="3", weight="bold", color=theme.TEXT),
            rx.text(desc, size="1", color=theme.MUTED, style={"line-height": "1.5"}),
            spacing="1",
            align="start",
            min_width="0",
        ),
        rx.spacer(),
        rx.icon("chevron-right", size=16, color=theme.MUTED, flex_shrink="0"),
        on_click=DashboardState.set_view(view_id),
        cursor="pointer",
        align="center",
        spacing="4",
        width="100%",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding="14px 16px",
        transition="background 0.15s ease, border-color 0.15s ease",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )


def _dialog_card(icon: str, title: str, desc: str, dialog_content: rx.Component,
                 on_open_change=None) -> rx.Component:
    """Igual que _card, pero abre un diálogo en el sitio en vez de navegar —
    para lo que es un ajuste puntual (un nombre, un interruptor) y no una
    pantalla propia con su propia lista de cosas."""
    kwargs = {} if on_open_change is None else {"on_open_change": on_open_change}
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=19, color=theme.ACCENT),
                    padding="11px",
                    border_radius="11px",
                    background=theme.alpha(theme.ACCENT, 0.14),
                    border=f"1px solid {theme.alpha(theme.ACCENT, 0.3)}",
                    flex_shrink="0",
                ),
                rx.vstack(
                    rx.text(title, size="3", weight="bold", color=theme.TEXT),
                    rx.text(desc, size="1", color=theme.MUTED, style={"line-height": "1.5"}),
                    spacing="1", align="start", min_width="0",
                ),
                rx.spacer(),
                rx.icon("chevron-right", size=16, color=theme.MUTED, flex_shrink="0"),
                cursor="pointer", align="center", spacing="4", width="100%",
                background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
                border_radius="12px", padding="14px 16px",
                transition="background 0.15s ease, border-color 0.15s ease",
                _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
            ),
        ),
        dialog_content,
        **kwargs,
    )


def _ajustes_avisos_dialog() -> rx.Component:
    """El nombre con el que se presenta la app en los avisos — el "De ..."
    que sale debajo de cada notificación. Vivía en un engranaje suelto en la
    barra de arriba, siempre visible; ahora es una tarjeta más aquí, que es
    donde tiene que estar algo que se toca una vez al instalar el dispositivo
    y nunca más."""
    return form_dialog_content(
        icon="bell",
        title="Nombre en los avisos",
        accent=theme.ACCENT,
        max_width="440px",
        form=rx.vstack(
            field(
                "Nombre en los avisos",
                styled_input(
                    value=PushState.nombre_app,
                    on_change=PushState.set_nombre_app,
                    placeholder="Noxus",
                    max_length=30,
                ),
                hint="Es el «De ...» que sale debajo de cada notificación. Lo pone "
                     "el móvil a partir del nombre de la app, no el propio aviso.",
            ),
            rx.hstack(
                rx.icon("info", size=15, color=theme.WARNING, flex_shrink="0"),
                rx.text(
                    "Cada dispositivo lo lee al instalar el acceso directo y no vuelve "
                    "a mirarlo: para ver el nombre nuevo hay que quitarlo de la "
                    "pantalla de inicio y volver a añadirlo.",
                    size="1", color=theme.MUTED,
                ),
                spacing="2", align="start",
                padding="10px", border_radius="9px",
                background=theme.alpha(theme.WARNING, 0.08),
                border=f"1px solid {theme.alpha(theme.WARNING, 0.3)}",
            ),
            rx.hstack(
                rx.spacer(),
                rx.dialog.close(
                    rx.button("Guardar", on_click=PushState.guardar_nombre_app, size="2"),
                ),
                width="100%",
            ),
            spacing="4", width="100%",
        ),
    )


def _section(title: str, items: list[tuple[str, str, str, str]]) -> rx.Component:
    return rx.vstack(
        rx.text(title, size="1", weight="bold", color=theme.MUTED,
                letter_spacing="0.08em", text_transform="uppercase"),
        rx.vstack(
            *[_card(*item) for item in items],
            spacing="2",
            width="100%",
        ),
        spacing="3",
        width="100%",
        align="start",
    )


def settings_hub_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Ajustes", size="5", color=theme.TEXT),
            rx.text(
                "Lo que se configura una vez al instalar algo, no lo que se usa "
                "cada día. Ver una cámara, abrir una puerta o encender la luz del "
                "salón se hace con un botón del Resumen — para eso no hace falta "
                "entrar aquí.",
                size="1", color=theme.MUTED,
            ),
            spacing="1",
            align="start",
        ),
        _section("Seguridad y accesos", _SEGURIDAD),
        _section("Vigilancia", _VIGILANCIA),
        _section("Dispositivos y automatización", _DISPOSITIVOS),
        rx.vstack(
            rx.text("Este dispositivo", size="1", weight="bold", color=theme.MUTED,
                    letter_spacing="0.08em", text_transform="uppercase"),
            _dialog_card(
                "bell", "Nombre en los avisos",
                "El «De ...» que sale debajo de cada notificación de este aparato.",
                _ajustes_avisos_dialog(),
                on_open_change=PushState.cargar_nombre_app,
            ),
            spacing="3", width="100%", align="start",
        ),
        spacing="5",
        width="100%",
        align="start",
        max_width="640px",
        padding_bottom="6",
    )
