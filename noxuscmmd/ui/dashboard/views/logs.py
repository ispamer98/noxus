"""
Vista "Registros": el histórico de todo lo que pasa en la casa.

La idea es que se lea de un vistazo, sin tener que ir frase por frase: cada
evento entra por el icono y el color, y el texto solo confirma lo que el icono
ya ha dicho. Una puerta que se abre es un icono de puerta abierta en ámbar; la
misma puerta cerrándose, el de puerta cerrada en verde. Una luz sale con el
icono y el color que ella tiene en el plano, y un equipo que se cae, con el
suyo en gris. Quién decide todo eso es LogsState._aspecto — aquí solo se
traduce la clave de color a un color de verdad.

Las pestañas de familia son de selección MÚLTIPLE: se pueden marcar varias a
la vez (p.ej. "Alarma" + "Luces") y ver solo esa mezcla. "Todo" es
independiente de las demás — marcarlo vacía cualquier selección en vez de
sumarse a ella (ver LogsState.ver_pestana).
"""
import reflex as rx

from ....domains.security.logs_state import LogsState, VENTANA
from .. import theme

# Traducción de la clave de color que trae cada fila. Hay dos familias de
# claves y conviven a propósito: las semánticas (qué ha pasado) y las del
# plano (de qué color lo pintó el usuario ahí), porque un evento de una luz o
# de una puerta debe salir con SU color y no con uno de sistema.
_COLORES = {
    # Semánticas
    "ok": theme.SUCCESS,
    "peligro": theme.DANGER,
    "aviso": theme.WARNING,
    "info": theme.ACCENT,
    "neutro": theme.MUTED,
    "armado_total": theme.DANGER,
    "armado_parcial": theme.WARNING,
    # Del plano (mismos nombres que el selector de color de los marcadores)
    "claro": "#cbd5e1", "verde": theme.SUCCESS, "azul": theme.ACCENT,
    "morado": theme.PURPLE, "ambar": "#f59e0b", "cian": "#22d3ee", "gris": "#64748b",
    # Por familia, cuando no hay nada más específico
    "alarma": theme.DANGER, "grupos": theme.PURPLE, "puertas": theme.WARNING,
    "luces": theme.WARNING, "sensores": theme.ACCENT, "cctv": theme.PURPLE,
    "accesos": theme.SUCCESS, "equipos": theme.ACCENT, "sistema": theme.MUTED,
}


def color_de(clave) -> rx.Var:
    """Traduce la clave de color de una fila (LogsState._aspecto) a un color de
    verdad. rx.match y no un dict porque dentro de un rx.foreach la clave es
    una Var, no un str de Python. Público — lo reutiliza el widget "Último
    evento" del Resumen, para que un aviso se vea con el mismo color aquí y
    allí."""
    return rx.match(clave, *[(k, v) for k, v in _COLORES.items()], theme.MUTED)


def bg_de(clave, opacidad: float = 0.14) -> rx.Var:
    """Como color_de, pero para el fondo translúcido del icono en vez del
    icono en sí — misma tabla, cada rama envuelta en theme.alpha() al
    construirla. alpha() opera sobre un str de Python, así que la conversión
    tiene que pasar rama a rama y no una vez sobre el resultado del match:
    para cuando color_de ya ha elegido, lo elegido es un Var y alpha() ya no
    lo puede tocar."""
    return rx.match(
        clave, *[(k, theme.alpha(v, opacidad)) for k, v in _COLORES.items()],
        theme.alpha(theme.MUTED, opacidad),
    )


def _pestana(p) -> rx.Component:
    activa = p["activa"]
    return rx.hstack(
        rx.icon(p["icon"].to(str), size=14,
                color=rx.cond(activa, theme.ACCENT, theme.MUTED), flex_shrink="0"),
        rx.text(p["label"], size="1",
                weight=rx.cond(activa, "bold", "medium"),
                color=rx.cond(activa, theme.TEXT, theme.MUTED),
                white_space="nowrap"),
        rx.text(p["conteo"], size="1", color=theme.MUTED, white_space="nowrap"),
        on_click=LogsState.ver_pestana(p["id"]),
        cursor="pointer",
        align="center",
        spacing="2",
        padding="7px 12px",
        border_radius="9px",
        flex_shrink="0",
        background=rx.cond(activa, theme.alpha(theme.ACCENT, 0.12), "transparent"),
        border=f"1px solid {rx.cond(activa, theme.ACCENT, theme.BORDER)}",
        _hover={"background": theme.alpha(theme.ACCENT, 0.06)},
    )


