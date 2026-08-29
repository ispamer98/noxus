"""dispositivos.json — qué aparatos conocen esta casa y qué puede cada uno.

Escritura atómica (.tmp + os.replace) como el resto de los ficheros de estado:
media escritura aquí dejaría el fichero ilegible y, con él, a todo el mundo
fuera del panel.
"""
import json
import os
import secrets
import time
import unicodedata
from pathlib import Path

from ...core import bus

ARCHIVO = Path(os.getenv("DISPOSITIVOS_FILE", "dispositivos.json"))

# ── Roles ────────────────────────────────────────────────────────────────
ADMIN = "admin"
FAMILIA = "familia"
INVITADO = "invitado"
# Un aparato que aparece por primera vez y al que nadie ha dado permiso
# todavía. No es un rol con menos permisos: es no tener ninguno. Existe para
# que el panel no quede abierto a cualquiera que sepa la dirección, que era el
# agujero de partida.
PENDIENTE = "pendiente"
# Y el «no» explícito. Por permisos es idéntico a PENDIENTE —ninguno—, pero
# significa otra cosa: a este aparato ya se le ha dicho que no. Por eso deja de
# aparecer en la lista de los que están pidiendo acceso; si no, el panel te
# preguntaría por el móvil del vecino una vez a la semana para siempre.
BLOQUEADO = "bloqueado"

ROLES = (ADMIN, FAMILIA, INVITADO, PENDIENTE, BLOQUEADO)

NOMBRES_DE_ROL = {
    ADMIN: "Administrador",
    FAMILIA: "Familia",
    INVITADO: "Invitado",
    PENDIENTE: "Desconocido",
    BLOQUEADO: "Bloqueado",
}

def normalizar(nombre: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", nombre or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.strip().lower()


# Qué aparatos arrancan siendo administradores, por su nombre de suscripción
# push. Se comparan normalizados (sin tildes ni mayúsculas) porque en
# suscriptores.json pueden convivir "PC Salon" y "PC Salón": el mismo equipo
# dado de alta dos veces, y con una comparación literal una de las dos grafías
# se quedaría sin ser administrador sin que se entendiera por qué.
#
# Sale del entorno y no del código porque este repositorio es PÚBLICO: los
# nombres de los aparatos de una casa dicen quién vive en ella. Se pone en .env
# como ADMINS_INICIALES="pc fulano,iphone fulano".
#
# Vacío es seguro: esto solo se usa para SEMBRAR dispositivos.json la primera
# vez (ver rol_de_partida). Con el fichero ya creado —que es el caso de
# cualquier instalación en marcha— manda lo que diga el fichero y esto no se
# vuelve a mirar.
_ADMINS_POR_NOMBRE = tuple(
    normalizar(nombre)
    for nombre in os.getenv("ADMINS_INICIALES", "").split(",")
    if nombre.strip()
)


def rol_de_partida(nombre: str) -> str:
    """Qué rol le toca a un dispositivo YA vinculado a los avisos.

    Solo se usa al sembrar el fichero la primera vez: a partir de ahí manda lo
    que diga dispositivos.json."""
    return ADMIN if normalizar(nombre) in _ADMINS_POR_NOMBRE else FAMILIA


# ── Lectura y escritura ──────────────────────────────────────────────────
_VACIO = {"dispositivos": {}, "invitaciones": {}, "ajustes": {"estricto": False}}

# El mismo vacío pero CERRADO, para cuando el fichero está y no se puede leer.
# No es lo mismo que no tenerlo: si existe, es que esta casa ya tenía sus
# permisos puestos, y perderlos de vista no puede significar «que pase todo el
# mundo». Sin dispositivos y en estricto nadie tiene rol, así que el panel se
# cierra hasta que se arregle el fichero (por SSH). Se prefiere quedarse fuera
# a que un fichero corrupto —o una restauración a medias— apague la
# autorización entera sin que se note.
_CERRADO = {"dispositivos": {}, "invitaciones": {}, "ajustes": {"estricto": True}}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            # Primera vez: rodaje, y que no se quede nadie tirado (ver estricto()).
            return json.loads(json.dumps(_VACIO))
        datos = json.loads(ARCHIVO.read_text())
        datos.setdefault("dispositivos", {})
        datos.setdefault("invitaciones", {})
        datos.setdefault("ajustes", {"estricto": False})
        return datos
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e} — el panel queda CERRADO para todos "
              f"hasta que el fichero se pueda leer otra vez.")
        return json.loads(json.dumps(_CERRADO))


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)
    # Único punto por el que pasa cualquier alta, cambio de rol, baja,
    # invitación o bloqueo: publicar aquí basta para que todas las pestañas
    # abiertas (la del propio afectado incluida) se enteren al instante en vez
    # de esperar a su próxima relectura por sondeo (ver core/bus.py).
    bus.publicar(bus.DISPOSITIVOS)


