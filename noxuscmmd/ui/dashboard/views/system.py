"""
Vista "Sistema": lo que hay que saber del panel en sí, no de la casa.

Nace con las copias de seguridad. Es su sitio natural y no "Ajustes": Ajustes
es donde se da de alta lo que hay en la casa (un sensor, una cámara, una
regla); esto es el estado del propio servicio — de lo que depende que todo lo
demás siga en pie.

Aquí es donde entrarán después el resto de comprobaciones de salud (MQTT,
go2rtc, túnel, disco, latido del motor de reglas): la pantalla ya está montada
como una lista de bloques para que añadir uno no obligue a recolocar nada.
"""
import reflex as rx

from ....domains.infra.backups import MAX_COPIAS
from ....domains.infra.backups_state import BackupsState
from ....domains.infra.salud_state import SaludState
from ....domains.infra import salud
from .. import theme


def _bloque(icon: str, titulo: str, descripcion: str, cuerpo: rx.Component,
            accion: rx.Component | None = None) -> rx.Component:
    """Un apartado de la pestaña. Cabecera con icono + qué es + qué hace, y
    debajo el contenido."""
    return rx.vstack(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=18, color=theme.ACCENT),
                padding="10px",
                border_radius="10px",
                background=theme.alpha(theme.ACCENT, 0.14),
                border=f"1px solid {theme.alpha(theme.ACCENT, 0.3)}",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(titulo, size="3", weight="bold", color=theme.TEXT),
                rx.text(descripcion, size="1", color=theme.MUTED,
                        style={"line-height": "1.5"}),
                spacing="1", align="start", min_width="0",
            ),
            rx.spacer(),
            accion if accion is not None else rx.fragment(),
            align="center", spacing="4", width="100%", wrap="wrap",
        ),
        cuerpo,
        spacing="3",
        width="100%",
        align="start",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding=["14px", "14px", "18px"],
    )


def _fila_copia(copia: dict) -> rx.Component:
    completa = copia["completa"].to(bool)
    return rx.hstack(
        rx.icon(
            rx.cond(completa, "archive", "triangle-alert"),
            size=15,
            color=rx.cond(completa, theme.MUTED, theme.WARNING),
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(copia["fecha_texto"], size="2", color=theme.TEXT, weight="medium"),
            # El .to(str) es obligatorio en el PRIMER trozo: el valor de una
            # clave de dict llega sin tipo dentro de un rx.foreach, y sin él
            # Reflex no sabe que lo que va a hacer con el "+" es pegar texto.
            rx.text(
                copia["motivo"].to(str) + " · " + copia["ficheros"].to_string()
                + " ficheros · " + copia["tamano_texto"].to(str),
                size="1", color=theme.MUTED,
            ),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.cond(
            ~completa,
            rx.badge("incompleta", color_scheme="orange", variant="soft", size="1"),
        ),
        rx.button(
            rx.icon("rotate-ccw", size=13), "Restaurar",
            on_click=BackupsState.pedir_confirmacion(copia["id"].to(str)),
            size="1", variant="surface", color_scheme="gray", flex_shrink="0",
        ),
        align="center",
        spacing="3",
        width="100%",
        padding="9px 11px",
        border_radius="9px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
    )


def _confirmacion() -> rx.Component:
    """Restaurar pisa el armado, los sensores, los grupos, las tarjetas y las
    reglas de golpe. El diálogo dice exactamente eso — y que lo de ahora no se
    pierde, porque se guarda antes."""
    copia = BackupsState.copia_confirmada
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("triangle-alert", size=19, color=theme.WARNING, flex_shrink="0"),
                    rx.text("Restaurar esta copia", size="4", weight="bold", color=theme.TEXT),
                    spacing="3", align="center",
                ),
                rx.text(
                    "Se va a devolver la casa al estado del " + copia["fecha_texto"].to(str) + ".",
                    size="2", color=theme.TEXT,
                ),
                rx.vstack(
                    rx.text(
                        "Se sustituyen el armado, los sensores y nodos, los grupos, las "
                        "tarjetas de acceso, las automatizaciones y el registro de eventos.",
                        size="1", color=theme.MUTED,
                    ),
                    rx.text(
                        "Si la copia se hizo con el sistema armado, la casa quedará armada.",
                        size="1", color=theme.WARNING,
                    ),
                    rx.text(
                        "Antes de tocar nada se guarda una copia con lo que hay ahora "
                        "mismo, por si te has equivocado de copia.",
                        size="1", color=theme.MUTED,
                    ),
                    spacing="2", align="start", width="100%",
                    padding="12px", border_radius="10px",
                    background=theme.alpha(theme.WARNING, 0.07),
                    border=f"1px solid {theme.alpha(theme.WARNING, 0.3)}",
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button("Cancelar", on_click=BackupsState.cancelar_confirmacion,
                              size="2", variant="soft", color_scheme="gray"),
                    rx.button(
                        rx.icon("rotate-ccw", size=14), "Restaurar",
                        on_click=BackupsState.restaurar_confirmada,
                        size="2", color_scheme="orange",
                    ),
                    spacing="2", width="100%",
                ),
                spacing="4", width="100%",
            ),
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.BORDER_STRONG}",
            max_width="460px",
        ),
        open=BackupsState.confirmando != "",
        on_open_change=BackupsState.confirmacion_open_change,
    )


