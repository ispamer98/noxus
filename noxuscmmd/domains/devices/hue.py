"""
Alexa sin nube, sin skill y sin cuenta de desarrollador: el panel se hace pasar
por un puente Philips Hue.

POR QUÉ ASÍ. Para que un Echo obedezca hay tres caminos: una Smart Home Skill
(cuenta de desarrollador de Amazon, un Lambda en AWS y todo pasando por su nube),
un dispositivo Zigbee de verdad, o **hablar el protocolo de un puente Hue**, que
los Echo descubren ellos solos en la red local. El tercero es el único que cumple
lo que se pidió: configurar solo Noxus y que se vincule con lo que haya. No hay
cuenta, no hay skill, no sale un byte de casa.

QUÉ VE ALEXA. Cada comando de voz guardado (Ajustes → Comandos de voz) se publica
como una «luz». Decir «Alexa, enciende buenas noches» la enciende, y encenderla
ejecuta el comando. Se publican SOLO los guardados y no los 89 del catálogo:
ochenta y nueve luces falsas en la app de Alexa no las quiere nadie, y así el
nombre con el que Alexa conoce cada cosa lo eliges tú.

DOS COSAS INCÓMODAS QUE HAY QUE SABER, y las digo aquí porque no se ven:

1. EL PUERTO 80 ES OBLIGATORIO. Los Echo no aceptan un puente Hue en otro puerto,
   está clavado en su firmware. Un proceso que no es root no puede abrirlo, así
   que la unidad de systemd necesita CAP_NET_BIND_SERVICE. Si no lo tiene, esto
   se queda dormido y lo dice en el log en vez de reventar el arranque.

2. QUIEN ESTÉ EN TU RED PUEDE EJECUTAR ESTOS COMANDOS. El protocolo Hue no tiene
   autenticación de verdad: el «usuario» que negocia es un trámite, cualquiera lo
   consigue pidiéndolo. Por eso escucha SOLO en la IP de la red local —nunca por
   el túnel— y por eso se publican solo los comandos que hayas elegido. Aun así:
   lo que publiques aquí lo puede accionar cualquier aparato de tu casa sin
   identificarse. No publiques la puerta si eso te preocupa.

Y una limitación de Alexa, no de esto: los dispositivos de un puente Hue son de
la CUENTA, no de un Echo concreto. Los dos Echo verán los mismos comandos y
cualquiera de los dos los ejecuta; no hay forma local de decir «esto solo desde
el de la habitación».
"""
import asyncio
import hashlib
import os
import socket

from aiohttp import web

from ..automations import actions
from ..modes import state as modes_state
from ..nodes import store as nodes_store
from ..security import logs
from . import comandos

# Obligatorio el 80: ver la nota 2 de la cabecera. Se deja en variable solo para
# poder probar en otro puerto sin permisos.
PUERTO = int(os.getenv("HUE_PUERTO", "80"))

# En qué IP se escucha. Vacío = se descubre la de la red local. NUNCA 0.0.0.0 por
# defecto: esto no debe asomar por el túnel ni por Tailscale.
IP = os.getenv("HUE_IP", "")

SSDP_GRUPO, SSDP_PUERTO = "239.255.255.250", 1900

# Un identificador estable para el puente. Sale del nombre de la máquina, así que
# no cambia entre reinicios: si cambiara, Alexa creería que es otro puente y
# duplicaría todos los dispositivos.
_SEMILLA = hashlib.sha1(socket.gethostname().encode()).hexdigest()
BRIDGE_ID = _SEMILLA[:12].upper()
BRIDGE_MAC = ":".join(BRIDGE_ID[i:i + 2] for i in range(0, 12, 2)).lower()
UUID = f"2f402f80-da50-11e1-9b23-{BRIDGE_ID.lower()}"

# El estado encendido/apagado de cada comando. Es solo para contestar a Alexa
# cuando pregunta: un comando no tiene estado de verdad («abrir la puerta» no se
# queda abierta), pero si el puente contesta siempre «apagado», Alexa insiste y
# acaba diciendo que el dispositivo no responde.
_encendidos: dict[str, bool] = {}


