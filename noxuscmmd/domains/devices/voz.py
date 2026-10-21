"""
Control local por voz: `POST /api/voz`. Lo usan Siri, atajos y clientes HTTP.

CÓMO FUNCIONA, en una frase: el atajo del móvil o un cliente propio manda la
frase dictada y una clave, y aquí se busca en el catálogo de comandos de la casa
y se ejecuta el que case. La respuesta trae una frase corta para que el
asistente la lea en voz alta.

SIN NUBE DE TERCEROS. En Siri es un Atajo con «Obtener contenido de una URL».
Este endpoint no interviene en la Skill oficial de Alexa, que usa el catálogo y
las directivas Smart Home de ``alexa_cloud_endpoint.py``.

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

import asyncio
import re
import sqlite3
import time
from datetime import datetime

import aiohttp
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store
from ..automations import actions
from ..automations import store as automations_store
from ..modes import state as modes_state
from ..modes import store as modes_store
from ..nodes import store as nodes_store
from ..security import audit, groups_store, logs, logs_store, shared_state
from ..notifications import alertas
from ..security import presencia, presencia_store
from ..devices import mqtt_bus
from ..inventory import catalogo
from . import comandos, overrides_store

# Cuántas alternativas se ofrecen cuando la frase es ambigua. Tres son las que
# caben en una frase hablada sin marear.
ALTERNATIVAS = 3

# Cuánto dura la clave de voz — la misma constante que usa "Generar una clave"
# en Ajustes (ui/dashboard/views/voz.py la importa de aquí).
DIAS_CLAVE = 365

_MAX_EVENTOS = 100
_MAX_EVENTOS_ALARMA = 50
_FOTO_TIMEOUT = 2
_FOTO_MAX_BYTES = 2 * 1024 * 1024
_DATO_SECRETO = re.compile(
    r"\b(?:pin|clave|token|contrase(?:ñ|n)a|password)\b\s*[:=]?\s*\S+", re.IGNORECASE)


def _quien(request, cuerpo: dict) -> tuple[str, str]:
    """(id de dispositivo, nombre) a partir de la clave. ("", "") si no vale."""
    clave = (request.headers.get("x-noxus-clave")
             or cuerpo.get("clave")
             or "")
    # verificar_voz y no verificar: una clave de voz es un testigo aparte,
    # no una sesión (ver auth/sessions.emitir_voz).
    id_dispositivo = sessions.verificar_voz(clave.strip())
    if not id_dispositivo:
        return "", ""
    ficha = auth_store.dispositivo(id_dispositivo)
    if ficha is None:
        return "", ""
    return id_dispositivo, ficha.get("nombre", "")


def _autorizar_lectura(request, ademas=None):
    """La misma identificación y capacidad VER de los GET de voz (más `ademas`, si se pide)."""
    id_dispositivo, _ = _quien(request, {})
    if not id_dispositivo:
        return None, JSONResponse({"ok": False, "mensaje": "La clave no vale."},
                                  status_code=401)
    for capacidad in (permisos.VER, ademas):
        if capacidad and not permisos.puede(id_dispositivo, capacidad):
            return None, JSONResponse({"ok": False, "mensaje": "Sin acceso."},
                                      status_code=403)
    return id_dispositivo, None


def _limite(request, maximo: int, defecto: int) -> tuple[int | None, JSONResponse | None]:
    valor = request.query_params.get("n", "")
    if not valor:
        return defecto, None
    try:
        return max(1, min(int(valor), maximo)), None
    except ValueError:
        return None, JSONResponse({"ok": False, "mensaje": "n debe ser un entero."},
                                  status_code=400)


def _desde(request) -> tuple[float | None, JSONResponse | None]:
    valor = request.query_params.get("desde", "").strip()
    if not valor:
        return 0.0, None
    try:
        return float(valor), None
    except ValueError:
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp(), None
        except ValueError:
            return None, JSONResponse(
                {"ok": False, "mensaje": "desde debe ser epoch o una fecha ISO-8601."},
                status_code=400)


_CAMPOS_INVENTARIO_VOZ = frozenset({
    "id", "nombre", "familia", "tipo", "padre", "estancia", "ip_lan",
    "ip_tailscale", "mac", "modelo", "ubicacion", "online", "estado",
    "controlable", "acciones",
})


def _texto_inventario(valor) -> str:
    """Convierte los marcadores visuales del catálogo en valores de API."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto in {"", "—"} else texto


