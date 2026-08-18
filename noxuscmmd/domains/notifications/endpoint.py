"""El endpoint que atienden los botones de la notificación.

Vive fuera del sistema de estados de Reflex porque quien llama es el service
worker del móvil, no una pestaña: cuando alguien pulsa «Visto» en la pantalla
de bloqueo puede no haber ninguna sesión abierta ni websocket por el que
hablar.

Quién llama se resuelve con la MISMA cookie firmada de las sesiones del panel
(domains/auth/sessions.py). El service worker manda la petición con las cookies
del origen, así que un aviso pulsado en un móvil que no está dado de alta no
puede confirmar ni silenciar nada.
"""

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store
from ..security import logs
from . import alertas


def _quien(request) -> tuple[str, str]:
    """(id de dispositivo, nombre) a partir de la cookie. ("", "") si no vale."""
    testigo = request.cookies.get(sessions.NOMBRE_COOKIE, "")
    id_dispositivo = sessions.verificar(testigo)
    if not id_dispositivo:
        return "", ""
    ficha = auth_store.dispositivo(id_dispositivo)
    if ficha is None:
        return "", ""
    return id_dispositivo, ficha.get("nombre", "")


async def accion_aviso(request):
    """POST /api/aviso — lo llama assets/sw.js al pulsar un botón del aviso.

    Devuelve siempre JSON, incluso al fallar, y con un `mensaje` escrito para
    que el service worker pueda enseñarlo tal cual en una notificación. Es lo
    que evita el fallo mudo: si esto no responde bien, el móvil tiene que
    DECIRLO, no quedarse callado como si hubiera funcionado.
    """
    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}
    accion = (cuerpo.get("accion") or "").strip()
    clave = (cuerpo.get("clave") or "").strip()

    id_dispositivo, nombre = _quien(request)
    if not id_dispositivo:
        return JSONResponse(
            {"ok": False, "mensaje": "Este dispositivo no está identificado. "
                                     "Abre Noxus y vuelve a intentarlo."},
            status_code=401)

    # ARMAR, no VER. Silenciar una alerta 30 minutos calla los avisos de un
    # sensor de la alarma: es de la misma familia que armar y desarmar, no de la
    # de entrar a mirar el panel. Con VER —como estaba— un dispositivo de rol
    # «invitado» podía callar la alarma de la casa.
    #
    # El mismo permiso se comprueba en AlertasState (la vía de dentro de la
    # aplicación). Si se cambia aquí, hay que cambiarlo allí: es la misma acción
    # por dos puertas, y dos varas de medir sería peor que cualquiera de las dos.
    if not permisos.puede(id_dispositivo, permisos.ARMAR):
        return JSONResponse(
            {"ok": False,
             "mensaje": "Este dispositivo no puede confirmar ni silenciar la "
                        "alarma."},
            status_code=403)

    quien = nombre or "desconocido"

    if accion == "confirmar":
        ficha = alertas.confirmar(clave, quien) if clave else None
        if ficha is None:
            # Ya la había confirmado otro. No es un error: es justo lo que se
            # busca — que baste con que UNO diga «visto».
            alertas.confirmar_todas(quien)
            logs.registrar(logs.ALARMA, "ALERTA_CONFIRMADA", quien,
                           "ya estaba confirmada")
            return JSONResponse({"ok": True, "mensaje": "Ya estaba confirmada."})
        logs.registrar(logs.ALARMA, "ALERTA_CONFIRMADA", quien, ficha["titulo"])
        return JSONResponse({"ok": True, "mensaje": "Confirmado. Deja de repetirse."})

    if accion == "silenciar":
        if not clave:
            return JSONResponse({"ok": False, "mensaje": "Aviso sin identificar."},
                                status_code=400)
        alertas.silenciar(clave, 30, quien)
        logs.registrar(logs.ALARMA, "ALERTA_SILENCIADA", quien,
                       "30 minutos sin avisar de esto")
        return JSONResponse({"ok": True, "mensaje": "Silenciado 30 minutos."})

    return JSONResponse({"ok": False, "mensaje": f"No sé hacer «{accion}»."},
                        status_code=400)


RUTAS = [Route("/api/aviso", accion_aviso, methods=["POST"])]
