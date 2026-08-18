"""
Vista "Plano": el plano de planta a tamaño completo, reutilizando
floor_plan_content() de ui/views/device_list.py tal cual (mismo componente
que ya usa el popover compacto de la vista clásica).

Lo único que añade esta vista es el botón de modo edición: por defecto el
plano es de solo lectura (cada marcador ejecuta su acción al pulsarlo) y solo
con "Recolocar iconos" activo se pueden arrastrar — así nadie mueve un icono
sin querer mientras usa el plano.
"""
import reflex as rx

from ....domains.nodes.state import NodesState
from ...views.device_list import (
    floor_plan_content, PLAN_COMMIT_SCRIPT, PLAN_RESET_SCRIPT, FLOOR_COLORS,
)
from .. import theme
from ..state import DashboardState
from ..components.floor_fields import FLOOR_ICON_OPTIONS
from ..components.icon_picker import icon_grid
from ..components.actions_menu import confirm_delete_dialog

_LEGEND = [
    ("triangle-alert", theme.DANGER, "En alarma: abierto — rojo parpadeando"),
    ("circle-dot", FLOOR_COLORS[""], "En reposo: el color que le pongas a cada uno"),
    ("lightbulb", theme.WARNING, "Luz encendida / puerta abriéndose"),
]


def _legend_item(icon: str, color: str, label: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=14, color=color),
        rx.text(label, size="1", color=theme.MUTED),
        spacing="2",
        align="center",
    )


def _color_swatch(clave: str, color: str, ref, activo: bool = False) -> rx.Component:
    """Una pastilla de color. `activo` decide si pinta el color de reposo o el
    de cuando el elemento está encendido/abierto: los dos se eligen igual y por
    separado para cada marcador."""
    return rx.popover.close(
        rx.box(
            width="18px", height="18px", border_radius="50%",
            background=color, cursor="pointer",
            border=f"1px solid {theme.BORDER_STRONG}",
            on_click=(NodesState.set_floor_color_on(ref, clave) if activo
                      else NodesState.set_floor_color(ref, clave)),
            title=clave or "por defecto",
        ),
    )


def _color_picker(entry: dict) -> rx.Component:
    """Color del marcador EN REPOSO — el mismo criterio para las cuatro
    familias: sensor o puerta cerrada, luz apagada, cámara siempre (no tiene
    estado). Lo que el sistema sigue poniendo por su cuenta es el rojo
    parpadeante de alarma (abierto) y el ámbar de "luz encendida / puerta
    abriéndose": eso no se puede cambiar desde aquí a propósito, para que
    ningún ajuste estético pueda esconder un aviso. Ver device_list.py."""
    ref = entry["ref"].to(str)
    return rx.popover.root(
        rx.popover.trigger(
            rx.box(
                width="18px", height="18px", border_radius="50%",
                background=rx.match(
                    entry["color"].to(str),
                    *[(k, v) for k, v in FLOOR_COLORS.items() if k],
                    FLOOR_COLORS[""],
                ),
                border=f"1px solid {theme.BORDER_STRONG}",
                cursor="pointer", flex_shrink="0",
                title="Color del marcador",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.text("EN REPOSO", size="1", color=theme.MUTED, weight="bold",
                        letter_spacing="0.08em"),
                rx.hstack(
                    *[_color_swatch(k, v, ref) for k, v in FLOOR_COLORS.items() if k],
                    spacing="2",
                ),
                # El de estar activo: encendido si es una luz o un accesorio,
                # abierto o disparado si es un sensor o una puerta. Se elige
                # aparte porque en un plano lleno el color es lo único que
                # distingue un marcador de otro de un vistazo.
                rx.text("ENCENDIDO / ABIERTO", size="1", color=theme.MUTED,
                        weight="bold", letter_spacing="0.08em"),
                rx.hstack(
                    *[_color_swatch(k, v, ref, activo=True)
                      for k, v in FLOOR_COLORS.items() if k],
                    spacing="2",
                ),
                rx.text("El parpadeo de alarma no se quita: el color cambia, "
                        "el aviso se sigue viendo.", size="1", color=theme.MUTED),
                spacing="2", align="start",
            ),
            side="bottom", align="end",
            style={
                "padding": "10px", "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}", "border_radius": "10px",
            },
        ),
    )


