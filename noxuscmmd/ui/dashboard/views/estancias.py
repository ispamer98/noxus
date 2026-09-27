"""
Pestaña «Estancias»: elige qué se ve en la pantalla de cada habitación y cómo.

Por estancia: sus elementos (mostrar u ocultar, ponerles otro nombre, ordenarlos,
añadir o quitar) y las opciones de su pantalla (plano, botones de cámaras y
sirena, hora, tamaño de las baldosas, sirena). Todo se guarda al instante.
"""
import reflex as rx

from ....domains.nodes.estancias_state import EstanciasState
from .. import theme

_SONIDOS = [("sirena", "Sirena"), ("pitido", "Pitido"), ("alarma", "Alarma"), ("timbre", "Timbre")]
_VOLUMENES = [("25", "Suave"), ("50", "Medio"), ("75", "Alto"), ("100", "Máximo")]
_BALDOSAS = [("compactas", "Compactas"), ("normales", "Normales"), ("grandes", "Grandes")]


def _tarjeta(*hijos, **kw) -> rx.Component:
    return rx.vstack(*hijos, spacing="3", width="100%", align="start", padding="12px",
                     border_radius="12px", background=theme.BG_CARD, class_name="nx-card",
                     border=f"1px solid {theme.BORDER}", **kw)


def _opciones(pares, actual: rx.Var, evento) -> rx.Component:
    return rx.hstack(*[
        rx.button(t, on_click=evento(v), size="2",
                  variant=rx.cond(actual == v, "solid", "surface"),
                  color_scheme=rx.cond(actual == v, "blue", "gray"))
        for v, t in pares], spacing="2", wrap="wrap")


def _interruptor(texto: str, ayuda: str, valor: rx.Var, clave: str) -> rx.Component:
    return rx.hstack(
        rx.switch(checked=valor, on_change=lambda _v: EstanciasState.alternar_opcion(clave), size="2"),
        rx.vstack(rx.text(texto, size="2", color=theme.TEXT),
                  rx.text(ayuda, size="1", color=theme.MUTED), spacing="0", align="start"),
        align="center", spacing="3", width="100%",
    )


def _chip_sala(s: rx.Var) -> rx.Component:
    activa = EstanciasState.sel == s["id"].to(str)
    return rx.button(
        s["name"].to(str), rx.badge(s["total"].to(str), variant="soft"),
        on_click=EstanciasState.seleccionar(s["id"].to(str)), size="2",
        variant=rx.cond(activa, "solid", "surface"),
        color_scheme=rx.cond(activa, "blue", "gray"),
    )


