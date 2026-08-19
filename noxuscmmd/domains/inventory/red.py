"""Lo que la máquina puede averiguar sola: tabla ARP y nodos de Tailscale.

Todo lo de aquí es de solo lectura y tolerante a fallos: si `tailscale` no está
instalado, si el mandato tarda, o si el formato cambia, se devuelve lo que haya
y el inventario enseña esos campos vacíos. Un inventario a medias es útil; uno
que revienta la pantalla de Ajustes, no.
"""
import json
import re
import subprocess
import time

# Las dos consultas se cachean: la pantalla de inventario repinta con cada
# cambio de estado y lanzar un proceso por repintado sobraría. 30 s es más que
# suficiente para algo que cambia cuando enchufas un aparato nuevo.
_TTL = 30.0
_cache: dict[str, tuple[float, object]] = {}


def _cacheado(clave: str, calcular):
    ahora = time.time()
    guardado = _cache.get(clave)
    if guardado and ahora - guardado[0] < _TTL:
        return guardado[1]
    valor = calcular()
    _cache[clave] = (ahora, valor)
    return valor


def olvidar_cache() -> None:
    """Para el botón de «actualizar ahora» de la pantalla."""
    _cache.clear()


# ── Tabla ARP ────────────────────────────────────────────────────────────
_MAC = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", re.I)


def es_de_tailscale(ip: str) -> bool:
    """Si una IP es del rango que reparte Tailscale (100.64.0.0/10).

    Hace falta porque el CurAddr de un nodo no siempre es una dirección de la
    red de casa: cuando la conexión va por un salto intermedio trae otra IP
    del propio Tailscale, y colarla en la columna «IP local» sería mentir —
    esa dirección no la va a encontrar nadie en el router."""
    partes = (ip or "").split(".")
    if len(partes) != 4:
        return False
    try:
        return int(partes[0]) == 100 and 64 <= int(partes[1]) <= 127
    except ValueError:
        return False


def _leer_arp() -> dict[str, str]:
    """{ip local: MAC} de lo que este servidor ha visto en la red.

    Solo aparece lo que ha hablado con este servidor hace poco: un aparato
    encendido pero callado puede no salir. Por eso la MAC descubierta no pisa
    nunca a la que esté escrita a mano."""
    tabla: dict[str, str] = {}
    try:
        salida = subprocess.run(
            ["ip", "neigh", "show"], capture_output=True, text=True, timeout=5
        ).stdout
        for linea in salida.splitlines():
            partes = linea.split()
            if "lladdr" not in partes:
                continue  # FAILED / INCOMPLETE: no se sabe la MAC
            ip = partes[0]
            mac = partes[partes.index("lladdr") + 1]
            if _MAC.match(mac):
                tabla[ip] = mac.lower()
    except Exception:
        # Sin `ip` (o sin permiso): el fichero de siempre.
        try:
            with open("/proc/net/arp") as f:
                for linea in f.readlines()[1:]:
                    campos = linea.split()
                    if len(campos) >= 4 and _MAC.match(campos[3]):
                        tabla[campos[0]] = campos[3].lower()
        except Exception:
            pass
    return tabla


def tabla_arp() -> dict[str, str]:
    return _cacheado("arp", _leer_arp)


# ── Tailscale ────────────────────────────────────────────────────────────
def _ip_local_propia() -> str:
    """La IP de este servidor en la red de casa.

    Hace falta aparte porque Tailscale no dice la IP local de uno mismo: el
    CurAddr es la dirección por la que se llega a OTRO nodo, y a uno mismo no
    se llega. Sin esto, el servidor —que es el aparato más importante del
    inventario— salía sin IP local."""
    try:
        salida = subprocess.run(
            ["ip", "route", "get", "1.1.1.1"],
            capture_output=True, text=True, timeout=4,
        ).stdout
        marca = salida.split(" src ")
        if len(marca) > 1:
            return marca[1].split()[0]
    except Exception:
        pass
    return ""


