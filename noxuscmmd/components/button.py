import reflex as rx

def control_button(text: str, icon: str, color: str, on_click):
    # Mapeo de colores para los glows neón
    glows = {
        "green": "rgba(34, 197, 94, 0.4)",
        "red": "rgba(239, 68, 68, 0.4)",
        "orange": "rgba(249, 115, 22, 0.4)",
        "blue": "rgba(59, 130, 246, 0.4)",
        "pink": "rgba(236, 72, 153, 0.4)",
        "gray": "rgba(107, 114, 128, 0.4)"
    }
    
    return rx.button(
        rx.hstack(
            rx.icon(icon, size=22),
            rx.text(text, size="3", weight="bold"),
            width="100%",
            justify="center",
        ),
        on_click=on_click,
        color_scheme=color,
        width="100%",
        height="3.8em",
        border_radius="15px",
        style={
            "box_shadow": f"0 4px 15px {glows.get(color, 'rgba(0,0,0,0.5)')}",
            "_hover": {
                "transform": "scale(1.03)",
                "filter": "brightness(1.2)",
                "box_shadow": f"0 6px 25px {glows.get(color, 'rgba(0,0,0,0.5)')}",
            },
            "transition": "all 0.2s ease",
        }
    )