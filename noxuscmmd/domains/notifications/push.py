"""
Envío de notificaciones Web Push. Función plana: no necesita ser reactiva,
cualquier dominio (seguridad, cámaras...) puede llamarla directamente.
"""
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@noxuscmmd.uk")
SUSCRIPTORES_FILE = "suscriptores.json"


TODOS = "todos"


def enviar_notificacion(titulo: str, mensaje: str, destino=TODOS,
                        tag: str = "", silencioso: bool = False,
                        acciones: tuple | list = (), url: str = "") -> None:
    """`destino`: "todos", el nombre de un dispositivo, o una lista de nombres.

    Acepta las tres formas porque las llamadas automáticas (una alarma que
    salta) van siempre a todo el mundo con una cadena, y el envío a mano deja
    marcar varios. Convertir la cadena en lista aquí evita que cada sitio que
    manda un aviso tenga que acordarse de en qué forma lo espera esto.

    `tag` agrupa: dos avisos con el mismo tag no se apilan en el móvil, el
    segundo sustituye al primero. Se le pasa algo que identifique al ELEMENTO
    ("alerta:<grupo>:<sensor>", "regla:<id>"), no al evento — la gracia es que
    la tercera apertura de la misma puerta ocupe la misma notificación que la
    primera.

    Sin tag NO se agrupa nada: cada aviso recibe uno único. Es a propósito y al
    revés de lo que parece cómodo — un genérico compartido haría que dos
    mensajes escritos a mano se taparan entre sí, y perder un mensaje distinto
    es mucho peor que ver dos veces el mismo. Agrupar es una decisión de quien
    manda el aviso, no el comportamiento por defecto.

    `silencioso` llega sin sonido ni vibración: para lo informativo (un equipo
    que vuelve a estar en línea). Lo que es de alarma nunca lo usa.

    `url` es a dónde lleva el aviso al pulsarlo, dentro del panel
    ("/panel?vista=logs"). Sin ella se abre el panel por donde estuviera, que
    para un aviso de movimiento obligaba a buscar el evento a mano. Un móvil con
    el service worker viejo la ignora y abre el panel, como hasta ahora."""
    from pywebpush import webpush

    if not os.path.exists(SUSCRIPTORES_FILE):
        return
    a_todos = destino == TODOS
    elegidos = set() if a_todos else ({destino} if isinstance(destino, str) else set(destino))
    if not a_todos and not elegidos:
        return  # nadie marcado: no se manda nada
    try:
        with open(SUSCRIPTORES_FILE) as f:
            subs = json.load(f)
        payload = json.dumps({
            "title": titulo, "body": mensaje,
            "icon": "/icono.png", "badge": "/icono.png",
            # Los lee assets/sw.js. Un dispositivo con el service worker viejo
            # los ignora sin romperse: sigue enseñando título y cuerpo igual.
            # Sin tag, uno único por envío — ver el docstring.
            "tag": tag or f"noxus:{time.time_ns()}",
            "silencioso": silencioso,
            # Botones de la propia notificación. Los pinta assets/sw.js; un
            # dispositivo con el service worker viejo los ignora y sigue viendo
            # el aviso normal, así que añadirlos no rompe nada.
            "acciones": list(acciones or ()),
            # A dónde lleva al pulsarla. Se valida en el sw contra su propio
            # origen: aquí solo se ponen rutas del panel.
            "url": url or "",
        })
        for sub in subs:
            if not a_todos and sub.get("nombre_usuario") not in elegidos:
                continue
            try:
                webpush(
                    subscription_info=sub, data=payload,
                    vapid_private_key=VAPID_PRIVATE,
                    vapid_claims={"sub": VAPID_EMAIL}, timeout=5,
                )
                print(f"✅ Push → {sub.get('nombre_usuario', '?')}")
            except Exception as ex:
                print(f"❌ Push → {sub.get('nombre_usuario', '?')}: {ex}")
    except Exception as e:
        print(f"❌ enviar_notificacion: {e}")