# ── Rodaje y bloqueo ─────────────────────────────────────────────────────
# Arranca en FALSO a propósito. Con los permisos recién puestos, ningún
# dispositivo se ha presentado todavía: si el bloqueo entrara en vigor de
# golpe, el primero en descubrirlo sería quien llegara a casa de noche y no
# pudiera desarmar. En falso, el panel identifica a todo el mundo y APUNTA lo
# que habría bloqueado, sin impedir nada. Cuando la lista de dispositivos se ve
# correcta, se enciende y ya sí manda.
def estricto() -> bool:
    return bool(leer()["ajustes"].get("estricto"))


def poner_estricto(valor: bool) -> None:
    datos = leer()
    datos["ajustes"]["estricto"] = bool(valor)
    escribir(datos)


# ── Dispositivos ─────────────────────────────────────────────────────────
# ── Preferencias de cada aparato ─────────────────────────────────────────────
# Van en la ficha del dispositivo y NO en un ajuste global, que es la diferencia
# entre «esta casa se ve así» y «este aparato se ve así». El televisor del salón
# quiere botones grandes y el portátil de administrar quiere ver el doble de
# cosas en la misma pantalla; con un ajuste único, uno de los dos pierde siempre.
#
# Densidad: "casa" es la de siempre, cómoda y con aire. "pro" aprieta espacios y
# tipografía para que quepa más.
DENSIDADES = ("casa", "pro")
DENSIDAD_POR_DEFECTO = "casa"

# Acento: los nombres son los de la paleta de Radix, que es la que pinta botones,
# insignias, interruptores y campos. Se queda en una lista corta a propósito:
# ofrecer las treinta de Radix es ofrecer treinta formas de que el panel quede
# ilegible sobre fondo oscuro. Estas seis pasan de sobra el contraste.
ACENTOS = ("blue", "cyan", "jade", "violet", "amber", "orange")
ACENTO_POR_DEFECTO = "blue"


def preferencias(id_dispositivo: str) -> dict:
    """{"densidad", "acento"} de un aparato, con los valores por defecto puestos
    y validados. Un valor inventado en el fichero no puede dejar el panel roto:
    se cae al de por defecto."""
    ficha = dispositivo(id_dispositivo) or {}
    densidad = ficha.get("densidad")
    acento = ficha.get("acento")
    return {
        "densidad": densidad if densidad in DENSIDADES else DENSIDAD_POR_DEFECTO,
        "acento": acento if acento in ACENTOS else ACENTO_POR_DEFECTO,
    }


def categorias_desactivadas(id_dispositivo: str) -> list[str]:
    """Qué avisos "de sistema" tiene silenciados este aparato — ver
    notifications/categorias.py. Vacío = recibe todo, que es el mismo
    comportamiento de siempre: un dispositivo ya vinculado antes de que esto
    existiera no pierde ningún aviso de golpe.

    Filtra contra el catálogo actual: una categoría que ya no existe no puede
    dejar un aviso bloqueado para siempre sin que se vea por qué en ningún
    sitio de la interfaz."""
    from ..notifications import categorias
    ficha = dispositivo(id_dispositivo) or {}
    return [c for c in ficha.get("categorias_desactivadas", []) if c in categorias.CATEGORIAS]


