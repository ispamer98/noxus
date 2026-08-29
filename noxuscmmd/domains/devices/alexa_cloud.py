"""Núcleo de la integración oficial Alexa Smart Home.

El puente Hue de :mod:`hue` es útil en una LAN, pero no permite que Noxus
avise a Alexa de que acaba de aparecer, cambiar de nombre o desaparecer un
dispositivo. Este módulo habla el modelo Smart Home v3: su salida no depende
de Alexa, AWS ni de Reflex y por eso se puede validar sin tocar la casa.

La capa HTTP/OAuth y el adaptador Lambda viven aparte. Así una petición de
Amazon jamás obtiene acceso directo a los stores sin haber pasado antes por
autenticación y verificación de origen.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from . import alexa_catalog_store
from ..nodes import store as nodes_store

FABRICANTE = "Noxus"
MODELO = "Noxus Control Center"
VERSION = "1.0"
PREFIJO_MANUAL = "noxus:manual:"


def _marca() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _capacidad_power() -> dict:
    return {
        "type": "AlexaInterface", "interface": "Alexa.PowerController",
        "version": "3", "properties": {
            "supported": [{"name": "powerState"}],
            # No se declara recuperable ni proactivo: un mando IR puede cambiar
            # fuera del panel y no siempre existe telemetría física fiable.
            "proactivelyReported": False, "retrievable": False,
        },
    }


def _capacidad_salud() -> dict:
    return {
        "type": "AlexaInterface", "interface": "Alexa.EndpointHealth",
        "version": "3.1", "properties": {
            "supported": [{"name": "connectivity"}],
            "proactivelyReported": False, "retrievable": True,
        },
    }


def _capacidad_base() -> dict:
    return {"type": "AlexaInterface", "interface": "Alexa", "version": "3"}


def _capacidad_scene(*, admite_desactivar: bool) -> dict:
    return {
        "type": "AlexaInterface", "interface": "Alexa.SceneController",
        "version": "3", "supportsDeactivation": admite_desactivar,
    }


def _endpoint(item: dict) -> dict:
    endpoint_id = f"{PREFIJO_MANUAL}{item['id']}"
    es_accion = item.get("behavior") == "action"
    categoria = "ACTIVITY_TRIGGER" if es_accion else item.get("category", "SWITCH")
    # Alexa SceneController ofrece operaciones predefinidas, no frases libres.
    # La ficha decide si Noxus publica esta acción para «activa» o «desactiva».
    capacidades = [
        _capacidad_base(),
        _capacidad_scene(
            admite_desactivar=item.get("scene_operation", "activate") == "deactivate"),
    ] if es_accion else [
        _capacidad_base(), _capacidad_power(), _capacidad_salud(),
    ]
    return {
        "endpointId": endpoint_id,
        "manufacturerName": FABRICANTE,
        "description": ("Acción" if es_accion else "Dispositivo") + " configurado en Noxus",
        "friendlyName": item["name"],
        "displayCategories": [categoria],
        "cookie": {},
        "additionalAttributes": {
            "manufacturer": FABRICANTE, "model": MODELO,
            "serialNumber": item["id"], "softwareVersion": VERSION,
            "customIdentifier": endpoint_id,
        },
        "capabilities": capacidades,
    }


def endpoints() -> list[dict]:
    """Solo lo que el propietario ha decidido publicar desde el panel.

    El inventario de la casa y el catálogo de Alexa son cosas distintas. Este
    límite explícito evita que un alta de hardware cree por sorpresa un
    dispositivo de voz o que una tecla de pulso finja tener estado ON/OFF.
    """
    return [_endpoint(item) for item in alexa_catalog_store.listar()
            if item.get("id") and item.get("name")]


def legacy_endpoint_ids() -> list[str]:
    """IDs de la versión que publicaba luces/equipos automáticamente.

    Algunos entraron por Discover antes de que Event Gateway guardase una lista
    ``publicados``. Se reconstruyen una vez para poder retirarlos sin obligar al
    usuario a buscarlos y borrarlos en la app Alexa.
    """
    datos = nodes_store.read_all()
    ids = [f"noxus.light.{item['id']}" for item in datos.get("lights", [])
           if item.get("id") and item.get("name")]
    ids.extend(
        f"noxus.host.{item['id']}" for item in datos.get("hosts", [])
        if item.get("id") and item.get("name") and item.get("mac") and item.get("user")
    )
    return sorted(set(ids))


def endpoint(endpoint_id: str) -> dict | None:
    if not endpoint_id.startswith(PREFIJO_MANUAL):
        return None
    return alexa_catalog_store.obtener(endpoint_id.removeprefix(PREFIJO_MANUAL))


def estado(endpoint_id: str) -> tuple[bool, bool]:
    """Compatibilidad: existencia y estado desconocido de un dispositivo."""
    item = endpoint(endpoint_id)
    if item is None or item.get("behavior") != "power":
        return False, False
    return True, False


def discovery_response() -> dict:
    return {
        "event": {
            "header": {
                "namespace": "Alexa.Discovery", "name": "Discover.Response",
                "payloadVersion": "3", "messageId": str(uuid4()),
            },
            "payload": {"endpoints": endpoints()},
        }
    }


def context(endpoint_id: str, *, encendido: bool | None = None) -> dict:
    conectado, _ = estado(endpoint_id)
    propiedades = [
        {"namespace": "Alexa.EndpointHealth", "name": "connectivity",
         "value": {"value": "OK" if conectado else "UNREACHABLE"},
         "timeOfSample": _marca(), "uncertaintyInMilliseconds": 0},
    ]
    # En mandos de una sola tecla no hay telemetría física. Se confirma el
    # estado solicitado al responder TurnOn/TurnOff, pero no se inventa en un
    # ReportState posterior.
    if encendido is not None:
        propiedades.append(
            {"namespace": "Alexa.PowerController", "name": "powerState",
             "value": "ON" if encendido else "OFF", "timeOfSample": _marca(),
             "uncertaintyInMilliseconds": 0})
    return {"properties": propiedades}


def _endpoint_respuesta(directive: dict) -> dict:
    origen = directive.get("directive", {}).get("endpoint", {})
    salida = {"endpointId": origen.get("endpointId", "")}
    if origen.get("scope"):
        salida["scope"] = origen["scope"]
    return salida


def response(directive: dict, *, context_data: dict | None = None) -> dict:
    """Respuesta v3 genérica correlacionada con la directiva recibida."""
    header = directive.get("directive", {}).get("header", {})
    return {
        "context": context_data or {"properties": []},
        "event": {
            "header": {"namespace": "Alexa", "name": "Response",
                       "payloadVersion": "3", "messageId": str(uuid4()),
                       "correlationToken": header.get("correlationToken", "")},
            "endpoint": _endpoint_respuesta(directive),
            "payload": {},
        },
    }


def state_report(directive: dict, endpoint_id: str) -> dict:
    """Respuesta específica a Alexa.ReportState (no Alexa.Response)."""
    header = directive.get("directive", {}).get("header", {})
    return {
        "context": context(endpoint_id),
        "event": {
            "header": {"namespace": "Alexa", "name": "StateReport",
                       "payloadVersion": "3", "messageId": str(uuid4()),
                       "correlationToken": header.get("correlationToken", "")},
            "endpoint": _endpoint_respuesta(directive),
            "payload": {},
        },
    }


def scene_response(directive: dict, *, activar: bool = True) -> dict:
    """Confirma el comienzo de una escena con el contrato propio de Alexa."""
    header = directive.get("directive", {}).get("header", {})
    return {
        "context": {},
        "event": {
            "header": {
                "namespace": "Alexa.SceneController",
                "name": "ActivationStarted" if activar else "DeactivationStarted",
                "payloadVersion": "3", "messageId": str(uuid4()),
                "correlationToken": header.get("correlationToken", ""),
            },
            "endpoint": _endpoint_respuesta(directive),
            "payload": {"cause": {"type": "VOICE_INTERACTION"},
                        "timestamp": _marca()},
        },
    }


def error(directive: dict, tipo: str, mensaje: str) -> dict:
    header = directive.get("directive", {}).get("header", {})
    return {
        "event": {
            "header": {"namespace": "Alexa", "name": "ErrorResponse",
                       "payloadVersion": "3", "messageId": str(uuid4()),
                       "correlationToken": header.get("correlationToken", "")},
            "endpoint": _endpoint_respuesta(directive),
            "payload": {"type": tipo, "message": mensaje},
        }
    }


def accept_grant_response(directive: dict) -> dict:
    return {
        "event": {
            "header": {"namespace": "Alexa.Authorization",
                       "name": "AcceptGrant.Response", "payloadVersion": "3",
                       "messageId": str(uuid4())},
            "payload": {},
        }
    }


def add_or_update_report(items: list[dict], token: str) -> dict:
    return {
        "event": {
            "header": {"namespace": "Alexa.Discovery", "name": "AddOrUpdateReport",
                       "payloadVersion": "3", "messageId": str(uuid4())},
            "payload": {"endpoints": items, "scope": {"type": "BearerToken", "token": token}},
        }
    }


def delete_report(endpoint_ids: list[str], token: str) -> dict:
    return {
        "event": {
            "header": {"namespace": "Alexa.Discovery", "name": "DeleteReport",
                       "payloadVersion": "3", "messageId": str(uuid4())},
            "payload": {"endpoints": [{"endpointId": x} for x in endpoint_ids],
                        "scope": {"type": "BearerToken", "token": token}},
        }
    }
