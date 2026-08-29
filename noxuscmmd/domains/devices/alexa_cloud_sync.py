"""
Sincronización PROACTIVA de Noxus hacia Alexa: cada vez que el catálogo de
dispositivos publicados cambia (alta, edición o baja en Ajustes → Alexa y
voz), este módulo se lo dice a Amazon sin esperar a que la app Alexa pregunte.

CÓMO SE ENTERA SIN SONDEAR: `run_forever` (lifespan task, ver noxuscmmd.py) se
queda dormido en `bus.Aviso(bus.ENTIDADES).espera(...)` hasta que algo publica
en ese canal (dar de alta una luz, cambiar un nombre...), y si no hay ningún
aviso en 300s igualmente reintenta — así una sincronización que falló por un
corte de red no se queda colgada hasta el próximo cambio manual.

DOS JUEGOS DE TOKENS DISTINTOS conviven en este dominio y no hay que
confundirlos: las credenciales de ESTE archivo (`ALEXA_EVENT_CLIENT_ID/
SECRET`) son las del Event Gateway — autorizan A NOXUS a avisar a Amazon de
cambios—; las de `alexa_cloud_endpoint.py` son las de la Skill en sí —
autorizan A ALEXA a mandarle órdenes a Noxus—. `aceptar_grant` es el único
punto de contacto entre ambos: Amazon manda el "AcceptGrant" cuando el usuario
vincula la Skill, y aquí se canjea por el primer par de tokens de eventos.

`sincronizar_cuenta` compara el catálogo actual con el último publicado
(`ficha["publicados"]`) para saber qué falta de dar de baja — Amazon no ofrece
"reemplaza todo el catálogo", solo altas y bajas puntuales.
"""
from __future__ import annotations

import os
import time
import json
from pathlib import Path

import aiohttp

from ...core import bus
from . import alexa_catalog_store, alexa_cloud, alexa_cloud_store


LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
# La Skill se ha configurado en Europa/India (Lambda eu-west-1), por lo que
# sus altas y bajas proactivas se deben publicar en el Event Gateway europeo.
EVENT_URL = "https://api.eu.amazonalexa.com/v3/events"
# Mantener cada informe holgadamente por debajo del máximo de 256 KiB del
# Event Gateway. El tope total por cuenta sigue siendo 300 endpoints.
ELEMENTOS_POR_INFORME = 100
# Aunque el contrato documenta varias bajas por informe, el Event Gateway de
# esta cuenta devuelve INVALID_REQUEST_EXCEPTION para el lote y acepta los
# mismos endpointId uno a uno. La operación es idempotente.
BAJAS_POR_INFORME = 1
ARCHIVO_CREDENCIALES = Path(os.getenv("ALEXA_EVENT_CLIENT_FILE", "alexa_event_client.json"))
_ULTIMO_ERROR = ""


def _credenciales() -> tuple[str, str]:
    """Lee las credenciales de eventos sin exponerlas al estado de la UI."""
    client_id = os.getenv("ALEXA_EVENT_CLIENT_ID", "")
    client_secret = os.getenv("ALEXA_EVENT_CLIENT_SECRET", "")
    if client_id and client_secret:
        return client_id, client_secret
    try:
        datos = json.loads(ARCHIVO_CREDENCIALES.read_text())
        return (str(datos.get("client_id") or ""),
                str(datos.get("client_secret") or ""))
    except (OSError, TypeError, ValueError):
        return "", ""


def eventos_configurados() -> bool:
    client_id, client_secret = _credenciales()
    return bool(client_id and client_secret)


def guardar_credenciales(client_id: str, client_secret: str) -> bool:
    """Guarda una sola vez las credenciales de Event Gateway, con permisos 0600."""
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id or not client_secret:
        return False
    ARCHIVO_CREDENCIALES.parent.mkdir(parents=True, exist_ok=True)
    temporal = ARCHIVO_CREDENCIALES.with_suffix(ARCHIVO_CREDENCIALES.suffix + ".tmp")
    temporal.write_text(json.dumps({"client_id": client_id,
                                    "client_secret": client_secret}, indent=2) + "\n")
    os.chmod(temporal, 0o600)
    os.replace(temporal, ARCHIVO_CREDENCIALES)
    return True


def ultimo_error() -> str:
    return _ULTIMO_ERROR


def _fallo(mensaje: str) -> bool:
    global _ULTIMO_ERROR
    _ULTIMO_ERROR = mensaje
    try:
        alexa_cloud_store.guardar_diagnostico("error", mensaje)
    except Exception:
        # El diagnóstico nunca debe tapar el fallo original.
        pass
    return False


async def aceptar_grant(cuenta: str, code: str) -> bool:
    """Canjea el grant de Amazon y deja listo el envío proactivo de eventos."""
    client_id, client_secret = _credenciales()
    if not client_id or not client_secret or not code:
        return _fallo("Faltan las credenciales de eventos o el grant de Amazon.")
    datos = {"grant_type": "authorization_code", "code": code,
             "client_id": client_id, "client_secret": client_secret}
    try:
        # Lambda espera como máximo siete segundos al panel. Dejar margen para
        # devolver AcceptGrant.Response en vez de agotar su conexión.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as sesion:
            async with sesion.post(LWA_TOKEN_URL, data=datos) as respuesta:
                salida = await respuesta.json(content_type=None)
                if respuesta.status >= 300:
                    print(f"⚠️ Alexa: no se pudo aceptar Event Gateway ({respuesta.status})")
                    return _fallo(f"Amazon OAuth rechazó el Event Gateway (HTTP {respuesta.status}).")
    except Exception as error:
        print(f"⚠️ Alexa: Event Gateway no accesible: {error}")
        return _fallo("No se pudo contactar con Amazon para autorizar los eventos.")
    access, refresh = salida.get("access_token", ""), salida.get("refresh_token", "")
    if not access or not refresh:
        return _fallo("Amazon no devolvió los tokens de Event Gateway.")
    alexa_cloud_store.guardar_eventos(cuenta, access, refresh,
                                      time.time() + int(salida.get("expires_in", 3600)))
    global _ULTIMO_ERROR
    _ULTIMO_ERROR = ""
    # No bloquear AcceptGrant mientras se publican altas/bajas: el bucle de
    # sincronización recibe este aviso y hace el trabajo en segundo plano.
    bus.publicar(bus.ENTIDADES)
    return True