def _online_inventario(valor):
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, str):
        valor = valor.strip().lower()
        if valor in {"sí", "si", "yes", "true", "1", "online"}:
            return True
        if valor in {"no", "false", "0", "offline"}:
            return False
    return None


def _estado_inventario(fila: dict, datos: dict):
    ident = fila.get("entity_id") or fila.get("id") or ""
    coleccion = fila.get("entity_collection", "")
    tipo = str(fila.get("entity_type") or fila.get("tipo") or "").lower()
    estados = datos.get("sensor_states", {}) or {}
    valor = estados.get(ident)
    if coleccion == "doors":
        puerta = next((d for d in datos.get("doors", []) or []
                       if d.get("id") == ident), {})
        valor = estados.get(puerta.get("sensor_id"), valor)
    if isinstance(valor, bool):
        if coleccion in {"sensors", "doors"} or tipo in {"door", "magnetic", "contact"}:
            return "abierto" if valor else "cerrado"
        if coleccion == "lights" or tipo in {"light", "relay", "switch"}:
            return "encendida" if valor else "apagada"
    estado = fila.get("estado")
    return estado if isinstance(estado, str) and estado.strip() else None


def _accion_publica(comando: dict) -> dict:
    return {"comando": comando["id"], "etiqueta": comando["etiqueta"],
            "familia": comando["familia"]}


def _inventario_fila_publica(fila: dict, datos: dict, por_id: dict,
                             acciones_por_id: dict[str, list[dict]]) -> dict:
    ident = _texto_inventario(fila.get("entity_id") or fila.get("id"))
    coleccion = fila.get("entity_collection", "")
    padre = _texto_inventario(
        fila.get("entity_parent_id") or fila.get("padre") or fila.get("parent_id"))
    item = por_id.get((coleccion, ident), {})
    if not padre:
        padre = _texto_inventario(item.get("node_id"))

    online = _online_inventario(fila.get("online"))
    if online is None and coleccion in {"hosts", "nodes"}:
        online = _online_inventario((datos.get("host_online", {}) or {}).get(ident))
    if online is None and padre:
        online = _online_inventario((datos.get("host_online", {}) or {}).get(padre))

    acciones = acciones_por_id.get(ident, [])

    estancia = _texto_inventario(fila.get("estancia"))
    if not estancia:
        room_id = item.get("room_id", "")
        estancia = _texto_inventario(
            next((r.get("name") for r in datos.get("rooms", [])
                  if r.get("id") == room_id), ""))

    return {
        "id": ident,
        "nombre": _texto_inventario(fila.get("entity_name") or fila.get("nombre") or ident),
        "familia": _texto_inventario(
            fila.get("entity_inventory_family") or fila.get("familia")),
        "tipo": _texto_inventario(fila.get("entity_type") or fila.get("tipo")),
        "padre": padre,
        "estancia": estancia,
        "ip_lan": _texto_inventario(fila.get("ip_lan") or fila.get("ip_local")),
        "ip_tailscale": _texto_inventario(fila.get("ip_tailscale")),
        "mac": _texto_inventario(fila.get("mac")),
        "modelo": _texto_inventario(fila.get("modelo")),
        "ubicacion": _texto_inventario(fila.get("ubicacion")),
        "online": online,
        "estado": _estado_inventario(fila, datos),
        "controlable": bool(acciones),
        "acciones": [_accion_publica(comando) for comando in acciones],
    }


