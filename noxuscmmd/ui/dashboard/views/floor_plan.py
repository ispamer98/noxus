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
from ....domains.security.state import SecurityState
from ...views.device_list import (
    floor_plan_content, PLAN_COMMIT_SCRIPT, PLAN_RESET_SCRIPT, FLOOR_COLORS,
)
from .. import theme
from ..state import DashboardState
from ....domains.auth.state import AuthState
from ..components.floor_fields import FLOOR_ICON_OPTIONS
from ..components.icon_picker import icon_grid
from ..components.actions_menu import confirm_delete_dialog
from ..components.boton_ajustes import boton_ajustes
from .overview import _quick_action
from ..components.form_dialog import select_content


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
            rx.el.button(
                rx.box(
                    width="18px", height="18px", border_radius="50%",
                    background=rx.match(
                        entry["color"].to(str),
                        *[(k, v) for k, v in FLOOR_COLORS.items() if k],
                        FLOOR_COLORS[""],
                    ),
                    border=f"1px solid {theme.BORDER_STRONG}",
                ),
                type="button", class_name="nx-ed-btn",
                title="Color del marcador", aria_label="Color del marcador",
            ),
        ),
        rx.popover.content(
            rx.vstack(
                rx.text("En reposo", size="1", color=theme.MUTED,
                        weight="bold", class_name="nx-label"),
                rx.hstack(
                    *[_color_swatch(k, v, ref) for k, v in FLOOR_COLORS.items() if k],
                    spacing="2",
                ),
                # El de estar activo: encendido si es una luz o un accesorio,
                # abierto o disparado si es un sensor o una puerta. Se elige
                # aparte porque en un plano lleno el color es lo único que
                # distingue un marcador de otro de un vistazo.
                rx.text("Encendido / abierto", size="1", color=theme.MUTED,
                        class_name="nx-label", weight="bold"),
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
                class_name="nx-ed-nombre",
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


def _boton_ed(icono, titulo, on_click=None, color=theme.MUTED, **props) -> rx.Component:
    """Botón de icono de una fila de edición: 32 px de zona táctil, nativo (teclado)
    y con nombre accesible. El CSS (.nx-ed-btn) fija el tamaño; nada de iconos
    sueltos con on_click, que en el móvil son un blanco de 15 px."""
    return rx.el.button(
        rx.icon(icono, size=15, color=color),
        type="button", class_name="nx-ed-btn", title=titulo, aria_label=titulo,
        on_click=on_click, **props,
    )


def _placed_row(entry: dict) -> rx.Component:
    """Un elemento ya puesto en el plano: se le puede cambiar el icono al
    vuelo o quitarlo (quitarlo NO borra el elemento, solo deja de pintarse).

    Dos zonas dentro de una tarjeta que NUNCA desborda (nx.css, .nx-ed-fila):
    identidad (icono + nombre con elipsis + familia) y controles (icono, color,
    integrado, copiar, quitar). Tarjeta ancha: una línea; estrecha: dos."""
    return rx.el.div(
        rx.el.div(
            rx.icon(entry["icon"].to(str), size=15, color=theme.ACCENT, flex_shrink="0"),
            _nombre_recortable(entry, theme.TEXT),
            # La familia («Sensor», «Luz»): se esconde sola en tarjeta muy
            # estrecha (container query); el nombre completo sigue en el
            # desplegable del nombre.
            rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray",
                     class_name="nx-plano-kind"),
            class_name="nx-ed-id",
        ),
        rx.el.div(
            rx.box(
                icon_grid(
                    entry["icon"].to(str),
                    lambda icon: NodesState.set_floor_icon(entry["ref"].to(str), icon),
                    FLOOR_ICON_OPTIONS,
                ),
                class_name="nx-ed-picker",
            ),
            _color_picker(entry),
            # Integrado: en reposo se pinta solo el icono con un brillo suave, sin
            # aro ni fondo, como un piloto del propio aparato. Al abrirse/dispararse
            # recupera el aspecto llamativo — ver _quiet() en device_list.py.
            _boton_ed(
                rx.cond(entry["subtle"], "sparkles", "circle"),
                rx.cond(entry["subtle"], "Integrado en el plano", "Integrar en el plano"),
                NodesState.toggle_floor_subtle(entry["ref"].to(str)),
                color=rx.cond(entry["subtle"], theme.ACCENT, theme.MUTED),
            ),
            # Copiar a otro plano, en el mismo sitio. Solo sale si hay otro plano al
            # que copiar: un menú con una sola opción imposible es peor que no tener
            # el botón.
            rx.cond(
                NodesState.hay_varios_planos,
                rx.menu.root(
                    rx.menu.trigger(
                        _boton_ed("copy", "Copiar a otro plano"),
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
            # Con confirmación: quitar un elemento del plano obliga a volver a
            # colocarlo y a recolocar su icono y su color. Va aparte, al final
            # de la línea, para no estar a un dedo de los demás.
            confirm_delete_dialog(
                rx.el.button(
                    rx.icon("x", size=15, color=theme.DANGER),
                    type="button", class_name="nx-ed-btn nx-ed-quitar",
                    title="Quitar de este plano", aria_label="Quitar de este plano",
                ),
                title="¿Quitar del plano?",
                tipo="del plano el elemento",
                nombre=entry["label"],
                on_confirm=NodesState.remove_from_floor(entry["ref"].to(str)),
                extra="El elemento no se borra: deja de pintarse en ESTE plano y "
                      "sigue en los demás donde esté.",
            ),
            class_name="nx-ed-ctl",
        ),
        class_name="nx-ed-fila",
    )


def _available_row(entry: dict) -> rx.Component:
    """Un elemento que todavía no está en ESTE plano — al pulsarlo aparece en el
    centro, listo para arrastrarlo donde toque.

    Si ya está colocado en otro plano, se ofrece además traerlo DE ALLÍ: llega
    con la posición que tenía. Es lo que hace llevadero tener un plano general y
    otros por habitaciones, o el mismo contacto magnético en dos estancias que
    comparten puerta — el sitio suele ser parecido, así que copiarlo deja el
    icono a un empujón en vez de haber que buscarlo otra vez.

    Línea 1: icono + nombre + familia + «+» (centro del plano). Línea 2, solo si
    ya está en otro plano: «ya en X» y «Copiar de ahí». Van como botones y NO
    como clic en toda la fila para poder elegir entre las dos formas."""
    return rx.el.div(
        rx.el.div(
            rx.icon(entry["icon"].to(str), size=15, color=theme.MUTED, flex_shrink="0"),
            _nombre_recortable(entry, theme.TEXT),
            rx.badge(entry["kind_label"], variant="soft", size="1", color_scheme="gray",
                     class_name="nx-plano-kind"),
            _boton_ed(
                "plus", "Ponerlo en el centro de este plano",
                NodesState.add_to_floor(entry["ref"].to(str)).stop_propagation,
                color=theme.SUCCESS,
            ),
            class_name="nx-ed-id",
        ),
        rx.cond(
            entry["origen"] != "",
            rx.el.div(
                rx.badge("ya en " + entry["origen_nombre"].to(str), size="1",
                         variant="surface", color_scheme="blue",
                         class_name="nx-ed-origen"),
                rx.button(
                    rx.icon("copy", size=13), "Copiar de ahí",
                    on_click=NodesState.duplicar_desde_plano(
                        entry["ref"].to(str), entry["origen"].to(str)
                    ).stop_propagation,
                    size="1", variant="surface", class_name="nx-ed-copiar",
                    title="Traerlo con la misma posición que tiene en el otro plano",
                ),
                class_name="nx-ed-ctl",
            ),
        ),
        class_name="nx-ed-fila",
    )


def _available_section(section: dict) -> rx.Component:
    """Un bloque por tipo (Sensores, Cámaras, Puertas, Luces) con lo que queda
    por colocar de esa familia — ver NodesState.floor_available_grouped.

    El .to(list[dict]) es obligatorio: el valor de una clave de dict llega sin
    tipo y rx.foreach no puede recorrerlo sin saber qué es."""
    items = section["items"].to(list[dict])
    return rx.el.div(
        rx.el.div(
            rx.el.span(section["kind_label"], class_name="nx-ed-tipo-nombre"),
            rx.badge(items.length(), variant="soft", size="1", color_scheme="gray"),
            class_name="nx-ed-tipo-cab",
        ),
        rx.foreach(items, _available_row),
        class_name="nx-ed-tipo",
    )


def _available_estancia(grupo: dict) -> rx.Component:
    """Una estancia plegable con lo que le queda por colocar, por tipos dentro
    — ver NodesState.floor_available_por_estancia."""
    tipos = grupo["tipos"].to(list[dict])
    return rx.el.div(
        rx.el.button(
            rx.icon(rx.cond(grupo["abierta"], "chevron-down", "chevron-right"),
                    size=15, color=theme.MUTED, flex_shrink="0"),
            rx.icon(rx.cond(grupo["id"] == "_sin", "circle-dashed", "house"),
                    size=14, color=theme.ACCENT, flex_shrink="0"),
            rx.el.span(grupo["nombre"], class_name="nx-ed-estancia-nombre"),
            rx.badge(grupo["total"], variant="soft", size="1", color_scheme="gray"),
            rx.cond(grupo["propia"], rx.badge("este plano", variant="soft", size="1",
                                              color_scheme="blue",
                                              class_name="nx-ed-propia")),
            type="button", class_name="nx-ed-estancia-cab",
            aria_expanded=grupo["abierta"],
            on_click=NodesState.alternar_estancia_catalogo(grupo["id"].to(str)),
        ),
        rx.cond(
            grupo["abierta"],
            rx.el.div(rx.foreach(tipos, _available_section), class_name="nx-ed-estancia-cuerpo"),
        ),
        class_name="nx-ed-estancia",
    )


def _cuerpo_en_plano() -> rx.Component:
    """«En el plano»: lo ya colocado, con su icono, color y botón de quitar."""
    return rx.cond(
        NodesState.floor_placed.length() > 0,
        rx.el.div(rx.foreach(NodesState.floor_placed, _placed_row), class_name="nx-ed-lista"),
        rx.el.p("Todavía no hay nada en el plano.", class_name="nx-plano-vacio"),
    )


def _cuerpo_anadir() -> rx.Component:
    """«Añadir al plano»: lo que falta por colocar, por estancias."""
    return rx.cond(
        NodesState.floor_available.length() > 0,
        rx.el.div(
            rx.foreach(NodesState.floor_available_por_estancia, _available_estancia),
            class_name="nx-ed-lista",
        ),
        rx.el.p("Ya está todo el sistema en el plano.", class_name="nx-plano-vacio"),
    )


_PESTANAS_EDICION = (
    ("plano", "En el plano"),
    ("anadir", "Añadir"),
    ("planos", "Planos"),
)


def _pestana_edicion(clave: str, texto: str, contador=None) -> rx.Component:
    activa = NodesState.pestana_edicion_plano == clave
    return rx.el.button(
        rx.el.span(texto, class_name="nx-ed-tab-txt"),
        *([rx.el.span(contador, class_name="nx-ed-tab-n")] if contador is not None else []),
        type="button", role="tab", id=f"nx-ed-tab-{clave}",
        class_name="nx-ed-tab",
        on_click=NodesState.elegir_pestana_edicion(clave),
        aria_selected=activa, aria_controls="nx-ed-panel",
        tab_index=rx.cond(activa, 0, -1),
        custom_attrs={"data-activa": activa},
    )


def _editor_plano() -> rx.Component:
    """UNA tarjeta con tres pestañas segmentadas: «En el plano», «Añadir al plano»
    y «Planos». Las tres vivían como paneles sueltos (dos columnas pegadas y un
    cajón flotante encima) y se pisaban; en una sola tarjeta con el cuerpo como
    única zona con scroll no tienen cómo solaparse. La tarjeta es un contenedor
    (container-type) y las filas se reorganizan según SU ancho, no el de la
    ventana (nx.css, «Edición del plano»)."""
    return rx.el.section(
        rx.el.div(
            _pestana_edicion("plano", "En el plano", NodesState.floor_placed.length()),
            _pestana_edicion("anadir", "Añadir", NodesState.floor_available.length()),
            _pestana_edicion("planos", "Planos", NodesState.planos_ui.length()),
            role="tablist", aria_label="Editar el plano", class_name="nx-ed-tabs",
        ),
        rx.el.div(
            rx.match(
                NodesState.pestana_edicion_plano,
                ("anadir", _cuerpo_anadir()),
                ("planos", _cuerpo_planos()),
                _cuerpo_en_plano(),
            ),
            role="tabpanel", id="nx-ed-panel",
            aria_labelledby="nx-ed-tab-" + NodesState.pestana_edicion_plano,
            class_name="nx-ed-cuerpo",
        ),
        class_name="nx-plano-panel nx-plano-editor",
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
        # Al cambiar de plano se descarta lo arrastrado sin guardar: si no, el
        # «Listo» lo guardaría en el plano NUEVO.
        on_click=[rx.call_script(PLAN_RESET_SCRIPT), NodesState.ver_plano(p["id"])],
        cursor="pointer", spacing="2", align="center", flex_shrink="0",
        padding="6px 10px", border_radius="9px",
        background=rx.cond(p["activo"], theme.alpha(theme.ACCENT, 0.12),
                           theme.BG_CARD), class_name="nx-card",
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
            overflow_x="auto", padding_block="3px",
        ),
    )


def _cuerpo_planos() -> rx.Component:
    """Subir, renombrar, marcar principal y quitar. Es la pestaña «Planos» de la
    tarjeta de edición (antes un cajón flotante que tapaba los menús).

    El principal es el que se abre al entrar y el que ve la vista clásica, así
    que se marca con una estrella y no se puede quedar sin marcar ninguno."""
    return rx.el.div(
        rx.foreach(
            NodesState.planos_ui,
            lambda p: rx.el.div(
                rx.input(
                    default_value=p["nombre"],
                    on_blur=lambda v: NodesState.renombrar_plano(p["id"], v),
                    size="1", class_name="nx-ed-plano-nombre",
                    aria_label="Nombre del plano",
                ),
                rx.badge(p["elementos_texto"], size="1", variant="surface",
                         class_name="nx-ed-plano-n"),
                rx.el.div(
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
                        rx.el.button(
                            rx.icon("trash-2", size=14, color=theme.DANGER),
                            type="button", class_name="nx-ed-btn",
                            title="Quitar el plano", aria_label="Quitar el plano",
                        ),
                        title="¿Quitar este plano?",
                        tipo="el plano",
                        nombre=p["nombre"],
                        on_confirm=NodesState.borrar_plano(p["id"]),
                        extra="Se borra su imagen y la posición de sus "
                              "elementos. Los elementos siguen existiendo y en "
                              "los demás planos donde estén.",
                    ),
                    class_name="nx-ed-plano-acc",
                ),
                class_name="nx-ed-fila nx-ed-plano",
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
            border_radius="10px", padding="14px", width="100%", min_width="0",
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
                        size="1", color=theme.TEXT, min_width="0", flex="1",
                        overflow="hidden", text_overflow="ellipsis",
                        white_space="nowrap"),
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
        class_name="nx-ed-lista",
    )


def _resumen_item(icon: str, etiqueta: str, valor, tono: str = "") -> rx.Component:
    return rx.el.div(
        rx.el.span(rx.icon(icon, size=15), class_name="nx-plano-resumen-icono"),
        rx.el.span(etiqueta, class_name="nx-plano-resumen-etiqueta"),
        rx.el.strong(valor, class_name="nx-plano-resumen-valor"),
        class_name="nx-plano-resumen-item",
        custom_attrs={"data-tono": tono},
    )


def _resumen_en_vivo() -> rx.Component:
    armado = SecurityState.sistema_armado
    return rx.el.div(
        _resumen_item(
            rx.cond(armado, "shield-check", "shield-off"),
            "Sistema",
            rx.cond(armado, "Armado", "Desarmado"),
            "armado",
        ),
        _resumen_item(
            "door-open", "Abiertos", SecurityState.lista_abiertos, "abiertos"),
        _resumen_item(
            "lightbulb", "Luces",
            NodesState.luces_encendidas_en_plano.to_string() + " encendidas",
            "luces",
        ),
        class_name="nx-plano-resumen",
        custom_attrs={"data-armado": armado},
    )


def _baldosa(b: rx.Var) -> rx.Component:
    """Una baldosa de «Luces y aparatos»: una luz o aparato (se conmuta) o una
    cerradura de puerta (se mantiene abierta o se suelta). En modo edición deja
    cambiar el icono y quitarla en vez de accionarla."""
    ref = b["ref"].to(str)
    activo = b["activo"].to(bool)
    modos = (("continuo", "Continuo"), ("1h", "1 h"), ("2h", "2 h"), ("3h", "3 h"))
    selector_modo = rx.menu.root(
        rx.menu.trigger(
            rx.el.span(b["meta"].to(str) + " · " + b["etiqueta_modo"].to(str),
                       class_name="nx-tile-meta", cursor="pointer", title="Cambiar modo"),
        ),
        rx.menu.content(
            *[rx.menu.item(
                rx.hstack(
                    rx.cond(b["modo_encendido"].to(str) == modo,
                            rx.icon("check", size=14), rx.el.span(width="14px")),
                    rx.text(etiqueta), spacing="2", align="center"),
                on_click=NodesState.elegir_modo_encendido(
                    b["light_id"].to(str), modo),
            ) for modo, etiqueta in modos],
        ),
    )
    meta = rx.cond(
        b["tiene_modos"].to(bool), selector_modo,
        rx.el.span(b["meta"].to(str), class_name="nx-tile-meta"),
    )
    normal = _quick_action(
        b["icon"].to(str), b["name"], NodesState.accionar_baldosa(ref),
        tono="lamp", activo=activo,
        trailing=rx.el.span(class_name="nx-tile-switch", aria_hidden="true"),
        meta=meta,
    )
    edicion = rx.hstack(
        rx.select.root(
            rx.select.trigger(rx.icon(b["icon"].to(str), size=16), variant="soft",
                              title="Cambiar icono"),
            select_content(*[
                rx.select.item(rx.hstack(rx.icon(ic, size=14), rx.text(ic, size="1"),
                                         spacing="2", align="center"), value=ic)
                for ic in FLOOR_ICON_OPTIONS
            ]),
            value=b["icon"].to(str),
            on_change=lambda v: NodesState.icono_baldosa(ref, v),
            size="1",
        ),
        rx.text(b["name"], size="2", color=theme.TEXT, flex="1", min_width="0",
                overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
        rx.icon("x", size=16, color=theme.DANGER, cursor="pointer", flex_shrink="0",
                on_click=NodesState.quitar_baldosa(ref), title="Quitar de aquí"),
        align="center", spacing="2", width="100%", padding="8px 10px",
        border_radius="10px", border=f"1px dashed {theme.BORDER_STRONG}",
    )
    return rx.cond(NodesState.editando_baldosas, edicion, normal)


def _luces_y_aparatos() -> rx.Component:
    return rx.el.section(
        rx.hstack(
            rx.el.h2("Luces y aparatos", class_name="nx-plano-panel-titulo"),
            rx.spacer(),
            rx.cond(
                AuthState.puede_ajustes,
                boton_ajustes(
                    NodesState.alternar_edicion_baldosas,
                    titulo="Ajustes de luces y aparatos",
                    activo=NodesState.editando_baldosas,
                ),
            ),
            align="center", width="100%",
        ),
        rx.cond(
            NodesState.baldosas_plano.length() > 0,
            rx.el.div(
                rx.foreach(NodesState.baldosas_plano, _baldosa),
                class_name="nx-plano-tiles",
            ),
            rx.el.p("No hay interruptores en este plano.", class_name="nx-plano-vacio"),
        ),
        rx.cond(
            NodesState.editando_baldosas,
            rx.select.root(
                rx.select.trigger(placeholder="Añadir luz, aparato o cerradura…",
                                  width="100%"),
                select_content(rx.foreach(
                    NodesState.opciones_baldosa,
                    lambda o: rx.select.item(o["nombre"], value=o["ref"]))),
                value="",
                on_change=NodesState.anadir_baldosa,
                size="2",
            ),
        ),
        class_name="nx-plano-panel",
    )


def _fila_equipo(equipo: rx.Var, editable=False) -> rx.Component:
    online = equipo["online"].to(bool)
    return rx.el.div(
        rx.el.span(
            rx.icon(equipo["icon"].to(str), size=15),
            class_name="nx-plano-equipo-icono",
        ),
        rx.cond(
            editable,
            rx.icon("x", size=15, color=theme.DANGER, cursor="pointer",
                    flex_shrink="0",
                    on_click=NodesState.quitar_equipo_vista(
                        equipo["ref"].to(str)), title="Quitar de aquí"),
        ),
        rx.el.span(equipo["name"].to(str), class_name="nx-plano-equipo-nombre"),
        rx.el.span(
            rx.cond(online, "En línea", "Sin conexión"),
            class_name="nx-plano-equipo-estado",
        ),
        class_name="nx-plano-equipo",
        custom_attrs={"data-online": online, "data-tipo": equipo["tipo"].to(str)},
    )


def _lateral(columna_a: list, columna_b: list, editando: bool) -> rx.Component:
    """La columna de menús a la derecha del plano.

    Estructura fija (el CSS y el ajuste de assets/nx.js dependen de ella):
    aside > .nx-plano-menu (la caja con la altura del plano y el scroll de
    último recurso) > .nx-plano-cols (centrada en vertical) > .nx-plano-col ×2
    (el menú principal y el secundario). Con una sola columna se apilan; si el
    contenido no cabe en la altura del plano, nx.js pone data-cols="2" y pasan
    a ir lado a lado. En pantallas estrechas todo el andamiaje es `display:
    contents` y los paneles caen debajo del plano como siempre.
    Detalle: docs/runbooks/layout-plano-menus.md."""
    return rx.el.aside(
        rx.el.div(
            rx.el.div(
                rx.el.div(*columna_a, class_name="nx-plano-col"),
                rx.el.div(*columna_b, class_name="nx-plano-col"),
                class_name="nx-plano-cols",
            ),
            class_name="nx-plano-menu",
        ),
        class_name="nx-plano-lateral-der",
        custom_attrs={"data-editando": editando},
    )


def _panel_equipos() -> rx.Component:
    return rx.el.section(
        rx.hstack(
            rx.el.h2("Equipos", class_name="nx-plano-panel-titulo"),
            rx.spacer(),
            rx.cond(
                AuthState.puede_ajustes,
                boton_ajustes(
                    NodesState.alternar_edicion_equipos_vista,
                    titulo="Ajustes de equipos",
                    activo=NodesState.editando_equipos_vista,
                ),
            ),
            align="center", width="100%",
        ),
        rx.cond(
            NodesState.equipos_del_plano.length() > 0,
            rx.el.div(
                rx.foreach(
                    NodesState.equipos_del_plano,
                    lambda e: _fila_equipo(e, NodesState.editando_equipos_vista)),
                class_name="nx-plano-equipos-lista",
            ),
            rx.el.p("No hay equipos en este plano.",
                    class_name="nx-plano-vacio"),
        ),
        rx.cond(
            NodesState.editando_equipos_vista,
            rx.select.root(
                rx.select.trigger(placeholder="Añadir equipo o nodo…", width="100%"),
                select_content(rx.foreach(
                    NodesState.opciones_equipo_vista,
                    lambda o: rx.select.item(o["nombre"].to(str),
                                             value=o["ref"].to(str)))),
                value="", on_change=NodesState.anadir_equipo_vista, size="2",
            ),
        ),
        class_name="nx-plano-panel nx-plano-equipos",
    )


def _ahora_mismo() -> rx.Component:
    return _lateral(
        [
            rx.el.section(
                rx.el.h2("Ahora mismo", class_name="nx-plano-panel-titulo"),
                _resumen_en_vivo(),
                class_name="nx-plano-panel",
            ),
            _luces_y_aparatos(),
        ],
        [_panel_equipos()],
        editando=False,
    )


def _menus_edicion() -> rx.Component:
    # Una sola tarjeta con pestañas (ver _editor_plano): la segunda columna va
    # vacía y nx.css/nx.js no la usan en edición.
    return _lateral([_editor_plano()], [], editando=True)


def _plano_enmarcado() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.cond(
                    DashboardState.editing_floor_plan,
                    rx.hstack(
                        rx.icon("move", size=15, color=theme.WARNING),
                        rx.text(
                            'Arrastra los iconos y pulsa "Listo" para guardar',
                            size="2", color=theme.WARNING, weight="medium",
                        ),
                        spacing="2", align="center",
                        class_name="nx-plano-instruccion",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    DashboardState.editing_floor_plan,
                    rx.hstack(
                        rx.cond(
                            AuthState.puede_ajustes,
                            rx.button(
                                rx.icon("cpu", size=13), "Probar nodos",
                                on_click=NodesState.probar_nodos_plano,
                                size="1", variant="soft",
                            ),
                        ),
                        rx.button(
                            rx.icon("check", size=14), "Listo",
                            on_click=[
                                rx.call_script(
                                    PLAN_COMMIT_SCRIPT,
                                    callback=NodesState.save_floor_positions,
                                ),
                                DashboardState.toggle_editing_floor_plan,
                            ],
                            size="1", variant="solid", color_scheme="green",
                        ),
                        spacing="2", align="center",
                    ),
                    boton_ajustes(
                        [
                            rx.call_script(PLAN_RESET_SCRIPT),
                            DashboardState.toggle_editing_floor_plan,
                        ],
                        titulo="Ajustes del plano",
                    ),
                ),
                class_name="nx-plano-cabecera",
                custom_attrs={"data-editando": DashboardState.editing_floor_plan},
            ),
            rx.el.div(
                rx.image(
                    src=NodesState.plano_imagen_url,
                    alt="",
                    aria_hidden="true",
                    class_name="nx-plano-fondo",
                    draggable=False,
                ),
                floor_plan_content(),
                class_name="nx-plano-lienzo",
            ),
            class_name="nx-plano-marco",
        ),
        class_name="nx-plano-centro",
    )


def floor_plan_view() -> rx.Component:
    return rx.vstack(
        _pestanas_planos(),
        rx.el.div(
            _plano_enmarcado(),
            # Los menús van SIEMPRE a la derecha del plano (debajo solo cuando no
            # cabe): en modo edición son «En el plano» / «Añadir al plano».
            rx.cond(
                DashboardState.editing_floor_plan,
                _menus_edicion(),
                _ahora_mismo(),
            ),
            class_name="nx-plano-layout",
            custom_attrs={"data-editando": DashboardState.editing_floor_plan},
        ),
        spacing="4",
        width="100%",
        align="center",
        class_name="nx-plano-vista",
    )
