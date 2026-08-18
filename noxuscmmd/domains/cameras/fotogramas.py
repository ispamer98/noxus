"""
Fotogramas guardados de lo que vio una cámara cuando pasó algo.

go2rtc sirve una imagen fija de cualquier stream en `/api/frame.jpeg?src=<x>`.
Esto la pide, la guarda en disco y devuelve el nombre del fichero para que quede
colgado del evento del registro (`logs_store.adjuntar_foto`).

LO QUE MANDA EN EL DISEÑO: PEDIR UN FOTOGRAMA PUEDE TARDAR MUCHÍSIMO O NO DAR
NADA. Medido el 2026-08-17 contra las dos cámaras de la casa:

    ptz  (Salón)      -> 140 KB en 1,1 s          bien
    fija (Habitación) -> 200 OK con CERO BYTES, tras 10 s el primer intento
                         y 32 s el segundo        roto

De ahí las tres reglas que sigue este módulo, y ninguna es paranoia:

1. TEMPORIZADOR CORTO Y SIEMPRE. Quien pide esto es el vigilante de la alarma,
   que da una vuelta por segundo y del que dependen los retardos de entrada, los
   armados en espera y la repetición de alertas. Una espera de 32 s ahí dentro
   congelaría todo eso: la casa dejaría de contar el tiempo para desarmar
   mientras espera una foto. La foto es lo secundario; la alarma, no.

2. UN 200 CON CERO BYTES ES UN FALLO. Mirar solo el código de estado daría por
   buena una imagen que no existe, y se guardaría un fichero vacío que luego
   sale como una foto rota en el registro. Se exige un tamaño mínimo.

3. NUNCA SE PROPAGA UN ERROR. Que no haya foto no puede impedir que la alarma
   suene, ni que el evento se registre. Todo devuelve "" y se apunta el motivo
   por consola.

El evento se guarda ANTES de tener la foto y ésta se le engancha después (ver
logs_store.adjuntar_foto): así el registro de la alarma no espera a nadie.

Los ficheros van a `fotogramas/`, fuera del repositorio (está en .gitignore):
son imágenes del interior de una casa. No se sirven como estático por eso mismo
— quien las quiera ver pasa por el endpoint, que comprueba la sesión.
"""
import asyncio
import os
import re
import time
from pathlib import Path

import aiohttp

CARPETA = Path(os.getenv("FOTOGRAMAS_DIR", "fotogramas"))

# Dónde vive go2rtc. En esta máquina es local; se deja en variable porque el
# resto del dominio habla con él por la IP de Tailscale (ver cameras/state.py).
GO2RTC = os.getenv("GO2RTC_URL", "http://127.0.0.1:1984").rstrip("/")

# Lo que se espera a la cámara. Cuatro segundos son de sobra para la que
# funciona (1,1 s) y cortan en seco a la que no.
ESPERA = float(os.getenv("FOTOGRAMA_ESPERA", "4"))

# Por debajo de esto no es una foto. Un JPEG de verdad de estas cámaras pesa
# más de 100 KB; el mínimo está bajo a propósito, solo para descartar el vacío
# y las respuestas de error que llegan como cuerpo de texto.
MINIMO = 1024

# Días que se conservan las imágenes. El EVENTO del registro no se borra nunca
# (ver logs_store): lo que caduca es la foto, no la memoria de que pasó.
MAX_DIAS = int(os.getenv("FOTOGRAMAS_MAX_DIAS", "365"))

# Los nombres los pone `guardar`, pero se leen de la base de datos y acaban en
# una petición HTTP, así que se validan antes de tocar el disco: sin esto, un
# nombre con «../» sería una forma de pedir cualquier fichero de la máquina.
_NOMBRE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}_evt\d+\.jpg$")


async def capturar(src: str) -> bytes | None:
    """El fotograma de ese stream, o None si no se pudo. Nunca levanta."""
    if not src:
        return None
    url = f"{GO2RTC}/api/frame.jpeg"
    try:
        tiempo = aiohttp.ClientTimeout(total=ESPERA)
        async with aiohttp.ClientSession(timeout=tiempo) as s:
            async with s.get(url, params={"src": src}) as r:
                if r.status != 200:
                    print(f"⚠️ Fotograma «{src}»: go2rtc devolvió {r.status}")
                    return None
                datos = await r.read()
    except asyncio.TimeoutError:
        print(f"⚠️ Fotograma «{src}»: la cámara no respondió en {ESPERA:g} s")
        return None
    except Exception as e:
        print(f"⚠️ Fotograma «{src}»: {e}")
        return None
    if len(datos) < MINIMO:
        # El caso de la cámara «fija»: contesta 200 y no manda nada.
        print(f"⚠️ Fotograma «{src}»: llegaron {len(datos)} bytes, no es una imagen")
        return None
    return datos


def guardar(datos: bytes, evento_id: int) -> str:
    """Escribe el fotograma y devuelve su nombre de fichero, o "" si no pudo.

    El nombre lleva la fecha delante para que la carpeta se ordene sola por
    orden cronológico, y el id del evento detrás para poder ir de una foto a su
    evento sin consultar nada. Escritura atómica (.tmp + os.replace) como todo
    lo que se guarda aquí: un fichero a medias se leería como una imagen rota.
    """
    nombre = f"{time.strftime('%Y-%m-%d_%H%M%S')}_evt{evento_id}.jpg"
    try:
        CARPETA.mkdir(parents=True, exist_ok=True)
        tmp = CARPETA / f"{nombre}.tmp"
        tmp.write_bytes(datos)
        os.replace(tmp, CARPETA / nombre)
        return nombre
    except OSError as e:
        print(f"⚠️ No se pudo guardar el fotograma {nombre}: {e}")
        return ""


def ruta(nombre: str) -> Path | None:
    """La ruta del fichero, o None si el nombre no vale o ya no está.

    Devolver None cuando el fichero se ha ido (lo purgó la retención) es parte
    del contrato: el evento recuerda que hubo foto aunque la foto ya no esté, y
    quien pinta decide qué enseñar."""
    if not nombre or not _NOMBRE.match(nombre):
        return None
    destino = CARPETA / nombre
    return destino if destino.is_file() else None


async def capturar_para(evento_id: int, src: str) -> str:
    """Captura y guarda para ese evento. Devuelve el nombre, o "" si no hubo.

    No engancha nada al evento: de eso se encarga quien llama (el vigilante),
    que es quien sabe si todavía tiene sentido hacerlo."""
    datos = await capturar(src)
    if datos is None:
        return ""
    return guardar(datos, evento_id)


def purgar() -> int:
    """Borra las imágenes de más de MAX_DIAS y devuelve cuántas quitó.

    Solo borra ficheros con el nombre que pone `guardar`: si algún día alguien
    deja algo suyo en esa carpeta, esto no se lo lleva por delante. Los `.tmp`
    huérfanos de una escritura interrumpida sí se limpian."""
    if not CARPETA.is_dir():
        return 0
    limite = time.time() - MAX_DIAS * 86400
    quitadas = 0
    for fichero in CARPETA.iterdir():
        if not fichero.is_file():
            continue
        huerfano = fichero.name.endswith(".tmp") and fichero.stat().st_mtime < limite
        caducado = bool(_NOMBRE.match(fichero.name)) and fichero.stat().st_mtime < limite
        if not (huerfano or caducado):
            continue
        try:
            fichero.unlink()
            quitadas += 1
        except OSError as e:
            print(f"⚠️ No se pudo borrar {fichero.name}: {e}")
    return quitadas
