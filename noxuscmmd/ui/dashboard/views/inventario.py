"""Vista "Inventario": todo lo que hay instalado, en tablas por familia.

Cada familia tiene sus propias columnas —las que de verdad comparten sus
elementos— y se declaran aquí, en Python. Eso importa: las columnas se conocen
al compilar, así que el bucle que las recorre es un bucle normal y solo las
FILAS pasan por rx.foreach. Al revés (columnas dinámicas dentro del foreach)
es justo el camino que rompe el frontend en esta versión de Reflex.
"""
import reflex as rx

from .. import theme
from ..state import DashboardState
from ....domains.inventory.state import InventoryState
from ....domains.inventory import catalogo

# (clave de la fila, encabezado). El nombre va siempre el primero y no se
from ..components.actions_menu import confirm_delete_dialog
# declara aquí: lo pone _tabla, junto al botón de abrir la ficha.
_COLUMNAS = {
    "equipos": [("ip_local", "IP local"), ("ip_tailscale", "Tailscale"),
                ("mac", "MAC"), ("so", "Sistema"), ("en_linea", "En línea"),
                ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "nodos": [("ip_local", "IP local"), ("mac", "MAC"), ("tipo", "Tipo"),
              ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "sensores": [("tipo", "Tipo"), ("nodo", "Nodo"), ("pin", "Pin"),
                 ("vigilado", "Vigilado"), ("modelo", "Modelo"),
                 ("ubicacion", "Ubicación")],
    "cerraderos": [("nodo", "Nodo"), ("pin", "Pin"), ("pulso", "Pulso"),
                   ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "luces": [("nodo", "Nodo"), ("pin", "Pin"), ("gobierno", "Se gobierna"),
              ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "camaras": [("origen", "Origen"), ("ptz", "Se mueve"), ("modelo", "Modelo"),
                ("ubicacion", "Ubicación")],
    "mandos": [("botones", "Botones"), ("modelo", "Modelo"),
               ("ubicacion", "Ubicación")],
    "sueltos": [("familia", "Qué es"), ("ip_local", "IP local"), ("mac", "MAC"),
                ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "accesorios": [("nodo", "Nodo"), ("pin", "Pin"),
                   ("gobierno", "Se gobierna"), ("modelo", "Modelo"),
                   ("ubicacion", "Ubicación")],
    "estancias": [("tipo", "Tipo"), ("modelo", "Modelo"),
                  ("ubicacion", "Ubicación")],
    "grupos": [("miembros", "Sensores"), ("principal", "Principal"),
                ("armado", "Armado"), ("modelo", "Modelo"),
                ("ubicacion", "Ubicación")],
    "automatizaciones": [("activa", "Activa"), ("disparadores", "Disparadores"),
                           ("acciones", "Acciones"), ("modelo", "Modelo"),
                           ("ubicacion", "Ubicación")],
    "carpetas": [("reglas", "Automatizaciones"), ("modelo", "Modelo"),
                 ("ubicacion", "Ubicación")],
    "planos": [("medidas", "Medidas"), ("principal", "Principal"),
                ("iconos", "Iconos colocados"), ("modelo", "Modelo"),
                ("ubicacion", "Ubicación")],
    "widgets": [("tipo", "Tipo"), ("destino", "Destino"),
                ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "botones": [("tipo", "Tipo"), ("padre", "Pertenece a"),
                 ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "metricas": [("forma", "Forma"), ("medida", "Mide"), ("dias", "Días"),
                  ("modelo", "Modelo"), ("ubicacion", "Ubicación")],
    "voz": [("comando", "Acción"), ("modelo", "Modelo"),
            ("ubicacion", "Ubicación")],
    "alexa": [("comportamiento", "Comportamiento"), ("accion", "Acción"),
              ("frase_alexa", "Cómo se pide"), ("modelo", "Modelo"),
              ("ubicacion", "Ubicación")],
}

def _celda(texto) -> rx.Component:
    return rx.table.cell(
        rx.text(texto, size="1", color=theme.TEXT, white_space="nowrap"),
        padding="8px 12px",
    )


def _fila(item: rx.Var, columnas: list[tuple[str, str]],
          borrable: bool) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(item["nombre"], size="1", weight="bold", color=theme.TEXT,
                        white_space="nowrap"),
                rx.cond(
                    item["notas"] != "",
                    rx.icon("sticky-note", size=12, color=theme.MUTED),
                ),
                spacing="2", align="center",
            ),
            padding="8px 12px",
        ),
        *[_celda(item[clave]) for clave, _ in columnas],
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.icon("pencil", size=12), size="1", variant="soft",
                    on_click=InventoryState.abrir_ficha(item["id"], item["nombre"]),
                ),
                rx.cond(
                    item["entity_can_delete"],
                    confirm_delete_dialog(
                        rx.button(
                            rx.icon("trash-2", size=12), size="1", variant="soft",
                            color_scheme="red"),
                        title="¿Eliminar este elemento?",
                        tipo="elemento", nombre=item["nombre"],
                        on_confirm=InventoryState.borrar_entidad(
                            item["entity_collection"], item["entity_id"],
                            item["nombre"]),
                    ),
                ),
                spacing="1", justify="end",
            ),
            padding="8px 12px",
        ),
    )


def _tabla(titulo: str, icono: str, familia: str, filas: rx.Var,
           borrable: bool = False) -> rx.Component:
    columnas = _COLUMNAS[familia]
    return rx.vstack(
        rx.hstack(
            rx.icon(icono, size=16, color=theme.ACCENT, flex_shrink="0"),
            rx.text(titulo, size="2", weight="bold", color=theme.TEXT),
            rx.text(filas.length().to_string(), size="1", color=theme.MUTED),
            align="center", spacing="2",
        ),
        rx.cond(
            filas.length() > 0,
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell(
                                rx.text("Nombre", size="1", color=theme.MUTED,
                                        white_space="nowrap"),
                                padding="8px 12px"),
                            *[
                                rx.table.column_header_cell(
                                    rx.text(etiqueta, size="1", color=theme.MUTED,
                                            white_space="nowrap"),
                                    padding="8px 12px")
                                for _, etiqueta in columnas
                            ],
                            rx.table.column_header_cell("", padding="8px 12px"),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(filas, lambda f: _fila(f, columnas, borrable)),
                    ),
                    variant="surface", size="1", width="100%",
                ),
                # La tabla se desborda a lo ancho en el móvil: que ruede ella
                # sola dentro de su caja en vez de mover la página entera.
                width="100%", overflow_x="auto",
            ),
            rx.text("Nada dado de alta en esta familia.", size="1",
                    color=theme.MUTED),
        ),
        spacing="2", width="100%", align="start",
    )