def _ip_local() -> str:
    """La IP de esta máquina en la red de casa.

    Se averigua abriendo un socket UDP hacia fuera y mirando qué IP le asigna el
    sistema: no manda ningún paquete, y acierta con la interfaz correcta sin
    tener que adivinar nombres (eno1, enp3s0...) ni quedarse con la de Tailscale.
    """
    if IP:
        return IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _ips_de_casa() -> list[str]:
    """Todas las IPv4 de la máquina en redes privadas, menos la de Tailscale.

    Hace falta porque este servidor está en el cable Y en la wifi a la vez, y los
    Echo están en la wifi: el multicast de descubrimiento no cruza de una a otra
    si el router no lo reenvía, así que hay que unirse al grupo y anunciarse por
    LAS DOS. Uniéndose solo por la de la ruta por defecto (el cable) el Echo no
    oía nada, que es lo que estaba pasando.

    Se descarta el 100.x de Tailscale: por ahí no hay ningún Echo y anunciarse
    sería asomar el puente a una red donde no debe estar."""
    salida = []
    try:
        import subprocess
        crudo = subprocess.run(["ip", "-4", "-o", "addr", "show"],
                               capture_output=True, text=True, timeout=3).stdout
        for linea in crudo.splitlines():
            partes = linea.split()
            if len(partes) < 4 or partes[1] == "lo" or "tailscale" in partes[1]:
                continue
            ip = partes[3].split("/")[0]
            if ip.startswith(("192.168.", "10.", "172.")) and ip not in salida:
                salida.append(ip)
    except Exception as e:
        print(f"⚠️ Alexa: no se pudieron listar las interfaces: {e}")
    return salida or [_ip_local()]


def _luces() -> dict[str, dict]:
    """Los comandos publicados, con la forma que espera un puente Hue.

    El id de cada luz es su POSICIÓN en la lista, empezando en 1, porque el
    protocolo Hue exige números. Se ordena por la frase (list_comandos_voz ya lo
    hace) para que el número de cada uno no baile al añadir otro — si bailara,
    Alexa acabaría con el nombre de un comando apuntando a otro."""
    salida = {}
    catalogo = {c["id"]: c for c in comandos.comandos()}
    for i, guardado in enumerate(nodes_store.list_comandos_voz(), start=1):
        if guardado.get("comando") not in catalogo:
            continue  # apunta a algo que ya no existe: no se publica
        nombre = guardado["frase"]
        salida[str(i)] = {
            "state": {
                "on": _encendidos.get(guardado["id"], False),
                "bri": 254, "alert": "none", "reachable": True,
            },
            # "Dimmable light" y no una de color: Alexa no le pide colores y así
            # no hay que fingir un espacio de color que no existe.
            "type": "Dimmable light",
            "name": nombre,
            "modelid": "LWB004",
            "manufacturername": "Philips",
            # Ocho pares y "-0b" al final, como un dispositivo Zigbee de verdad:
            # Alexa valida la forma de este campo y descarta las luces cuyo
            # identificador no le cuadra.
            "uniqueid": f"00:17:88:5e:d3:00:{i:02x}:{i:02x}-0b",
            "swversion": "66009461",
            # Lo que hay que hacer si la encienden. No se lo manda a Alexa: es
            # para uso interno de este módulo.
            "_comando": guardado["comando"],
            "_voz": guardado["id"],
        }
    return salida


async def _ejecutar(luz: dict) -> None:
    """Ejecuta el comando de esa luz. No levanta nunca: si algo falla, Alexa se
    queda sin saberlo (no hay forma de decírselo) pero el log sí lo cuenta."""
    catalogo = {c["id"]: c for c in comandos.comandos()}
    comando = catalogo.get(luz["_comando"])
    if comando is None:
        return
    try:
        paso = comando["paso"]
        if paso["type"] == "modo":
            await modes_state.aplicar(paso["target"], "Alexa")
        elif paso["type"] != "vista":
            await actions.dispatch(paso)
        logs.registrar(logs.SISTEMA, "COMANDO_POR_VOZ", "Alexa",
                       f"{comando['etiqueta']} · «{luz['name']}»")
    except Exception as e:
        print(f"⚠️ Alexa pidió «{luz['name']}» y falló: {e}")
        logs.registrar(logs.SISTEMA, "COMANDO_POR_VOZ", "Alexa",
                       f"{comando['etiqueta']} — FALLÓ: {e}")


