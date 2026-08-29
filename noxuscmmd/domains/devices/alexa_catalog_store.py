"""Catálogo manual de lo que Noxus publica en Alexa.

Este fichero es deliberadamente distinto del inventario de hardware. Una luz
que existe en Noxus no aparece en Alexa por accidente: el propietario decide
qué nombre oye Alexa y qué orden concreta corresponde a encender, apagar o
activar. Las referencias apuntan al catálogo común de comandos, de modo que no
hay un segundo ejecutor que pueda comportarse distinto al botón del panel.

Es estado vivo. Todas las escrituras son atómicas y avisan al bus para que el
sincronizador proactivo publique el alta, cambio o baja en Amazon.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import unicodedata
from pathlib import Path

import fcntl

from ...core import bus


ARCHIVO = Path(os.getenv("ALEXA_DEVICES_FILE", "alexa_dispositivos.json"))
REPETICIONES_MAXIMAS = 50
# Límite de Discovery de Alexa Smart Home por cuenta. No es un límite de
# Noxus: Amazon rechazará el elemento 301 aunque el panel lo guarde.
ELEMENTOS_MAXIMOS = 300
COMPORTAMIENTOS = ("power", "action")
# SceneController no admite frases libres: Alexa decide cómo invocar estas dos
# operaciones predefinidas. El catálogo solo elige cuál ejecuta la acción.
OPERACIONES_ESCENA = ("activate", "deactivate")
CATEGORIAS_POWER = (
    "SWITCH", "LIGHT", "TV", "FAN", "COMPUTER", "SMARTPLUG", "OTHER",
)
_VACIO = {"endpoints": []}


class CatalogoAlexaError(ValueError):
    """La ficha no puede publicarse tal como está."""


class ArchivoCorrupto(Exception):
    """El catálogo existe pero no se puede interpretar con seguridad."""


_CERROJO = threading.RLock()


def _copia_vacia() -> dict:
    return json.loads(json.dumps(_VACIO))


def _estructura_valida(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get("id"), str) or not item.get("id"):
        return False
    if not isinstance(item.get("name"), str) or not item.get("name"):
        return False
    if item.get("behavior") == "power":
        return bool(item.get("category") in CATEGORIAS_POWER and
                    isinstance(item.get("on_command"), str) and
                    isinstance(item.get("off_command"), str) and
                    item.get("on_command") and item.get("off_command"))
    if item.get("behavior") == "action":
        try:
            repeticiones = int(item.get("repeat", 1))
            pausa = float(item.get("repeat_pause", 0.4))
        except (TypeError, ValueError):
            return False
        return bool(isinstance(item.get("command"), str) and item.get("command") and
                    item.get("scene_operation", "activate") in OPERACIONES_ESCENA and
                    1 <= repeticiones <= REPETICIONES_MAXIMAS and 0 <= pausa <= 60)
    return False


def leer() -> dict:
    with _CERROJO:
        if not ARCHIVO.exists():
            return _copia_vacia()
        try:
            datos = json.loads(ARCHIVO.read_text())
        except (OSError, TypeError, ValueError) as error:
            raise ArchivoCorrupto(f"{ARCHIVO} no se puede leer: {error}") from error
        if not isinstance(datos, dict) or not isinstance(datos.get("endpoints", []), list):
            raise ArchivoCorrupto(f"{ARCHIVO} no contiene un catálogo de Alexa válido")
        datos.setdefault("endpoints", [])
        if any(not _estructura_valida(item) for item in datos["endpoints"]):
            raise ArchivoCorrupto(
                f"{ARCHIVO} contiene una ficha Alexa incompleta o inválida")
        ids = [item["id"] for item in datos["endpoints"]]
        if len(ids) != len(set(ids)):
            raise ArchivoCorrupto(f"{ARCHIVO} contiene identificadores Alexa duplicados")
        return datos


def _escribir(datos: dict) -> None:
    with _CERROJO:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        temporal = ARCHIVO.with_suffix(ARCHIVO.suffix + ".tmp")
        with open(temporal, "w") as fichero:
            fcntl.flock(fichero.fileno(), fcntl.LOCK_EX)
            json.dump(datos, fichero, indent=2, ensure_ascii=False)
            fichero.write("\n")
            fichero.flush()
            os.fsync(fichero.fileno())
            fcntl.flock(fichero.fileno(), fcntl.LOCK_UN)
        os.replace(temporal, ARCHIVO)
        bus.publicar(bus.ENTIDADES)


def listar() -> list[dict]:
    salida = []
    for item in leer()["endpoints"]:
        if not isinstance(item, dict):
            continue
        copia = dict(item)
        # Los catálogos anteriores solo conocían Activate. Exponer el valor
        # implícito mantiene el mismo contrato para UI, Discovery y ejecución
        # sin reescribir datos vivos durante una simple lectura.
        if copia.get("behavior") == "action":
            copia.setdefault("scene_operation", "activate")
        salida.append(copia)
    return salida


def obtener(endpoint_id: str) -> dict | None:
    return next((item for item in listar() if item.get("id") == endpoint_id), None)


def _nombre_normalizado(nombre: str) -> str:
    sin_tildes = "".join(
        caracter for caracter in unicodedata.normalize("NFD", nombre.casefold())
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(sin_tildes.split())


def _repeticiones(valor) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError) as error:
        raise CatalogoAlexaError("Las repeticiones deben ser un número entero.") from error
    if not 1 <= numero <= REPETICIONES_MAXIMAS:
        raise CatalogoAlexaError(
            f"Las repeticiones deben estar entre 1 y {REPETICIONES_MAXIMAS}.")
    return numero


def _pausa(valor) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError) as error:
        raise CatalogoAlexaError("La pausa debe ser un número.") from error
    if not 0 <= numero <= 60:
        raise CatalogoAlexaError("La pausa debe estar entre 0 y 60 segundos.")
    return round(numero, 3)


def _validar(campos: dict, *, actual_id: str = "") -> dict:
    nombre = " ".join(str(campos.get("name") or "").split())
    if len(nombre) < 2 or len(nombre) > 128:
        raise CatalogoAlexaError("El nombre para Alexa debe tener entre 2 y 128 caracteres.")
    if any(not (caracter.isalnum() or caracter.isspace())
           for caracter in nombre):
        raise CatalogoAlexaError(
            "El nombre de Alexa solo puede llevar letras, números y espacios.")
    normalizado = _nombre_normalizado(nombre)
    for item in listar():
        if item.get("id") != actual_id and _nombre_normalizado(str(item.get("name") or "")) == normalizado:
            raise CatalogoAlexaError("Ya existe un elemento de Alexa con ese nombre.")

    comportamiento = str(campos.get("behavior") or "power")
    if comportamiento not in COMPORTAMIENTOS:
        raise CatalogoAlexaError("El comportamiento de Alexa no es válido.")

    base = {"name": nombre, "behavior": comportamiento}

    def comando_valido(comando_id: str) -> dict:
        # Importación local para mantener el store independiente al cargarlo.
        from . import comandos
        comando = next((item for item in comandos.comandos()
                        if item.get("id") == comando_id), None)
        if comando is None:
            raise CatalogoAlexaError("La acción elegida ya no existe en Noxus.")
        if not comando.get("alexa_allowed", False):
            raise CatalogoAlexaError(
                "Alexa no admite esa acción (puertas, seguridad o referencia no válida).")
        return comando

    if comportamiento == "power":
        categoria = str(campos.get("category") or "SWITCH").upper()
        if categoria not in CATEGORIAS_POWER:
            raise CatalogoAlexaError("La categoría del dispositivo no es válida.")
        on_command = str(campos.get("on_command") or "").strip()
        off_command = str(campos.get("off_command") or "").strip()
        if not on_command or not off_command:
            raise CatalogoAlexaError("Elige una acción para encender y otra para apagar.")
        comando_on = comando_valido(on_command)
        comando_off = comando_valido(off_command)
        tipos_power = {
            "light.set", "ir_button.press", "host.wol", "host.action",
            # Una regla manual segura es la forma de expresar «enciende/apaga
            # toda la habitación» sin duplicar un motor de secuencias.
            "rule.run",
        }
        if any(comando.get("paso", {}).get("type") not in tipos_power
               for comando in (comando_on, comando_off)):
            raise CatalogoAlexaError(
                "Encender/apagar solo admite luces, mandos, equipos y "
                "secuencias seguras.")
        base.update({
            "category": categoria,
            "on_command": comando_on["id"],
            "off_command": comando_off["id"],
        })
    else:
        command = str(campos.get("command") or "").strip()
        if not command:
            raise CatalogoAlexaError("Elige la acción que debe ejecutar Alexa.")
        operacion_escena = campos.get("scene_operation", "activate")
        if operacion_escena not in OPERACIONES_ESCENA:
            raise CatalogoAlexaError("La operación de escena de Alexa no es válida.")
        comando_elegido = comando_valido(command)
        repeticiones = _repeticiones(campos.get("repeat", 1))
        if (repeticiones > 1 and
                comando_elegido.get("paso", {}).get("type") != "ir_button.press"):
            raise CatalogoAlexaError(
                "Solo las teclas de mando pueden repetirse. Para una secuencia, "
                "crea una automatización y elígela como acción.")
        base.update({
            "category": "ACTIVITY_TRIGGER",
            "scene_operation": operacion_escena,
            "command": comando_elegido["id"],
            "repeat": repeticiones,
            "repeat_pause": _pausa(campos.get("repeat_pause", 0.4)),
        })
    return base


def añadir(**campos) -> dict:
    with _CERROJO:
        datos = leer()
        if len(datos["endpoints"]) >= ELEMENTOS_MAXIMOS:
            raise CatalogoAlexaError(
                f"Alexa admite como máximo {ELEMENTOS_MAXIMOS} elementos por cuenta.")
        ficha = _validar(campos)
        ahora = time.time()
        ficha.update({
            "id": "alexa_" + secrets.token_urlsafe(9),
            "created_at": ahora,
            "updated_at": ahora,
        })
        datos["endpoints"].append(ficha)
        _escribir(datos)
        return dict(ficha)


def editar(endpoint_id: str, **campos) -> dict | None:
    with _CERROJO:
        datos = leer()
        actual = next((item for item in datos["endpoints"]
                       if item.get("id") == endpoint_id), None)
        if actual is None:
            return None
        mezcla = dict(actual)
        mezcla.update(campos)
        validada = _validar(mezcla, actual_id=endpoint_id)
        # Al cambiar de comportamiento se descartan las claves del anterior;
        # una ficha no acumula acciones invisibles.
        nueva = {
            "id": endpoint_id,
            **validada,
            "created_at": actual.get("created_at", time.time()),
            "updated_at": time.time(),
        }
        datos["endpoints"][datos["endpoints"].index(actual)] = nueva
        _escribir(datos)
        return dict(nueva)


def borrar(endpoint_id: str) -> bool:
    with _CERROJO:
        datos = leer()
        quedan = [item for item in datos["endpoints"] if item.get("id") != endpoint_id]
        if len(quedan) == len(datos["endpoints"]):
            return False
        datos["endpoints"] = quedan
        _escribir(datos)
        return True