async def _token_eventos(cuenta: str, ficha: dict) -> str | None:
    if ficha.get("caduca", 0) > time.time() + 120:
        return str(ficha.get("access") or "") or None
    client_id, client_secret = _credenciales()
    if not client_id or not client_secret or not ficha.get("refresh"):
        _fallo("Faltan credenciales para renovar los eventos de Alexa.")
        return None
    datos = {"grant_type": "refresh_token", "refresh_token": ficha["refresh"],
             "client_id": client_id, "client_secret": client_secret}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as sesion:
            async with sesion.post(LWA_TOKEN_URL, data=datos) as respuesta:
                salida = await respuesta.json(content_type=None)
                if respuesta.status >= 300:
                    _fallo(
                        f"Amazon rechazó la renovación de eventos (HTTP {respuesta.status}).")
                    return None
    except Exception as error:
        print(f"⚠️ Alexa: no se pudo renovar Event Gateway: {error}")
        _fallo("No se pudo contactar con Amazon para renovar los eventos.")
        return None
    access = str(salida.get("access_token") or "")
    refresh = str(salida.get("refresh_token") or ficha["refresh"])
    if not access:
        _fallo("Amazon no devolvió un token de eventos renovado.")
        return None
    alexa_cloud_store.actualizar_eventos(
        cuenta, access=access, refresh=refresh,
        caduca=time.time() + int(salida.get("expires_in", 3600)),
    )
    return access


async def _enviar(payload: dict, token: str) -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as sesion:
            async with sesion.post(
                    EVENT_URL, json=payload,
                    headers={"Authorization": f"Bearer {token}"}) as respuesta:
                if respuesta.status < 300:
                    return True
                print(f"⚠️ Alexa: Event Gateway respondió {respuesta.status}: "
                      f"{(await respuesta.text())[:300]}")
                return _fallo(
                    f"Alexa rechazó la sincronización (HTTP {respuesta.status}).")
    except Exception as error:
        print(f"⚠️ Alexa: no se pudo publicar cambio: {error}")
        return _fallo("No se pudo contactar con Alexa para sincronizar cambios.")
    return False


async def sincronizar_cuenta(cuenta: str) -> None:
    """Publica altas/cambios y bajas comparando con el último catálogo enviado."""
    ficha = alexa_cloud_store.eventos().get(cuenta)
    if ficha is None:
        return
    token = await _token_eventos(cuenta, ficha)
    if not token:
        return
    try:
        items = alexa_cloud.endpoints()
    except alexa_catalog_store.ArchivoCorrupto as error:
        # Un fichero ilegible no significa «el usuario borró todo». Frenar aquí
        # evita enviar un DeleteReport masivo por una avería de disco/JSON.
        _fallo(f"Catálogo Alexa dañado; no se ha sincronizado: {error}")
        return
    actuales = {item["endpointId"] for item in items}
    anteriores = set(ficha.get("publicados") or [])
    # Enviar la ficha completa también actualiza nombres o capacidades, aunque
    # el id ya existiera. Amazon permite enviar solo los afectados, pero este
    # catálogo es pequeño y así se evita perder un cambio de nombre.
    for inicio in range(0, len(items), ELEMENTOS_POR_INFORME):
        lote = items[inicio:inicio + ELEMENTOS_POR_INFORME]
        if not await _enviar(alexa_cloud.add_or_update_report(lote, token), token):
            return
    eliminados = anteriores - actuales
    if not ficha.get("legacy_retirados", False):
        eliminados.update(alexa_cloud.legacy_endpoint_ids())
    eliminados = sorted(eliminados - actuales)
    for inicio in range(0, len(eliminados), BAJAS_POR_INFORME):
        lote = eliminados[inicio:inicio + BAJAS_POR_INFORME]
        if not await _enviar(alexa_cloud.delete_report(lote, token), token):
            return
    alexa_cloud_store.actualizar_eventos(
        cuenta, publicados=sorted(actuales), legacy_retirados=True)
    global _ULTIMO_ERROR
    _ULTIMO_ERROR = ""
    alexa_cloud_store.guardar_diagnostico(
        "sincronizado", f"Catálogo Alexa sincronizado: {len(actuales)} elemento(s).")


async def sincronizar_todo() -> None:
    for cuenta in alexa_cloud_store.eventos():
        await sincronizar_cuenta(cuenta)


class _Proceso:
    @staticmethod
    def sigue() -> bool:
        return True


async def run_forever() -> None:
    """Duerme hasta una mutación, sin sondear los JSON de la casa."""
    aviso = bus.Aviso(bus.ENTIDADES)
    # Retira en el arranque los antiguos endpoints automáticos y publica los
    # manuales incluso si no hay otra mutación durante los próximos minutos.
    await sincronizar_todo()
    while True:
        await aviso.espera(_Proceso(), 300)
        await sincronizar_todo()
