import reflex as rx

from .. import theme


def stat_tile(label: str, value, icon: str, color=theme.ACCENT, hint: str | None = None, icon_bg=None):
    """`color` puede ser un Var reactivo (p.ej. rx.cond(...)) para tiles con
    estado dinámico; en ese caso hay que pasar `icon_bg` ya calculado, porque
    theme.alpha() solo sabe operar sobre literales Python (hex fijos)."""
    if icon_bg is None:
        icon_bg = theme.alpha(color, 0.14)
    info = [
        rx.text(
            label,
            size="1",
            color=theme.MUTED,
            letter_spacing="0.06em",
            text_transform="uppercase",
            weight="medium",
            white_space="nowrap",
        ),
        rx.text(
            value,
            size=rx.breakpoints(initial="3", md="4"),
            weight="bold",
            color=theme.TEXT,
            white_space="nowrap",
            overflow="hidden",
            text_overflow="ellipsis",
            max_width="100%",
        ),
    ]
    if hint is not None:
        # OJO: comparar `if hint:` rompe cuando hint es un Var reactivo (una
        # f-string con NodesState.algo.length() dentro) — Reflex no permite
        # evaluar la verdad de un Var en Python. `is not None` es seguro
        # porque None siempre es un literal, nunca un Var.
        info.append(rx.text(hint, size="1", color=theme.MUTED))

    return rx.hstack(
        rx.box(
            rx.icon(icon, size=18, color=color),
            padding=["8px", "8px", "10px"],
            border_radius="10px",
            background=icon_bg,
            flex_shrink="0",
        ),
        rx.vstack(*info, spacing="0", align="start", min_width="0", width="100%"),
        spacing="3",
        align="center",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="12px",
        padding=["12px", "12px", "16px"],
        backdrop_filter="blur(10px)",
        flex="1",
        min_width=["135px", "150px", "200px"],
        overflow="hidden",
        transition="background 0.15s ease, border-color 0.15s ease",
        _hover={"background": theme.BG_CARD_HOVER, "border_color": theme.BORDER_STRONG},
    )
