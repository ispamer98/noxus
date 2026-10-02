"""
Pantalla «Pruebas» (Ajustes): forzar el estado de cualquier elemento (sensores,
cerraduras, luces, persianas, aparatos) o la conexión de nodos y equipos, para
probar la alarma, los avisos y las pantallas sin tocar nada.

Lo forzado solo lo ve el panel (alarma, pantallas, métricas): no cambia el
aparato real, no lanza automatizaciones ni órdenes, caduca solo y desaparece al
reiniciar. Ver core/pruebas.py.

Diseño: un desplegable por tipo (<details> nativo, sin estado en el servidor) y,
dentro, filas de una línea con el nombre y un selector de tres posiciones. Los
estilos están en assets/nx.css (bloque «Pruebas»).
"""
import reflex as rx

from ....domains.infra.pruebas_state import PruebasState


def _opcion(texto, valor: str, actual, tono, al_pulsar) -> rx.Component:
    return rx.el.button(
        texto, type="button", on_click=al_pulsar,
        class_name="nx-pr-op",
        custom_attrs={"data-activo": actual == valor, "data-tono": tono},
    )


def _selector(actual, g: rx.Var, evento) -> rx.Component:
    """Real · <sí> · <no>. `evento(modo)` da el manejador de cada botón."""
    return rx.el.div(
        _opcion("Real", "real", actual, "blue", evento("real")),
        _opcion(g["si"].to(str), "on", actual, g["color_si"].to(str), evento("on")),
        _opcion(g["no"].to(str), "off", actual, g["color_no"].to(str), evento("off")),
        class_name="nx-pr-seg", role="group",
    )


def _fila(f: rx.Var, g: rx.Var) -> rx.Component:
    fid = f["id"].to(str)
    real = rx.cond(f["real_on"].to(bool), g["si"].to(str), g["no"].to(str))
    return rx.el.div(
        rx.el.span(class_name="nx-pr-punto", title="De verdad: " + real,
                   custom_attrs={"data-on": f["real_on"].to(bool),
                                 "data-tono": g["color_si"].to(str)}),
        rx.el.span(f["nombre"].to(str), class_name="nx-pr-nombre",
                   title=f["nombre"].to(str) + " · de verdad: " + real),
        _selector(f["modo"].to(str), g, lambda modo: PruebasState.forzar(fid, modo)),
        class_name="nx-pr-fila",
        custom_attrs={"data-forzado": f["modo"].to(str) != "real"},
    )


def _grupo(g: rx.Var) -> rx.Component:
    clave = g["clave"].to(str)
    return rx.el.details(
        rx.el.summary(
            rx.icon(g["icono"].to(str), size=16, class_name="nx-pr-icono"),
            rx.el.span(g["titulo"].to(str), class_name="nx-pr-titulo"),
            rx.el.span(g["total"].to(str), class_name="nx-pr-total"),
            rx.cond(g["forzados"].to(int) > 0,
                    rx.el.span(g["forzados"].to(str) + " forzado(s)",
                               class_name="nx-pr-marca")),
            rx.icon("chevron-down", size=16, class_name="nx-pr-flecha"),
        ),
        rx.el.div(
            rx.el.span("Todos", class_name="nx-pr-todos"),
            _selector("", g, lambda modo: PruebasState.forzar_grupo(clave, modo)),
            class_name="nx-pr-fila nx-pr-fila-todos",
        ),
        rx.el.div(
            rx.foreach(g["filas"].to(list[dict]), lambda f: _fila(f, g)),
            class_name="nx-pr-rejilla",
        ),
        class_name="nx-pr-grupo",
        custom_attrs={"data-forzado": g["forzados"].to(int) > 0},
    )


def pruebas_view() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.icon("flask-conical", size=18, class_name="nx-pr-icono"),
                rx.el.div(
                    rx.el.h2("Pruebas", class_name="nx-pr-h"),
                    rx.el.p("Simula estados sin tocar nada real. Caduca a los 10 min.",
                            class_name="nx-pr-sub"),
                ),
                class_name="nx-pr-cab-texto",
            ),
            rx.el.span(
                rx.cond(PruebasState.hay_forzados,
                        PruebasState.cuantos.to_string() + " forzados · hasta las "
                        + PruebasState.caduca,
                        "Todo real"),
                class_name="nx-pr-estado",
                custom_attrs={"data-activo": PruebasState.hay_forzados},
            ),
            rx.el.button(
                rx.icon("rotate-ccw", size=14), rx.el.span("Restablecer"),
                type="button", on_click=PruebasState.restablecer,
                disabled=~PruebasState.hay_forzados, class_name="nx-pr-reset",
            ),
            class_name="nx-pr-cab",
        ),
        rx.el.details(
            rx.el.summary(rx.icon("siren", size=14), "¿Cómo pruebo la alarma?"),
            rx.el.p("Magnético en «Cerrado» → arma su grupo → ponlo en «Abierto». "
                    "Salta como de verdad (avisos, sirena, foto). «Real» lo devuelve."),
            class_name="nx-pr-ayuda",
        ),
        rx.foreach(PruebasState.grupos, _grupo),
        class_name="nx-pr",
        on_mount=PruebasState.cargar,
    )
