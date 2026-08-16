"""
Puente con la TV LG (webOS) por red local — para lo que el Broadlink NO puede
hacer.

El Magic Remote es híbrido: la mayoría de sus botones (encender, números,
volumen, canales, flechas, OK, atrás, ajustes) SÍ salen por infrarrojos y por
tanto se aprenden y se repiten con el Broadlink como cualquier otro mando. Pero
Home, el micrófono, la rueda y los accesos directos a apps viajan por una RF
propietaria de LG hacia la tele: no emiten infrarrojos, así que no hay nada que
el Broadlink pueda escuchar ni repetir. Esos van por aquí.

Es la MISMA vía que usa la app oficial de LG, pero hablando directamente con la
tele por su IP local (WebSocket), sin pasar por ninguna nube. La primera vez la
tele muestra en pantalla un aviso pidiendo permiso: se acepta UNA vez con el
mando físico y queda una clave guardada en disco (WEBOS_KEY_FILE) que ya vale
para siempre.

Igual que ir_bus/mqtt_bus: cliente único de proceso, reutilizado entre botones.
"""
import asyncio
import json
import os
from pathlib import Path

# Fichero donde queda la clave que devuelve la tele al aceptar el emparejamiento.
_KEY_FILE = Path(os.getenv("WEBOS_KEY_FILE", "webos_key.json"))

_client = None

# Hay UNA tele y UN WebSocket hacia ella, así que las órdenes van de una en
# una. Sin esto, dos pulsaciones a la vez (dos pestañas abiertas, o una regla
# disparando mientras alguien usa el mando de la web) se entrelazan sobre la
# misma conexión, y dos que lleguen antes de que _get_client termine de
# conectar abren DOS clientes: el segundo pisa el global y el primero queda
# huérfano y sin cerrar.
_LOCK = asyncio.Lock()


def _leer_clave(host: str) -> str | None:
    try:
        return json.loads(_KEY_FILE.read_text()).get(host)
    except Exception:
        return None


def _guardar_clave(host: str, clave: str) -> None:
    try:
        datos = json.loads(_KEY_FILE.read_text()) if _KEY_FILE.exists() else {}
    except Exception:
        datos = {}
    datos[host] = clave
    _KEY_FILE.write_text(json.dumps(datos, indent=2))


async def _get_client():
    """Cliente conectado y autorizado. La primera vez que se llama sin clave
    guardada, la tele saca el aviso de permiso en pantalla y esta llamada se
    queda esperando a que se acepte con el mando."""
    global _client
    host = os.getenv("IP_TV_LG", "").strip()
    if not host:
        raise RuntimeError(
            "Falta IP_TV_LG en .env — pon ahí la IP local de la tele (reservada "
            "en el router, igual que la del Broadlink) para poder usar los "
            "botones que no salen por infrarrojos."
        )

    if _client is not None and _client.is_connected():
        return _client

    # Import perezoso: si aiowebostv no está instalado, el resto del sistema
    # (que no lo necesita) tiene que seguir arrancando igual.
    from aiowebostv import WebOsClient

    _client = WebOsClient(host, _leer_clave(host))
    await _client.connect()
    # connect() rellena client_key tras aceptar el aviso en la tele; se guarda
    # para no volver a pedir permiso nunca más.
    if _client.client_key:
        _guardar_clave(host, _client.client_key)
    return _client


# Botones de navegación que webOS entiende por su nombre. El resto de comandos
# (lanzar una app) se resuelven como id de aplicación — ver send_command.
_BOTONES = {
    "HOME", "BACK", "UP", "DOWN", "LEFT", "RIGHT", "ENTER", "EXIT", "MENU",
    "INFO", "GUIDE", "QMENU", "DASH", "ASTERISK", "CC", "RED", "GREEN",
    "YELLOW", "BLUE", "VOLUMEUP", "VOLUMEDOWN", "CHANNELUP", "CHANNELDOWN",
    "PLAY", "PAUSE", "STOP", "REWIND", "FASTFORWARD",
}

# Nombre corto -> id real de la app en webOS. Los ids son los que usa LG
# internamente y no coinciden con el nombre comercial.
_APPS = {
    "netflix": "netflix",
    "amazon": "amazon",
    "disneyplus": "com.disney.disneyplus-prod",
    "rakuten": "ui30",
    "youtube": "youtube.leanback.v4",
    "spotify": "spotify-beehive",
    "plex": "cdp-30",
    "movistar": "com.movistarplus.webos",
}


async def send_command(comando: str) -> None:
    """Ejecuta un comando webOS. `comando` es o el nombre de un botón de
    navegación (HOME, BACK...) o el nombre corto de una app a lanzar
    (netflix, disneyplus...) — ver _BOTONES y _APPS."""
    if not comando:
        raise RuntimeError(
            "Este botón no tiene comando asignado — edítalo y elige qué debe hacer."
        )
    async with _LOCK:
        client = await _get_client()
        clave = comando.strip()
        if clave.upper() in _BOTONES:
            await client.button(clave.upper())
            return
        await client.launch_app(_APPS.get(clave.lower(), clave))


async def is_on() -> bool:
    """True si la tele está encendida y responde. A diferencia del IR (que es
    ciego), aquí sí hay estado real que consultar."""
    try:
        async with _LOCK:
            client = await _get_client()
            return bool(client.is_connected())
    except Exception:
        return False


def comandos_disponibles() -> list[tuple[str, str]]:
    """[(valor, etiqueta)] para el desplegable del editor de botón."""
    navegacion = [
        ("HOME", "Home (pantalla de inicio)"),
        ("BACK", "Atrás"),
        ("UP", "Arriba"), ("DOWN", "Abajo"),
        ("LEFT", "Izquierda"), ("RIGHT", "Derecha"),
        ("ENTER", "OK / Entrar"),
        ("EXIT", "Salir"),
        ("MENU", "Menú"),
        ("INFO", "Info"),
        ("GUIDE", "Guía"),
        ("VOLUMEUP", "Volumen +"), ("VOLUMEDOWN", "Volumen −"),
        ("CHANNELUP", "Canal +"), ("CHANNELDOWN", "Canal −"),
        ("PLAY", "Reproducir"), ("PAUSE", "Pausa"), ("STOP", "Parar"),
        ("REWIND", "Retroceder"), ("FASTFORWARD", "Avanzar"),
        ("RED", "Botón rojo"), ("GREEN", "Botón verde"),
        ("YELLOW", "Botón amarillo"), ("BLUE", "Botón azul"),
    ]
    apps = [
        ("netflix", "Abrir Netflix"),
        ("amazon", "Abrir Prime Video"),
        ("disneyplus", "Abrir Disney+"),
        ("rakuten", "Abrir Rakuten TV"),
        ("youtube", "Abrir YouTube"),
        ("spotify", "Abrir Spotify"),
        ("plex", "Abrir Plex"),
        ("movistar", "Abrir Movistar+"),
    ]
    return navegacion + apps


def forget_connection() -> None:
    """Fuerza reconexión en el próximo uso (cambio de IP, tele reiniciada)."""
    global _client
    _client = None
