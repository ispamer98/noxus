"""
Ventana flotante genérica: arrastrable por la cabecera, cerrable, se trae al
frente al interactuar con ella. El arrastre y el z-index se gestionan
enteramente en el DOM (ver el script inyectado por shell/dashboard.py) para
que mover una ventana no dispare ida y vuelta al backend — la posición no
necesita persistir en el estado de Reflex.
"""
import reflex as rx

from .. import theme


def floating_window(
    *children,
    window_id: str,
    title: str,
    icon: str,
    is_open,
    on_close,
    accent: str = theme.ACCENT,
    top: str = "10%",
    left: str = "12%",
    width: str = "560px",
    fullscreen_on_mobile: bool = True,
    dismiss_on_outside="",
):
    """`fullscreen_on_mobile=False` deja la ventana flotando también en el
    móvil, ceñida a su contenido, en vez de ocupar la pantalla entera. Es lo
    que quieren las ventanas pequeñas y de uso rápido (un mando): tragarse
    toda la pantalla para enseñar algo que ocupa un tercio molesta más que
    ayuda.

    `dismiss_on_outside=True` marca la ventana para que se cierre al tocar
    fuera de ella — lo aplica el script del panel (ver ir_remotes.py), no
    Reflex, para no tener que enganchar un listener global por ventana."""
    return rx.cond(
        is_open,
        rx.box(
            rx.box(
                rx.hstack(
                    rx.icon(
                    "grip-horizontal",
                    size=13,
                    color=theme.MUTED,
                    flex_shrink="0",
                    display=["none !important", "none !important", "block !important"],
                ),
                    rx.icon(icon, size=15, color=accent, flex_shrink="0"),
                    rx.text(
                        title,
                        size="2",
                        weight="bold",
                        color=theme.TEXT,
                        letter_spacing="0.03em",
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                    ),
                    rx.spacer(),
                    rx.box(
                        rx.icon("x", size=13, color=theme.MUTED),
                        class_name="nx-window-close",
                        on_click=on_close,
                        cursor="pointer",
                        padding="4px",
                        border_radius="6px",
                        _hover={"background": theme.alpha(theme.DANGER, 0.18), "color": theme.DANGER},
                    ),
                    width="100%",
                    align="center",
                    spacing="2",
                ),
                class_name="nx-window-handle",
                padding="10px 14px",
                background="rgba(15, 23, 42, 0.9)",
                border_bottom=f"1px solid {theme.BORDER}",
                cursor=["default", "default", "grab"],
                flex_shrink="0",
            ),
            rx.box(
                *children,
                padding="16px",
                flex="1",
                overflow_y="auto",
            ),
            class_name="nx-window",
            data_window_id=window_id,
            # Lo lee el script de cierre al tocar fuera (ver ir_remotes.py).
            data_nx_dismiss=dismiss_on_outside,
            position="fixed",
            display="flex",
            flex_direction="column",
            # Móvil: pantalla completa, sin arrastre. Escritorio (md+): ventana
            # flotante en la posición/tamaño pedidos por quien la invoca.
            # Con fullscreen_on_mobile=False flota también en el móvil, ceñida
            # a su contenido y centrada.
            top=["0", "0", top] if fullscreen_on_mobile else ["6%", "6%", top],
            left=(
                ["0", "0", left] if fullscreen_on_mobile
                else ["50%", "50%", left]
            ),
            transform=(
                None if fullscreen_on_mobile
                else ["translateX(-50%)", "translateX(-50%)", "none"]
            ),
            right=["0", "0", "auto"] if fullscreen_on_mobile else "auto",
            bottom=["0", "0", "auto"] if fullscreen_on_mobile else "auto",
            width=["100vw", "100vw", width] if fullscreen_on_mobile else width,
            height=["100dvh", "100dvh", "auto"] if fullscreen_on_mobile else "auto",
            max_width=["100vw", "100vw", "94vw"] if fullscreen_on_mobile else "94vw",
            max_height=(
                ["100dvh", "100dvh", "80vh"] if fullscreen_on_mobile else "88vh"
            ),
            background=theme.BG_WINDOW,
            border=(
                ["none", "none", f"1px solid {theme.BORDER_STRONG}"] if fullscreen_on_mobile
                else f"1px solid {theme.BORDER_STRONG}"
            ),
            border_radius=["0", "0", "12px"] if fullscreen_on_mobile else "16px",
            box_shadow="0 24px 64px -12px rgba(0, 0, 0, 0.75)",
            z_index="200",
            overflow="hidden",
        ),
        rx.fragment(),
    )
