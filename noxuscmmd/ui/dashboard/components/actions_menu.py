"""
Menú de acciones genérico para la tarjeta de CUALQUIER entidad (sensor, nodo,
equipo, cámara, puerta, luz, credencial, nivel, grupo...): un único icono "⋮"
agrupa Editar / Aislar-Reactivar (opcional) / Eliminar-u-Ocultar, en vez de
tener 2-3 iconos sueltos (ojo, lápiz, papelera) repartidos por la fila de
cada tarjeta — mismo componente, mismo aspecto, en todas las pestañas.

remove_style="destructive" (por defecto, entidades dadas de alta en caliente):
pide confirmación, no se puede deshacer. remove_style="reversible" (entidades
de fábrica del registry: se "ocultan", no se borran de verdad — ver
registry.hide): sin confirmación, se restauran desde la tarjeta de ocultos.
"""
import reflex as rx

from .. import theme


def confirm_delete(tipo: str, nombre, extra: str = "") -> rx.Component:
    """Texto del diálogo de confirmación, SIEMPRE con el nombre del elemento
    concreto: al borrar hay que ver qué se está borrando, no un genérico "este
    sensor" que se lee igual en las diez tarjetas de la lista. `nombre` puede
    ser un Var, así que se compone con + y no con f-string."""
    aviso = "Esta acción no se puede deshacer."
    return rx.vstack(
        rx.hstack(
            rx.text("Se va a eliminar " + tipo + " ", size="2", color=theme.MUTED),
            rx.text(nombre, size="2", weight="bold", color=theme.TEXT),
            spacing="1", align="center", wrap="wrap",
        ),
        rx.text(f"{extra} {aviso}".strip(), size="2", color=theme.MUTED),
        spacing="1", align="start", width="100%",
    )


def confirm_delete_dialog(trigger: rx.Component, *, title: str, tipo: str, nombre,
                          on_confirm, extra: str = "") -> rx.Component:
    """Diálogo de confirmación suelto, para borrados que no cuelgan de un
    actions_menu (una estancia, un botón de equipo...). Mismo aspecto y mismo
    texto —con el nombre del elemento— que el del menú ⋮, para que borrar se
    sienta igual en todo el panel."""
    return rx.alert_dialog.root(
        rx.alert_dialog.trigger(trigger),
        rx.alert_dialog.content(
            rx.alert_dialog.title(title),
            rx.alert_dialog.description(confirm_delete(tipo, nombre, extra)),
            rx.hstack(
                rx.alert_dialog.cancel(
                    rx.button("Cancelar", variant="soft", color_scheme="gray", size="2"),
                ),
                rx.alert_dialog.action(
                    rx.button("Eliminar", color_scheme="red", size="2", on_click=on_confirm),
                ),
                spacing="3", justify="end", width="100%", padding_top="3",
            ),
            style={
                "max_width": "380px",
                "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}",
                "border_radius": "16px",
            },
        ),
    )


def _menu_row(icon: str, label, color: str = None, **props) -> rx.Component:
    color = color or theme.TEXT
    return rx.hstack(
        rx.icon(icon, size=14, color=color),
        rx.text(label, size="2", color=color),
        spacing="2",
        align="center",
        width="100%",
        padding="8px 10px",
        border_radius="7px",
        cursor="pointer",
        _hover={"background": theme.alpha(theme.ACCENT, 0.08)},
        **props,
    )


def actions_menu(
    *,
    edit_content: rx.Component | None = None,
    on_edit=None,
    on_remove,
    remove_label: str = "Eliminar",
    remove_icon: str = "trash-2",
    remove_style: str = "destructive",  # "destructive" | "reversible"
    remove_confirm_title: str = "¿Eliminar este elemento?",
    remove_confirm_description: str = "Esta acción no se puede deshacer.",
    edit_label: str = "Editar",
    on_isolate=None,
    isolate_label: str = "",
    isolate_icon: str = "eye-off",
    extra_items=(),   # [(icono, etiqueta, evento)] entre "Editar" y "Eliminar"
) -> rx.Component:
    # "Editar" abre un diálogo (lo normal en el panel) o lanza un evento, para
    # las pantallas donde editar no cabe en una ventanita y ocupa la pestaña
    # entera — ver la vista de Automatizaciones.
    if edit_content is not None:
        rows = [
            rx.dialog.root(
                rx.dialog.trigger(_menu_row("pencil", edit_label)),
                edit_content,
            ),
        ]
    elif on_edit is not None:
        rows = [_menu_row("pencil", edit_label, on_click=on_edit)]
    else:
        rows = []

    for icono, etiqueta, evento in extra_items:
        rows.append(_menu_row(icono, etiqueta, on_click=evento))

    if on_isolate is not None:
        rows.append(_menu_row(isolate_icon, isolate_label, on_click=on_isolate))

    if remove_style == "reversible":
        rows.append(_menu_row(remove_icon, remove_label, color=theme.MUTED, on_click=on_remove))
    else:
        rows.append(
            rx.alert_dialog.root(
                rx.alert_dialog.trigger(_menu_row(remove_icon, remove_label, color=theme.DANGER)),
                rx.alert_dialog.content(
                    rx.alert_dialog.title(remove_confirm_title),
                    rx.alert_dialog.description(remove_confirm_description, size="2", color=theme.MUTED),
                    rx.hstack(
                        rx.alert_dialog.cancel(
                            rx.button("Cancelar", variant="soft", color_scheme="gray", size="2"),
                        ),
                        rx.alert_dialog.action(
                            rx.button(remove_label, color_scheme="red", size="2", on_click=on_remove),
                        ),
                        spacing="3",
                        justify="end",
                        width="100%",
                        padding_top="3",
                    ),
                    style={
                        "max_width": "360px",
                        "background": theme.BG_WINDOW,
                        "border": f"1px solid {theme.BORDER_STRONG}",
                        "border_radius": "16px",
                    },
                ),
            )
        )

    return rx.popover.root(
        rx.popover.trigger(
            rx.icon_button(
                rx.icon("ellipsis-vertical", size=16),
                variant="ghost",
                color_scheme="gray",
                size="1",
                cursor="pointer",
                # La marca que busca la pulsación larga. Al mantener el dedo
                # sobre una tarjeta, el script encuentra el menú de ESA tarjeta y
                # lo pulsa por ti (ver components/pulsacion_larga.py). Está aquí,
                # en un solo sitio, y no repartida por las treinta tarjetas del
                # panel: cualquier tarjeta con menú lo gana sin tocarla.
                custom_attrs={"data-nx-menu": "1"},
            ),
        ),
        rx.popover.content(
            rx.vstack(*rows, spacing="0", width="190px"),
            side="bottom",
            align="end",
            style={
                "padding": "6px",
                "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}",
                "border_radius": "12px",
            },
        ),
    )
