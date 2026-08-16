"""
Los dos trozos de JavaScript que hacen falta para las notificaciones: leer la
suscripción que ya tenga el navegador y crear una nueva.

Viven aquí y no en la vista porque tienen que poder encadenarse: al entrar en
el panel se lee la suscripción, y si resulta que este aparato no está vinculado
hay que lanzar el alta a continuación. Esa decisión la toma PushState mirando
suscriptores.json, así que es PushState quien necesita poder devolver el
segundo script — y para eso tiene que tenerlo a mano sin importar la capa de
interfaz.
"""
import json

from .push import VAPID_PUBLIC

# Devuelve el endpoint de la suscripción de este navegador, o "" si no hay.
LEER_SUSCRIPCION = """
(async function() {
    try {
        if (!('serviceWorker' in navigator)) return "";
        // navigator.serviceWorker.ready no resuelve NUNCA si no hay ningún
        // service worker registrado (ej: justo después de borrar el storage
        // del sitio) — con una carrera contra un timeout evitamos que esto
        // se quede colgado para siempre y bloquee la comprobación.
        const timeout = new Promise((resolve) => setTimeout(() => resolve(null), 3000));
        const reg = await Promise.race([navigator.serviceWorker.ready, timeout]);
        if (!reg) return "";
        const sub = await reg.pushManager.getSubscription();
        return sub ? sub.endpoint : "";
    } catch (e) {
        return "";
    }
})();
"""


def _alta(mensaje: str, exigir_permiso_previo: bool, rehacer: bool = False) -> str:
    """Genera el script de alta.

    EL ORDEN IMPORTA, y es el motivo de que esto fallara la mitad de las veces
    en iPhone y en Mac: Notification.requestPermission() solo vale si se llama
    mientras el navegador considera que estás "recién pulsando", y Safari da
    para eso una ventana de tiempo muy corta. La versión anterior abría primero
    el window.prompt del nombre y registraba el Service Worker, y para cuando
    llegaba a pedir el permiso esa ventana ya se había cerrado: el navegador lo
    rechazaba de oficio. De ahí lo de "pone permiso denegado, pero al segundo o
    tercer intento entra" — en los reintentos el permiso ya había quedado
    concedido de una vez anterior, o se llegaba a tiempo por poco.

    Ahora se pide el permiso lo PRIMERO, sin ningún await ni ningún diálogo por
    delante. El nombre se pregunta después, que no tiene prisa. En Chrome no se
    notaba porque es mucho más permisivo con esto.

    `exigir_permiso_previo`: al entrar en el panel no hay pulsación ninguna, así
    que ni se intenta pedirlo — se mira si ya estaba dado y, si no, se avisa
    para que alguien pulse (ese toque es justo lo que hace falta).

    `rehacer`: tira la suscripción anterior antes de crear la nueva. Es lo que
    arregla un dispositivo que dejó de recibir avisos porque su suscripción
    caducó en el servidor de Apple o Google."""
    guarda = """
        if (!('Notification' in window) || !('serviceWorker' in navigator)) return "NO_SOPORTADO";
        if (Notification.permission !== 'granted') return "SIN_PERMISO";
    """ if exigir_permiso_previo else """
        if (!('Notification' in window) || !('serviceWorker' in navigator)) return "NO_SOPORTADO";
        // Lo PRIMERO, aprovechando la pulsación que acaba de ocurrir.
        if (Notification.permission === 'denied') return "PERMISO_BLOQUEADO";
        if (Notification.permission !== 'granted') {
            const perm = await Notification.requestPermission();
            if (perm !== 'granted') return "PERMISO_DENEGADO";
        }
    """

    limpiar = """
        try {
            const reg0 = await navigator.serviceWorker.getRegistration();
            const vieja = reg0 && await reg0.pushManager.getSubscription();
            if (vieja) await vieja.unsubscribe();
        } catch (e) { console.warn("No se pudo soltar la suscripción anterior", e); }
    """ if rehacer else ""

    return f"""
(async function() {{
    try {{
        {guarda}
        let nombre = window.prompt({json.dumps(mensaje)}, {json.dumps("")});
        if (nombre === null) return "USER_CANCEL";
        nombre = nombre.trim();
        if (nombre === "") {{
            alert("El nombre no puede estar vacío. Cancelado.");
            return "USER_CANCEL";
        }}

        let reg;
        for (let intentos = 0; intentos < 3; intentos++) {{
            try {{
                reg = await navigator.serviceWorker.register('/sw.js');
                await navigator.serviceWorker.ready;
                break;
            }} catch (e) {{
                console.warn("Intento " + (intentos+1) + " fallido", e);
                await new Promise(r => setTimeout(r, 500));
            }}
        }}
        if (!reg) throw new Error("No se pudo registrar el Service Worker");
        {limpiar}

        const publicKey = '{VAPID_PUBLIC}';
        const toUint8 = (b) => {{
            const pad = '='.repeat((4 - b.length % 4) % 4);
            const b64 = (b + pad).replace(/-/g, '+').replace(/_/g, '/');
            const raw = window.atob(b64);
            const out = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
            return out;
        }};

        // Por si acaso: si ya hay una suscripción viva se reutiliza en vez de
        // pedir otra, que en Safari devuelve error en lugar de la existente.
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {{
            sub = await reg.pushManager.subscribe({{
                userVisibleOnly: true,
                applicationServerKey: toUint8(publicKey)
            }});
        }}

        return JSON.stringify({{ subscription: sub, nombre: nombre }});
    }} catch (err) {{
        if (err.name === "NotAllowedError") return "PERMISO_BLOQUEADO";
        return "ERROR_" + err.message;
    }}
}})();
"""


SUSCRIBIR = _alta(
    "Nombre para este dispositivo (ej: Mi iPhone, PC Oficina):",
    exigir_permiso_previo=False,
)

SUSCRIBIR_AL_ENTRAR = _alta(
    "Este dispositivo no está vinculado. Ponle un nombre para recibir avisos y "
    "que sus acciones queden identificadas en los registros:",
    exigir_permiso_previo=True,
)

# Para un dispositivo que ya estaba vinculado pero dejó de recibir avisos.
REACTIVAR = _alta(
    "Vamos a volver a activar los avisos en este dispositivo. Confirma su nombre:",
    exigir_permiso_previo=False,
    rehacer=True,
)

# Solo suelta la suscripción del navegador; borrar la ficha del servidor es
# cosa de PushState.desvincular.
OLVIDAR = """
(async function() {
    try {
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = reg && await reg.pushManager.getSubscription();
        if (sub) await sub.unsubscribe();
        return "OK";
    } catch (e) {
        return "OK";
    }
})();
"""