def _rango(r) -> rx.Component:
    activa = r["activa"]
    return rx.text(
        r["label"], size="1",
        weight=rx.cond(activa, "bold", "regular"),
        color=rx.cond(activa, theme.TEXT, theme.MUTED),
        on_click=LogsState.set_rango(r["id"]),
        cursor="pointer",
        padding="5px 10px",
        border_radius="7px",
        white_space="nowrap",
        background=rx.cond(activa, theme.alpha(theme.ACCENT, 0.12), "transparent"),
        border=f"1px solid {rx.cond(activa, theme.ACCENT, 'transparent')}",
    )


def _intervalo() -> rx.Component:
    """Calendario: un intervalo exacto, con fecha Y hora en los dos extremos.

    Es lo que hace falta cuando ya sabes lo que buscas ("el martes entre las
    tres y las cuatro"), que es justo cuando los atajos de al lado no valen: el
    de 7 días te trae siete días para encontrar un minuto.

    Se puede rellenar solo un extremo — "desde el martes" sin tope, o "hasta
    ayer" sin principio — y el botón lo dice para que no parezca que no filtra
    nada."""
    activo = LogsState.intervalo_activo
    return rx.popover.root(
        rx.popover.trigger(
            rx.hstack(
                rx.icon("calendar-range", size=14,
                        color=rx.cond(activo, theme.ACCENT, theme.MUTED), flex_shrink="0"),
                rx.text(LogsState.etiqueta_intervalo, size="1",
                        weight=rx.cond(activo, "bold", "regular"),
                        color=rx.cond(activo, theme.TEXT, theme.MUTED),
                        white_space="nowrap"),
                spacing="1", align="center", cursor="pointer",
                padding="5px 10px", border_radius="7px", flex_shrink="0",
                background=rx.cond(activo, theme.alpha(theme.ACCENT, 0.12), "transparent"),
                border=f"1px solid {rx.cond(activo, theme.ACCENT, 'transparent')}",
                _hover={"background": theme.alpha(theme.ACCENT, 0.06)},
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.text("Ver eventos entre", size="1", color=theme.MUTED,
                        letter_spacing="0.05em", weight="bold"),
                rx.vstack(
                    rx.text("Desde", size="1", color=theme.MUTED),
                    rx.input(type="datetime-local", value=LogsState.desde,
                             on_change=LogsState.set_desde, size="2", width="100%"),
                    spacing="1", width="100%",
                ),
                rx.vstack(
                    rx.text("Hasta", size="1", color=theme.MUTED),
                    rx.input(type="datetime-local", value=LogsState.hasta,
                             on_change=LogsState.set_hasta, size="2", width="100%"),
                    spacing="1", width="100%",
                ),
                rx.button(
                    rx.icon("eraser", size=13), "Quitar el intervalo",
                    on_click=LogsState.limpiar_intervalo,
                    size="1", variant="soft", color_scheme="gray", width="100%",
                ),
                spacing="3", width="100%",
            ),
            background=theme.BG_WINDOW,
            border=f"1px solid {theme.BORDER_STRONG}",
            border_radius="12px",
            padding="14px",
            width="min(280px, 88vw)",
        ),
    )


def _controles() -> rx.Component:
    return rx.vstack(
        # La tira de pestañas se desplaza en horizontal en vez de partirse en
        # varias líneas: en móvil, diez familias apiladas empujaban la lista de
        # eventos fuera de la pantalla.
        rx.box(
            rx.hstack(
                rx.foreach(LogsState.pestanas, _pestana),
                spacing="2", width="max-content",
            ),
            width="100%", overflow_x="auto", padding_bottom="4px",
        ),
        rx.flex(
            rx.hstack(
                _intervalo(),
                rx.foreach(LogsState.rangos_ui, _rango),
                spacing="1", align="center", flex_shrink="0",
            ),
            rx.input(
                rx.input.slot(rx.icon("search", size=14)),
                placeholder="Buscar...",
                value=LogsState.busqueda,
                on_change=LogsState.set_busqueda,
                size="2", auto_complete=False, flex="1", min_width="160px",
            ),
            rx.button(
                rx.icon("refresh-cw", size=14),
                on_click=LogsState.refrescar, size="2", variant="surface",
                title="Releer ahora", flex_shrink="0",
            ),
            # Exporta lo filtrado, no lo que se ve: el título lo dice para que
            # nadie crea que se lleva solo la página cargada.
            rx.button(
                rx.icon("download", size=14),
                on_click=LogsState.exportar_csv, size="2", variant="surface",
                title="Exportar a CSV lo filtrado", flex_shrink="0",
            ),
            gap="10px", wrap="wrap", align="center", width="100%",
        ),
        spacing="3", width="100%",
    )