async def inventario_casa(request):
    """`GET /api/voz/inventario` — catálogo seguro, solo lectura y sin red."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    datos = nodes_store.read_all()
    catalogo_por_familia = catalogo.construir()
    todos_comandos = comandos.comandos()
    acciones_por_id: dict[str, list[dict]] = {}
    acciones_casa = []
    for comando in todos_comandos:
        elemento = str(comando.get("elemento") or "")
        tipo = comando.get("paso", {}).get("type")
        if elemento:
            acciones_por_id.setdefault(elemento, []).append(comando)
        elif tipo in {"modo", "rule.run", "system.arm"}:
            acciones_casa.append(_accion_publica(comando))
    por_id = {
        (coleccion, str(item.get("id", ""))): item
        for coleccion in ("hosts", "nodes", "sensors", "doors", "lights", "cameras")
        for item in datos.get(coleccion, []) or []
    }
    elementos = []
    ids = set()
    for filas in catalogo_por_familia.values():
        for fila in filas:
            publico = _inventario_fila_publica(fila, datos, por_id, acciones_por_id)
            if publico["id"] and publico["id"] not in ids:
                ids.add(publico["id"])
                elementos.append(publico)
    return JSONResponse({"ok": True, "generado": time.time(),
                         "elementos": elementos, "acciones_casa": acciones_casa})


def _evento_publico(evento: dict) -> dict:
    """La forma segura del histórico: nunca expone foto ni datos de acceso."""
    return {
        "id": evento["id"], "ts": evento["ts"], "timestamp": evento["timestamp"],
        "categoria": evento["categoria"], "accion": evento["accion"],
        "usuario": evento["usuario"],
        "detalle": _DATO_SECRETO.sub("[dato oculto]", evento["detalle"]),
        "grupo": evento["grupo"], "dispositivo": evento["entidad"],
    }


def _zonas_abiertas(grupo: dict, datos: dict) -> list[dict]:
    """Miembros abiertos del grupo, sin usar helpers que puedan migrar datos."""
    sensores = {sensor.get("id"): sensor for sensor in datos.get("sensors", [])}
    estados = datos.get("sensor_states", {})
    aislados = overrides_store.get_isolated_ids()
    salida = []
    for miembro in grupo.get("members", []):
        sensor = sensores.get(miembro.get("id"))
        if (sensor is None or sensor.get("isolated")
                or miembro.get("id") in aislados or not estados.get(miembro.get("id"), False)):
            continue
        salida.append({"id": miembro["id"], "nombre": sensor.get("name", miembro.get("name", ""))})
    return salida


async def _estado_streams() -> dict:
    """Estado que conoce go2rtc, sin abrir un vídeo ni arrancar productores."""
    from ..cameras.fotogramas import GO2RTC

    try:
        timeout = aiohttp.ClientTimeout(total=_FOTO_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as sesion:
            async with sesion.get(f"{GO2RTC}/api/streams") as respuesta:
                if respuesta.status != 200:
                    return {}
                datos = await respuesta.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {
        nombre: bool(info.get("producers")) if isinstance(info, dict) else False
        for nombre, info in datos.items()
    }


async def _foto_go2rtc(src: str) -> tuple[bytes | None, str]:
    """Una instantánea acotada; los errores de una cámara no salen como 500."""
    from ..cameras.fotogramas import GO2RTC

    try:
        timeout = aiohttp.ClientTimeout(total=_FOTO_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as sesion:
            async with sesion.get(f"{GO2RTC}/api/frame.jpeg", params={"src": src}) as respuesta:
                if respuesta.status != 200:
                    return None, "La cámara está parada o no responde."
                longitud = respuesta.content_length
                if longitud is not None and longitud > _FOTO_MAX_BYTES:
                    return None, "La instantánea supera el tamaño permitido."
                partes, total = [], 0
                async for parte in respuesta.content.iter_chunked(64 * 1024):
                    total += len(parte)
                    if total > _FOTO_MAX_BYTES:
                        return None, "La instantánea supera el tamaño permitido."
                    partes.append(parte)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None, "La cámara está parada o no responde."
    datos = b"".join(partes)
    if len(datos) < 4 or not datos.startswith(b"\xff\xd8"):
        return None, "La cámara no devolvió una imagen JPEG válida."
    return datos, ""


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

    # Solo resolver: el cliente (p. ej. el asistente) quiere saber QUÉ comando casaría y de qué
    # familia, para decidir si necesita confirmación, sin ejecutar nada. Usa el mismo
    # emparejador y el mismo permiso que la ejecución real: no se duplica lógica fuera.
    if cuerpo.get("solo_resolver") is True:
        return JSONResponse({"ok": True, "comando": comando["id"],
                             "etiqueta": comando["etiqueta"], "familia": comando["familia"]})

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


async def estado_casa(request):
    """`GET /api/voz/estado` — el estado actual, solo lectura, con la misma clave y el
    permiso VER. Lo lee de las mismas fuentes que pinta el panel (no hay copia aparte)."""
    id_dispositivo, _ = _quien(request, {})
    if not id_dispositivo:
        return JSONResponse({"ok": False, "mensaje": "La clave no vale."}, status_code=401)
    if not permisos.puede(id_dispositivo, permisos.VER):
        return JSONResponse({"ok": False, "mensaje": "Sin acceso."}, status_code=403)
    datos = nodes_store.read_all()
    estancias = {r.get("id"): r.get("name", "") for r in datos.get("rooms", [])}
    estados = datos.get("sensor_states", {})
    luces = []
    persianas = []
    for luz in datos.get("lights", []):
        valor = estados.get(luz.get("id"))
        tipo_luz = str(luz.get("kind", "")).lower()
        if any(marca in tipo_luz for marca in ("persiana", "blind", "roller", "shutter")):
            persianas.append({"id": luz.get("id", ""), "nombre": luz.get("name", ""),
                              "estado": (datos.get("persianas_estado", {}) or {}).get(luz.get("id"))})
        luces.append({"nombre": luz.get("name", ""), "estancia": estancias.get(luz.get("room_id"), ""),
                      "estado": "encendida" if valor is True else "apagada" if valor is False else "desconocido",
                      "tipo": luz.get("kind", "")})
    modo = modes_store.leer()
    hosts = datos.get("host_online", {})
    return JSONResponse({
        "ok": True,
        "alarma_armada": bool(shared_state.get_sistema_armado()),
        "modo": modo.get("activo", ""),
        "modo_cambiado_por": modo.get("por", ""),
        "modo_cambiado_ts": modo.get("cambiado"),
        "luces": luces,
        "persianas": persianas,
        "equipos_conectados": sorted(n for n, ok in hosts.items() if ok and not n.startswith(("host_", "node_"))),
        "equipos_sin_conexion": sorted(n for n, ok in hosts.items() if not ok and not n.startswith(("host_", "node_"))),
    })


def _iso_epoch(epoch):
    return datetime.fromtimestamp(epoch).astimezone().isoformat() if epoch else None


async def nodos_casa(request):
    """GET /api/voz/nodos: estado y contacto reciente sin datos de conexión."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    datos = nodes_store.read_all()
    contactos = mqtt_bus.ultimo_contacto_nodos()
    nodos = []
    for nodo in datos.get("nodes", []):
        slug = nodes_store.slugify(nodo.get("name", ""))
        contacto = contactos.get(slug)
        nodos.append({
            "id": nodo.get("id", ""), "nombre": nodo.get("name", ""),
            "host_online": (datos.get("host_online", {}) or {}).get(nodo.get("id")),
            "ultimo_contacto": _iso_epoch(contacto[1]) if contacto else None,
            "segundos_sin_contacto": max(0, int(time.monotonic() - contacto[0])) if contacto else None,
        })
    return JSONResponse({"ok": True, "nodos": nodos})


