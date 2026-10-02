"""
Terminal de despliegue: `GET /api/despliegue/log`.

Devuelve en texto plano las últimas líneas del registro del servicio
`noxus-panel` (journalctl), para la ventanita tipo terminal del panel (ver
ui/pages/dashboard.py:_TERMINAL_SCRIPT). Esa ventana vive en el navegador y
pregunta aquí cada pocos segundos: mientras el servicio se reinicia esta ruta
no contesta, y la propia ventana cuenta los segundos hasta que vuelve.

Solo para aparatos con la casilla «Ver despliegue» (ficha `ver_despliegue`,
Ajustes → Dispositivos) Y rol de administrador: el registro dice qué se abre,
quién entra y desde dónde, así que no es para cualquiera.
"""
import asyncio
import time

from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store

SERVICIO = "noxus-panel.service"
LINEAS = 80
# Varias pestañas abiertas preguntando cada 2 s no deben lanzar un journalctl
# cada una: se sirve la misma lectura durante un segundo.
_CACHE: dict = {"t": 0.0, "texto": ""}
_CACHE_LOCK = asyncio.Lock()


def _quien(request) -> str:
    testigo = request.cookies.get(sessions.NOMBRE_COOKIE, "")
    id_dispositivo = sessions.verificar(testigo)
    if not id_dispositivo or auth_store.dispositivo(id_dispositivo) is None:
        return ""
    return id_dispositivo


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        salida, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return "(sin respuesta)"
    return salida.decode("utf-8", "replace")


async def _leer() -> str:
    ahora = time.monotonic()
    if ahora - _CACHE["t"] < 1.0:
        return _CACHE["texto"]

    # Dos pestañas pueden llegar en el mismo instante. Solo una consulta el
    # journal; la otra reutiliza lo que la primera acaba de dejar en caché.
    async with _CACHE_LOCK:
        ahora = time.monotonic()
        if ahora - _CACHE["t"] < 1.0:
            return _CACHE["texto"]
        estado = (await _run("systemctl", "is-active", SERVICIO)).strip()
        log = await _run("journalctl", "-u", SERVICIO, "-n", str(LINEAS),
                         "--no-pager", "-o", "short")
        texto = f"● {SERVICIO}: {estado}\n{log}"
        _CACHE.update(t=time.monotonic(), texto=texto)
        return texto


async def ver_log(request):
    id_dispositivo = _quien(request)
    if not id_dispositivo:
        return Response(status_code=401)
    ficha = auth_store.dispositivo(id_dispositivo) or {}
    if not ficha.get("ver_despliegue") or not permisos.puede(id_dispositivo, permisos.AJUSTES):
        return Response(status_code=403)
    return PlainTextResponse(await _leer(), headers={"Cache-Control": "no-store"})


RUTAS = [Route("/api/despliegue/log", ver_log, methods=["GET"])]

# La MISMA lectura, servida por un proceso APARTE (noxus-despliegue.service,
# :8096) para que siga contestando mientras noxus-panel se reinicia. El VPS le
# manda /despliegue/* y la página «Algo tenemos en proceso…» la usa para su
# terminal. Misma cookie, misma casilla, mismo rol.
from starlette.applications import Starlette  # noqa: E402

app = Starlette(routes=[Route("/despliegue/log", ver_log, methods=["GET"])])
