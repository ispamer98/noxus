"""404 pública del panel, sin estado ni datos de la casa."""
from pathlib import Path

import reflex as rx


# La viñeta procede de la página de caída ya diseñada. Se mantiene como SVG
# junto al componente para que rx.html la incruste de verdad y sus animaciones
# puedan controlarse desde nx.css (incluido prefers-reduced-motion).
_VINETA = Path(__file__).with_name("404_vineta.svg").read_text(encoding="utf-8")


def not_found_page() -> rx.Component:
    """Página que Reflex usa para cualquier ruta desconocida de la SPA."""
    return rx.el.main(
        rx.el.div(
            rx.el.img(src="/noxus-marca.svg", alt="", width="30", height="30"),
            rx.el.span("noxus"),
            class_name="nx-404-brand",
            custom_attrs={"translate": "no"},
        ),
        rx.el.div(
            rx.html(_VINETA),
            class_name="nx-404-vignette",
        ),
        rx.el.h1("Esta página no existe… todavía"),
        rx.el.p(
            rx.el.b("Rubén está trabajando en ello"),
            ", pero aquí no hay nada que ver. Vuelve al panel y sigue por donde ibas.",
        ),
        rx.el.a("Volver al panel", href="/panel", class_name="nx-404-button"),
        class_name="nx-404",
    )
