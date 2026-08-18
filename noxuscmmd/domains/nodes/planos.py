"""
Las imágenes de los planos: dónde viven, cómo se miden y cómo se sirven.

POR QUÉ NO VAN EN `assets/`, que sería lo fácil: los ficheros de `assets/` se
copian a `.web/public` **al compilar**, así que un plano subido esta tarde no se
serviría hasta el siguiente reinicio del servicio. Un plano que no se ve hasta
reiniciar no es un plano que se pueda subir desde la web. Así que viven en
`planos/` (en .gitignore, que es el mapa de una casa real) y los sirve una ruta
del backend, con la misma cookie firmada que el resto del panel.

EL TAMAÑO SE LEE DE LA CABECERA DEL FICHERO, a mano, sin Pillow. No está
instalado y no merece una dependencia nueva: el ancho y el alto de un PNG están
en los bytes 16-24, y en un JPEG en el primer marco SOF. Hacen falta porque el
contenedor del plano usa la proporción de la imagen para que las posiciones en
tanto por ciento caigan siempre en el mismo punto del dibujo, sea cual sea el
ancho de la pantalla.

`room.png` es el plano que ya existía y vive en `assets/` desde antes de todo
esto. En vez de moverlo (y arriesgarse a dejar el plano de la casa en blanco si
la copia falla), `ruta()` lo busca ahí cuando no está en `planos/`. Es un caso
especial de una línea, y el día que se sustituya por otra imagen desaparece solo.
"""
import os
import re
import struct
from pathlib import Path

from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store

CARPETA = Path(os.getenv("PLANOS_DIR", "planos"))

# Donde vivía el plano único de antes.
CARPETA_HEREDADA = Path("assets")

# Formatos que un navegador pinta y de los que sabemos leer el tamaño.
EXTENSIONES = (".png", ".jpg", ".jpeg", ".webp")

# Tope de tamaño. Un plano es un dibujo, no una foto de 40 megapíxeles; y esto
# lo sube alguien por la web, así que conviene un límite.
MAX_BYTES = int(os.getenv("PLANO_MAX_BYTES", str(12 * 1024 * 1024)))

# Los nombres los pone `guardar`, pero acaban en una URL, así que se validan
# antes de tocar el disco: sin esto, "../../.env" sería una forma de pedir
# cualquier fichero de la máquina.
_NOMBRE = re.compile(r"^[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)$")


def medidas(datos: bytes) -> tuple[int, int]:
    """(ancho, alto) leídos de la cabecera. (0, 0) si no se reconoce.

    Cero no es un fallo grave: significa «no sé la proporción», y quien pinta
    usa entonces la cuadrada de siempre. Peor sería inventarse un número."""
    try:
        if datos[:8] == b"\x89PNG\r\n\x1a\n":
            ancho, alto = struct.unpack(">II", datos[16:24])
            return int(ancho), int(alto)
        if datos[:2] == b"\xff\xd8":
            # JPEG: se recorren los marcos hasta el SOF, que es el que lleva el
            # tamaño. Los marcos de relleno (0xFF repetido) se saltan.
            i = 2
            while i < len(datos) - 9:
                if datos[i] != 0xFF:
                    i += 1
                    continue
                marca = datos[i + 1]
                if marca in (0xD8, 0x01) or 0xD0 <= marca <= 0xD7:
                    i += 2
                    continue
                largo = struct.unpack(">H", datos[i + 2:i + 4])[0]
                if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
                    alto, ancho = struct.unpack(">HH", datos[i + 5:i + 9])
                    return int(ancho), int(alto)
                i += 2 + largo
        if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP" and datos[12:16] == b"VP8X":
            ancho = int.from_bytes(datos[24:27], "little") + 1
            alto = int.from_bytes(datos[27:30], "little") + 1
            return ancho, alto
    except Exception:
        pass
    return 0, 0


def guardar(nombre_original: str, datos: bytes) -> tuple[str, int, int]:
    """Guarda la imagen y devuelve (nombre, ancho, alto).

    Levanta ValueError con el motivo escrito para la interfaz: quien sube un
    fichero tiene que enterarse de por qué no ha colado, no ver que «no pasa
    nada»."""
    extension = Path(nombre_original).suffix.lower()
    if extension not in EXTENSIONES:
        raise ValueError(f"Solo se pueden subir imágenes {', '.join(EXTENSIONES)}.")
    if not datos:
        raise ValueError("El fichero está vacío.")
    if len(datos) > MAX_BYTES:
        raise ValueError(f"La imagen pasa de {MAX_BYTES // (1024 * 1024)} MB.")

    ancho, alto = medidas(datos)
    # El nombre se limpia y se le pega un sufijo para no pisar un plano anterior
    # que se llamara igual: dos plantas llamadas "plano.png" son dos ficheros.
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(nombre_original).stem)[:40] or "plano"
    nombre = f"{base}-{os.urandom(4).hex()}{extension}"
    CARPETA.mkdir(parents=True, exist_ok=True)
    tmp = CARPETA / f"{nombre}.tmp"
    tmp.write_bytes(datos)
    os.replace(tmp, CARPETA / nombre)
    return nombre, ancho, alto


def ruta(nombre: str) -> Path | None:
    """La ruta del fichero, o None si el nombre no vale o no está."""
    if not nombre or not _NOMBRE.match(nombre):
        return None
    propio = CARPETA / nombre
    if propio.is_file():
        return propio
    heredado = CARPETA_HEREDADA / nombre
    return heredado if heredado.is_file() else None


def borrar(nombre: str) -> None:
    """Se traga los fallos: si la imagen no se puede borrar, el plano se borra
    igual. Un fichero huérfano de 2 MB molesta menos que un plano que no se deja
    quitar. Y nunca toca `assets/`, que es del repositorio."""
    destino = CARPETA / nombre
    if _NOMBRE.match(nombre or "") and destino.is_file():
        try:
            destino.unlink()
        except OSError as e:
            print(f"⚠️ No se pudo borrar la imagen del plano {nombre}: {e}")


# ── La ruta que la sirve ─────────────────────────────────────────────────────
async def ver_plano(request):
    testigo = request.cookies.get(sessions.NOMBRE_COOKIE, "")
    id_dispositivo = sessions.verificar(testigo)
    if not id_dispositivo or auth_store.dispositivo(id_dispositivo) is None:
        return JSONResponse({"ok": False, "mensaje": "No identificado."},
                            status_code=401)
    if not permisos.puede(id_dispositivo, permisos.VER):
        return JSONResponse({"ok": False, "mensaje": "Sin acceso."},
                            status_code=403)
    destino = ruta(request.path_params.get("nombre", ""))
    if destino is None:
        return JSONResponse({"ok": False, "mensaje": "Ese plano no está."},
                            status_code=404)
    return FileResponse(
        destino,
        # El nombre lleva un sufijo aleatorio y el contenido nunca cambia, así
        # que se puede cachear a gusto en el navegador. `private` para que no lo
        # guarde ningún intermediario: es el mapa de una casa.
        headers={"Cache-Control": "private, max-age=86400"},
    )


RUTAS = [Route("/api/plano/{nombre}", ver_plano, methods=["GET"])]