def dispositivo(id_dispositivo: str) -> dict | None:
    if not id_dispositivo:
        return None
    return leer()["dispositivos"].get(id_dispositivo)


def rol_de(id_dispositivo: str) -> str:
    """El rol que vale AHORA, ya contada la caducidad.

    Un invitado con fecha de fin no hay que ir a borrarlo: en cuanto pasa la
    hora, esta función deja de devolver `invitado` y el acceso se cae solo."""
    d = dispositivo(id_dispositivo)
    if not d:
        return PENDIENTE
    caduca = d.get("caduca")
    if caduca and time.time() > caduca:
        return PENDIENTE
    rol = d.get("rol", PENDIENTE)
    return rol if rol in ROLES else PENDIENTE


def por_endpoint(endpoint: str) -> tuple[str, dict] | tuple[None, None]:
    """Busca el dispositivo por su suscripción push."""
    if not endpoint:
        return None, None
    for id_d, d in leer()["dispositivos"].items():
        if d.get("endpoint") == endpoint:
            return id_d, d
    return None, None


def por_nombre(nombre: str) -> tuple[str, dict] | tuple[None, None]:
    if not nombre:
        return None, None
    objetivo = normalizar(nombre)
    for id_d, d in leer()["dispositivos"].items():
        if normalizar(d.get("nombre", "")) == objetivo:
            return id_d, d
    return None, None


def alta(id_dispositivo: str, nombre: str = "", rol: str = PENDIENTE,
         endpoint: str = "", caduca: float | None = None) -> dict:
    datos = leer()
    ficha = {
        "nombre": nombre,
        "rol": rol if rol in ROLES else PENDIENTE,
        "creado": time.time(),
        "visto": time.time(),
        "endpoint": endpoint,
        "caduca": caduca,
    }
    datos["dispositivos"][id_dispositivo] = ficha
    escribir(datos)
    return ficha


def actualizar(id_dispositivo: str, **campos) -> bool:
    """Cambia campos sueltos de un dispositivo. Devuelve si existía."""
    datos = leer()
    d = datos["dispositivos"].get(id_dispositivo)
    if d is None:
        return False
    for clave, valor in campos.items():
        if clave == "rol" and valor not in ROLES:
            continue
        d[clave] = valor
    escribir(datos)
    return True


def visto(id_dispositivo: str) -> None:
    """Marca que este aparato ha entrado ahora.

    Se guarda solo si ha pasado un rato desde la última vez: sin eso, cada
    recarga de cada pestaña reescribiría el fichero entero."""
    datos = leer()
    d = datos["dispositivos"].get(id_dispositivo)
    if d is None:
        return
    if time.time() - d.get("visto", 0) < 300:
        return
    d["visto"] = time.time()
    escribir(datos)


def eliminar(id_dispositivo: str) -> None:
    datos = leer()
    if datos["dispositivos"].pop(id_dispositivo, None) is not None:
        escribir(datos)


def todos() -> list[dict]:
    """Los dispositivos con su id dentro, ordenados por visto más reciente."""
    datos = leer()
    lista = [{"id": i, **d} for i, d in datos["dispositivos"].items()]
    return sorted(lista, key=lambda d: d.get("visto", 0), reverse=True)


# ── Siembra inicial ──────────────────────────────────────────────────────
def sembrar_si_hace_falta() -> int:
    """La primera vez, da de alta los aparatos que YA reciben avisos.

    Sin esto, el día que esto se active toda la casa —incluido quien lo
    instaló— aparecería como desconocida y sin acceso, y no habría ningún
    administrador desde el que arreglarlo. Devuelve cuántos sembró."""
    from ..notifications import suscriptores

    datos = leer()
    if datos["dispositivos"]:
        return 0

    sembrados = 0
    for s in suscriptores.leer():
        nombre = (s.get("nombre_usuario") or "").strip()
        if not nombre:
            continue
        from . import sessions
        datos["dispositivos"][sessions.nuevo_id()] = {
            "nombre": nombre,
            "rol": rol_de_partida(nombre),
            "creado": time.time(),
            "visto": 0,
            "endpoint": s.get("endpoint", ""),
            "caduca": None,
        }
        sembrados += 1

    if sembrados:
        escribir(datos)
        print(f"👥 Dispositivos sembrados desde suscriptores.json: {sembrados}")
    return sembrados


