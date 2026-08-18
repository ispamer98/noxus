"""
Copias de seguridad de los ficheros que SON la casa.

Los JSON de la raíz no son datos de una aplicación cualquiera: son el estado de
armado, los sensores dados de alta, los grupos, las tarjetas de acceso y las
automatizaciones de una instalación real. Perderlos no es perder una base de
datos, es tener que volver a montar la casa entera a mano. Hasta ahora la única
red de seguridad eran ficheros `.bak.<fecha>` sueltos, hechos a mano y solo
cuando alguien se acordaba — la prueba está en la propia raíz del proyecto, con
copias de julio y ninguna de agosto.

Tres decisiones que explican el resto del módulo:

1. LAS RUTAS NO SE ESCRIBEN AQUÍ. Cada dominio resuelve su fichero con su
   propia variable de entorno (NODOS_FILE, GRUPOS_FILE, ESTADO_FILE...), que es
   justo lo que permite probar contra copias temporales sin tocar los de la
   casa. Si este módulo repitiera los nombres a mano, una prueba apuntando a
   /tmp haría copias del fichero de verdad — o peor, restauraría encima. Por eso
   se importan los módulos y se leen SUS rutas.

2. RESTAURAR ES TODO O NADA. Antes de escribir un solo byte se comprueba que
   todos los JSON de la copia parsean. Una restauración a medias deja la casa en
   un estado que no existió nunca: grupos de ayer con sensores de hoy.

3. ANTES DE RESTAURAR SE COPIA. La equivocación más fácil es restaurar la copia
   que no era. Cuando eso pasa, lo que había hace un segundo tiene que seguir
   estando en algún sitio.

La carpeta de copias vive fuera del repositorio (está en .gitignore): contiene
control_accesos.json con nombres y tarjetas RFID reales.
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..access import store as access_store
from ..automations import store as auto_store
from ..devices import overrides_store
from ..notifications import branding
from ..notifications import suscriptores
from ..security import groups_store, logs_store, shared_state
from ..nodes import store as nodes_store

CARPETA = Path(os.getenv("COPIAS_DIR", "copias"))

# Cuántas se conservan. Catorce son dos semanas: tiempo de sobra para darse
# cuenta de que algo se rompió. Los JSON de la casa suman menos de 300 KB; lo
# que crece es el histórico de eventos (unos 5 MB al año), así que catorce
# copias son catorce veces eso — sigue siendo poco, pero ya no es despreciable.
MAX_COPIAS = int(os.getenv("COPIAS_MAX", "14"))

# Hora de la copia diaria. De madrugada a propósito: es cuando menos se toca la
# casa, así que la foto sale coherente.
HORA_DIARIA = os.getenv("COPIAS_HORA", "04:00")

MANIFIESTO = "manifiesto.json"

# Motivos, para que el listado diga por qué existe cada copia sin que haya que
# adivinarlo por la hora.
DIARIA = "copia diaria"
ARRANQUE = "al arrancar el panel"
MANUAL = "a mano"
PRE_RESTAURACION = "antes de restaurar"


class BackupError(Exception):
    """No se pudo copiar o restaurar. Lleva el motivo ya escrito para la UI."""


def ficheros() -> list[tuple[str, Path]]:
    """(etiqueta legible, ruta) de todo lo que compone la casa, resuelto EN LA
    LLAMADA — ver la decisión 1 de la cabecera.

    No están aquí `.env`, `tinytuya.json` ni `webos_key.json`: son credenciales,
    no estado de la casa. Una copia que las incluyera convertiría esta carpeta
    en algo que no se puede mover ni enseñar sin cuidado, y esas tres no cambian
    solas: se escriben una vez al configurar el servicio.

    El último de la lista no es un JSON, es la base de datos del histórico. Se
    copia y se comprueba de otra manera (`_copiar` y `_legible`), porque un
    SQLite no se copia con shutil ni se valida con json.load."""
    return [
        ("Armado del sistema", Path(shared_state.ESTADO_FILE)),
        ("Sensores, nodos, luces y equipos", Path(nodes_store.ARCHIVO)),
        ("Grupos de armado", Path(groups_store.ARCHIVO)),
        ("Control de accesos", Path(access_store.ARCHIVO)),
        ("Automatizaciones", Path(auto_store.ARCHIVO)),
        ("Estado de las automatizaciones", Path(auto_store.ARCHIVO_ESTADO)),
        ("Ajustes del registro de dispositivos", Path(overrides_store.ARCHIVO)),
        ("Nombre en los avisos", Path(branding.ARCHIVO)),
        ("Dispositivos con avisos", Path(suscriptores.ARCHIVO)),
        ("Registro de eventos e histórico", Path(logs_store.RUTA)),
    ]


def _es_bd(ruta: Path) -> bool:
    return ruta.suffix == ".db"


def _json_valido(ruta: Path) -> bool:
    try:
        with open(ruta, encoding="utf-8") as f:
            json.load(f)
        return True
    except (OSError, ValueError):
        return False


def _legible(ruta: Path) -> bool:
    """¿Se puede leer ese fichero de la copia? Es la comprobación que decide si
    una copia está completa y si se puede restaurar."""
    return logs_store.integro(ruta) if _es_bd(ruta) else _json_valido(ruta)


def _copiar(origen: Path, destino: Path) -> None:
    """Copia uno de los ficheros de la casa.

    El histórico va por su propio camino: copiarlo con shutil dejaría fuera los
    eventos que aún vivan en el -wal, y la copia saldría sin lo último — ver
    logs_store.copia_a. Los fallos salen como OSError igual que los de shutil,
    así que quien llama no distingue."""
    if _es_bd(origen):
        logs_store.copia_a(destino)
    else:
        shutil.copy2(origen, destino)


def _tamano(carpeta: Path) -> int:
    return sum(f.stat().st_size for f in carpeta.glob("*") if f.is_file())


# ── Crear ───────────────────────────────────────────────────────────────────
def crear(motivo: str = MANUAL) -> dict:
    """Una copia con todos los ficheros que existan ahora mismo. Devuelve su
    entrada de listado.

    Un fichero que no existe no es un error: `automatizaciones.json` no aparece
    hasta que se crea la primera regla, y una instalación recién montada no
    tiene la mitad de estos. Lo que sí se apunta es si el fichero no se podía
    leer al copiarlo — así una copia hecha justo mientras algo escribía no se
    confunde con una copia buena."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    # El nombre de la carpeta es la marca de tiempo, y es también el id: por eso
    # listar() puede ordenar por nombre sin abrir un solo manifiesto, y por eso
    # la marca lleva milisegundos aunque nadie los vaya a leer. Con precisión de
    # segundos, dos copias del mismo segundo (restaurar hace una justo antes de
    # restaurar) necesitaban un sufijo "_1", y entonces el orden alfabético
    # dejaba de ser el orden temporal: la copia recién hecha podía ordenarse
    # como la MÁS ANTIGUA y la borraba la rotación de tres líneas más abajo.
    #
    # El hueco se reserva con mkdir(), que falla si ya existe: comprobar antes
    # con exists() dejaría una rendija entre la comprobación y la creación.
    while True:
        marca = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
        destino = CARPETA / marca
        try:
            destino.mkdir()
            break
        except FileExistsError:
            time.sleep(0.002)

    copiados = []
    for etiqueta, ruta in ficheros():
        if not ruta.exists():
            continue
        try:
            _copiar(ruta, destino / ruta.name)
        except OSError as e:
            shutil.rmtree(destino, ignore_errors=True)
            raise BackupError(f"No se pudo copiar {ruta.name}: {e}") from e
        copiados.append({
            "nombre": ruta.name,
            "etiqueta": etiqueta,
            "bytes": (destino / ruta.name).stat().st_size,
            "legible": _legible(destino / ruta.name),
        })

    if not copiados:
        shutil.rmtree(destino, ignore_errors=True)
        raise BackupError("No hay ningún fichero de la casa que copiar.")

    manifiesto = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "motivo": motivo,
        "ficheros": copiados,
    }
    # El manifiesto se escribe con .tmp + os.replace igual que los ficheros de
    # la casa: si el proceso muere a mitad, la copia se descarta al listarla
    # (sin manifiesto no es una copia) en vez de aparecer como buena a medias.
    tmp = destino / f"{MANIFIESTO}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifiesto, f, ensure_ascii=False, indent=2)
    os.replace(tmp, destino / MANIFIESTO)

    rotar()
    return _entrada(destino) or {}