def mac_propia() -> str:
    """La MAC de este servidor.

    Tampoco sale en la tabla ARP: ahí está lo que el servidor ha visto de los
    DEMÁS, no lo suyo. Se lee de la interfaz por la que sale a la red."""
    try:
        salida = subprocess.run(
            ["ip", "route", "get", "1.1.1.1"],
            capture_output=True, text=True, timeout=4,
        ).stdout
        trozos = salida.split(" dev ")
        if len(trozos) < 2:
            return ""
        interfaz = trozos[1].split()[0]
        with open(f"/sys/class/net/{interfaz}/address") as f:
            mac = f.read().strip().lower()
        return mac if _MAC.match(mac) else ""
    except Exception:
        return ""


def _leer_tailscale() -> list[dict]:
    try:
        salida = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=8,
        )
        if salida.returncode != 0:
            return []
        datos = json.loads(salida.stdout)
    except Exception:
        return []

    nodos = []

    def _añadir(p: dict, propio: bool):
        ips = p.get("TailscaleIPs") or []
        # Solo la IPv4 (100.x): la IPv6 de Tailscale no la teclea nadie.
        ip_ts = next((i for i in ips if ":" not in i), "")
        # CurAddr trae "192.168.1.151:41641" cuando la conexión es DIRECTA.
        # Si va por relay o el aparato está apagado, viene vacío — de ahí que
        # el emparejamiento tenga que saber apañarse también por el nombre.
        ip_lan = (p.get("CurAddr") or "").rsplit(":", 1)[0]
        if es_de_tailscale(ip_lan):
            ip_lan = ""  # no es una dirección de la red de casa
        if propio:
            ip_lan = _ip_local_propia()
        nodos.append({
            "nombre": p.get("HostName") or "",
            "ip_tailscale": ip_ts,
            "ip_lan": ip_lan,
            "so": p.get("OS") or "",
            "en_linea": bool(p.get("Online")) or propio,
            "propio": propio,
        })

    if datos.get("Self"):
        _añadir(datos["Self"], True)
    for p in (datos.get("Peer") or {}).values():
        _añadir(p, False)
    return nodos


def nodos_tailscale() -> list[dict]:
    return _cacheado("tailscale", _leer_tailscale)


def hay_tailscale() -> bool:
    return bool(nodos_tailscale())


# ── Emparejar un equipo del panel con su nodo de Tailscale ───────────────
def _palabras(nombre: str) -> frozenset[str]:
    """Las palabras de un nombre, en minúsculas y sin separadores.

    Sirve para que «SALON-PC» (como se llama en Tailscale) y «PC Salon» (como
    se llama en el panel) se reconozcan como el mismo equipo. Comparar las
    cadenas enteras no valdría: nadie pone el mismo nombre en los dos sitios.
    """
    limpio = re.sub(r"[^a-z0-9]+", " ", (nombre or "").lower())
    return frozenset(p for p in limpio.split() if len(p) > 1)


def emparejar(nombre: str, ip: str = "") -> dict | None:
    """El nodo de Tailscale que corresponde a un equipo, o None.

    `ip` es la que tenga puesta el equipo en su ficha, sea la de la red de
    casa o la de Tailscale — en esta instalación los equipos están dados de
    alta con la de Tailscale (100.x), que es la que funciona desde fuera, así
    que hay que mirar las dos.

    Por orden de fiabilidad: las dos IP primero, que son datos duros, y solo si
    no hay suerte por el nombre, que es una apuesta. Un empate entre varios
    nombres se deja sin resolver a propósito: preferimos un hueco vacío a
    decirle a alguien que el portátil tiene una IP que no es la suya."""
    nodos = nodos_tailscale()
    if not nodos or not (nombre or ip):
        return None

    if ip:
        for n in nodos:
            if n["ip_tailscale"] and n["ip_tailscale"] == ip:
                return n
        for n in nodos:
            if n["ip_lan"] and n["ip_lan"] == ip:
                return n

    mias = _palabras(nombre)
    if not mias:
        return None
    candidatos = [n for n in nodos if _palabras(n["nombre"]) == mias]
    if len(candidatos) == 1:
        return candidatos[0]

    # Sin coincidencia exacta: uno que contenga a todas las palabras del otro
    # («pc casa» dentro de «pc casa portatil»). También tiene que ser único.
    candidatos = [
        n for n in nodos
        if mias and (mias <= _palabras(n["nombre"]) or _palabras(n["nombre"]) <= mias)
    ]
    return candidatos[0] if len(candidatos) == 1 else None
