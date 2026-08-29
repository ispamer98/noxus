"""OAuth y entrada firmada desde el adaptador AWS de Alexa.

Amazon invoca una Lambda, no el panel doméstico. La Lambda es el perímetro que
AWS autentica; reenvía una sola directiva al panel con HMAC y fecha. Así el
panel no acepta nunca una orden de Internet sin verificar, ni siquiera si
alguien descubre la URL del túnel.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from ..auth import permisos, sessions
from ..automations import actions
from ..modes import state as modes_state
from ..security import logs
from . import alexa_cloud, alexa_cloud_store, alexa_cloud_sync, comandos
from . import alexa_catalog_store


ARCHIVO_OAUTH = Path(os.getenv("ALEXA_OAUTH_FILE", "alexa_oauth_client.json"))
PROXY_SECRET = os.getenv("ALEXA_PROXY_SECRET", "")
ARCHIVO_PROXY_SECRET = Path(os.getenv("ALEXA_PROXY_SECRET_FILE", "alexa_proxy_secret"))
VENTANA_FIRMA = 300
_TAREAS_DIRECTIVA: dict[str, tuple[float, asyncio.Task]] = {}
_CADUCA_DEDUP = 600
_ESPERA_POWER = 4.5
_AUTOR_ALEXA = "Alexa"


def _lista(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items()}


def _oauth() -> tuple[str, str, tuple[str, ...]]:
    """Configuración privada del cliente OAuth, con el entorno como prioridad."""
    client_id = os.getenv("ALEXA_OAUTH_CLIENT_ID", "")
    secret = os.getenv("ALEXA_OAUTH_CLIENT_SECRET", "")
    redirects = tuple(x.strip() for x in os.getenv("ALEXA_OAUTH_REDIRECT_URIS", "").split(",")
                      if x.strip())
    if client_id and secret:
        return client_id, secret, redirects
    try:
        data = json.loads(ARCHIVO_OAUTH.read_text())
        return (str(data.get("client_id") or ""), str(data.get("client_secret") or ""),
                tuple(str(x) for x in data.get("redirect_uris", []) if x))
    except (OSError, ValueError, TypeError):
        return "", "", ()


def _redirect_amazon(uri: str, permitidas: tuple[str, ...]) -> bool:
    if uri in permitidas:
        return True
    # Mientras Alexa muestra sus URLs de retorno en la consola, se acepta SOLO
    # un host de Amazon por HTTPS; jamás un redirect arbitrario de Internet.
    host = (urlparse(uri).hostname or "").lower()
    return (urlparse(uri).scheme == "https" and host in {
        "alexa.amazon.com", "layla.amazon.com", "pitangui.amazon.com",
        "alexa.amazon.co.jp", "alexa.amazon.co.uk",
        "layla.amazon.co.uk", "alexa.amazon.de", "layla.amazon.de",
        "alexa.amazon.fr", "layla.amazon.fr", "alexa.amazon.it", "layla.amazon.it",
        "alexa.amazon.es", "layla.amazon.es",
    })


def _cliente_valido(request, form: dict[str, str]) -> bool:
    client_id, secret = form.get("client_id", ""), form.get("client_secret", "")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
            client_id, secret = decoded.split(":", 1)
        except Exception:
            return False
    configurado_id, configurado_secret, _ = _oauth()
    return bool(configurado_id and configurado_secret and
                hmac.compare_digest(client_id, configurado_id) and
                hmac.compare_digest(secret, configurado_secret))


def _parametros_validos(params: dict[str, str]) -> str | None:
    client_id, secret, redirects = _oauth()
    if not client_id or not secret:
        return "La cuenta cloud de Alexa aún no está configurada en Noxus."
    if params.get("response_type") != "code":
        return "Alexa debe usar OAuth 2 con código de autorización."
    if not hmac.compare_digest(params.get("client_id", ""), client_id):
        return "El identificador OAuth de Alexa no coincide."
    if not _redirect_amazon(params.get("redirect_uri", ""), redirects):
        return "La URL de retorno no está autorizada."
    method = params.get("code_challenge_method", "")
    if method and method != "S256":
        return "Solo se acepta PKCE S256."
    if method and not params.get("code_challenge"):
        return "Falta el comprobante PKCE."
    return None


def _cuenta(request) -> str | None:
    testigo = request.cookies.get(sessions.NOMBRE_COOKIE, "")
    cuenta = sessions.verificar(testigo)
    # Enlazar Alexa da control sobre la casa entera, no se delega a invitados.
    return cuenta if cuenta and permisos.puede(cuenta, permisos.AJUSTES) else None


def _campos_ocultos(params: dict[str, str]) -> str:
    permitidos = ("response_type", "client_id", "redirect_uri", "state",
                  "scope", "code_challenge", "code_challenge_method")
    return "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(params.get(k, ""))}">'
        for k in permitidos if k in params
    )


def _terminar_autorizacion(cuenta: str, params: dict[str, str]):
    code = alexa_cloud_store.emitir_codigo(cuenta, params["redirect_uri"],
                                           params.get("code_challenge", ""))
    retorno = f"{params['redirect_uri']}?" + urlencode({
        "code": code, "state": params.get("state", ""),
    })
    return RedirectResponse(retorno, status_code=302)


def _pedir_codigo(params: dict[str, str], problema: str = ""):
    aviso = f"<p>{html.escape(problema)}</p>" if problema else ""
    return HTMLResponse(
        "<h1>Vincular Alexa con Noxus</h1>"
        "<p>Abre Noxus en un dispositivo administrador, entra en Ajustes → "
        "Alexa y voz → Alexa Cloud y genera un código de enlace. Este "
        "código vale cinco minutos y solo una vez.</p>" + aviso +
        f'<form method="post">{_campos_ocultos(params)}'
        '<label>Código de enlace <input name="codigo_noxus" autocomplete="one-time-code" required></label>'
        '<button type="submit">Vincular Alexa</button></form>')


async def autorizar(request):
    params = {k: v for k, v in request.query_params.items()}
    if request.method == "POST":
        params = _lista(await request.body())
    problema = _parametros_validos(params)
    if problema:
        return HTMLResponse(problema, status_code=400)
    cuenta = _cuenta(request)
    if not cuenta:
        if request.method == "POST":
            cuenta = alexa_cloud_store.canjear_autorizacion(params.get("codigo_noxus", ""))
            if cuenta:
                return _terminar_autorizacion(cuenta, params)
            return _pedir_codigo(params, "El código no es válido o ya ha caducado.")
        return _pedir_codigo(params)
    if request.method == "GET":
        return HTMLResponse(
            "<h1>Vincular Alexa con Noxus</h1>"
            "<p>Alexa podrá ver y controlar los elementos compatibles de esta casa. "
            "Puedes revocar la vinculación desde Noxus.</p>"
            f'<form method="post">{_campos_ocultos(params)}'
            '<button type="submit">Autorizar Alexa</button></form>')
    return _terminar_autorizacion(cuenta, params)


async def token(request):
    form = _lista(await request.body())
    if not _cliente_valido(request, form):
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    grant = form.get("grant_type", "")
    if grant == "authorization_code":
        par = alexa_cloud_store.canjear_codigo(form.get("code", ""),
                                                form.get("redirect_uri", ""),
                                                form.get("code_verifier", ""))
    elif grant == "refresh_token":
        par = alexa_cloud_store.renovar(form.get("refresh_token", ""))
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    if par is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    access, refresh = par
    # RFC 6749 exige impedir que un intermediario conserve estas credenciales.
    # Alexa es estricta con esta respuesta: devuelve scope, tipo bearer y una
    # caducidad corta; el refresh vive separado en el almacén privado.
    return JSONResponse(
        {"access_token": access, "refresh_token": refresh,
         "token_type": "bearer", "expires_in": alexa_cloud_store.CADUCA_TOKEN,
         "scope": "noxus"},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def privacidad(_request):
    return HTMLResponse(
        "<h1>Privacidad de Noxus para Alexa</h1>"
        "<p>Noxus es un panel doméstico privado. La integración Alexa conserva "
        "solo los testigos necesarios para vincular la cuenta y la configuración "
        "de los dispositivos que el propietario publica.</p>"
        "<p>No vende datos, no incorpora publicidad y no envía vídeo, audio ni "
        "credenciales de la casa a terceros salvo las órdenes necesarias para "
        "responder a Alexa.</p>")


async def condiciones(_request):
    return HTMLResponse(
        "<h1>Condiciones de Noxus para Alexa</h1>"
        "<p>La Skill Noxus controla únicamente dispositivos configurados por su "
        "propietario. El propietario es responsable de no publicar acciones "
        "peligrosas ni conceder acceso a personas no autorizadas.</p>")


def _firma_valida(request, body: bytes) -> bool:
    secreto = PROXY_SECRET
    if not secreto:
        try:
            secreto = ARCHIVO_PROXY_SECRET.read_text().strip()
        except OSError:
            secreto = ""
    if not secreto:
        return False
    try:
        timestamp = int(request.headers.get("x-noxus-alexa-timestamp", "0"))
    except ValueError:
        return False
    if abs(time.time() - timestamp) > VENTANA_FIRMA:
        return False
    recibida = request.headers.get("x-noxus-alexa-signature", "")
    mensaje = str(timestamp).encode() + b"." + body
    esperada = hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recibida, esperada)


def _token_directiva(directiva: dict) -> str:
    d = directiva.get("directive", {})
    return str((d.get("endpoint", {}).get("scope", {}) or d.get("payload", {}).get("scope", {})).get("token", ""))


async def _ejecutar_comando(comando_id: str, quien: str) -> str:
    comando = next((x for x in comandos.comandos() if x["id"] == comando_id), None)
    if comando is None or not comando.get("alexa_allowed", False):
        raise actions.ActionError("esa acción ya no existe o no se puede usar con Alexa")
    paso = comando["paso"]
    if paso["type"] == "modo":
        ok, resumen = await modes_state.aplicar(paso["target"], quien)
        if not ok:
            raise actions.ActionError(resumen)
        return resumen
    if paso["type"] == "vista":
        raise actions.ActionError("la navegación solo funciona dentro del panel")
    return await actions.dispatch(paso)


def _detalle_log(endpoint_id: str, operacion: str, comando_id: str,
                 resultado: str = "", error: str = "") -> str:
    """Descripción estable de una orden oficial de Alexa.

    El nombre publicado va primero porque la vista de Registros interpreta el
    primer tramo como sujeto. Resolver la etiqueta es solo decorativo: si el
    catálogo cambiara justo al terminar la orden, el registro se conserva con
    los ids en vez de convertir un éxito real en una excepción tardía.
    """
    nombre = endpoint_id
    try:
        if endpoint_id.startswith(alexa_cloud.PREFIJO_MANUAL):
            item = alexa_catalog_store.obtener(
                endpoint_id.removeprefix(alexa_cloud.PREFIJO_MANUAL))
            if item is not None:
                nombre = str(item.get("name") or nombre)
    except Exception:
        pass

    etiqueta = comando_id
    try:
        comando = next((item for item in comandos.comandos()
                        if item.get("id") == comando_id), None)
        if comando is not None:
            etiqueta = str(comando.get("etiqueta") or etiqueta)
    except Exception:
        pass

    verbo = {"on": "Encender", "off": "Apagar",
             "activate": "Ejecutar", "deactivate": "Apagar"}.get(
                 operacion, operacion)
    partes = [nombre, verbo]
    if etiqueta:
        partes.append(etiqueta)
    if error:
        partes.append(f"FALLÓ: {error[:300]}")
    elif resultado:
        partes.append(resultado[:300])
    return " · ".join(partes)


def _registrar_orden_alexa(endpoint_id: str, operacion: str, comando_id: str,
                           *, resultado: str = "", error: str = "") -> None:
    """Una línea por petición lógica, no una por repetición ni por paso."""
    logs.registrar(
        logs.SISTEMA, "COMANDO_POR_VOZ", _AUTOR_ALEXA,
        _detalle_log(endpoint_id, operacion, comando_id, resultado, error),
    )


def _orden(endpoint_id: str, operacion: str) -> tuple[str, int, float]:
    """Resuelve una directiva a comando/repeticiones sin tocar hardware."""
    if not endpoint_id.startswith(alexa_cloud.PREFIJO_MANUAL):
        raise actions.ActionError("ese elemento de Alexa no existe")
    item = alexa_catalog_store.obtener(
        endpoint_id.removeprefix(alexa_cloud.PREFIJO_MANUAL))
    if item is None:
        raise actions.ActionError("ese elemento de Alexa ya no existe")
    if operacion == "on" and item.get("behavior") == "power":
        comando_id, repeticiones, pausa = item.get("on_command", ""), 1, 0.0
    elif operacion == "off" and item.get("behavior") == "power":
        comando_id, repeticiones, pausa = item.get("off_command", ""), 1, 0.0
    elif (item.get("behavior") == "action" and
          operacion == item.get("scene_operation", "activate")):
        comando_id = item.get("command", "")
        repeticiones = max(1, min(alexa_catalog_store.REPETICIONES_MAXIMAS,
                                  int(item.get("repeat", 1))))
        pausa = max(0.0, min(60.0, float(item.get("repeat_pause", 0.4))))
    else:
        raise actions.ActionError("esa orden no corresponde al comportamiento configurado")
    return str(comando_id), repeticiones, pausa


async def _ejecutar(endpoint_id: str, operacion: str, quien: str) -> None:
    comando_id = ""
    ultimo_resultado = ""
    try:
        comando_id, repeticiones, pausa = _orden(endpoint_id, operacion)
        for numero in range(repeticiones):
            if numero:
                await asyncio.sleep(pausa)
            ultimo_resultado = await asyncio.wait_for(
                _ejecutar_comando(comando_id, quien), timeout=20)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        _registrar_orden_alexa(
            endpoint_id, operacion, comando_id, error=str(error))
        raise
    _registrar_orden_alexa(
        endpoint_id, operacion, comando_id, resultado=ultimo_resultado)


def _tarea_unica(message_id: str, fabrica) -> asyncio.Task:
    """Una directiva de Amazon se ejecuta una vez aunque llegue reintentada."""
    ahora = time.monotonic()
    for clave, (creada, tarea) in list(_TAREAS_DIRECTIVA.items()):
        if ahora - creada > _CADUCA_DEDUP and tarea.done():
            _TAREAS_DIRECTIVA.pop(clave, None)
    if message_id and message_id in _TAREAS_DIRECTIVA:
        return _TAREAS_DIRECTIVA[message_id][1]
    tarea = asyncio.create_task(fabrica())
    if message_id:
        _TAREAS_DIRECTIVA[message_id] = (ahora, tarea)
    return tarea


def _consumir_resultado(tarea: asyncio.Task) -> None:
    """Recoge un fallo tardío para que asyncio no lo pierda ni lo duplique."""
    try:
        tarea.result()
    except asyncio.CancelledError:
        pass
    except Exception as error:
        print(f"⚠️ Alexa: una acción terminó tarde con error: {error}")


async def _escena_diferida(endpoint_id: str, operacion: str, quien: str) -> None:
    """Responde primero a Alexa; luego ejecuta incluso si reinicia Noxus."""
    # ActivationStarted/DeactivationStarted debe alcanzar Lambda antes de que
    # una acción como «reiniciar el panel» pueda detener este proceso.
    await asyncio.sleep(0.25)
    try:
        await _ejecutar(endpoint_id, operacion, quien)
    except Exception as error:
        print(f"⚠️ Alexa: falló {endpoint_id}: {error}")


async def directiva(request):
    body = await request.body()
    if not _firma_valida(request, body):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        data = json.loads(body)
        header = data["directive"]["header"]
    except (TypeError, ValueError, KeyError):
        return JSONResponse({"error": "bad_request"}, status_code=400)
    namespace, nombre = header.get("namespace"), header.get("name")
    if namespace == "Alexa.Authorization" and nombre == "AcceptGrant":
        cuenta = alexa_cloud_store.cuenta_de_token(
            str(data["directive"].get("payload", {}).get("grantee", {}).get("token", "")))
        code = str(data["directive"].get("payload", {}).get("grant", {}).get("code", ""))
        if not cuenta or not permisos.puede(cuenta, permisos.AJUSTES):
            alexa_cloud_store.guardar_diagnostico(
                "accept_grant", "Alexa llegó con un token sin permisos de administrador.")
            return JSONResponse(alexa_cloud.error(data, "ACCEPT_GRANT_FAILED",
                                                   "No se pudo autorizar el Event Gateway."))
        if not await alexa_cloud_sync.aceptar_grant(cuenta, code):
            alexa_cloud_store.guardar_diagnostico(
                "accept_grant", alexa_cloud_sync.ultimo_error() or
                "No se pudo autorizar el Event Gateway.")
            return JSONResponse(alexa_cloud.error(data, "ACCEPT_GRANT_FAILED",
                                                   "No se pudo autorizar el Event Gateway."))
        alexa_cloud_store.guardar_diagnostico(
            "completado", "Alexa y el Event Gateway quedaron autorizados.")
        return JSONResponse(alexa_cloud.accept_grant_response(data))
    cuenta = alexa_cloud_store.cuenta_de_token(_token_directiva(data))
    if namespace == "Alexa.Discovery" and nombre == "Discover":
        if not cuenta or not permisos.puede(cuenta, permisos.AJUSTES):
            return JSONResponse(alexa_cloud.error(data, "INVALID_AUTHORIZATION_CREDENTIAL", "Vincula Noxus de nuevo."))
        try:
            return JSONResponse(alexa_cloud.discovery_response())
        except alexa_catalog_store.ArchivoCorrupto:
            return JSONResponse(alexa_cloud.error(
                data, "INTERNAL_ERROR", "El catálogo Alexa de Noxus necesita revisión."))
    if not cuenta or not permisos.puede(cuenta, permisos.AJUSTES):
        return JSONResponse(alexa_cloud.error(data, "INVALID_AUTHORIZATION_CREDENTIAL", "Vincula Noxus de nuevo."))
    endpoint_id = str(data["directive"].get("endpoint", {}).get("endpointId", ""))
    try:
        item = alexa_cloud.endpoint(endpoint_id)
    except alexa_catalog_store.ArchivoCorrupto:
        return JSONResponse(alexa_cloud.error(
            data, "INTERNAL_ERROR", "El catálogo Alexa de Noxus necesita revisión."))
    if item is None:
        return JSONResponse(alexa_cloud.error(data, "NO_SUCH_ENDPOINT", "Ese elemento ya no existe."))
    if namespace == "Alexa.PowerController" and nombre in {"TurnOn", "TurnOff"}:
        encender = nombre == "TurnOn"
        message_id = str(header.get("messageId") or "")
        tarea = _tarea_unica(
            message_id,
            lambda: _ejecutar(
                endpoint_id, "on" if encender else "off", _AUTOR_ALEXA),
        )
        try:
            # Las órdenes directas suelen acabar en milisegundos. Si un PC
            # tarda en reconectar por SSH, confirmar dentro del plazo de Alexa
            # y dejar que la misma tarea termine; messageId evita duplicarla.
            await asyncio.wait_for(asyncio.shield(tarea), timeout=_ESPERA_POWER)
        except asyncio.TimeoutError:
            tarea.add_done_callback(_consumir_resultado)
        except Exception as error:
            print(f"⚠️ Alexa: no se pudo actuar sobre {endpoint_id}: {error}")
            return JSONResponse(alexa_cloud.error(
                data, "ENDPOINT_UNREACHABLE", "No se pudo completar la orden."))
        return JSONResponse(alexa_cloud.response(data, context_data=alexa_cloud.context(endpoint_id, encendido=encender)))
    if (namespace == "Alexa.SceneController" and
            nombre in {"Activate", "Deactivate"} and
            item.get("behavior") == "action"):
        operacion = "activate" if nombre == "Activate" else "deactivate"
        if operacion != item.get("scene_operation", "activate"):
            # No se crea ninguna tarea: la operación contraria no es un alias
            # y no debe llegar al comando ni dejar un falso registro de éxito.
            return JSONResponse(alexa_cloud.error(
                data, "INVALID_DIRECTIVE",
                "Esa operación de escena no está configurada para este elemento."))
        _tarea_unica(str(header.get("messageId") or ""),
                     lambda: _escena_diferida(
                         endpoint_id, operacion, _AUTOR_ALEXA))
        return JSONResponse(alexa_cloud.scene_response(
            data, activar=operacion == "activate"))
    if namespace == "Alexa" and nombre == "ReportState":
        if item.get("behavior") != "power":
            return JSONResponse(alexa_cloud.error(
                data, "INVALID_DIRECTIVE", "Las acciones no tienen estado."))
        return JSONResponse(alexa_cloud.state_report(data, endpoint_id))
    return JSONResponse(alexa_cloud.error(data, "INVALID_DIRECTIVE", "Directiva no soportada."))


RUTAS = [
    Route("/api/alexa/privacy", privacidad, methods=["GET"]),
    Route("/api/alexa/terms", condiciones, methods=["GET"]),
    Route("/api/alexa/authorize", autorizar, methods=["GET", "POST"]),
    Route("/api/alexa/token", token, methods=["POST"]),
    Route("/api/alexa/directive", directiva, methods=["POST"]),
]