def _dato(etiqueta: str, valor, mono: bool = False) -> rx.Component:
    """Una línea del bocadillo. `valor` puede venir vacío, y entonces la línea
    entera desaparece en vez de dejar una etiqueta huérfana."""
    return rx.cond(
        valor != "",
        rx.hstack(
            rx.text(etiqueta, size="1", color=theme.MUTED, width="86px", flex_shrink="0"),
            rx.text(valor, size="1", color=theme.TEXT, white_space="pre-wrap",
                    font_family=theme.FONT_MONO if mono else "inherit"),
            spacing="2", align="start", width="100%",
        ),
    )


def _bocadillo(e, color) -> rx.Component:
    """Todo lo del evento, al pulsar la fila.

    Está aquí y no debajo de la fila porque una fila que crece empuja a las de
    abajo: buscando algo en una lista larga, cada vez que abrías una se te
    movía todo lo demás. El bocadillo flota y no toca la lista.

    Es también el sitio de lo que en el móvil no cabe (el dispositivo, la
    fecha, el detalle entero), y por eso sale siempre, no solo cuando hay texto
    largo: así el gesto es el mismo en cualquier fila y en cualquier pantalla."""
    return rx.popover.content(
        rx.vstack(
            rx.hstack(
                rx.icon(e["icono"].to(str), size=16, color=color, flex_shrink="0"),
                rx.text(e["titulo"], size="2", weight="bold", color=theme.TEXT),
                spacing="2", align="center",
            ),
            rx.divider(border_color=theme.BORDER),
            _dato("Evento", e["tag"]),
            _dato("Detalle", e["extra"]),
            _dato("Zona", e["grupo"]),
            _dato("Desde", e["usuario"]),
            # .to(str) para poder concatenar: el valor de una clave de dict
            # llega sin tipo y el "+" no sabe si es suma o unión de textos.
            _dato("Cuándo", e["fecha"].to(str) + "  " + e["hora"].to(str), mono=True),
            # Lo que vio la cámara en ese instante. Va al final y solo si la hay:
            # es lo más grande del bocadillo, y en la enorme mayoría de eventos
            # (una luz, un armado) no existe. Se abre a tamaño completo en otra
            # pestaña porque aquí caben 300 px y la imagen tiene 2304.
            rx.cond(
                e["foto_url"] != "",
                rx.vstack(
                    rx.divider(border_color=theme.BORDER),
                    rx.hstack(
                        rx.icon("camera", size=13, color=theme.MUTED),
                        rx.text("Lo que vio la cámara", size="1",
                                color=theme.MUTED),
                        spacing="2", align="center",
                    ),
                    rx.link(
                        rx.image(
                            src=e["foto_url"],
                            width="100%", border_radius="8px",
                            border=f"1px solid {theme.BORDER}",
                            loading="lazy",
                        ),
                        href=e["foto_url"], is_external=True, width="100%",
                    ),
                    spacing="2", width="100%",
                ),
            ),
            spacing="2", width="100%",
        ),
        background=theme.BG_WINDOW,
        border=f"1px solid {theme.BORDER_STRONG}",
        border_radius="12px",
        padding="14px",
        max_width="min(340px, 88vw)",
    )


def _separador_dia(e) -> rx.Component:
    """Cabecera del bloque de un día: la fecha entre dos líneas finas.

    Sutil a propósito — en gris y con la línea a media opacidad: sirve para
    situarse al barrer la lista, no para competir con los eventos, que son lo
    que de verdad se está mirando."""
    return rx.hstack(
        rx.box(height="1px", flex="1", background=theme.BORDER),
        rx.text(
            e["fecha_larga"], size="1", color=theme.MUTED, weight="medium",
            letter_spacing="0.06em", white_space="nowrap", flex_shrink="0",
        ),
        rx.box(height="1px", flex="1", background=theme.BORDER),
        spacing="3",
        align="center",
        width="100%",
        # Más aire por arriba que por abajo: así el rótulo se lee pegado a su
        # bloque y separado del día anterior, en vez de flotando entre los dos.
        padding_top="10px",
        padding_bottom="2px",
    )