def _fila(m: rx.Var) -> rx.Component:
    ref = m["ref"].to(str)
    return rx.hstack(
        rx.switch(checked=m["visible"].to(bool),
                  on_change=lambda v: EstanciasState.miembro_visible(ref, v), size="2"),
        rx.vstack(
            rx.text(m["nombre"].to(str), size="2", weight="bold", color=theme.TEXT),
            rx.text(m["familia"].to(str), size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0", flex="1",
        ),
        rx.input(default_value=m["etiqueta"].to(str), placeholder="Otro nombre en la pantalla",
                 on_blur=lambda v: EstanciasState.miembro_etiqueta(ref, v),
                 key=ref + EstanciasState.sel, size="2", max_length=40, width="min(240px, 100%)"),
        rx.hstack(
            rx.icon_button(rx.icon("chevron-up", size=15), on_click=EstanciasState.mover(ref, -1),
                           size="2", variant="soft", aria_label="Subir"),
            rx.icon_button(rx.icon("chevron-down", size=15), on_click=EstanciasState.mover(ref, 1),
                           size="2", variant="soft", aria_label="Bajar"),
            rx.cond(
                m["automatico"].to(bool),
                rx.icon_button(rx.icon("lock", size=15), size="2", variant="soft", disabled=True,
                               title="Es de esta estancia por la propia luz: se cambia en Luces"),
                rx.icon_button(rx.icon("trash-2", size=15), on_click=EstanciasState.quitar(ref),
                               size="2", variant="soft", color_scheme="red", aria_label="Quitar"),
            ),
            spacing="1",
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="8px 10px", border_radius="10px", background=theme.BG_CARD,
        class_name="nx-card", border=f"1px solid {theme.BORDER}",
    )


def _editor() -> rx.Component:
    return rx.vstack(
        _tarjeta(
            rx.hstack(
                rx.input(default_value=EstanciasState.nombre, key=EstanciasState.sel,
                         on_blur=EstanciasState.renombrar, size="3", max_length=40,
                         width="min(320px, 100%)"),
                rx.link(rx.button(rx.icon("external-link", size=14), "Abrir su pantalla",
                                  size="2", variant="soft"),
                        href="/estancia/" + EstanciasState.sel, is_external=True),
                rx.spacer(),
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(rx.button(rx.icon("trash-2", size=14), "Eliminar estancia",
                                                      size="2", variant="soft", color_scheme="red")),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("¿Eliminar esta estancia?"),
                        rx.alert_dialog.description(
                            "Se borra su configuración. Las luces, cámaras y equipos "
                            "no se tocan: solo dejan de pertenecerle."),
                        rx.hstack(
                            rx.alert_dialog.cancel(rx.button("Cancelar", variant="soft", color_scheme="gray")),
                            rx.alert_dialog.action(rx.button("Eliminar", color_scheme="red",
                                                             on_click=EstanciasState.borrar)),
                            spacing="3", justify="end", margin_top="12px",
                        ),
                    ),
                ),
                align="center", spacing="3", width="100%", wrap="wrap",
            ),
        ),
        _tarjeta(
            rx.text("Qué muestra su pantalla", size="3", weight="bold", color=theme.TEXT),
            _interruptor("Plano", "El plano de la planta con sus marcadores.",
                         EstanciasState.op_plano, "plano"),
            _interruptor("Botón de cámaras", "Abre el mural (solo si la tablet tiene cámaras concedidas).",
                         EstanciasState.op_camaras, "camaras"),
            _interruptor("Botón de sirena", "Para elegir el sonido desde la propia tablet.",
                         EstanciasState.op_sirena, "sirena"),
            _interruptor("Hora", "El reloj de la cabecera.", EstanciasState.op_hora, "hora"),
            rx.text("Tamaño de las baldosas", size="2", color=theme.TEXT),
            _opciones(_BALDOSAS, EstanciasState.op_baldosas, EstanciasState.elegir_baldosas),
        ),
        _tarjeta(
            rx.text("Sirena de la tablet", size="3", weight="bold", color=theme.TEXT),
            rx.hstack(
                rx.switch(checked=EstanciasState.sirena_activa,
                          on_change=lambda _v: EstanciasState.sirena_alternar(), size="2"),
                rx.text("Suena si salta la alarma, hasta que alguien confirme o silencie.",
                        size="1", color=theme.MUTED),
                align="center", spacing="3", wrap="wrap",
            ),
            _opciones(_SONIDOS, EstanciasState.sirena_sonido, EstanciasState.sirena_sonido_elegir),
            _opciones(_VOLUMENES, EstanciasState.sirena_volumen, EstanciasState.sirena_volumen_elegir),
            rx.button(rx.icon("volume-2", size=15), "Probar en la tablet",
                      on_click=EstanciasState.sirena_probar, size="2", variant="soft"),
            rx.text("Suena en la tablet de esta estancia, con el sonido y el volumen de arriba, "
                    "aunque la sirena esté desactivada.", size="1", color=theme.MUTED),
        ),
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Elementos", size="3", weight="bold", color=theme.TEXT),
                    rx.text("Apaga el interruptor para ocultar uno solo en esta pantalla "
                            "(sigue siendo de la estancia). Sube o baja para ordenar.",
                            size="1", color=theme.MUTED),
                    spacing="0", align="start",
                ),
                rx.spacer(),
                rx.button(rx.icon("plus", size=14), "Añadir elemento",
                          on_click=EstanciasState.alternar_anadir, size="2", variant="soft"),
                align="center", width="100%", wrap="wrap", spacing="3",
            ),
            rx.cond(
                EstanciasState.anadiendo,
                rx.vstack(
                    rx.foreach(EstanciasState.catalogo, lambda c: rx.button(
                        c["label"].to(str), on_click=EstanciasState.anadir(c["value"].to(str)),
                        size="2", variant="surface", justify_content="start", width="100%")),
                    rx.cond(EstanciasState.catalogo.length() == 0,
                            rx.text("No queda nada por añadir.", size="1", color=theme.MUTED)),
                    spacing="1", width="100%", max_height="280px", overflow_y="auto",
                    padding="8px", border_radius="10px", border=f"1px solid {theme.BORDER}",
                ),
            ),
            rx.vstack(rx.foreach(EstanciasState.miembros, _fila), spacing="2", width="100%"),
            spacing="3", width="100%", align="start",
        ),
        spacing="4", width="100%", align="start",
    )


def estancias_view() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Estancias", size="5", color=theme.TEXT),
            rx.text("Elige, para cada habitación, qué aparece en su pantalla (tablet de pared) "
                    "y cómo. Los cambios se guardan al instante y la tablet los recoge sola.",
                    size="1", color=theme.MUTED),
            spacing="1", align="start",
        ),
        rx.hstack(
            rx.foreach(EstanciasState.salas, _chip_sala),
            rx.form(
                rx.hstack(
                    rx.input(name="name", placeholder="Nueva estancia", size="2", max_length=40,
                             width="170px"),
                    rx.button(rx.icon("plus", size=14), "Crear", type="submit", size="2", variant="soft"),
                    spacing="2",
                ),
                on_submit=EstanciasState.crear, reset_on_submit=True,
            ),
            spacing="2", wrap="wrap", align="center", width="100%",
        ),
        rx.cond(EstanciasState.sel != "", _editor(),
                rx.text("Crea una estancia para empezar.", size="2", color=theme.MUTED)),
        spacing="4", width="100%", align="start", on_mount=EstanciasState.cargar,
    )

