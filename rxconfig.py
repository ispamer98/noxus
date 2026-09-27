import reflex as rx

config = rx.Config(
    app_name="noxuscmmd",
    frontend_port=3000,
    backend_port=8000,
    # api_url NO se pone al dominio, y es a proposito. El JS de Reflex 0.8.28
    # (reflex/.templates/web/utils/state.js, SAME_DOMAIN_HOSTNAMES) sustituye
    # los hostnames `localhost`, `0.0.0.0` y `::` por `window.location.hostname`
    # al cargar, y si la pagina va por HTTPS sube a `wss:` y quita el puerto.
    # O sea que con este valor el panel habla con el backend del MISMO sitio
    # desde el que se sirvio:
    #
    #   https://panel.noxuscmmd.uk  -> wss://panel.noxuscmmd.uk/_event   (VPS)
    #   http://100.98.98.1:3000     -> ws://100.98.98.1:8000/_event      (casa)
    #
    # Eso hace dos cosas. Una, que cambiar de dominio ya no obligue a
    # recompilar. Y dos, que la entrada por Tailscale siga funcionando **aunque
    # el VPS este caido** — con el dominio puesto a fuego, el panel cargaba
    # pero no respondia, porque el websocket seguia yendo al VPS.
    #
    # Que quede claro el limite: eso cubre que falle lo de FUERA (el VPS, el
    # DNS, la fibra). Si el que no arranca es este servicio, por Tailscale
    # tampoco hay nada: el :3000 y el :8000 son el mismo proceso.
    # Comprobado en el codigo de la version instalada, no de memoria.
    api_url="http://localhost:8000",
    deploy_url="https://panel.noxuscmmd.uk",
    admin_dash=False,  # Opcional: quita el panel de admin si no lo usas
    # Quien puede hablar con este backend desde el navegador de otra persona.
    # Reflex trae `*` por defecto, y con `*` cualquier web que visite alguien
    # podria lanzar peticiones contra el panel de esta casa. Hoy no llegaba a
    # explotar porque la cookie de sesion es `same_site="lax"` y el navegador
    # no la adjunta desde fuera, pero eso es una red que se rompe sola el dia
    # que alguien toque ese flag. Se cierra al unico origen que existe.
    #
    # Comprobado con el usuario el 2026-09-20: al panel se entra SIEMPRE por
    # https://panel.noxuscmmd.uk, nunca por http://192.168.1.x:3000. Va tambien
    # la IP de Tailscale de esta casa, que es la puerta de emergencia si el VPS
    # se cae: cerrar el CORS solo al dominio la dejaba inservible. Si algun dia
    # vuelve el acceso por IP de la LAN, hay que anadir ese origen aqui.
    cors_allowed_origins=[
        "https://panel.noxuscmmd.uk",   # la via normal, por el VPS
        "http://100.98.98.1:3000",      # Tailscale: la via de emergencia
    ],
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
