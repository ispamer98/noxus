"""Piezas comunes de las botoneras del plano y la tablet."""
from collections.abc import Callable, Iterable

import reflex as rx

from .icono_propio import icono


def panel_cabecera(nombre_icono, titulo, estado, activo=False,
                   subtitulo="") -> rx.Component:
    return rx.el.header(
        rx.el.div(icono(nombre_icono, 28), class_name="nx-control-icono"),
        rx.el.div(
            rx.el.h3(titulo, class_name="nx-control-titulo"),
            rx.cond(subtitulo != "", rx.el.p(subtitulo, class_name="nx-control-subtitulo")),
            class_name="nx-control-identidad",
        ),
        rx.el.span(estado, class_name="nx-control-estado",
                   custom_attrs={"data-activo": activo}),
        class_name="nx-control-cab",
    )


def boton_control(nombre_icono, texto, evento, tono="", activo=False) -> rx.Component:
    return rx.el.button(
        icono(nombre_icono, 19), rx.el.span(texto), on_click=evento, type="button",
        class_name="nx-control-boton",
        custom_attrs={"data-tono": tono, "data-activo": activo},
    )


def segmentado(opciones: Iterable[tuple[str, str]], actual, evento: Callable,
               etiqueta: str = "") -> rx.Component:
    return rx.el.div(
        rx.cond(etiqueta != "", rx.el.span(etiqueta, class_name="nx-control-label")),
        rx.el.div(*[
            rx.el.button(texto, type="button", on_click=evento(valor),
                         class_name="nx-control-segmento",
                         custom_attrs={"data-activo": actual == valor})
            for valor, texto in opciones
        ], class_name="nx-control-segmentos"),
        class_name="nx-control-campo",
    )


def stepper(etiqueta: str, valor, unidad: str, menos, mas) -> rx.Component:
    return rx.el.div(
        rx.el.span(etiqueta, class_name="nx-control-label"),
        rx.el.div(
            rx.el.button(rx.icon("minus", size=21), on_click=menos, type="button",
                         class_name="nx-control-step", aria_label="Reducir " + etiqueta),
            rx.el.output(valor, rx.el.small(unidad), class_name="nx-control-valor"),
            rx.el.button(rx.icon("plus", size=21), on_click=mas, type="button",
                         class_name="nx-control-step", aria_label="Aumentar " + etiqueta),
            class_name="nx-control-stepper",
        ),
        class_name="nx-control-campo",
    )


def anillo(progreso, restante, fin) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span(restante, class_name="nx-cuenta nx-control-tiempo",
                       custom_attrs={"data-fin": fin}),
            rx.el.small("restante"),
            class_name="nx-control-anillo-centro",
        ),
        class_name="nx-control-anillo",
        style={"--nx-progreso": (progreso.to(str) + "%") if isinstance(progreso, rx.Var) else f"{progreso}%"},
        aria_label="Tiempo restante",
    )


def panel(*hijos, clase: str = "", modo=None) -> rx.Component:
    attrs = {"data-modo": modo} if modo is not None else {}
    return rx.el.div(*hijos, class_name="nx-control-panel " + clase, custom_attrs=attrs)