def _ficha_dialog() -> rx.Component:
    """Lo que se puede escribir a mano de cualquier elemento."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("clipboard-list", size=18, color=theme.ACCENT),
                    rx.text(InventoryState.editando_nombre, size="3",
                            weight="bold", color=theme.TEXT),
                    align="center", spacing="2",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Lo que el panel no sabe de este elemento. Se queda "
                    "guardado aunque el aparato esté apagado.",
                    size="1", color=theme.MUTED,
                ),
                rx.text("Modelo", size="1", color=theme.MUTED),
                rx.input(value=InventoryState.ed_modelo,
                         on_change=InventoryState.set_ed_modelo,
                         placeholder="Sonoff SNZB-04, Hikvision DS-2CD...",
                         width="100%"),
                rx.text("Ubicación", size="1", color=theme.MUTED),
                rx.input(value=InventoryState.ed_ubicacion,
                         on_change=InventoryState.set_ed_ubicacion,
                         placeholder="Cuadro de la entrada, techo del pasillo...",
                         width="100%"),
                rx.text("IP a mano", size="1", color=theme.MUTED),
                rx.input(value=InventoryState.ed_ip,
                         on_change=InventoryState.set_ed_ip,
                         placeholder="solo si no se descubre sola", width="100%"),
                rx.text("MAC a mano", size="1", color=theme.MUTED),
                rx.input(value=InventoryState.ed_mac,
                         on_change=InventoryState.set_ed_mac,
                         placeholder="solo si no se descubre sola", width="100%"),
                rx.text("Notas", size="1", color=theme.MUTED),
                rx.text_area(value=InventoryState.ed_notas,
                             on_change=InventoryState.set_ed_notas,
                             placeholder="Lo que haga falta recordar el día de la avería.",
                             width="100%", rows="3"),
                rx.hstack(
                    rx.spacer(),
                    rx.button("Cancelar", variant="soft", color_scheme="gray",
                              on_click=InventoryState.cerrar_ficha),
                    rx.button("Guardar", on_click=InventoryState.guardar_ficha),
                    spacing="2", width="100%",
                ),
                spacing="2", width="100%",
            ),
            max_width="460px",
        ),
        open=InventoryState.editando_id != "",
        on_open_change=lambda abierto: rx.cond(
            abierto, rx.noop(), InventoryState.cerrar_ficha()),
    )


def _añadir_suelto() -> rx.Component:
    return rx.hstack(
        rx.input(value=InventoryState.nuevo_nombre,
                 on_change=InventoryState.set_nuevo_nombre,
                 placeholder="Router del salón, lector de la entrada...",
                 flex="1", min_width="0"),
        rx.select(
            list(catalogo.FAMILIAS_SUELTAS),
            value=InventoryState.nuevo_familia,
            on_change=InventoryState.set_nuevo_familia,
            width="150px",
        ),
        rx.button("Añadir", on_click=InventoryState.añadir_suelto,
                  flex_shrink="0"),
        spacing="2", width="100%", align="center", wrap="wrap",
    )


def inventario_view() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("clipboard-list", size=22, color=theme.ACCENT),
            rx.heading("Inventario", size="6", color=theme.TEXT),
            rx.spacer(),
            rx.button(rx.icon("refresh-cw", size=15), "Actualizar", size="2",
                      variant="soft", on_click=InventoryState.actualizar),
            rx.button(rx.icon("arrow-left", size=15), "Ajustes", size="2",
                      variant="soft",
                      on_click=DashboardState.set_view("settings_hub")),
            align="center", spacing="2", width="100%", wrap="wrap",
        ),
        rx.text(
            "Todo lo que hay instalado, con lo que se puede averiguar solo ya "
            "puesto: la IP local y la MAC salen de la tabla ARP del servidor y "
            "la de Tailscale de la propia red privada. El modelo y la "
            "ubicación se escriben a mano — son justo lo que hace falta el día "
            "que algo se avería.",
            size="1", color=theme.MUTED, style={"line-height": "1.6"},
        ),
        rx.hstack(
            rx.icon("info", size=15, color=theme.MUTED, flex_shrink="0"),
            rx.text(InventoryState.resumen, size="1", color=theme.MUTED),
            rx.spacer(),
            rx.button("Limpiar fichas huérfanas", size="1", variant="soft",
                      color_scheme="gray", on_click=InventoryState.limpiar),
            align="center", spacing="2", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
            border_radius="10px", padding="10px 12px",
        ),
        rx.cond(
            ~InventoryState.hay_tailscale,
            rx.hstack(
                rx.icon("triangle-alert", size=15, color=theme.WARNING,
                        flex_shrink="0"),
                rx.text(
                    "No se ha podido preguntar a Tailscale, así que la columna "
                    "de su IP va vacía. El resto del inventario funciona igual.",
                    size="1", color=theme.MUTED,
                ),
                align="center", spacing="2", width="100%",
                background=theme.alpha(theme.WARNING, 0.08),
                border=f"1px solid {theme.alpha(theme.WARNING, 0.3)}",
                border_radius="10px", padding="10px 12px",
            ),
        ),

        _tabla("Equipos", "server", "equipos", InventoryState.equipos),
        _tabla("Nodos", "cpu", "nodos", InventoryState.nodos),
        _tabla("Sensores", "radar", "sensores", InventoryState.sensores),
        _tabla("Cerraderos y puertas", "door-open", "cerraderos",
               InventoryState.cerraderos),
        _tabla("Luces", "lightbulb", "luces", InventoryState.luces),
        _tabla("Cámaras", "video", "camaras", InventoryState.camaras),
        _tabla("Mandos", "gamepad-2", "mandos", InventoryState.mandos),
        _tabla("Accesorios", "box", "accesorios", InventoryState.accesorios),
        _tabla("Estancias", "house", "estancias", InventoryState.estancias),
        _tabla("Grupos de alarma", "layers", "grupos", InventoryState.grupos),
        _tabla("Automatizaciones", "workflow", "automatizaciones",
               InventoryState.automatizaciones),
        _tabla("Carpetas de automatizaciones", "folder", "carpetas",
               InventoryState.carpetas),
        _tabla("Planos", "map", "planos", InventoryState.planos),
        _tabla("Widgets del resumen", "layout-grid", "widgets",
               InventoryState.widgets),
        _tabla("Botones y mandos", "square-mouse-pointer", "botones",
               InventoryState.botones),
        _tabla("Paneles de métricas", "chart-no-axes-combined", "metricas",
               InventoryState.metricas),
        _tabla("Comandos de voz", "mic", "voz", InventoryState.voz),
        _tabla("Elementos publicados en Alexa", "audio-lines", "alexa",
               InventoryState.alexa),

        rx.text("Otros equipos de red", size="1", weight="bold",
                color=theme.MUTED, margin_top="6px"),
        rx.text(
            "Lo que está en la casa pero el panel no gobierna: el router, un "
            "switch, un lector de tarjetas. Se apunta a mano para que el "
            "inventario sea el de la instalación y no el del panel.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        _añadir_suelto(),
        _tabla("Otros equipos de red", "network", "sueltos",
               InventoryState.sueltos, borrable=True),

        _ficha_dialog(),
        spacing="4", width="100%", max_width="1100px", align="start",
        on_mount=InventoryState.on_load,
    )