async def alertas_casa(request):
    """GET /api/voz/alertas: alertas pendientes en forma de lista blanca."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    pendientes = alertas.leer().get("pendientes", {})
    salida = []
    for ident, ficha in pendientes.items():
        partes = ident.split(":")
        if len(partes) != 3 or partes[0] != "alerta":
            continue
        salida.append({"id": ident, "tipo": "alarma", "zona": partes[1],
                       "elemento": partes[2], "hora": _iso_epoch(ficha.get("desde")),
                       "visto": False})
    return JSONResponse({"ok": True, "alertas": salida})


async def alerta_visto(request):
    """POST /api/voz/alertas/{id}/visto: confirma solo el id exacto."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    ident = request.path_params.get("id", "")
    pendientes = alertas.leer().get("pendientes", {})
    if ident not in pendientes:
        return JSONResponse({"ok": False, "mensaje": "La alerta no está pendiente."}, status_code=404)
    alertas.confirmar(ident, "Noxus")
    logs.registrar(logs.ALARMA, "ALERTA_CONFIRMADA", "Noxus",
                   "Alerta confirmada desde la API de voz.", entidad=ident)
    return JSONResponse({"ok": True, "id": ident, "visto": True})


async def automatizaciones_casa(request):
    _, error = _autorizar_lectura(request)
    if error:
        return error
    estados = automations_store.read_state()
    salida = []
    for regla in automations_store.read_all():
        ultima = (estados.get(regla.get("id"), {}) or {}).get("last_run")
        salida.append({"nombre": regla.get("name", ""), "activa": bool(regla.get("enabled")),
                       "ultima_ejecucion": _iso_epoch(ultima) if ultima else None})
    return JSONResponse({"ok": True, "automatizaciones": salida})


