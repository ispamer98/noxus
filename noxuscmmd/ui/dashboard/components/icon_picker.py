"""
Selector de icono visual: una rejilla de iconos en un popover, en vez de un
desplegable con los nombres técnicos ("door-open", "circle-dot"...) que no le
dicen nada a nadie.

Dos formas de usarlo, según dónde esté:

- icon_field(): dentro de un formulario. Lleva un <input type=hidden> con el
  nombre del campo, así que se envía con el resto del formulario igual que
  cualquier otro select — quien lo recibe (submit_edit_sensor, apply_override,
  etc.) no nota ninguna diferencia.
- icon_grid(): fuera de un formulario (p.ej. el panel de edición del plano),
  donde cada elección dispara su propio evento al momento.

No se usa rx.select con iconos dentro de cada opción porque Radix construye el
texto del disparador a partir del contenido del item seleccionado: con items
que solo llevan un icono, el disparador se queda en blanco. Con popover +
input oculto controlamos las dos partes.
"""
import reflex as rx

from .. import theme


class IconPickerState(rx.State):
    """Icono elegido en cada selector abierto, indexado por una clave que
    identifica el campo concreto (normalmente "<id de entidad>:<campo>") para
    que dos selectores distintos en la misma página no se pisen.

    Solo guarda lo que el usuario toca: mientras no elija nada, icon_field()
    sigue mostrando el valor que traía la entidad de disco."""
    picked: dict[str, str] = {}

    @rx.event
    def pick(self, key: str, icon: str):
        self.picked[key] = icon


def _cell(icon: str, current, on_click) -> rx.Component:
    """Una casilla de la rejilla. Se resalta la que está elegida ahora mismo."""
    selected = current == icon
    return rx.popover.close(
        rx.box(
            rx.icon(icon, size=17, color=rx.cond(selected, theme.ACCENT, theme.TEXT)),
            on_click=on_click,
            cursor="pointer",
            display="flex",
            align_items="center",
            justify_content="center",
            padding="9px",
            border_radius="9px",
            background=rx.cond(selected, theme.alpha(theme.ACCENT, 0.16), "transparent"),
            border=rx.cond(selected, f"1px solid {theme.ACCENT}", f"1px solid {theme.BORDER}"),
            title=icon,
            _hover={"background": theme.alpha(theme.ACCENT, 0.10), "border_color": theme.BORDER_STRONG},
        ),
    )


def _trigger(current) -> rx.Component:
    return rx.popover.trigger(
        rx.hstack(
            rx.icon(current, size=17, color=theme.ACCENT),
            rx.spacer(),
            rx.icon("chevron-down", size=14, color=theme.MUTED),
            align="center",
            width="100%",
            padding="9px 12px",
            border_radius="8px",
            background=theme.BG_CARD,
            border=f"1px solid {theme.BORDER}",
            cursor="pointer",
            _hover={"border_color": theme.BORDER_STRONG},
        ),
    )


def icon_grid(current, on_pick, options: list[str], columns: int = 6) -> rx.Component:
    """`current` es el icono actual (str o Var). `on_pick` recibe el nombre
    del icono elegido y devuelve el evento a disparar."""
    return rx.popover.root(
        _trigger(current),
        rx.popover.content(
            rx.grid(
                *[_cell(opt, current, on_pick(opt)) for opt in options],
                columns=str(columns),
                spacing="2",
                width="100%",
            ),
            side="bottom",
            align="start",
            style={
                "padding": "10px",
                "width": "min(310px, 90vw)",
                "background": theme.BG_WINDOW,
                "border": f"1px solid {theme.BORDER_STRONG}",
                "border_radius": "12px",
            },
        ),
    )


def icon_field(*, name: str, key, default_value, options: list[str], columns: int = 6) -> rx.Component:
    """Versión para formularios: rejilla + <input type=hidden name=...> con el
    icono elegido, para que se envíe con el resto del formulario.

    `key` debe ser única por campo dentro de la página; si viene de un
    rx.foreach hay que pasarla ya como str (con .to(str))."""
    current = IconPickerState.picked.get(key, default_value)
    return rx.box(
        rx.input(name=name, value=current, type="hidden"),
        icon_grid(current, lambda icon: IconPickerState.pick(key, icon), options, columns),
        width="100%",
    )
