import reflex as rx

config = rx.Config(
    app_name="noxuscmmd",
    frontend_port=3000,
    backend_port=8000,
    api_url = "https://panel.noxuscmmd.uk",   # Sin /api
    deploy_url="https://panel.noxuscmmd.uk",
    admin_dash=False,  # Opcional: quita el panel de admin si no lo usas
    # Reflex crea un evento `set_<var>` por cada variable PÚBLICA de cada
    # estado, y ese evento lo puede invocar cualquier navegador conectado por
    # el websocket, pase o no por un botón de la interfaz. En un panel que
    # gobierna la alarma y las cerraduras de una casa eso sobra.
    #
    # Se puede poner en False sin romper nada porque ningún set_ automático se
    # usa: los únicos `.set_*` que aparecen en el código son los que están
    # definidos a mano y los de librerías (rx.set_clipboard, setvar, y
    # set_missing_host_key_policy / set_socket, que son de paramiko).
    # Comprobado cruzando los usados contra los declarados, no de memoria.
    #
    # Reflex ya avisa de que este será el valor por defecto más adelante.
    state_auto_setters=False,
    overlay_component=None,  # <--- ESTA ES LA CLAVE para quitar el logo
    app_styles={
        ".reflex-overlay": rx.Style(display="none"),
    },
    show_built_with_reflex=False,
    show_reflex_badge=False,
    telemetry_enabled=False,
)
