"""
Salud del sistema: las cinco piezas de las que depende que la casa funcione.

Existe porque hasta ahora todas fallaban en silencio. Si el motor de
automatizaciones se para, las reglas dejan de ejecutarse y el panel sigue
enseñándolas como activas. Si go2rtc se cae, el mural sale en negro y parece un
problema de la cámara. Si el túnel se cae, desde dentro de casa todo va bien.
Cada una de esas averías se ha notado antes por sus consecuencias —«esto ya no
hace lo que hacía»— y no por el sitio donde estaba el problema.

Reglas de esta pantalla:

  - CADA COMPROBACIÓN CON SU PROPIO TEMPORIZADOR Y SU PROPIO try. Es una pantalla
    de diagnóstico: si se cuelga entera porque una de las cinco no responde, deja
    de servir justo el día que hace falta.
  - TRES ESTADOS Y NO DOS. «bien», «aviso» y «mal». Un disco al 85 % no está roto
    pero tampoco bien, y meterlo en el mismo cajón que «va todo perfecto» es como
    se llega al 100 % por sorpresa.
  - EL DETALLE DICE EL NÚMERO. «MQTT conectado» no vale; vale «conectado a
    127.0.0.1:1883». Lo que se mira en una pantalla de salud es para poder
    actuar, y para eso hace falta el dato.
"""
import asyncio
import os
import shutil
import time

import aiohttp

BIEN, AVISO, MAL = "bien", "aviso", "mal"

# Cuánto se espera a cada comprobación. Corto: es una pantalla que se abre para
# mirar, no un servicio.
ESPERA = 3.0

# A partir de qué ocupación de disco se avisa y se alarma. El 90 % no es una
# catástrofe todavía, pero con las copias diarias y el histórico creciendo es el
# momento de enterarse.
DISCO_AVISO, DISCO_MAL = 85.0, 95.0

# Cuánto puede tardar un bucle en dar una vuelta antes de considerarlo parado.
# El vigilante va a una vuelta por segundo y el motor a su propio ritmo, así que
# se les da margen de sobra: lo que se busca es «está parado», no «va lento».
LATIDO_AVISO, LATIDO_MAL = 15.0, 60.0


def _hace(marca: float) -> str:
    if not marca:
        return "nunca"
    segundos = max(0, int(time.time() - marca))
    if segundos < 60:
        return f"hace {segundos} s"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    return f"hace {segundos // 3600} h"


def _por_latido(marca: float, quien: str) -> tuple[str, str]:
    if not marca:
        return MAL, f"{quien} no ha dado ninguna vuelta todavía"
    edad = time.time() - marca
    if edad > LATIDO_MAL:
        return MAL, f"parado: última vuelta {_hace(marca)}"
    if edad > LATIDO_AVISO:
        return AVISO, f"lento: última vuelta {_hace(marca)}"
    return BIEN, f"última vuelta {_hace(marca)}"


async def _mqtt() -> dict:
    """El bus por el que hablan los sensores y los relés.

    Se pregunta al propio bus si está conectado en vez de abrir una conexión
    nueva: lo que importa es si el bus QUE USA LA CASA está en pie, no si el
    broker acepta conexiones."""
    broker = os.getenv("MQTT_BROKER", "127.0.0.1")
    puerto = os.getenv("MQTT_PORT", "1883")
    try:
        from ..devices import mqtt_bus
        bus = mqtt_bus.get_running_bus()
        if bus is None:
            # El bus lo arranca SecurityState.on_load, o sea la primera sesión
            # que entra: recién reiniciado el servicio y sin nadie mirando, esto
            # es lo normal y no es una avería.
            return {"estado": AVISO,
                    "detalle": f"sin arrancar todavía ({broker}:{puerto})"}
        conectado = bool(bus.client.is_connected())
        if conectado:
            return {"estado": BIEN, "detalle": f"conectado a {broker}:{puerto}"}
        return {"estado": MAL, "detalle": f"sin conexión con {broker}:{puerto}"}
    except Exception as e:
        return {"estado": AVISO, "detalle": f"no se pudo comprobar: {e}"}


