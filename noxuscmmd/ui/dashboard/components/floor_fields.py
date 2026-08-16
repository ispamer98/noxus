"""
Sección "mostrar en el plano de planta" para el formulario de edición de
CUALQUIER entidad que pueda salir en el plano: sensores, cámaras, puertas y
luces — de fábrica o dadas de alta desde la web.

La posición en sí NO se elige aquí: se arrastra el marcador directamente
sobre el plano (pestaña Plano) y se guarda solo — ver ui/views/device_list.py
y domains/nodes/store.py:floor_fields(), que traduce estos dos campos del
formulario a floor_top/floor_left/floor_icon en el almacén.

Los valores por defecto se aceptan tanto como literales Python (entidades de
fábrica, que se construyen una vez al compilar) como Vars reactivos (entidades
dadas de alta, que vienen de un rx.foreach) — de ahí que show_on_floor/
floor_icon no se comparen nunca con `if` en Python.
"""
import reflex as rx

from .form_dialog import field, styled_select, select_content
from .icon_picker import icon_field

# Iconos disponibles para el marcador del plano. Sirven para cualquier tipo de
# entidad (una puerta puede querer "lock", una luz "lamp"...), así que la lista
# es común a propósito en vez de una por tipo.
FLOOR_ICON_OPTIONS = [
    "door-open", "door-closed", "lock", "lock-open", "radar", "circle-dot",
    "triangle-alert", "siren", "cctv", "camera", "video", "lightbulb", "lamp",
    "plug", "thermometer", "bell", "key", "flame", "droplet", "wind",
    "tv", "fan", "air-vent", "gamepad-2",
]


def floor_plan_fields(show_on_floor, floor_icon, default_icon: str = "circle-dot",
                       key="floor", con_icono: bool = True) -> list[rx.Component]:
    """`show_on_floor` puede ser un bool (entidad de fábrica) o un Var
    (rx.cond(...) sobre el dict de una entidad dinámica). Se usa un select en
    vez de un checkbox a propósito: un checkbox desmarcado NO se envía en el
    FormData, así que no habría forma de distinguir "lo ha desactivado" de
    "este formulario no trae el campo" al guardar.

    `con_icono=False` para las entidades que ya eligen su icono en otro campo
    de la misma ficha y lo reutilizan en el plano (los mandos IR): ofrecer un
    segundo selector solo servía para que los dos iconos acabaran distintos."""
    campos = [
        field("¿Mostrar en el plano de planta?", styled_select(
            "Mostrar en el plano",
            select_content(
                rx.select.item("No mostrar", value=""),
                rx.select.item("Mostrar en el plano", value="on"),
            ),
            name="show_on_floor",
            default_value=rx.cond(show_on_floor, "on", "") if isinstance(show_on_floor, rx.Var) else ("on" if show_on_floor else ""),
        )),
    ]
    if con_icono:
        campos.append(field("Icono en el plano", icon_field(
            name="floor_icon",
            key=key,
            default_value=floor_icon if isinstance(floor_icon, rx.Var) else (floor_icon or default_icon),
            options=FLOOR_ICON_OPTIONS,
        )))
    return campos