def rotar(maximo: int | None = None) -> int:
    """Borra las copias más viejas y devuelve cuántas quitó."""
    tope = MAX_COPIAS if maximo is None else maximo
    todas = listar()
    sobran = todas[tope:] if len(todas) > tope else []
    for copia in sobran:
        shutil.rmtree(CARPETA / copia["id"], ignore_errors=True)
    return len(sobran)


# ── Listar ──────────────────────────────────────────────────────────────────
def _entrada(carpeta: Path) -> dict | None:
    manifiesto = carpeta / MANIFIESTO
    if not manifiesto.exists():
        return None
    try:
        with open(manifiesto, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return None
    fecha = datos.get("fecha", "")
    try:
        cuando = datetime.fromisoformat(fecha)
        texto = cuando.strftime("%d/%m/%Y a las %H:%M")
    except ValueError:
        texto = fecha
    archivos = datos.get("ficheros", [])
    return {
        "id": carpeta.name,
        "fecha": fecha,
        "fecha_texto": texto,
        "motivo": datos.get("motivo", ""),
        "ficheros": len(archivos),
        "bytes": _tamano(carpeta),
        "tamano_texto": _kb(_tamano(carpeta)),
        # Una copia con algún JSON ilegible se puede restaurar igual (los demás
        # sí valen), pero tiene que decirlo antes, no después.
        "completa": all(a.get("legible", True) for a in archivos),
    }


def _kb(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def listar() -> list[dict]:
    """De la más reciente a la más antigua."""
    if not CARPETA.exists():
        return []
    salida = []
    for carpeta in CARPETA.iterdir():
        if not carpeta.is_dir():
            continue
        entrada = _entrada(carpeta)
        if entrada:
            salida.append(entrada)
    return sorted(salida, key=lambda c: c["id"], reverse=True)


def hay_copia_de_hoy() -> bool:
    hoy = datetime.now().strftime("%Y-%m-%d")
    return any(c["id"].startswith(hoy) for c in listar())


# ── Restaurar ───────────────────────────────────────────────────────────────
def restaurar(copia_id: str) -> dict:
    """Devuelve la casa al estado de esa copia. Ver la decisión 2 de la
    cabecera: se comprueba TODO antes de escribir NADA.

    Ojo con lo que esto significa de verdad: si la copia se hizo con el sistema
    armado, al terminar el sistema queda armado. El sync_loop de SecurityState
    lo recoge del disco en medio segundo, sin reiniciar el servicio."""
    origen = CARPETA / copia_id
    if not (origen / MANIFIESTO).exists():
        raise BackupError("Esa copia no existe o está incompleta.")

    with open(origen / MANIFIESTO, encoding="utf-8") as f:
        manifiesto = json.load(f)

    # Qué fichero de la copia va a qué ruta de AHORA (que puede no ser la misma
    # de cuando se hizo la copia, si cambiaron las variables de entorno).
    destinos = {ruta.name: ruta for _, ruta in ficheros()}

    plan = []
    for archivo in manifiesto.get("ficheros", []):
        nombre = archivo["nombre"]
        fuente = origen / nombre
        destino = destinos.get(nombre)
        if destino is None or not fuente.exists():
            continue
        if not _legible(fuente):
            raise BackupError(
                f"La copia tiene {nombre} ilegible: no se restaura nada para no "
                f"dejar la casa a medias."
            )
        plan.append((fuente, destino))

    if not plan:
        raise BackupError("Esa copia no tiene ningún fichero que restaurar.")

    previa = crear(PRE_RESTAURACION)

    restaurados = []
    for fuente, destino in plan:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if _es_bd(destino):
            # El histórico se vuelca DENTRO de la base que ya existe, no se
            # sustituye el fichero: dejar un .db nuevo con el -wal del anterior
            # al lado no es restaurar, es corromper. Ver
            # logs_store.restaurar_desde.
            logs_store.restaurar_desde(fuente)
        else:
            tmp = destino.with_suffix(destino.suffix + ".tmp")
            shutil.copy2(fuente, tmp)
            os.replace(tmp, destino)
        restaurados.append(destino.name)

    return {"restaurados": restaurados, "copia_previa": previa.get("id", "")}


# ── Tarea de ciclo de vida ──────────────────────────────────────────────────
def _segundos_hasta_la_hora() -> float:
    try:
        hh, mm = (int(x) for x in HORA_DIARIA.split(":", 1))
    except (ValueError, TypeError):
        hh, mm = 4, 0
    ahora = datetime.now()
    proxima = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if proxima <= ahora:
        proxima += timedelta(days=1)
    return (proxima - ahora).total_seconds()


async def run_forever() -> None:
    """Copia diaria. Va colgada del PROCESO (register_lifespan_task en
    noxuscmmd.py) y no de una sesión, por el mismo motivo que el motor de
    automatizaciones: una copia que solo se hace si alguien tiene el panel
    abierto a las cuatro de la mañana no es una copia.

    Al arrancar hace una si hoy no hay ninguna. Reiniciar el servicio diez
    veces seguidas NO genera diez copias: la segunda ya ve la de hoy."""
    try:
        if not await asyncio.to_thread(hay_copia_de_hoy):
            copia = await asyncio.to_thread(crear, ARRANQUE)
            print(f"✅ Copia de seguridad {copia.get('id', '')} ({ARRANQUE})")
    except Exception as e:
        print(f"⚠️ No se pudo hacer la copia de arranque: {e}")

    while True:
        try:
            await asyncio.sleep(_segundos_hasta_la_hora())
            copia = await asyncio.to_thread(crear, DIARIA)
            print(f"✅ Copia de seguridad {copia.get('id', '')} ({DIARIA})")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"⚠️ Error en la copia diaria: {e}")
            # Un fallo no puede dejar el bucle pegado reintentando sin parar.
            await asyncio.sleep(300)