# ── Invitaciones ─────────────────────────────────────────────────────────
def crear_invitacion(horas: float, creada_por: str, rol: str = INVITADO,
                     nota: str = "") -> str:
    """Devuelve el código a compartir. Caduca por sí solo."""
    datos = leer()
    codigo = secrets.token_urlsafe(9)
    datos["invitaciones"][codigo] = {
        "rol": rol if rol in ROLES else INVITADO,
        "creada": time.time(),
        "caduca": time.time() + horas * 3600,
        "creada_por": creada_por,
        "nota": nota,
        "usada_por": None,
        "usada": None,
    }
    escribir(datos)
    return codigo


def invitacion(codigo: str) -> dict | None:
    return leer()["invitaciones"].get(codigo) if codigo else None


def canjear(codigo: str, id_dispositivo: str, nombre: str = "") -> tuple[bool, str]:
    """Convierte una invitación válida en acceso para este aparato.

    La caducidad de la invitación pasa a ser la del acceso: una invitación de
    dos horas da dos horas de acceso, no un acceso perpetuo a quien llegó a
    tiempo. Es lo que se pidió — entrar en un momento concreto y perderlo
    solo."""
    datos = leer()
    inv = datos["invitaciones"].get(codigo)
    if inv is None:
        return False, "Esa invitación no existe."
    if inv.get("usada_por"):
        return False, "Esa invitación ya se usó."
    if time.time() > inv.get("caduca", 0):
        return False, "Esa invitación ya ha caducado."

    inv["usada_por"] = id_dispositivo
    inv["usada"] = time.time()

    ficha = datos["dispositivos"].get(id_dispositivo)
    if ficha is None:
        ficha = {
            "nombre": nombre or "Invitado",
            "creado": time.time(),
            "endpoint": "",
        }
        datos["dispositivos"][id_dispositivo] = ficha
    ficha["rol"] = inv.get("rol", INVITADO)
    ficha["caduca"] = inv.get("caduca")
    ficha["visto"] = time.time()
    ficha.setdefault("nombre", nombre or "Invitado")
    if nombre:
        ficha["nombre"] = nombre

    escribir(datos)
    return True, ""


def revocar_invitacion(codigo: str) -> None:
    """Retira la invitación Y el acceso que hubiera dado.

    Las dos cosas juntas a propósito: revocar solo el código dejaría dentro a
    quien ya lo hubiera usado, que es justo de quien te quieres deshacer."""
    datos = leer()
    inv = datos["invitaciones"].pop(codigo, None)
    if inv is None:
        return
    usada_por = inv.get("usada_por")
    if usada_por and usada_por in datos["dispositivos"]:
        datos["dispositivos"][usada_por]["rol"] = PENDIENTE
        datos["dispositivos"][usada_por]["caduca"] = None
    escribir(datos)


def invitaciones_vivas() -> list[dict]:
    """Las que aún sirven o se han usado y siguen dando acceso."""
    datos = leer()
    ahora = time.time()
    vivas = []
    for codigo, inv in datos["invitaciones"].items():
        if inv.get("caduca", 0) < ahora:
            continue
        vivas.append({"codigo": codigo, **inv})
    return sorted(vivas, key=lambda i: i.get("caduca", 0))


def limpiar_caducadas() -> int:
    """Quita invitaciones pasadas de fecha. El acceso ya se cayó solo (lo mira
    rol_de); esto es solo no acumular basura en el fichero."""
    datos = leer()
    ahora = time.time()
    viejas = [c for c, i in datos["invitaciones"].items()
              if i.get("caduca", 0) < ahora - 7 * 24 * 3600]
    for c in viejas:
        datos["invitaciones"].pop(c, None)
    if viejas:
        escribir(datos)
    return len(viejas)
