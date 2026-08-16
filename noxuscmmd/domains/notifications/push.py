"""
Envío de notificaciones Web Push. Función plana: no necesita ser reactiva,
cualquier dominio (seguridad, cámaras...) puede llamarla directamente.
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@noxuscmmd.uk")
SUSCRIPTORES_FILE = "suscriptores.json"


TODOS = "todos"


def enviar_notificacion(titulo: str, mensaje: str, destino=TODOS) -> None:
    """`destino`: "todos", el nombre de un dispositivo, o una lista de nombres.

    Acepta las tres formas porque las llamadas automáticas (una alarma que
    salta) van siempre a todo el mundo con una cadena, y el envío a mano deja
    marcar varios. Convertir la cadena en lista aquí evita que cada sitio que
    manda un aviso tenga que acordarse de en qué forma lo espera esto."""
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
