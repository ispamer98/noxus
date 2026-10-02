"""Iconos que Lucide no trae, pintados con su mismo trazo, y `icono()`, que
sirve igual para estos que para cualquiera de Lucide (nombre fijo o Var)."""
import reflex as rx

# Iconos del plano que Lucide no trae, con su mismo trazo (24×24, línea de 2,
# puntas redondas) para que no desentonen al lado de los demás.
_ICONOS_PROPIOS = {
    # El portón levantado: el «warehouse» de Lucide (el portón cerrado, con sus
    # lamas) con la hoja recogida arriba y el hueco libre.
    "warehouse-open": (
        "M22 19V8.35a2 2 0 0 0-1.26-1.86l-8-3.2a2 2 0 0 0-1.48 0l-8 3.2A2 2 0 0 0 "
        "2 8.35V19a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2Z",
        "M18 21V10a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1v11",
        "M6 12h12",
    ),
}


def _svg_propio(trazos: tuple[str, ...], size: int, color) -> rx.Component:
    return rx.el.svg(
        *[rx.el.svg.path(d=d) for d in trazos],
        xmlns="http://www.w3.org/2000/svg", width=str(size), height=str(size),
        view_box="0 0 24 24", fill="none", stroke="currentColor",
        stroke_width="2", stroke_linecap="round", stroke_linejoin="round",
        color=color, flex_shrink="0", display="block",
    )


def icono(nombre, size: int, color="currentColor") -> rx.Component:
    """rx.icon que además sabe pintar los iconos propios (_ICONOS_PROPIOS)."""
    if isinstance(nombre, str):
        trazos = _ICONOS_PROPIOS.get(nombre)
        return _svg_propio(trazos, size, color) if trazos else rx.icon(nombre, size=size, color=color)
    resultado = rx.icon(nombre, size=size, color=color)
    for propio, trazos in _ICONOS_PROPIOS.items():
        resultado = rx.cond(nombre == propio, _svg_propio(trazos, size, color), resultado)
    return resultado