async def presencia_casa(request):
    _, error = _autorizar_lectura(request)
    if error:
        return error
    config = presencia_store.leer()
    patron = presencia.aprender()
    ahora = time.localtime()
    fecha = time.strftime("%Y-%m-%d", ahora)
    acciones = presencia.plan_del_dia(
        patron, ahora.tm_wday, config["luces"] or None,
        semilla=int(time.strftime("%Y%m%d", ahora)))
    plan = [{"hora": f"{a['minuto'] // 60:02d}:{a['minuto'] % 60:02d}",
             "elemento": a["luz"], "accion": "encender" if a["encender"] else "apagar"}
            for a in acciones]
    return JSONResponse({"ok": True, "activada": config["activada"], "fecha": fecha,
                         "plan": plan})


async def sensores_casa(request):
    """`GET /api/voz/sensores` — sensores binarios y su último cambio."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    datos = nodes_store.read_all()
    estancias = {r.get("id"): r.get("name", "") for r in datos.get("rooms", [])}
    sensores = datos.get("sensors", [])
    try:
        cambios = logs_store.cambios_sensores_solo_lectura(
            [sensor.get("id", "") for sensor in sensores])
    except (OSError, sqlite3.Error):
        cambios = {}
    estados = datos.get("sensor_states", {})
    salida = []
    for sensor in sensores:
        ident = sensor.get("id", "")
        activo = estados.get(ident)
        kind = sensor.get("kind", "generic")
        if activo is True:
            estado = "abierto" if kind == "door" else "disparado"
        elif activo is False:
            estado = "cerrado" if kind == "door" else "normal"
        else:
            estado = "desconocido"
        cambio = cambios.get(ident, {})
        salida.append({
            "id": ident, "nombre": sensor.get("name", ident),
            "estancia": estancias.get(sensor.get("room_id"), ""),
            "tipo": kind, "estado": estado,
            "cambio_ts": cambio.get("ts"), "cambio": cambio.get("timestamp"),
        })
    return JSONResponse({"ok": True, "sensores": salida})


async def estado_alarma(request):
    """`GET /api/voz/alarma` — armado, zonas que bloquean y eventos recientes."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    limite, error = _limite(request, _MAX_EVENTOS_ALARMA, 20)
    if error:
        return error
    grupos = groups_store.read_all()
    datos = nodes_store.read_all()
    zonas = []
    for grupo in grupos:
        abiertas = _zonas_abiertas(grupo, datos)
        zonas.append({
            "id": grupo.get("id", ""), "nombre": grupo.get("name", ""),
            "armada": bool(grupo.get("armed")),
            "principal": bool(grupo.get("is_principal")),
            "zonas_abiertas": abiertas,
        })
    try:
        eventos = logs_store.eventos_solo_lectura(tipo=logs.ALARMA, limite=limite)
    except (OSError, sqlite3.Error):
        return JSONResponse({"ok": False, "mensaje": "El histórico no está disponible."},
                            status_code=503)
    return JSONResponse({
        "ok": True,
        "armada": bool(shared_state.get_sistema_armado()),
        "modo": modes_store.leer().get("activo", ""),
        "grupos": zonas,
        "zonas_abiertas_que_impiden_armar": [
            {"grupo": zona["nombre"], **abierta}
            for zona in zonas for abierta in zona["zonas_abiertas"]
        ],
        "eventos": [_evento_publico(evento) for evento in eventos],
    })


