import reflex as rx

config = rx.Config(
    app_name="noxuscmmd",
    api_url="https://access.noxuscmmd.uk",
    deploy_url="https://access.noxuscmmd.uk",
    # Añade esto si no está, para forzar el puerto de escucha
    backend_port=8000, 
    frontend_port=3000,
    admin_dash=False,  # Opcional: quita el panel de admin si no lo usas
    overlay_component=None,  # <--- ESTA ES LA CLAVE para quitar el logo
    app_styles={
        ".reflex-overlay": rx.Style(display="none"),
    },
    show_built_with_reflex=False,
    show_reflex_badge=False,
)