def _copias() -> rx.Component:
    return _bloque(
        "hard-drive-download",
        "Copias de seguridad",
        "Los ficheros que son la casa —armado, sensores, grupos, tarjetas, "
        f"automatizaciones y registro— se copian solos cada día. Se guardan las "
        f"últimas {MAX_COPIAS}.",
        cuerpo=rx.vstack(
            rx.cond(
                BackupsState.mensaje != "",
                rx.hstack(
                    rx.icon(
                        rx.cond(BackupsState.error, "circle-x", "circle-check"),
                        size=15,
                        color=rx.cond(BackupsState.error, theme.DANGER, theme.SUCCESS),
                        flex_shrink="0",
                    ),
                    rx.text(BackupsState.mensaje, size="1", color=theme.TEXT),
                    align="center", spacing="2", width="100%",
                    padding="10px 12px", border_radius="9px",
                    background=rx.cond(
                        BackupsState.error,
                        theme.alpha(theme.DANGER, 0.08),
                        theme.alpha(theme.SUCCESS, 0.08),
                    ),
                ),
            ),
            rx.cond(
                BackupsState.hay_copias,
                rx.vstack(
                    rx.foreach(BackupsState.copias, _fila_copia),
                    spacing="2", width="100%",
                ),
                rx.text(
                    "Todavía no hay ninguna copia. Se hará una sola al arrancar el "
                    "panel, o puedes hacerla ahora.",
                    size="1", color=theme.MUTED, italic=True,
                ),
            ),
            spacing="3", width="100%",
        ),
        accion=rx.button(
            rx.icon("plus", size=14), "Copiar ahora",
            on_click=BackupsState.crear_ahora,
            loading=BackupsState.trabajando,
            size="2", variant="surface", color_scheme="blue", flex_shrink="0",
        ),
    )


_COLOR_ESTADO = {salud.BIEN: theme.SUCCESS, salud.AVISO: theme.WARNING,
                 salud.MAL: theme.DANGER}
_ICONO_ESTADO = {salud.BIEN: "circle-check", salud.AVISO: "triangle-alert",
                 salud.MAL: "circle-x"}


def _pieza(p: rx.Var) -> rx.Component:
    """Una pieza del sistema: su estado, el dato concreto y por que importa.

    El "por que" no es relleno: un semaforo rojo junto a "Motor de
    automatizaciones" no le dice nada a quien no sepa que es el motor, y esta
    pantalla se mira justo cuando algo va mal y no se sabe por donde empezar."""
    color = rx.match(p["estado"].to(str),
                     *[(k, v) for k, v in _COLOR_ESTADO.items()], theme.MUTED)
    return rx.hstack(
        rx.icon(
            rx.match(p["estado"].to(str),
                     *[(k, v) for k, v in _ICONO_ESTADO.items()], "circle"),
            size=18, color=color, flex_shrink="0",
        ),
        rx.vstack(
            rx.hstack(
                rx.icon(p["icono"].to(str), size=13, color=theme.MUTED),
                rx.text(p["nombre"], size="2", weight="bold", color=theme.TEXT),
                spacing="2", align="center",
            ),
            rx.text(p["detalle"], size="1", color=color,
                    style={"font-family": theme.FONT_MONO}),
            rx.text(p["porque"], size="1", color=theme.MUTED,
                    style={"font-size": "0.68rem", "line-height": "1.4"}),
            spacing="0", align="start", min_width="0",
        ),
        align="start", spacing="3", width="100%",
        padding="10px 12px", border_radius="10px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
    )


def _salud() -> rx.Component:
    return _bloque(
        "activity", "Salud del sistema",
        "De que depende que la casa funcione, y si ahora mismo esta en pie.",
        rx.vstack(
            rx.hstack(
                rx.badge(SaludState.resumen, size="2",
                         color_scheme=rx.cond(SaludState.hay_problemas,
                                              "orange", "green")),
                rx.cond(
                    SaludState.cuando != "",
                    rx.text("Comprobado a las " + SaludState.cuando, size="1",
                            color=theme.MUTED),
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    rx.cond(SaludState.comprobando, "Comprobando...", "Comprobar"),
                    on_click=SaludState.comprobar, size="2", variant="surface",
                    loading=SaludState.comprobando,
                ),
                align="center", spacing="3", width="100%", wrap="wrap",
            ),
            rx.foreach(SaludState.piezas, _pieza),
            spacing="2", width="100%",
        ),
    )


def system_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Sistema", size="5", color=theme.TEXT),
            rx.text(
                "El estado del propio panel: de lo que depende que todo lo demás "
                "siga funcionando.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),
        _salud(),
        _copias(),
        _confirmacion(),
        spacing="5",
        width="100%",
        align="start",
        max_width="720px",
        padding_bottom="6",
        # Se comprueba al abrir la pantalla: quien entra aqui viene a ver como
        # esta el sistema, no a pulsar un boton para averiguarlo.
        on_mount=SaludState.on_load,
    )
