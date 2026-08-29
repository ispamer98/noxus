"""Credenciales de enlace de Alexa, separadas de los datos de la casa.

Aquí no se guardan secretos en claro: los códigos OAuth y los testigos se
persisten como SHA-256. Que alguien leyera el fichero no le permitiría mandar
órdenes a la casa. El fichero es estado vivo y se escribe siempre con
``os.replace``.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path


ARCHIVO = Path(os.getenv("ALEXA_CLOUD_FILE", "alexa_cloud.json"))
_VACIO = {"codes": {}, "tokens": {}, "eventos": {}, "autorizaciones": {},
          "diagnostico": {}}
CADUCA_CODIGO = 300
# OAuth exige que el token de acceso sea corto y que el refresh sea el que
# mantenga el enlace vivo. Alexa recomienda al menos una hora y 180 días.
CADUCA_TOKEN = 3600
CADUCA_REFRESH = 180 * 24 * 3600


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _leer() -> dict:
    try:
        data = json.loads(ARCHIVO.read_text()) if ARCHIVO.exists() else {}
    except Exception:
        data = {}
    data.setdefault("codes", {})
    data.setdefault("tokens", {})
    data.setdefault("eventos", {})
    data.setdefault("autorizaciones", {})
    data.setdefault("diagnostico", {})
    return data


def _escribir(data: dict) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVO.with_suffix(ARCHIVO.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ARCHIVO)


def _limpiar(data: dict, ahora: float) -> None:
    data["codes"] = {k: v for k, v in data["codes"].items()
                     if v.get("caduca", 0) >= ahora}
    data["tokens"] = {k: v for k, v in data["tokens"].items()
                      if v.get("caduca_refresh", v.get("caduca", 0)) >= ahora}
    data["autorizaciones"] = {k: v for k, v in data["autorizaciones"].items()
                               if v.get("caduca", 0) >= ahora}


def emitir_autorizacion(cuenta: str) -> str:
    """Código breve, de un uso, para enlazar desde el navegador de Alexa.

    El panel no usa usuario/contraseña: su identidad vive en la cookie del
    dispositivo. Este código permite probar el enlace desde el WebView aislado
    de Alexa sin entregar una cookie de administrador a otra aplicación.
    """
    ahora = time.time()
    data = _leer()
    _limpiar(data, ahora)
    codigo = secrets.token_urlsafe(12)
    data["autorizaciones"][_hash(codigo)] = {"cuenta": cuenta, "caduca": ahora + CADUCA_CODIGO}
    _escribir(data)
    return codigo


def canjear_autorizacion(codigo: str) -> str | None:
    """Consume el código de enlace y devuelve el administrador que lo emitió."""
    ahora = time.time()
    data = _leer()
    _limpiar(data, ahora)
    ficha = data["autorizaciones"].pop(_hash(codigo), None)
    _escribir(data)
    if ficha is None or ficha.get("caduca", 0) < ahora:
        return None
    return str(ficha.get("cuenta") or "") or None


def emitir_codigo(cuenta: str, redirect_uri: str, challenge: str = "") -> str:
    """Código OAuth de un solo uso; se devuelve solo al navegador de enlace."""
    now = time.time()
    data = _leer()
    _limpiar(data, now)
    code = secrets.token_urlsafe(32)
    data["codes"][_hash(code)] = {
        "cuenta": cuenta, "redirect_uri": redirect_uri, "challenge": challenge,
        "caduca": now + CADUCA_CODIGO,
    }
    _escribir(data)
    return code


def canjear_codigo(code: str, redirect_uri: str, verifier: str = "") -> tuple[str, str] | None:
    """Canjea un código por ``(access_token, refresh_token)`` una sola vez."""
    now = time.time()
    data = _leer()
    _limpiar(data, now)
    ficha = data["codes"].pop(_hash(code), None)
    if ficha is None or ficha.get("redirect_uri") != redirect_uri:
        _escribir(data)
        return None
    if ficha.get("challenge"):
        challenge = hashlib.sha256(verifier.encode()).digest()
        import base64
        calculado = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
        if not secrets.compare_digest(calculado, ficha["challenge"]):
            _escribir(data)
            return None
    access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
    data["tokens"][_hash(access)] = {
        "cuenta": ficha["cuenta"], "caduca": now + CADUCA_TOKEN,
        "caduca_refresh": now + CADUCA_REFRESH, "refresh": _hash(refresh),
    }
    _escribir(data)
    return access, refresh


def renovar(refresh: str) -> tuple[str, str] | None:
    now = time.time()
    data = _leer()
    _limpiar(data, now)
    actual = _hash(refresh)
    token_id, ficha = next(((k, v) for k, v in data["tokens"].items()
                            if (v.get("caduca_refresh", v.get("caduca", 0)) >= now and
                                secrets.compare_digest(v.get("refresh", ""), actual))), (None, None))
    if ficha is None:
        _escribir(data)
        return None
    data["tokens"].pop(token_id, None)
    access, nuevo_refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
    data["tokens"][_hash(access)] = {
        "cuenta": ficha["cuenta"], "caduca": now + CADUCA_TOKEN,
        "caduca_refresh": now + CADUCA_REFRESH, "refresh": _hash(nuevo_refresh),
    }
    _escribir(data)
    return access, nuevo_refresh


def cuenta_de_token(access: str) -> str | None:
    data = _leer()
    ficha = data["tokens"].get(_hash(access))
    if not ficha or ficha.get("caduca", 0) < time.time():
        return None
    return str(ficha.get("cuenta") or "") or None


def guardar_eventos(cuenta: str, access: str, refresh: str, caduca: float) -> None:
    """Testigos del Event Gateway, protegidos por permisos 0600 del fichero."""
    data = _leer()
    data["eventos"][cuenta] = {
        "access": access, "refresh": refresh, "caduca": caduca, "publicados": [],
    }
    _escribir(data)


def eventos() -> dict[str, dict]:
    data = _leer()
    return {str(k): dict(v) for k, v in data["eventos"].items()}


def actualizar_eventos(cuenta: str, **campos) -> None:
    data = _leer()
    ficha = data["eventos"].get(cuenta)
    if ficha is None:
        return
    ficha.update(campos)
    _escribir(data)


def guardar_diagnostico(etapa: str, detalle: str) -> None:
    """Deja una traza breve y segura de la última fase que alcanzó Alexa.

    No contiene códigos OAuth, tokens, cabeceras ni secretos: solo permite
    distinguir si Amazon llegó a Lambda, al panel o al Event Gateway.
    """
    data = _leer()
    data["diagnostico"] = {"etapa": etapa, "detalle": detalle,
                           "actualizado": time.time()}
    _escribir(data)


def diagnostico() -> dict:
    data = _leer()
    return dict(data.get("diagnostico") or {})
