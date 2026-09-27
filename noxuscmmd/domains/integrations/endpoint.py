"""
La entrada de n8n a la casa: `POST /api/integraciones/aviso`.

Es la otra mitad de `n8n.py`. Aquel manda hacia fuera lo que pasa; este deja
que el workflow conteste mandando un aviso al móvil de quien hizo la acción,
que es lo que cierra el círculo «has encendido la luz de la habitación».

QUÉ NO ES: no es una vía para accionar la casa. Aquí solo se mandan avisos.
Para que n8n encienda o abra algo ya está `/api/voz`, que pasa por el catálogo
de comandos, comprueba permisos por dispositivo y registra quién lo pidió. Una
segunda puerta que accionara hardware sin ese control es exactamente el agujero
que no queremos: el panel abre puertas de verdad.

AUTENTICACIÓN: el mismo secreto compartido que se manda al salir
(`X-Noxus-Token`), comparado con `compare_digest` para no filtrar por el tiempo
de respuesta cuántos caracteres se acertaron. No se reutiliza la cookie de
sesión ni la clave de voz porque quien llama no es un dispositivo de nadie: es
un servicio, no tiene dueño y no debe heredar los permisos de ninguna persona.

DESTINO DESCONOCIDO ES UN ERROR, NO UN SILENCIO. `push.enviar_notificacion` se
calla si el nombre no está en la lista, y desde n8n eso es indistinguible de
«enviado»: la ejecución sale verde y al móvil no llega nada. Aquí se comprueba
antes y se contesta 404, que es lo que hace que el fallo se vea en el historial
de n8n en vez de en una hora de buscar por qué no suena el teléfono.
"""
import asyncio
import secrets

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..notifications import push, suscriptores
from ..security import logs
from . import n8n

# Lo que se apunta en el registro cuando n8n manda un aviso. Está en
# n8n.NO_SALEN, así que este apunte NO vuelve a salir hacia n8n: es la mitad
# del corta-bucles (la otra es el filtro del workflow).
ACCION = "AVISO_N8N"


def _autorizado(request) -> bool:
    esperado = n8n.token()
    enviado = request.headers.get("x-noxus-token", "")
    if not esperado or not enviado:
        # Sin token configurado la puerta se queda cerrada, no abierta. Un
        # `.env` a medio rellenar no puede dejar que cualquiera mande avisos a
        # los móviles de la casa.
        return False
    return secrets.compare_digest(enviado, esperado)


def _destinatarios(destino) -> tuple[list[str], list[str]]:
    """(a quién se manda de verdad, nombres que no existen).

    Acepta las tres formas que acepta `push.enviar_notificacion`: "todos", un
    nombre suelto o una lista."""
    conocidos = suscriptores.nombres()
    if destino == push.TODOS:
        return conocidos, []
    pedidos = [destino] if isinstance(destino, str) else list(destino)
    pedidos = [str(p).strip() for p in pedidos if str(p).strip()]
    validos = [p for p in pedidos if p in conocidos]
    return validos, [p for p in pedidos if p not in conocidos]


async def enviar_aviso(request):
    """Manda un aviso al móvil. Cuerpo JSON:

        destino    "todos", un nombre de dispositivo, o una lista de nombres
        titulo     el título del aviso (por defecto "NOXUS")
        mensaje    el texto — obligatorio
        url        a dónde lleva al pulsarlo ("/panel?vista=logs")
        tag        agrupa avisos: uno nuevo con el mismo tag sustituye al viejo
        silencioso sin sonido ni vibración
    """
    if not _autorizado(request):
        return JSONResponse(
            {"ok": False, "mensaje": "Token no válido."}, status_code=401)

    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}

    mensaje = str(cuerpo.get("mensaje") or "").strip()
    if not mensaje:
        return JSONResponse(
            {"ok": False, "mensaje": "Falta «mensaje»."}, status_code=400)
    titulo = str(cuerpo.get("titulo") or "NOXUS").strip()
    destino = cuerpo.get("destino") or push.TODOS

    validos, desconocidos = _destinatarios(destino)
    if desconocidos:
        return JSONResponse(
            {"ok": False,
             "mensaje": "No hay ningún dispositivo con avisos activados "
                        f"llamado «{', '.join(desconocidos)}».",
             "desconocidos": desconocidos},
            status_code=404)
    if not validos:
        return JSONResponse(
            {"ok": False, "mensaje": "No hay a quién avisar."}, status_code=404)

    # to_thread porque pywebpush es bloqueante y va a la nube de cada
    # navegador: con seis suscriptores lentos, hacerlo aquí mismo colgaría el
    # bucle de eventos del backend, que es el que atiende el panel entero.
    await asyncio.to_thread(
        push.enviar_notificacion, titulo, mensaje, destino,
        str(cuerpo.get("tag") or ""), bool(cuerpo.get("silencioso")),
        (), str(cuerpo.get("url") or ""))

    logs.registrar(logs.SISTEMA, ACCION, "n8n",
                   f"{titulo} · para {', '.join(validos)}")
    return JSONResponse({"ok": True, "enviados": len(validos),
                         "destinatarios": validos})


RUTAS = [Route("/api/integraciones/aviso", enviar_aviso, methods=["POST"])]
