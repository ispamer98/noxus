"""
Control por voz: `POST /api/voz`. Es lo que usan Siri y Alexa.

CÓMO FUNCIONA, en una frase: el atajo del móvil (o la rutina del altavoz) manda
la frase dictada y una clave, y aquí se busca en el catálogo de comandos de la
casa y se ejecuta el que case. La respuesta trae una frase corta para que el
asistente la lea en voz alta.

SIN NUBE DE TERCEROS. No hay integración con Apple ni con Amazon: los dos saben
hacer una petición HTTP, y eso es todo lo que hace falta. En Siri es un Atajo con
«Obtener contenido de una URL»; en Alexa, una rutina con un webhook. Nada de esta
casa pasa por un servidor ajeno, y el día que Apple o Amazon cambien su API, esto
sigue funcionando igual.

LA CLAVE ES UNA SESIÓN FIRMADA, la misma máquina que el resto del panel
(auth/sessions.py). Ventajas de no inventarse otro sistema: se firma con el mismo
secreto, caduca, se puede revocar cambiando el rol del dispositivo, y **hereda
sus permisos** — la clave de un invitado enciende luces y no abre la puerta, sin
tener que mantener una segunda tabla de quién puede qué.

La clave viaja en el cuerpo o en la cabecera `X-Noxus-Clave`, y no en la URL:
las URL acaban en los registros del navegador, en el historial de atajos y en
cualquier proxy por el que pasen. Se acepta también por parámetro porque algunas
rutinas de Alexa no dejan poner cabeceras, pero se avisa en la respuesta.

QUÉ DEVUELVE: siempre JSON con `mensaje`, escrito para leerse en voz alta. Si no
entiende la frase, lo dice y ofrece lo más parecido; si hay varias posibles, NO
elige — pregunta. En una casa donde una frase puede abrir una puerta, adivinar no
es una opción.
"""

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store
from ..automations import actions
from ..modes import state as modes_state
from ..security import audit, logs
from . import comandos

# Cuántas alternativas se ofrecen cuando la frase es ambigua. Tres son las que
# caben en una frase hablada sin marear.
ALTERNATIVAS = 3


def _quien(request, cuerpo: dict) -> tuple[str, str]:
    """(id de dispositivo, nombre) a partir de la clave. ("", "") si no vale."""
    clave = (request.headers.get("x-noxus-clave")
             or cuerpo.get("clave")
             or request.query_params.get("clave")
             or "")
    id_dispositivo = sessions.verificar(clave.strip())
    if not id_dispositivo:
        return "", ""
    ficha = auth_store.dispositivo(id_dispositivo)
    if ficha is None:
        return "", ""
    return id_dispositivo, ficha.get("nombre", "")


async def _ejecutar(comando: dict, quien: str) -> str:
    """Hace lo que diga el comando y devuelve la frase para leer en voz alta."""
    paso = comando["paso"]
    if paso["type"] == "modo":
        ok, resumen = await modes_state.aplicar(paso["target"], quien)
        if not ok:
            raise RuntimeError(resumen)
        return f"{comando['etiqueta']}. {resumen}"
    if paso["type"] == "vista":
        # Cambiar de pestaña no significa nada por voz: no hay pantalla delante.
        raise RuntimeError("eso solo se puede hacer desde el panel")
    resumen = await actions.dispatch(paso)
    return resumen or comando["etiqueta"]