def _fila(e) -> rx.Component:
    """UNA línea por evento, siempre — también en el móvil.

    Nada de apilar en dos líneas ni de tarjetas altas: un registro se lee
    barriendo la columna de iconos de arriba abajo, y para eso todas las filas
    tienen que medir lo mismo y ser bajas. Lo que no cabe (el dispositivo y la
    fecha en pantallas estrechas, el detalle largo en cualquiera) no se recorta
    a la brava: está a un toque, en el bocadillo.

    El truco para que la línea no se rompa es que el título es el único que
    puede encoger (flex + min_width 0 + ellipsis); lo demás lleva flex_shrink 0
    y conserva su tamaño."""
    color = color_de(e["color"])
    fila = rx.popover.root(
        rx.popover.trigger(
            rx.hstack(
                rx.box(
                    rx.icon(e["icono"].to(str), size=15, color=color),
                    padding="6px",
                    border_radius="8px",
                    background=theme.alpha(theme.ACCENT, 0.07),
                    flex_shrink="0",
                    display="flex",
                ),
                rx.text(
                    e["titulo"], size="2", weight="bold", color=theme.TEXT,
                    white_space="nowrap", overflow="hidden", text_overflow="ellipsis",
                    min_width="0",
                ),
                rx.cond(
                    e["tag"] != "",
                    rx.text(e["tag"], size="1", color=color, weight="medium",
                            white_space="nowrap", flex_shrink="0"),
                ),
                rx.cond(
                    e["grupo"] != "",
                    rx.badge(e["grupo"], size="1", variant="soft",
                             color_scheme="purple", flex_shrink="0"),
                ),
                # Que este evento tiene foto se ve SIN abrirlo: con decenas de
                # aperturas en la lista, tener que abrirlas una a una para
                # descubrir cuál trae imagen haría que no se mirara nunca.
                rx.cond(
                    e["foto_url"] != "",
                    rx.icon("camera", size=13, color=color, flex_shrink="0"),
                ),
                # El detalle solo se asoma cuando hay sitio: en el móvil vive
                # en el bocadillo.
                rx.text(
                    e["extra"], size="1", color=theme.MUTED,
                    white_space="nowrap", overflow="hidden", text_overflow="ellipsis",
                    min_width="0", flex="1",
                    display=["none", "none", "block"],
                ),
                rx.spacer(),
                rx.text(e["usuario"], size="1", color=theme.MUTED, white_space="nowrap",
                        flex_shrink="0", display=["none", "none", "block"]),
                rx.text(e["hora"], size="1", color=theme.TEXT, font_family=theme.FONT_MONO,
                        white_space="nowrap", flex_shrink="0"),
                rx.icon("info", size=13, color=theme.MUTED, flex_shrink="0"),
                spacing="2",
                align="center",
                width="100%",
                padding="7px 10px",
                border_radius="9px",
                border=f"1px solid {theme.BORDER}",
                border_left=f"3px solid {color}",
                background=theme.BG_CARD,
                cursor="pointer",
                _hover={"background": theme.BG_CARD_HOVER},
            ),
        ),
        _bocadillo(e, color),
    )
    # La cabecera del día va DENTRO de la misma celda del foreach que su
    # primera fila: así el bloque no se puede romper ni quedar un rótulo suelto
    # al final de la página cuando se pulsa "Ver más".
    return rx.cond(
        e["nuevo_dia"],
        rx.vstack(_separador_dia(e), fila, spacing="2", width="100%"),
        fila,
    )


def logs_view() -> rx.Component:
    return rx.vstack(
        _controles(),
        rx.text(f"{LogsState.total_filtradas} eventos · más reciente primero",
                size="1", color=theme.MUTED),
        # Solo aparece cuando el intervalo tiene más eventos de los que se han
        # traído (ver LogsState.VENTANA). Sin esto, un "Todo" con años de
        # historia haría creer que antes de esa fecha no pasó nada.
        rx.cond(
            LogsState.recortado,
            rx.hstack(
                rx.icon("info", size=13, color=theme.MUTED),
                rx.text(
                    f"Se están mirando los {VENTANA} eventos más recientes del "
                    f"intervalo. Acota las fechas para ver más atrás, o "
                    f"descarga el CSV, que sí lleva el intervalo completo.",
                    size="1", color=theme.MUTED,
                ),
                spacing="2", align="center", width="100%",
            ),
        ),
        rx.cond(
            LogsState.filtradas.length() > 0,
            rx.vstack(
                rx.foreach(LogsState.filtradas, _fila),
                rx.cond(
                    LogsState.hay_mas,
                    rx.button(
                        rx.icon("chevron-down", size=14), "Ver más",
                        on_click=LogsState.ver_mas, size="2", variant="surface", width="100%",
                    ),
                ),
                spacing="2", width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.icon("file-search", size=28, color=theme.MUTED),
                    rx.text("No hay eventos aquí en el periodo elegido.",
                            size="2", color=theme.MUTED),
                    spacing="3", align="center",
                ),
                padding="40px", width="100%",
            ),
        ),
        spacing="4",
        width="100%",
        max_width="920px",
    )
