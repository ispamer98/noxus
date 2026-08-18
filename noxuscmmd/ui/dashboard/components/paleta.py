"""
La paleta de comandos: Ctrl+K, escribe dos letras, hecho.

Cómo llega el atajo de teclado hasta Python, que es la única parte con truco: un
`keydown` de JavaScript no puede invocar un evento de Reflex directamente, así
que el script pulsa un elemento oculto que sí lleva el evento colgado
(`.click()` funciona en un elemento con display:none). Es el mismo apaño con el
que el plano manda las posiciones al soltar un icono.

Se monta DENTRO del panel, no al nivel de la página, para que un dispositivo sin
acceso no la tenga ni cargada: la paleta es la lista de todo lo que se puede
hacer en la casa, así que no es algo que deba existir en una pantalla cerrada.
"""
import reflex as rx

from ....domains.devices.paleta_state import PaletaState
from .. import theme

# Ctrl+K y ⌘K. También se cancela el atajo del navegador (en Chrome, Ctrl+K va a
# la barra de direcciones), que si no se lleva el foco y la paleta se abre detrás.
ATAJO = """
document.addEventListener('keydown', (e) => {
    const combo = (e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K');
    if (!combo) return;
    e.preventDefault();
    document.getElementById('nx-abrir-paleta')?.click();
});
"""


def _resultado(c: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon(c["icono"].to(str), size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.text(c["etiqueta"], size="2", color=theme.TEXT),
        rx.spacer(),
        rx.badge(c["familia"], size="1", variant="surface", flex_shrink="0"),
        on_click=PaletaState.ejecutar(c["id"]),
        cursor="pointer", align="center", spacing="3", width="100%",
        padding="8px 10px", border_radius="8px",
        _hover={"background": theme.BG_CARD_HOVER},
    )


def paleta_comandos() -> rx.Component:
    return rx.fragment(
        rx.script(ATAJO),
        # El puente del atajo. Oculto pero pulsable desde el script de arriba.
        rx.box(id="nx-abrir-paleta", on_click=PaletaState.abrir, display="none"),
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.hstack(
                        rx.icon("search", size=16, color=theme.MUTED),
                        rx.input(
                            value=PaletaState.busqueda,
                            on_change=PaletaState.set_busqueda,
                            placeholder="Encender salón, abrir puerta, armar...",
                            # Enfocado al abrir: la paleta se abre para escribir,
                            # y tener que pulsar dentro antes la haría inútil.
                            auto_focus=True,
                            variant="soft", size="3", width="100%",
                        ),
                        align="center", spacing="2", width="100%",
                    ),
                    rx.cond(
                        PaletaState.sin_resultados,
                        rx.box(
                            rx.text("Nada que coincida.", size="2",
                                    color=theme.MUTED),
                            padding="18px 10px",
                        ),
                        rx.vstack(
                            rx.foreach(PaletaState.resultados, _resultado),
                            spacing="0", width="100%",
                            max_height="52vh", overflow_y="auto",
                        ),
                    ),
                    rx.text("Ctrl+K para abrirla · Esc para cerrar", size="1",
                            color=theme.MUTED,
                            style={"font-size": "0.7rem", "opacity": "0.7"}),
                    spacing="2", width="100%",
                ),
                background=theme.BG_WINDOW,
                border=f"1px solid {theme.BORDER_STRONG}",
                max_width="min(560px, 94vw)",
            ),
            open=PaletaState.abierta,
            # Cerrar con Esc o pulsando fuera pasa por aquí, así que el estado no
            # se queda diciendo que está abierta cuando ya no lo está.
            on_open_change=PaletaState.set_abierta,
        ),
    )


def boton_paleta() -> rx.Component:
    """La lupa de la barra superior — la otra forma de abrirla, para quien no
    tiene teclado (que en esta casa son los dos móviles)."""
    return rx.box(
        rx.icon("search", size=18, color=theme.MUTED),
        on_click=PaletaState.abrir,
        cursor="pointer", padding="8px", border_radius="8px", flex_shrink="0",
        _hover={"background": theme.alpha(theme.ACCENT, 0.10)},
        title="Buscar y ejecutar (Ctrl+K)",
    )
