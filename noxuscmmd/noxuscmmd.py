"""
Punto de entrada de la aplicación Reflex: aquí nace el objeto `app` que sirve
`reflex run`, y con él, todo lo que no depende de que alguien tenga el panel
abierto en un navegador.

Tres cosas viven en este archivo y en ningún otro:

  1. LAS RUTAS HTTP PROPIAS (`_api`, vía `api_transformer`): lo que Reflex 0.8
     no sabe servir por su cuenta (webhooks, descargas con cabeceras propias,
     endpoints que no son un componente). Cada dominio declara sus `RUTAS` y
     aquí solo se juntan.
  2. LA ANIMACIÓN GLOBAL (`STYLE`): los `@keyframes` que usan varios
     componentes sueltos (el plano de planta, el mando virtual) y que Reflex
     necesita inyectar una sola vez a nivel de app, no por componente.
  3. LAS TAREAS DE FONDO (`register_lifespan_task`): todo lo que vigila la
     casa (alarma, presencia, movimiento, tiempo en línea, backups, métricas,
     Alexa, SSH) tiene que seguir corriendo con el navegador cerrado — de ahí
     que cuelguen del PROCESO y no de una sesión ni de un `on_load`. El orden
     de arranque no importa entre ellas: cada una se resuelve sola si su
     dependencia (un fichero, una conexión) todavía no está lista.

`/` y `/panel` sirven la MISMA vista a propósito: quitar cualquiera de las dos
rompería enlaces ya guardados (el acceso directo del móvil apunta a `/panel`,
ver ui/pages/dashboard.py y el manifest en assets/).
"""
import reflex as rx
from starlette.applications import Starlette

from .domains.cameras import endpoint as fotograma_endpoint
from .domains.cameras import fotogramas
from .domains.devices import alexa_cloud_endpoint, alexa_cloud_sync, hue, voz
from .domains.notifications import endpoint as aviso_endpoint
from .domains.automations import engine as automations_engine
from .domains.infra import backups
from .domains.infra import metricas
from .domains.infra import ping_motor
from .core.ssh_manager import SSHManager
from .domains.nodes import planos
from .domains.security import logs_store
from .domains.security import presencia_motor
from .domains.cameras import movimiento_motor
from .domains.security import watcher
from .ui.pages.upload import upload_page
from .ui.pages.dashboard import EVENTOS_DE_ENTRADA, dashboard_page

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


# Rutas HTTP propias del backend, fuera del websocket de Reflex. Es lo que
# admite Reflex 0.8 para añadir rutas propias.
#
#   - Los botones de los avisos: cuando alguien pulsa "Visto" en la pantalla de
#     bloqueo no hay ninguna pestaña abierta con la que hablar.
#   - Los fotogramas que guarda la alarma: no se sirven como estático porque son
#     imágenes del interior de la casa y hay que comprobar la sesión (ver
#     domains/cameras/endpoint.py).
#
# Las dos entran por ^/api/.*$, que es la regla que el túnel ya manda al :8000.
_api = Starlette(routes=[*aviso_endpoint.RUTAS, *fotograma_endpoint.RUTAS,
                         *planos.RUTAS,
                         *alexa_cloud_endpoint.RUTAS,
                         *voz.RUTAS])

app = rx.App(
    api_transformer=_api,
    theme=rx.theme(appearance="dark", accent_color="blue"),
    style=STYLE,   # <--- Aquí inyectamos la animación
    head_components=[
        rx.el.link(rel="manifest", href="/manifest.json"),
        # iOS no lee los iconos del manifest: para el acceso directo de la
        # pantalla de inicio mira SOLO esto. Sin ello, el iPhone se inventa el
        # icono con una captura de la página.
        rx.el.link(rel="apple-touch-icon", href="/icono-192.png"),
        # Color de la barra del navegador y de la de estado en la aplicación
        # instalada. Es BG_APP (ui/dashboard/theme.py): sin esto el móvil pinta
        # una franja blanca encima del panel, que es oscuro entero.
        rx.el.meta(name="theme-color", content="#05070a"),
        rx.el.meta(name="mobile-web-app-capable", content="yes"),
        rx.el.meta(name="apple-mobile-web-app-capable", content="yes"),
        rx.el.meta(name="apple-mobile-web-app-status-bar-style", content="black"),
        # A propósito NO se pone apple-mobile-web-app-title: iOS usaría ese
        # texto fijo y dejaría de hacer caso al short_name del manifest, que es
        # justo lo que se puede cambiar desde Ajustes (ver
        # domains/notifications/branding.py).
    ],
    admin_dash=False,
)