async def _go2rtc() -> dict:
    """El servidor de vídeo. Se le piden los streams: es la forma de saber que
    responde Y cuántas cámaras tiene montadas."""
    url = os.getenv("GO2RTC_URL", "http://127.0.0.1:1984").rstrip("/")
    try:
        tiempo = aiohttp.ClientTimeout(total=ESPERA)
        async with aiohttp.ClientSession(timeout=tiempo) as s:
            async with s.get(f"{url}/api/streams") as r:
                if r.status != 200:
                    return {"estado": MAL, "detalle": f"responde {r.status}"}
                streams = await r.json()
        if not streams:
            return {"estado": AVISO, "detalle": "en pie, sin ninguna cámara montada"}
        return {"estado": BIEN,
                "detalle": f"{len(streams)} cámara(s): {', '.join(sorted(streams))}"}
    except asyncio.TimeoutError:
        return {"estado": MAL, "detalle": f"no responde en {ESPERA:g} s"}
    except Exception as e:
        return {"estado": MAL, "detalle": f"{type(e).__name__}: {e}"}


async def _tunel() -> dict:
    """El túnel de Cloudflare, que es lo único que hace que el panel exista
    desde fuera de casa.

    Se pregunta a systemd y no al dominio a propósito: pedir la página desde
    aquí saldría por el túnel y volvería, así que un fallo de DNS o de la nube de
    Cloudflare se contaría como «el túnel está caído» cuando el túnel está
    perfectamente. Lo que esta pantalla puede afirmar es si el proceso de esta
    máquina está en pie."""
    unidad = os.getenv("TUNEL_UNIDAD", "cloudflared-noxus")
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", unidad,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        salida, _ = await asyncio.wait_for(proc.communicate(), timeout=ESPERA)
        estado = (salida or b"").decode().strip()
        if estado == "active":
            return {"estado": BIEN, "detalle": f"{unidad} activo"}
        return {"estado": MAL, "detalle": f"{unidad}: {estado or 'desconocido'}"}
    except asyncio.TimeoutError:
        return {"estado": AVISO, "detalle": "systemctl no respondió"}
    except Exception as e:
        return {"estado": AVISO, "detalle": f"no se pudo comprobar: {e}"}


async def _disco() -> dict:
    """El disco donde viven el histórico, las copias y los fotogramas."""
    try:
        uso = shutil.disk_usage(".")
        ocupado = uso.used / uso.total * 100
        libre_gb = uso.free / (1024 ** 3)
        detalle = f"{ocupado:.0f}% ocupado · {libre_gb:.0f} GB libres"
        if ocupado >= DISCO_MAL:
            return {"estado": MAL, "detalle": detalle}
        if ocupado >= DISCO_AVISO:
            return {"estado": AVISO, "detalle": detalle}
        return {"estado": BIEN, "detalle": detalle}
    except Exception as e:
        return {"estado": AVISO, "detalle": f"no se pudo comprobar: {e}"}


async def _motor() -> dict:
    from ..automations import engine
    estado, detalle = _por_latido(engine.LATIDO, "el motor")
    return {"estado": estado, "detalle": detalle}


async def _vigilante() -> dict:
    from ..security import watcher
    estado, detalle = _por_latido(watcher.LATIDO, "el vigilante")
    return {"estado": estado, "detalle": detalle}


# (id, nombre, icono, qué comprueba, por qué importa)
COMPROBACIONES = (
    ("vigilante", "Vigilante de la alarma", "siren", _vigilante,
     "Si se para, un sensor abierto con la casa armada no avisa a nadie."),
    ("motor", "Motor de automatizaciones", "workflow", _motor,
     "Si se para, las reglas dejan de ejecutarse y el panel sigue "
     "enseñándolas como activas."),
    ("mqtt", "Bus MQTT", "radio", _mqtt,
     "Por aquí hablan los sensores y los relés. Sin él, la casa no se "
     "entera de nada ni puede accionar nada."),
    ("go2rtc", "Servidor de vídeo", "video", _go2rtc,
     "Sin él, el mural sale en negro y parece un problema de las cámaras."),
    ("tunel", "Túnel de Cloudflare", "globe", _tunel,
     "Lo único que hace que el panel exista desde fuera de casa."),
    ("disco", "Disco", "hard-drive", _disco,
     "Aquí viven el histórico, las copias y los fotogramas."),
)


async def comprobar() -> list[dict]:
    """Las seis comprobaciones, en paralelo y sin que ninguna pueda tumbar a las
    demás: `return_exceptions=True` convierte un fallo en un resultado más."""
    resultados = await asyncio.gather(
        *(fn() for _, _, _, fn, _ in COMPROBACIONES), return_exceptions=True
    )
    salida = []
    for (cid, nombre, icono, _, porque), res in zip(COMPROBACIONES, resultados):
        if isinstance(res, BaseException):
            res = {"estado": AVISO, "detalle": f"la comprobación falló: {res}"}
        salida.append({
            "id": cid, "nombre": nombre, "icono": icono,
            "estado": res["estado"], "detalle": res["detalle"], "porque": porque,
        })
    return salida
