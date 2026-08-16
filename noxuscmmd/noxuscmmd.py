import reflex as rx
from .domains.automations import engine as automations_engine
from .domains.security import watcher
from .ui.pages.index import index_page
from .ui.pages.upload import upload_page
from .ui.pages.dashboard import dashboard_page

STYLE = {
    "@keyframes pulse": {
        "0%": {"opacity": "0.6", "transform": "scale(1)"},
        "100%": {"opacity": "1", "transform": "scale(1.05)"},
    },
    # ALARMA en el plano de planta: un sensor o una puerta que se abre. Rojo,
    # rápido (0.35s, el doble de rápido que el pulso de puerta de abajo) y con
    # halo que se expande — tiene que cantar entre los marcadores en reposo,
    # que van del color que se les haya puesto en el selector del plano y no
    # se mueven (ver ui/views/device_list.py).
    #
    # El translate(-50%, -50%) va repetido en CADA keyframe a propósito: los
    # marcadores se centran sobre su coordenada con ese transform, y una
    # animación CSS pisa la propiedad transform ENTERA mientras corre. Sin
    # repetirlo, el icono perdía el centrado y saltaba media anchura
    # abajo-derecha justo al abrirse el sensor.
    "@keyframes nxAlarmPulse": {
        "0%": {
            "opacity": "1",
            "transform": "translate(-50%, -50%) scale(1)",
            "box-shadow": "0 0 0 0 rgba(239, 68, 68, 0.85)",
        },
        "50%": {
            "opacity": "0.35",
            "transform": "translate(-50%, -50%) scale(1.3)",
            "box-shadow": "0 0 0 14px rgba(239, 68, 68, 0)",
        },
        "100%": {
            "opacity": "1",
            "transform": "translate(-50%, -50%) scale(1)",
            "box-shadow": "0 0 0 0 rgba(239, 68, 68, 0)",
        },
    },
    # Pulso de apertura de una puerta en el plano de planta: mientras el relé
    # está activado, su marcador late y suelta un halo ámbar, para verse de un
    # vistazo que la orden salió y está en curso (ver ui/views/device_list.py
    # y NodesState.pulsing_doors). El translate(-50%,-50%) va incluido porque
    # el marcador lo necesita para centrarse sobre su coordenada, y una
    # animación sobre transform pisaría el que trae por CSS.
    "@keyframes nxDoorPulse": {
        "0%": {
            "transform": "translate(-50%, -50%) scale(1)",
            "box-shadow": "0 0 0 0 rgba(245, 158, 11, 0.75)",
        },
        "70%": {
            "transform": "translate(-50%, -50%) scale(1.25)",
            "box-shadow": "0 0 0 18px rgba(245, 158, 11, 0)",
        },
        "100%": {
            "transform": "translate(-50%, -50%) scale(1)",
            "box-shadow": "0 0 0 0 rgba(245, 158, 11, 0)",
        },
    },
    # Iconos de las teclas del mando virtual (ver ui/dashboard/views/
    # ir_remotes.py). rx.icon dibuja el SVG con un tamaño fijo en px, y el
    # cuerpo del mando se encoge con la altura de la pantalla: sin esto, al
    # achicarse el mando los iconos se quedaban grandes y se salían de su
    # tecla. En % se escalan con ella. Solo el icono principal — los de
    # editar/borrar van aparte y sí son de tamaño fijo.
    # El tamaño sale de --nx-ico, que pone cada tecla: los pares "más/menos"
    # del mando (los dos soles de la luz, las dos aspas de la velocidad) se
    # distinguen SOLO por lo grande que está dibujado el icono.
    ".nx-remote-marker > svg": {
        "width": "var(--nx-ico, 46%)",
        "height": "var(--nx-ico, 46%)",
    },
}


app = rx.App(
    theme=rx.theme(appearance="dark", accent_color="blue"),
    style=STYLE,   # <--- Aquí inyectamos la animación
    head_components=[
        rx.el.link(rel="manifest", href="/manifest.json"),
    ],
    admin_dash=False,
)

# Tareas del CICLO DE VIDA del proceso: arrancan con la aplicación y siguen
# aunque no haya ninguna pestaña abierta. Aquí solo va lo que no puede depender
# de que alguien entre en la web — hasta ahora el vigilante de la alarma se
# arrancaba desde un on_load, así que tras reiniciar el proceso la casa podía
# quedarse armada sin nadie mirando.
app.register_lifespan_task(watcher.run_forever)
app.register_lifespan_task(automations_engine.run_forever)

# IMPORTANTE: on_load se gestiona vía on_mount en index_page (uno por domain
# state: SecurityState, InfraState) para evitar que Reflex arranque los
# background tasks múltiples veces (una por conexión WebSocket nueva). Cada
# domain state protege sus propios background tasks globales con su propio
# flag _STARTED, igual que hacía _SSH_STARTED antes.
app.add_page(dashboard_page, route="/", title="Noxus Control Center")
app.add_page(index_page, route="/clasica", title="Noxus Pro")
app.add_page(upload_page, route="/upload")
app.add_page(dashboard_page, route="/panel", title="Noxus Control Center")
