import reflex as rx

config = rx.Config(
    app_name="noxuscmmd",
    frontend_port=3000,
    backend_port=8000,
    api_url = "https://panel.noxuscmmd.uk",   # Sin /api
    deploy_url="https://panel.noxuscmmd.uk",
    admin_dash=False,  # Opcional: quita el panel de admin si no lo usas
    overlay_component=None,  # <--- ESTA ES LA CLAVE para quitar el logo
    app_styles={
        ".reflex-overlay": rx.Style(display="none"),
    },
    show_built_with_reflex=False,
    show_reflex_badge=False,
    telemetry_enabled=False,
)