def _nombre_recortable(entry: dict, color: str) -> rx.Component:
    """El nombre del elemento, y es LO ÚNICO que se recorta.

    El problema que arregla: la fila es un hstack y este texto no tenía freno, así
    que un nombre largo empujaba los iconos de la derecha fuera del contenedor y
    el contenedor los recortaba. En el móvil eso significaba perder el selector de
    icono, el color y el botón de quitar — funciones enteras desaparecidas por un
    nombre largo.

    Ahora el texto es el único que puede encogerse (flex + min_width 0 +
    ellipsis) y todo lo demás lleva flex_shrink 0, así que cada columna conserva
    su sitio. Y como recortar texto es esconder información, al pulsarlo se abre
    con el nombre completo: en el móvil no hay «pasar el ratón por encima»."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.text(
                entry["label"], size="2", color=color,
                white_space="nowrap", overflow="hidden", text_overflow="ellipsis",
                min_width="0", flex="1", cursor="pointer",
                title="Pulsa para ver el nombre completo",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.text(entry["label"], size="2", weight="bold", color=theme.TEXT),
                rx.badge(entry["kind_label"], size="1", variant="soft"),
                spacing="1", align="start",
            ),
            side="bottom", align="start",
            style={"padding": "10px", "background": theme.BG_WINDOW,
                   "border": f"1px solid {theme.BORDER_STRONG}",
                   "border_radius": "10px", "max_width": "min(280px, 86vw)"},
        ),
    )


def _placed_row(entry: dict) -> rx.Component:
    """Un elemento ya puesto en el plano: se le puede cambiar el icono al
    vuelo o quitarlo (quitarlo NO borra el elemento, solo deja de pintarse)."""
    return rx.hstack(
        rx.icon(entry["icon"].to(str), size=15, color=theme.ACCENT, flex_shrink="0"),
        _nombre_recortable(entry, theme.TEXT),
        # La familia («Sensor», «Luz») es lo primero que sobra en una pantalla
        # estrecha: se sabe por el icono, y está en el desplegable del nombre.
        rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray",
                 flex_shrink="0", display=["none", "none", "inline-flex"]),
        rx.box(
            icon_grid(
                entry["icon"].to(str),
                lambda icon: NodesState.set_floor_icon(entry["ref"].to(str), icon),
                FLOOR_ICON_OPTIONS,
            ),
            width="90px",
            flex_shrink="0",
        ),
        _color_picker(entry),
        # Integrado: en reposo se pinta solo el icono con un brillo suave, sin
        # aro ni fondo, como un piloto del propio aparato. Al abrirse/dispararse
        # recupera el aspecto llamativo — ver _quiet() en device_list.py.
        rx.icon(
            rx.cond(entry["subtle"], "sparkles", "circle"),
            size=15,
            color=rx.cond(entry["subtle"], theme.ACCENT, theme.MUTED),
            cursor="pointer", flex_shrink="0",
            on_click=NodesState.toggle_floor_subtle(entry["ref"].to(str)),
            title=rx.cond(entry["subtle"], "Integrado en el plano", "Integrar en el plano"),
        ),
        # Copiar a otro plano, en el mismo sitio. Solo sale si hay otro plano al
        # que copiar: un menú con una sola opción imposible es peor que no tener
        # el botón.
        rx.cond(
            NodesState.hay_varios_planos,
            rx.menu.root(
                rx.menu.trigger(
                    rx.icon("copy", size=15, color=theme.MUTED, cursor="pointer",
                            flex_shrink="0", title="Copiar a otro plano"),
                ),
                rx.menu.content(
                    rx.foreach(
                        NodesState.otros_planos,
                        lambda p: rx.menu.item(
                            p["nombre"],
                            on_click=NodesState.duplicar_a_plano(
                                entry["ref"].to(str), p["id"]),
                        ),
                    ),
                ),
            ),
        ),
        # Con confirmación: en el móvil este icono está a un dedo de los otros
        # cuatro, y quitar un elemento del plano obliga a volver a colocarlo y a
        # recolocar su icono y su color.
        confirm_delete_dialog(
            rx.icon("x", size=15, color=theme.DANGER, cursor="pointer",
                    flex_shrink="0", title="Quitar de este plano"),
            title="¿Quitar del plano?",
            tipo="del plano el elemento",
            nombre=entry["label"],
            on_confirm=NodesState.remove_from_floor(entry["ref"].to(str)),
            extra="El elemento no se borra: deja de pintarse en ESTE plano y "
                  "sigue en los demás donde esté.",
        ),
        spacing="2",
        align="center",
        width="100%",
        min_width="0",
        padding="7px 10px",
        border_radius="8px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
    )


def _available_row(entry: dict) -> rx.Component:
    """Un elemento que todavía no está en ESTE plano — al pulsarlo aparece en el
    centro, listo para arrastrarlo donde toque.

    Si ya está colocado en otro plano, se ofrece además traerlo DE ALLÍ: llega
    con la posición que tenía. Es lo que hace llevadero tener un plano general y
    otros por habitaciones, o el mismo contacto magnético en dos estancias que
    comparten puerta — el sitio suele ser parecido, así que copiarlo deja el
    icono a un empujón en vez de haber que buscarlo otra vez."""
    return rx.hstack(
        rx.icon(entry["icon"].to(str), size=15, color=theme.MUTED, flex_shrink="0"),
        _nombre_recortable(entry, theme.TEXT),
        rx.cond(
            entry["origen"] != "",
            rx.badge("ya en " + entry["origen_nombre"].to(str), size="1",
                     variant="surface", color_scheme="blue", flex_shrink="0"),
        ),
        rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray",
                 flex_shrink="0", display=["none", "none", "inline-flex"]),
        # Dos formas de traerlo, y la de la izquierda solo aparece si tiene
        # sentido: «Copiar de aquel plano» conserva la posición, «+» lo pone en
        # el centro. Van como botones y NO como clic en toda la fila para que se
        # pueda elegir: con la fila entera pulsable, una de las dos ganaría
        # siempre y la otra sería inalcanzable.
        rx.cond(
            entry["origen"] != "",
            rx.button(
                rx.icon("copy", size=13), "Copiar de ahí",
                on_click=NodesState.duplicar_desde_plano(
                    entry["ref"].to(str), entry["origen"].to(str)
                ).stop_propagation,
                size="1", variant="surface", flex_shrink="0",
                title="Traerlo con la misma posición que tiene en el otro plano",
            ),
        ),
        rx.icon("plus", size=15, color=theme.SUCCESS, flex_shrink="0",
                cursor="pointer",
                on_click=NodesState.add_to_floor(entry["ref"].to(str)).stop_propagation,
                title="Ponerlo en el centro de este plano"),
        spacing="2",
        align="center",
        width="100%",
        min_width="0",
        padding="7px 10px",
        border_radius="8px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )


def _available_section(section: dict) -> rx.Component:
    """Un bloque por tipo (Sensores, Cámaras, Puertas, Luces) con lo que queda
    por colocar de esa familia — ver NodesState.floor_available_grouped.

    El .to(list[dict]) es obligatorio: el valor de una clave de dict llega sin
    tipo y rx.foreach no puede recorrerlo sin saber qué es."""
    items = section["items"].to(list[dict])
    return rx.vstack(
        rx.hstack(
            rx.text(
                section["kind_label"], size="1", color=theme.TEXT,
                weight="bold", letter_spacing="0.04em",
            ),
            rx.badge(items.length(), variant="soft", size="1", color_scheme="gray"),
            spacing="2",
            align="center",
        ),
        rx.foreach(items, _available_row),
        spacing="1",
        width="100%",
        align="start",
    )


def _editor_panel() -> rx.Component:
    return rx.vstack(
        rx.text("EN EL PLANO", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
        rx.cond(
            NodesState.floor_placed.length() > 0,
            rx.vstack(rx.foreach(NodesState.floor_placed, _placed_row), spacing="2", width="100%"),
            rx.text("Todavía no hay nada en el plano.", size="1", color=theme.MUTED, italic=True),
        ),
        rx.divider(opacity="0.1", margin_y="2"),
        rx.text("AÑADIR AL PLANO", size="1", color=theme.MUTED, letter_spacing="0.08em", weight="bold"),
        rx.cond(
            NodesState.floor_available.length() > 0,
            rx.vstack(
                rx.foreach(NodesState.floor_available_grouped, _available_section),
                spacing="3", width="100%",
            ),
            rx.text("Ya está todo el sistema en el plano.", size="1", color=theme.MUTED, italic=True),
        ),
        spacing="2",
        width="100%",
        max_width="720px",
        padding="14px",
        border_radius="12px",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER_STRONG}",
    )


def _pestana_plano(p: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.text(p["nombre"], size="1", weight="medium",
                color=rx.cond(p["activo"], theme.TEXT, theme.MUTED)),
        # Cuántos elementos tiene, para saber de un vistazo cuál está sin montar.
        rx.text(p["elementos"], size="1", color=theme.MUTED,
                style={"font-size": "0.65rem", "opacity": "0.8"}),
        rx.cond(
            p["principal"] != "",
            rx.icon("star", size=11, color=theme.WARNING),
        ),
        on_click=NodesState.ver_plano(p["id"]),
        cursor="pointer", spacing="2", align="center", flex_shrink="0",
        padding="6px 10px", border_radius="9px",
        background=rx.cond(p["activo"], theme.alpha(theme.ACCENT, 0.12),
                           theme.BG_CARD),
        border=rx.cond(p["activo"], f"1px solid {theme.alpha(theme.ACCENT, 0.55)}",
                       f"1px solid {theme.BORDER}"),
    )


def _pestanas_planos() -> rx.Component:
    """La fila para saltar de un plano a otro, arriba del plano y SIEMPRE que
    haya más de uno — también sin modo edición.

    Es el selector principal de la pantalla: si solo saliera al editar, tener dos
    plantas no serviría de nada para el uso normal, que es justo mirar una y
    luego la otra. Con un plano único sigue escondido, que una fila de pestañas
    con una sola pestaña es ruido."""
    return rx.cond(
        NodesState.hay_varios_planos | DashboardState.editing_floor_plan,
        rx.box(
            rx.hstack(
                rx.foreach(NodesState.planos_ui, _pestana_plano),
                spacing="2", align="center",
            ),
            width="100%", max_width="720px",
            overflow_x="auto", padding_bottom="4px",
        ),
    )


def _gestion_planos() -> rx.Component:
    """Subir, renombrar, marcar principal y quitar. Solo con el modo edición.

    El principal es el que se abre al entrar y el que ve la vista clásica, así
    que se marca con una estrella y no se puede quedar sin marcar ninguno."""
    return rx.cond(
        DashboardState.editing_floor_plan,
        rx.vstack(
            rx.text("PLANOS", size="1", color=theme.MUTED, weight="bold",
                    letter_spacing="0.08em"),
            rx.foreach(
                NodesState.planos_ui,
                lambda p: rx.hstack(
                    rx.input(
                        default_value=p["nombre"],
                        on_blur=lambda v: NodesState.renombrar_plano(p["id"], v),
                        size="1", width="160px",
                    ),
                    rx.badge(p["elementos_texto"], size="1", variant="surface"),
                    rx.spacer(),
                    rx.cond(
                        p["principal"] != "",
                        rx.badge("Principal", size="1", color_scheme="orange"),
                        rx.button("Hacer principal", size="1", variant="surface",
                                  on_click=NodesState.marcar_plano_principal(p["id"])),
                    ),
                    # Borrar un plano NO se puede deshacer: se va su imagen y
                    # las posiciones de todo lo que tuviera colocado. Confirmación
                    # obligatoria, y con el número de elementos delante para que
                    # se vea lo que se está tirando.
                    confirm_delete_dialog(
                        rx.icon_button(
                            rx.icon("trash-2", size=13), size="1",
                            variant="surface", color_scheme="red",
                            title="Quitar el plano",
                        ),
                        title="¿Quitar este plano?",
                        tipo="el plano",
                        nombre=p["nombre"],
                        on_confirm=NodesState.borrar_plano(p["id"]),
                        extra="Se borra su imagen y la posición de sus "
                              "elementos. Los elementos siguen existiendo y en "
                              "los demás planos donde estén.",
                    ),
                    align="center", spacing="2", width="100%",
                    padding="7px 10px", border_radius="8px",
                    background=theme.BG_CARD,
                    border=f"1px solid {theme.BORDER}",
                ),
            ),
            rx.upload(
                rx.vstack(
                    rx.icon("image-plus", size=18, color=theme.MUTED),
                    rx.text("Arrastra una imagen o pulsa para elegirla",
                            size="1", color=theme.MUTED),
                    rx.text("PNG, JPG o WebP. El nombre del fichero será el "
                            "nombre del plano.",
                            size="1", color=theme.MUTED,
                            style={"font-size": "0.65rem"}),
                    spacing="1", align="center",
                ),
                id="plano_upload",
                # Un solo tipo con comodín en vez de tres entradas por formato.
                # Con el diccionario detallado, el selector del móvil y el de
                # Windows rechazaban ficheros perfectamente válidos y el
                # resultado era mudo: se volvía a abrir la carpeta y no pasaba
                # nada, sin un solo error ni en pantalla ni en el log.
                accept={"image/*": [".png", ".jpg", ".jpeg", ".webp"]},
                max_files=1,
                # SIN on_drop a propósito: la subida la lanza el botón de abajo.
                # Con las dos vías, un navegador donde on_drop sí dispare subiría
                # el plano dos veces y aparecerían dos plantas iguales.
                #
                # Lo que sí se escucha es el rechazo: si el navegador no acepta el
                # fichero, que lo DIGA. Un rechazo silencioso es lo que hace que
                # parezca que la aplicación está rota.
                on_drop_rejected=NodesState.plano_rechazado,
                border=f"1px dashed {theme.BORDER_STRONG}",
                border_radius="10px", padding="14px", width="100%",
            ),
            # El botón explícito, que es el patrón que de verdad funciona en esta
            # versión de Reflex. Con solo `on_drop` la subida no llegaba nunca al
            # servidor: no salía ni error ni nada, el selector se volvía a abrir
            # y el plano no aparecía. Comprobado en el log — el manejador no se
            # ejecutaba, así que el problema estaba antes, en el navegador.
            #
            # Además así se VE lo que se ha elegido antes de subirlo, que con un
            # fichero de 12 MB no es un detalle.
            rx.cond(
                rx.selected_files("plano_upload").length() > 0,
                rx.hstack(
                    rx.icon("image", size=14, color=theme.ACCENT),
                    rx.text(rx.selected_files("plano_upload").join(", "),
                            size="1", color=theme.TEXT),
                    rx.spacer(),
                    rx.button(
                        rx.icon("upload", size=14), "Subir plano",
                        on_click=NodesState.subir_plano(
                            rx.upload_files(upload_id="plano_upload")),
                        size="2",
                    ),
                    rx.button(
                        "Quitar", on_click=rx.clear_selected_files("plano_upload"),
                        size="2", variant="surface",
                    ),
                    align="center", spacing="2", width="100%", wrap="wrap",
                ),
            ),
            spacing="2", width="100%", max_width="720px",
        ),
    )


def floor_plan_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.cond(
                DashboardState.editing_floor_plan,
                rx.hstack(
                    rx.icon("move", size=15, color=theme.WARNING),
                    rx.text(
                        'Arrastra los iconos y pulsa "Listo" para guardar',
                        size="2", color=theme.WARNING, weight="medium",
                    ),
                    spacing="2", align="center",
                ),
                rx.fragment(),
            ),
            rx.spacer(),
            rx.cond(
                DashboardState.editing_floor_plan,
                rx.button(
                    rx.icon("check", size=14), "Listo",
                    # Aquí es donde se GRABA: el script devuelve todas las
                    # posiciones movidas y save_floor_positions las escribe de
                    # una vez. Antes cada suelta guardaba por su cuenta.
                    on_click=[
                        rx.call_script(
                            PLAN_COMMIT_SCRIPT,
                            callback=NodesState.save_floor_positions,
                        ),
                        DashboardState.toggle_editing_floor_plan,
                    ],
                    size="1", variant="solid", color_scheme="green",
                ),
                # Discreto a propósito: el plano se usa mucho más de lo que se
                # edita, así que el botón se mantiene tenue hasta pasar por
                # encima (mismo criterio que el enlace al panel en la clásica).
                rx.hstack(
                    rx.icon("pencil", size=13, color=theme.MUTED),
                    rx.text("Editar plano", size="1", color=theme.MUTED),
                    on_click=[
                        rx.call_script(PLAN_RESET_SCRIPT),
                        DashboardState.toggle_editing_floor_plan,
                    ],
                    cursor="pointer",
                    spacing="1",
                    align="center",
                    padding="5px 9px",
                    border_radius="8px",
                    opacity="0.55",
                    transition="opacity 0.15s ease, background 0.15s ease",
                    _hover={"opacity": "1", "background": theme.BG_CARD},
                ),
            ),
            width="100%",
            max_width="720px",
            align="center",
            wrap="wrap",
        ),
        _pestanas_planos(),
        rx.box(
            floor_plan_content(),
            width="100%",
            max_width="720px",
        ),
        rx.cond(DashboardState.editing_floor_plan, _editor_panel(), rx.fragment()),
        _gestion_planos(),
        rx.hstack(
            *[_legend_item(icon, color, label) for icon, color, label in _LEGEND],
            spacing="4",
            wrap="wrap",
            padding_top="2",
        ),
        spacing="4",
        width="100%",
        align="center",
    )