async def control_por_voz(request):
    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}

    id_dispositivo, nombre = _quien(request, cuerpo)
    if not id_dispositivo:
        return JSONResponse(
            {"ok": False, "mensaje": "La clave no vale. Vuelve a crearla en el "
                                     "panel, en el icono de tu dispositivo."},
            status_code=401)

    frase = str(cuerpo.get("texto") or cuerpo.get("frase")
                or request.query_params.get("texto") or "").strip()
    comando_id = str(cuerpo.get("comando") or "").strip()
    if not frase and not comando_id:
        return JSONResponse(
            {"ok": False, "mensaje": "No he entendido qué quieres que haga."},
            status_code=400)

    todos = comandos.comandos()
    # PRIMERO las frases que ha atado el usuario (Ajustes → Comandos de voz).
    # Van antes que la búsqueda por parecido a propósito: son exactas y las ha
    # decidido una persona, así que no hay nada que interpretar. «Buenas noches»
    # no se parece a ningún comando del catálogo y aun así es lo que uno dice.
    if frase and not comando_id:
        guardado = comandos.por_frase_guardada(frase, todos)
        if guardado is not None:
            comando_id = guardado["id"]
    if comando_id:
        # Invocación exacta, para atajos ya montados y para las frases atadas a
        # mano: no depende de cómo se pronuncie nada.
        comando = next((c for c in todos if c["id"] == comando_id), None)
        alternativas = []
    else:
        comando, alternativas = comandos.elegir(frase, todos)

    if comando is None and not alternativas:
        return JSONResponse(
            {"ok": False,
             "mensaje": f"No sé hacer «{frase}»." if frase else "No sé hacer eso."},
            status_code=404)

    # Varias posibles y ninguna mejor: se PREGUNTA. Ejecutar la primera de tres
    # opciones parecidas es como se acaba apagando el ordenador de alguien porque
    # el altavoz oyó «apaga» y decidió por su cuenta.
    if comando is None:
        opciones = ", ".join(c["etiqueta"] for c in alternativas[:ALTERNATIVAS])
        return JSONResponse(
            {"ok": False, "ambiguo": True,
             "mensaje": f"No sé si quieres {opciones}. Dilo más concreto.",
             "opciones": [{"id": c["id"], "etiqueta": c["etiqueta"]}
                          for c in alternativas[:ALTERNATIVAS]]},
            status_code=409)

    # El permiso del DISPOSITIVO cuya clave se ha usado. Una clave de invitado
    # enciende luces y no abre la puerta, igual que su dueño en el panel.
    capacidad = comandos.CAPACIDAD.get(comando["paso"]["type"], permisos.AJUSTES)
    if not permisos.puede(id_dispositivo, capacidad):
        logs.registrar(logs.ACCESOS, "ACCESO_DENEGADO", nombre or "por voz",
                       f"por voz: «{comando['etiqueta']}»")
        return JSONResponse(
            {"ok": False, "mensaje": f"No tienes permiso para {comando['etiqueta']}."},
            status_code=403)

    try:
        mensaje = await _ejecutar(comando, nombre or audit.SISTEMA)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "mensaje": f"No pude: {e}"}, status_code=500)

    logs.registrar(logs.SISTEMA, "COMANDO_POR_VOZ", nombre or "por voz",
                   f"{comando['etiqueta']} · dicho «{frase}»" if frase
                   else comando["etiqueta"])
    return JSONResponse({"ok": True, "mensaje": mensaje,
                         "comando": comando["id"]})


async def listar_comandos(request):
    """`GET /api/voz` — la lista de lo que se puede pedir.

    Sirve para montar el atajo: se copian los ids y se hacen botones. Pide la
    misma clave, porque la lista de todo lo que hay en una casa tampoco es
    pública."""
    id_dispositivo, _ = _quien(request, {})
    if not id_dispositivo:
        return JSONResponse({"ok": False, "mensaje": "La clave no vale."},
                            status_code=401)
    if not permisos.puede(id_dispositivo, permisos.VER):
        return JSONResponse({"ok": False, "mensaje": "Sin acceso."},
                            status_code=403)
    return JSONResponse({
        "ok": True,
        "comandos": [
            {"id": c["id"], "etiqueta": c["etiqueta"], "familia": c["familia"]}
            for c in comandos.comandos()
        ],
    })


RUTAS = [
    Route("/api/voz", control_por_voz, methods=["POST"]),
    Route("/api/voz", listar_comandos, methods=["GET"]),
]
