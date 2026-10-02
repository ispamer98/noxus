"""El botón de ajustes del dashboard: el único «entrar a cambiar cosas».

Sustituye al lápiz y a la palabra «Editar», que no deben verse en ningún punto:
un engranaje discreto, del tamaño de los demás iconos-botón, con el nombre solo
en `aria-label` y `title` (para lector de pantalla y para el rato encima).

Dos usos con el mismo componente:
- `boton_ajustes(on_click, titulo=...)`: solo el engranaje.
- `boton_ajustes(on_click, titulo=..., activo=<Var bool>)`: engranaje y, mientras
  el modo está activo, el «Listo» de siempre (check + texto) para salir de él.

El estilo vive en assets/nx.css (`.nx-ajustes-btn`).
"""
import reflex as rx

# UN icono para todo el panel. `settings` y `ellipsis` son los únicos candidatos
# que existen en LUCIDE_ICON_LIST de Reflex 0.8.28 (`settings-2` y
# `sliders-horizontal` no están); el engranaje es el que se reconoce sin texto.
ICONO_AJUSTES = "settings"


def boton_ajustes(on_click=None, *, titulo: str = "Ajustes", activo=None,
                  tamano: int = 15, class_name: str = "", **props) -> rx.Component:
    """Engranaje (y «Listo» si `activo`). `titulo` es accesible, no visible."""
    clases = f"nx-ajustes-btn {class_name}".strip()
    if on_click is not None:
        props["on_click"] = on_click
    engranaje = rx.el.button(
        rx.icon(ICONO_AJUSTES, size=tamano),
        class_name=clases,
        title=titulo, aria_label=titulo, type="button", **props,
    )
    if activo is None:
        return engranaje
    listo = rx.el.button(
        rx.icon("check", size=14), rx.el.span("Listo"),
        class_name=f"{clases} nx-ajustes-listo",
        title="Terminar", aria_label="Terminar de ajustar", type="button",
        custom_attrs={"aria-pressed": "true"}, **props,
    )
    return rx.cond(activo, listo, engranaje)