async def eventos_casa(request):
    """`GET /api/voz/eventos` — histórico acotado y estrictamente de lectura."""
    _, error = _autorizar_lectura(request)
    if error:
        return error
    limite, error = _limite(request, _MAX_EVENTOS, 50)
    if error:
        return error
    desde, error = _desde(request)
    if error:
        return error
    try:
        eventos = logs_store.eventos_solo_lectura(
            desde=desde, tipo=request.query_params.get("tipo", "").strip(),
            dispositivo=request.query_params.get("dispositivo", "").strip(), limite=limite,
        )
    except (OSError, sqlite3.Error):
        return JSONResponse({"ok": False, "mensaje": "El histórico no está disponible."},
                            status_code=503)
    return JSONResponse({"ok": True, "eventos": [_evento_publico(evento) for evento in eventos]})


async def camaras_casa(request):
    """`GET /api/voz/camaras` — configuración y productor activo en go2rtc."""
    _, error = _autorizar_lectura(request, permisos.CAMARAS)
    if error:
        return error
    datos = nodes_store.read_all()
    estancias = {r.get("id"): r.get("name", "") for r in datos.get("rooms", [])}
    streams = await _estado_streams()
    camaras = []
    for camara in datos.get("cameras", []):
        src = camara.get("url") or camara.get("stream_src") or ""
        es_go2rtc = camara.get("kind") == "go2rtc"
        camaras.append({
            "id": camara.get("id", ""), "nombre": camara.get("name", ""),
            "estancia": estancias.get(camara.get("room_id"), ""),
            "en_linea": bool(streams.get(src)) if es_go2rtc else False,
            "foto_disponible": es_go2rtc,
        })
    return JSONResponse({"ok": True, "camaras": camaras})


async def foto_camara(request):
    """`GET /api/voz/camaras/{id}/foto` — JPEG privado, pequeño y sin caché."""
    _, error = _autorizar_lectura(request, permisos.CAMARAS)
    if error:
        return error
    ident = request.path_params.get("id", "")
    camara = next((item for item in nodes_store.read_all().get("cameras", [])
                   if item.get("id") == ident), None)
    if camara is None:
        return JSONResponse({"ok": False, "mensaje": "La cámara no existe."}, status_code=404)
    if camara.get("kind") != "go2rtc":
        return JSONResponse({"ok": False, "mensaje": "Esta cámara no admite instantáneas."},
                            status_code=409)
    src = camara.get("url") or camara.get("stream_src") or ""
    if not src:
        return JSONResponse({"ok": False, "mensaje": "La cámara no tiene fuente configurada."},
                            status_code=409)
    datos, mensaje = await _foto_go2rtc(src)
    if datos is None:
        return JSONResponse({"ok": False, "mensaje": mensaje}, status_code=503)
    return Response(datos, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


RUTAS = [
    Route("/api/voz", control_por_voz, methods=["POST"]),
    Route("/api/voz", listar_comandos, methods=["GET"]),
    Route("/api/voz/inventario", inventario_casa, methods=["GET"]),
    Route("/api/voz/estado", estado_casa, methods=["GET"]),
    Route("/api/voz/nodos", nodos_casa, methods=["GET"]),
    Route("/api/voz/alertas", alertas_casa, methods=["GET"]),
    Route("/api/voz/alertas/{id}/visto", alerta_visto, methods=["POST"]),
    Route("/api/voz/automatizaciones", automatizaciones_casa, methods=["GET"]),
    Route("/api/voz/presencia", presencia_casa, methods=["GET"]),
    Route("/api/voz/sensores", sensores_casa, methods=["GET"]),
    Route("/api/voz/alarma", estado_alarma, methods=["GET"]),
    Route("/api/voz/eventos", eventos_casa, methods=["GET"]),
    Route("/api/voz/camaras", camaras_casa, methods=["GET"]),
    Route("/api/voz/camaras/{id}/foto", foto_camara, methods=["GET"]),
]
