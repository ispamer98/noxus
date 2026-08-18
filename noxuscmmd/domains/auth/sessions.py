"""La cookie de sesión: firmada por el servidor, legible por nadie más.

Formato del testigo: `<id>.<caduca>.<firma>`

`id` identifica al dispositivo, `caduca` es una marca de tiempo unix y `firma`
es un HMAC-SHA256 de los dos anteriores con un secreto que solo está en este
servidor. Cualquiera puede LEER su cookie y ver qué pone —no hay nada
confidencial ahí—, pero no puede fabricar una nueva ni cambiarle la fecha sin
la firma, y sin firma válida el panel la trata como si no existiera.

Deliberadamente NO lleva el rol dentro. Ver el porqué en __init__.py.
"""
import hmac
import json
import os
import secrets
import time
from hashlib import sha256
from pathlib import Path

# El secreto vive fuera del código y fuera del repositorio. Se crea solo la
# primera vez. Si se borra, todas las sesiones dejan de valer a la vez y cada
# dispositivo tiene que volver a identificarse — que es exactamente lo que se
# quiere de un "cerrar sesión en todas partes".
ARCHIVO_SECRETO = Path(os.getenv("AUTH_SECRETO_FILE", "auth_secreto.json"))

NOMBRE_COOKIE = "noxus_sesion"

# Un año. Es un panel de casa, no un banco: obligar a reidentificarse cada
# pocos días sería justo el engorro que se pide evitar. La seguridad no la da
# la caducidad de la cookie sino poder retirarle el rol al dispositivo en el
# acto, que es inmediato porque el rol se consulta aparte en cada acción.
DURACION = 365 * 24 * 3600

# Cuando a una sesión le queda menos de esto, se reemite al vuelo. Sin esto,
# un dispositivo que entra a diario se encontraría un día con la sesión
# caducada sin motivo.
RENOVAR_SI_QUEDA_MENOS_DE = 90 * 24 * 3600

_secreto_cache: bytes | None = None


def _secreto() -> bytes:
    global _secreto_cache
    if _secreto_cache is not None:
        return _secreto_cache
    try:
        if ARCHIVO_SECRETO.exists():
            valor = json.loads(ARCHIVO_SECRETO.read_text()).get("secreto", "")
            if valor:
                _secreto_cache = valor.encode()
                return _secreto_cache
    except Exception as e:
        print(f"⚠️ Secreto de sesión ilegible ({e}); se genera uno nuevo")

    valor = secrets.token_urlsafe(48)
    tmp = ARCHIVO_SECRETO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"secreto": valor}, indent=2) + "\n")
    # Solo el dueño puede leerlo: quien tenga este fichero puede fabricar
    # sesiones de administrador.
    os.chmod(tmp, 0o600)
    os.replace(tmp, ARCHIVO_SECRETO)
    print(f"🔑 Secreto de sesión creado en {ARCHIVO_SECRETO}")
    _secreto_cache = valor.encode()
    return _secreto_cache


def nuevo_id() -> str:
    """Identificador de un dispositivo que aparece por primera vez."""
    return secrets.token_urlsafe(16)


def _firma(id_dispositivo: str, caduca: int) -> str:
    mensaje = f"{id_dispositivo}.{caduca}".encode()
    return hmac.new(_secreto(), mensaje, sha256).hexdigest()


def emitir(id_dispositivo: str, duracion: int = DURACION) -> str:
    caduca = int(time.time()) + duracion
    return f"{id_dispositivo}.{caduca}.{_firma(id_dispositivo, caduca)}"


def verificar(testigo: str) -> str | None:
    """Devuelve el id del dispositivo, o None si la cookie no vale.

    No vale si: está vacía, tiene otra forma, la firma no cuadra (alguien la
    ha manipulado o viene de otro servidor) o ya caducó."""
    if not testigo:
        return None
    partes = testigo.split(".")
    if len(partes) != 3:
        return None
    id_dispositivo, caduca_txt, firma = partes
    try:
        caduca = int(caduca_txt)
    except ValueError:
        return None
    # compare_digest y no ==: comparar firmas con == filtra por el tiempo que
    # tarda en fallar y deja adivinarlas byte a byte.
    if not hmac.compare_digest(firma, _firma(id_dispositivo, caduca)):
        return None
    if caduca < time.time():
        return None
    return id_dispositivo


def hay_que_renovar(testigo: str) -> bool:
    try:
        caduca = int(testigo.split(".")[1])
    except (IndexError, ValueError):
        return False
    return caduca - time.time() < RENOVAR_SI_QUEDA_MENOS_DE