# ── El puente, por HTTP ─────────────────────────────────────────────────────
def _descripcion(ip: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion><major>1</major><minor>0</minor></specVersion>
<URLBase>http://{ip}:{PUERTO}/</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>Noxus ({ip})</friendlyName>
<manufacturer>Royal Philips Electronics</manufacturer>
<modelName>Philips hue bridge 2015</modelName>
<modelNumber>BSB002</modelNumber>
<serialNumber>{BRIDGE_ID.lower()}</serialNumber>
<UDN>uuid:{UUID}</UDN>
</device>
</root>"""


async def _get_descripcion(request):
    return web.Response(text=_descripcion(_ip_local()), content_type="application/xml")


async def _emparejar(request):
    """El «registro» de un usuario nuevo. Se acepta a cualquiera: en el protocolo
    Hue esto se autoriza pulsando el botón físico del puente, que aquí no existe.
    Es la razón de que este servicio solo escuche en la red local."""
    print(f"🔊 Alexa: {request.remote} se ha emparejado con el puente")
    return web.json_response([{"success": {"username": "noxus"}}])


def _sin_internos(luces: dict) -> dict:
    """Las luces sin los campos que empiezan por «_»: son de este módulo y no
    tienen por qué viajar a Alexa."""
    return {
        lid: {k: v for k, v in luz.items() if not k.startswith("_")}
        for lid, luz in luces.items()
    }


def _config() -> dict:
    """La ficha del puente.

    Los números NO son inventados y no conviene "actualizarlos": son los de un
    puente Hue viejo a propósito. Alexa mira `apiversion` para decidir con qué
    dialecto habla, y anunciando uno moderno se pone a pedir el API nuevo (el de
    los recursos v2) que esto no implementa — y el resultado es que descubre el
    puente, no encuentra ninguna luz y se queda callada. Con 1.16.0 usa el API
    v1, que es el que hay aquí.
    """
    return {
        "name": "Noxus", "bridgeid": BRIDGE_ID, "modelid": "BSB002",
        "mac": BRIDGE_MAC, "ipaddress": _ip_local(),
        "swversion": "01041302", "apiversion": "1.16.0",
        "datastoreversion": "63", "zigbeechannel": 15,
        "linkbutton": False, "dhcp": True, "portalservices": False,
        "factorynew": False, "replacesbridgeid": None, "starterkitid": "",
        "timezone": "Europe/Madrid",
        "whitelist": {"noxus": {"name": "Noxus", "create date": "2026-01-01",
                                "last use date": "2026-01-01"}},
    }


async def _get_config(request):  # noqa: D401
    """`/api/config` SIN usuario. Es la primera que pide Alexa para comprobar que
    al otro lado hay un puente Hue de verdad; sin ella descubre el aparato, no lo
    reconoce y no llega a pedir las luces nunca."""
    print(f"🔊 Alexa: {request.remote} está comprobando el puente")
    return web.json_response(_config())


async def _get_todo(request):
    return web.json_response({
        "lights": _sin_internos(_luces()),
        "groups": {}, "schedules": {}, "scenes": {}, "rules": {}, "sensors": {},
        "config": _config(),
    })


async def _get_grupos(request):
    return web.json_response({})


async def _get_luces(request):
    """Además de contestar, deja rastro. Sin esto no había forma de saber si el
    Echo llegaba a hablar con el puente o se quedaba en el descubrimiento: el
    servidor va sin registro de accesos a propósito (una petición por segundo de
    Alexa llenaría el journal), así que esta línea es el único aviso de «te ha
    encontrado»."""
    luces = _luces()
    print(f"🔊 Alexa: {request.remote} ha pedido la lista — {len(luces)} comando(s)")
    return web.json_response(_sin_internos(luces))


async def _get_luz(request):
    luces = _luces()
    luz = luces.get(request.match_info["lid"])
    if luz is None:
        return web.json_response({}, status=404)
    return web.json_response(_sin_internos({"x": luz})["x"])


async def _put_estado(request):
    """Aquí es donde Alexa dice «enciéndela». `on: true` ejecuta el comando.

    Se contesta ANTES de ejecutar, y no después: un comando puede tardar
    (un SSH, un pulso de puerta) y si el puente tarda en responder, Alexa da el
    dispositivo por no disponible y dice «no responde» aunque haya funcionado.
    La ejecución se queda corriendo en su propia tarea."""
    lid = request.match_info["lid"]
    luz = _luces().get(lid)
    if luz is None:
        return web.json_response({}, status=404)
    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}

    respuesta = []
    if "on" in cuerpo:
        encendida = bool(cuerpo["on"])
        _encendidos[luz["_voz"]] = encendida
        respuesta.append({"success": {f"/lights/{lid}/state/on": encendida}})
        if encendida:
            tarea = asyncio.create_task(_ejecutar(luz))
            _tareas.add(tarea)
            tarea.add_done_callback(_tareas.discard)
    if "bri" in cuerpo:
        # El brillo se acepta y se ignora: un comando no tiene intensidad, pero
        # si el puente rechaza la petición, Alexa lo cuenta como un fallo.
        respuesta.append({"success": {f"/lights/{lid}/state/bri": cuerpo["bri"]}})
    return web.json_response(respuesta or [{"success": {}}])


# Las ejecuciones en vuelo. Igual que en el vigilante: el bucle de eventos solo
# guarda una referencia débil a las tareas y una que nadie sujete puede irse con
# el recolector de basura a mitad.
_tareas: set[asyncio.Task] = set()


def _app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/description.xml", _get_descripcion),
        web.post("/api", _emparejar),
        web.post("/api/", _emparejar),
        # `config` va ANTES de la ruta con comodín: si no, "/api/config" casaría
        # con "/api/{usuario}" y contestaría el volcado entero en vez de la ficha.
        web.get("/api/config", _get_config),
        web.get("/api/{usuario}/config", _get_config),
        web.get("/api/{usuario}/groups", _get_grupos),
        web.get("/api/{usuario}", _get_todo),
        web.get("/api/{usuario}/", _get_todo),
        web.get("/api/{usuario}/lights", _get_luces),
        web.get("/api/{usuario}/lights/{lid}", _get_luz),
        web.put("/api/{usuario}/lights/{lid}/state", _put_estado),
    ])
    return app


# ── El anuncio, por SSDP ────────────────────────────────────────────────────
# IPs que ya han buscado alguna vez, para no repetir la línea del log: un Echo
# manda M-SEARCH cada pocos segundos y llenaría el journal.
_vistos: set[str] = set()


class _Ssdp(asyncio.DatagramProtocol):
    """Contesta a los «¿hay algún puente ahí?» que lanzan los Echo.

    Es la mitad que hace que no haya que configurar nada: Alexa manda un M-SEARCH
    por multicast al buscar dispositivos, y quien contesta con la pinta de un
    puente Hue entra en la lista."""

    def __init__(self, ip: str):
        self.ip = ip
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            texto = data.decode(errors="ignore")
        except Exception:
            return
        if "M-SEARCH" not in texto.upper():
            return
        # Rastro de que alguien pregunta, una vez por aparato. Sin esto no había
        # forma de distinguir «el Echo no me llega» de «me llega y me ignora», que
        # son dos averías completamente distintas.
        if addr[0] not in _vistos:
            _vistos.add(addr[0])
            print(f"🔊 Alexa: {addr[0]} está buscando dispositivos en la red")
        # Solo a quien busca dispositivos básicos o todo: contestar a cualquier
        # M-SEARCH es ruido en la red de casa.
        buscado = texto.lower()
        if not any(x in buscado for x in ("basic:1", "ssdp:all", "rootdevice")):
            return
        respuesta = (
            "HTTP/1.1 200 OK\r\n"
            f"HOST: {SSDP_GRUPO}:{SSDP_PUERTO}\r\n"
            "EXT:\r\n"
            "CACHE-CONTROL: max-age=100\r\n"
            f"LOCATION: http://{self.ip}:{PUERTO}/description.xml\r\n"
            "SERVER: FreeRTOS/6.0.5, UPnP/1.0, IpBridge/1.17.0\r\n"
            f"hue-bridgeid: {BRIDGE_ID}\r\n"
            "ST: urn:schemas-upnp-org:device:basic:1\r\n"
            f"USN: uuid:{UUID}\r\n\r\n"
        )
        try:
            self.transport.sendto(respuesta.encode(), addr)
        except Exception as e:
            print(f"⚠️ SSDP: no se pudo contestar a {addr}: {e}")


async def run_forever() -> None:
    """Levanta el puente falso. Si no puede, lo dice y se calla.

    No reventar el arranque es deliberado: esto es un extra. Que Alexa no
    funcione no puede impedir que la casa arranque con su alarma."""
    ip = _ip_local()
    try:
        runner = web.AppRunner(_app(), access_log=None)
        await runner.setup()
        # Se escucha SOLO en las IP de casa, una a una. En todas y no en una
        # sola porque el Echo puede estar en la wifi y el panel en el cable,
        # pero NUNCA en 0.0.0.0: este servicio no tiene autenticación de verdad
        # (_emparejar acepta a cualquiera y _put_estado ejecuta comandos de la
        # casa), así que con 0.0.0.0 quedaría también en la IP 100.x de
        # Tailscale y cualquier nodo del tailnet accionaría la casa sin decir
        # quién es. _ips_de_casa() ya descarta esa.
        abiertas = []
        for una in _ips_de_casa():
            try:
                await web.TCPSite(runner, una, PUERTO).start()
                abiertas.append(una)
            except OSError as e:
                print(f"⚠️ Alexa: no se puede escuchar en {una}:{PUERTO}: {e}")
        if not abiertas:
            print("⚠️ Alexa: no se pudo escuchar en ninguna IP de casa. El "
                  "puente Hue queda apagado; todo lo demás funciona igual.")
            return
    except PermissionError:
        print(f"⚠️ Alexa: no se puede abrir el puerto {PUERTO} (hace falta "
              f"CAP_NET_BIND_SERVICE en el servicio). El puente Hue queda "
              f"apagado; todo lo demás funciona igual.")
        return
    except Exception as e:
        print(f"⚠️ Alexa: no se pudo levantar el puente Hue: {e}")
        return

    try:
        transporte, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: _Ssdp(ip),
            local_addr=("0.0.0.0", SSDP_PUERTO),
            reuse_port=True,
            family=socket.AF_INET,
        )
        sock = transporte.get_extra_info("socket")
        # Al grupo por CADA interfaz de casa: el cable y la wifi. Con una sola no
        # se oye lo que llega por la otra.
        for una in _ips_de_casa():
            try:
                sock.setsockopt(
                    socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton(SSDP_GRUPO) + socket.inet_aton(una),
                )
            except OSError as e:
                print(f"⚠️ Alexa: no se pudo escuchar multicast por {una}: {e}")
    except Exception as e:
        print(f"⚠️ Alexa: el puente responde en http://{ip}:{PUERTO} pero no "
              f"puede anunciarse (SSDP): {e}")
    else:
        print(f"🔊 Alexa: puente Hue (id {BRIDGE_ID}) en "
              f"{', '.join(f'{x}:{PUERTO}' for x in _ips_de_casa())} "
              f"— di «Alexa, busca dispositivos»")

    # Y se anuncia por su cuenta cada minuto, sin esperar a que pregunten.
    #
    # Hace falta de verdad: no todos los Echo descubren por M-SEARCH. Varios
    # modelos se quedan con lo que hayan oído en los anuncios NOTIFY que los
    # aparatos mandan al aparecer, y con un puente que solo contesta cuando se le
    # pregunta no se enteran nunca — que es exactamente lo que estaba pasando.
    #
    # Un paquete por minuto en la red de casa no molesta a nadie, y es lo que hace
    # un puente Hue de verdad.
    while True:
        try:
            for una in _ips_de_casa():
                await asyncio.to_thread(_anunciar, una)
        except Exception as e:
            print(f"⚠️ Alexa: no se pudo anunciar el puente: {e}")
        await asyncio.sleep(60)


def _anunciar(ip: str) -> None:
    """Manda los tres NOTIFY que manda un puente Hue al aparecer: uno por cada
    tipo de servicio que anuncia. Los tres, y no uno, porque cada modelo de Echo
    se fija en uno distinto."""
    aviso = (
        "NOTIFY * HTTP/1.1\r\n"
        f"HOST: {SSDP_GRUPO}:{SSDP_PUERTO}\r\n"
        "CACHE-CONTROL: max-age=100\r\n"
        f"LOCATION: http://{ip}:{PUERTO}/description.xml\r\n"
        "SERVER: FreeRTOS/6.0.5, UPnP/1.0, IpBridge/1.17.0\r\n"
        "NTS: ssdp:alive\r\n"
        f"hue-bridgeid: {BRIDGE_ID}\r\n"
        "NT: {nt}\r\n"
        "USN: {usn}\r\n\r\n"
    )
    tipos = (
        ("upnp:rootdevice", f"uuid:{UUID}::upnp:rootdevice"),
        (f"uuid:{UUID}", f"uuid:{UUID}"),
        ("urn:schemas-upnp-org:device:basic:1", f"uuid:{UUID}"),
    )
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        # Se sale por la interfaz de la red de casa y no por la que el sistema
        # elija: con Tailscale levantado, el anuncio se iba por el túnel y no lo
        # oía nadie de casa.
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                     socket.inet_aton(ip))
        for nt, usn in tipos:
            s.sendto(aviso.format(nt=nt, usn=usn).encode(),
                     (SSDP_GRUPO, SSDP_PUERTO))
    finally:
        s.close()