# Tareas del CICLO DE VIDA del proceso: arrancan con la aplicación y siguen
# aunque no haya ninguna pestaña abierta. Aquí solo va lo que no puede depender
# de que alguien entre en la web — hasta ahora el vigilante de la alarma se
# arrancaba desde un on_load, así que tras reiniciar el proceso la casa podía
# quedarse armada sin nadie mirando.

# El histórico de eventos, antes de nada: la copia de seguridad de arranque va
# unas líneas más abajo y no puede copiar un fichero que todavía no existe.
logs_store.preparar()

# Y de paso se tira lo caducado. Al arrancar y no con un temporizador porque no
# hay ninguna prisa: los fotogramas se guardan un año y el registro no se poda
# (LOGS_MAX_DIAS=0), así que con que esto pase de vez en cuando sobra, y el
# servicio se reinicia a menudo. Si algún día el panel se queda meses sin
# reiniciar, esto es lo que habrá que colgar de la tarea diaria de las copias.
try:
    _fotos = fotogramas.purgar()
    _eventos = logs_store.purgar()
    _muestras = logs_store.purgar_metricas(metricas.MAX_DIAS)
    if _fotos or _eventos or _muestras:
        print(f"🧹 Purga: {_fotos} fotograma(s), {_eventos} evento(s) y "
              f"{_muestras} muestra(s) caducados")
except Exception as e:
    print(f"⚠️ No se pudo purgar lo caducado: {e}")

app.register_lifespan_task(watcher.run_forever)
app.register_lifespan_task(automations_engine.run_forever)
# Copia de seguridad de los JSON de la casa: una al arrancar (si hoy no hay) y
# una diaria de madrugada. Va aquí por lo mismo que las dos de arriba — una
# copia que dependiera de que alguien tenga el panel abierto a las 4:00 no
# serviría de nada.
app.register_lifespan_task(backups.run_forever)
# Muestreo de temperatura y equipos en línea para el histórico. Aquí y no en una
# sesión por el mismo motivo que las tres de arriba: un histórico que solo se
# rellena cuando alguien tiene la web abierta tendría un agujero cada noche.
app.register_lifespan_task(metricas.run_forever)

# Quién está en línea. De proceso y no por sesión: dependía de que hubiera un
# navegador abierto y, cuando ese navegador se cerraba, el estado de los
# equipos se quedaba congelado hasta reiniciar el servicio (ver la cabecera de
# infra/ping_motor.py).
app.register_lifespan_task(ping_motor.run_forever)

# La conexión SSH persistente (y su keepalive, que la reconecta si se cae).
# Misma razón que el ping: no puede depender de que haya un navegador abierto.
app.register_lifespan_task(SSHManager.run_forever)
# El puente Hue falso con el que los Echo descubren los comandos de voz sin
# skill, sin cuenta de Amazon y sin nube (ver domains/devices/hue.py). Si no
# puede abrir el puerto 80 lo dice en el log y se apaga: es un extra, y que
# Alexa no funcione no puede impedir que la casa arranque con su alarma.
app.register_lifespan_task(hue.run_forever)
app.register_lifespan_task(alexa_cloud_sync.run_forever)
# La simulación de presencia. De proceso y no por sesión porque tiene que
# funcionar con todos los navegadores cerrados: es justo entonces cuando hace
# falta. Solo mueve algo si está encendida en Ajustes Y el sistema está armado
# (ver domains/security/presencia_motor.py).
app.register_lifespan_task(presencia_motor.run_forever)
# La detección de movimiento por comparación de fotogramas. También de proceso:
# vigilar solo mientras alguien tiene el panel abierto no vigila nada. Arranca
# apagada y solo mira las cámaras que se marquen (ver cameras/movimiento_motor).
app.register_lifespan_task(movimiento_motor.run_forever)

# Los eventos de entrada van como on_load y NO como on_mount del componente.
# Es a propósito y es justo al revés de lo que ponía aquí antes: Reflex reenvía
# los on_load en CADA (re)conexión del websocket, y eso es lo que hace que una
# pestaña que vuelve de segundo plano recupere sus bucles de refresco sin
# recargar la página. Con on_mount solo corrían al montar el componente, así
# que tras una reconexión la pantalla se quedaba viva pero sorda —una solicitud
# de acceso nueva no aparecía— y no había más remedio que cerrar y abrir.
#
# Lo que antes lo desaconsejaba —que se arrancaran bucles de más, uno por
# conexión— ya no puede pasar: los de sesión se relevan entre ellos (ver
# core/sesiones.py) y los de proceso siguen protegidos por su flag _STARTED.
app.add_page(dashboard_page, route="/", title="Noxus Control Center",
             on_load=EVENTOS_DE_ENTRADA)
app.add_page(upload_page, route="/upload")
app.add_page(dashboard_page, route="/panel", title="Noxus Control Center",
             on_load=EVENTOS_DE_ENTRADA)
