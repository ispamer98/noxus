import reflex as rx

def status_row(name: str, ip: str, online: bool, icon: str, on_rdp=None):
    color  = rx.cond(online, "green", "red")
    # Separamos el punto del texto
    punto_status = rx.cond(online, "🟢", "🔴")
    texto_status = rx.cond(online, " En línea", " Sin conexión")

    icon_style = {
        "transition": "transform 0.2s",
        "_hover": {
            "transform": "scale(1.4)",
        },
    }
    
    style_clickable = {"cursor": "pointer"} if on_rdp is not None else {}

    row_content = rx.hstack(
        rx.icon(icon, color=color, style=icon_style),
        rx.text(name, weight="medium"),
        rx.spacer(),
        
        # Grupo de Estado + IP
        rx.hstack(
            # Este es el PUNTITO (Se ve siempre: móvil y PC)
            rx.text(punto_status, size="1"),
            
            # Este es el TEXTO (Solo se ve en PC)
            rx.text(
                texto_status, 
                color=color, 
                display=["none", "none", "block"], 
                white_space="nowrap",
            ),
            
            # Esta es la IP (Se ve siempre)
            rx.text(
                ip, 
                color="gray.300", 
                size="2",
                white_space="nowrap",
            ),
            spacing="2", 
            align="center",
        ),
        
        width="100%", 
        align="center", 
        spacing="3",
        style=style_clickable,
    )

    if on_rdp is not None:
        return rx.popover.root(
            rx.popover.trigger(
                rx.box(row_content, width="100%")
            ),
            rx.popover.content(
                rx.button(
                    f"Conectar con {name} ⌘",
                    on_click=on_rdp, 
                    variant="soft",
                    style={
                        "border": "3px solid #000000",
                        "border-radius": "12px",       
                        "padding": "8px 16px",
                        "cursor": "pointer",
                    }
                ),
                style={
                    "padding": "0",
                    "margin": "0",
                    "boxShadow": "none",
                    "border": "none",
                    "minWidth": "auto",
                    "minHeight": "auto",
                }
            ),
        )
    
    return row_content