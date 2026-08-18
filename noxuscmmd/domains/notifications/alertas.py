"""Alertas que alguien tiene que confirmar, y silencios temporales.

Una alarma que salta y nadie ve es una alarma que no ha servido de nada. Aquí
se apunta cada alerta enviada como PENDIENTE DE CONFIRMAR; si a los 60 s nadie
ha dicho «visto», se repite a todos los dispositivos. Quien confirma, corta la
repetición para todos — no hace falta que confirmen los cinco.

Igual que los retardos: no hay temporizadores. Se guarda la hora y el vigilante,
que ya da una vuelta por segundo, mira si toca repetir. Así una repetición
pendiente sobrevive a un reinicio del panel.
"""
import json
import os
import time
from pathlib import Path

ARCHIVO = Path(os.getenv("ALERTAS_FILE", "alertas.json"))

# Cuánto se espera a que alguien diga «visto» antes de repetir.
ESPERA = 60.0
# Cuántas veces se repite antes de dejarlo. Repetir para siempre convertiría
# una puerta rota en un castigo, y a los tres avisos ya está claro que nadie
# está mirando el móvil.
MAX_REPETICIONES = 3

# Cuánto aguanta una pendiente que nadie confirma antes de darla por perdida, y
# cada cuánto se pasa la escoba. Lo segundo hace falta porque quien llama es el
# vigilante, que da una vuelta por segundo: limpiar en cada vuelta serían dos
# lecturas y una escritura de disco por segundo para no hacer nada.
CADUCIDAD = 12.0
LIMPIEZA_CADA = 3600.0

# Los botones que lleva un aviso de alarma. `action` es lo que el service
# worker manda de vuelta al servidor; `title` lo que se lee en el móvil.
# Máximo dos o tres: Android enseña dos en la mayoría de los casos y el resto
# se pierden, así que van por orden de importancia.
ACCIONES_ALARMA = (
    {"action": "confirmar", "title": "Visto"},
    {"action": "silenciar", "title": "Silenciar 30 min"},
    {"action": "camara", "title": "Ver cámara"},
)

_VACIO = {"pendientes": {}, "silencios": {}}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            return json.loads(json.dumps(_VACIO))
        datos = json.loads(ARCHIVO.read_text())
        datos.setdefault("pendientes", {})
        datos.setdefault("silencios", {})
        return datos
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e}")
        return json.loads(json.dumps(_VACIO))


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


# ── Pendientes de confirmar ──────────────────────────────────────────────
def crear(clave: str, titulo: str, cuerpo: str) -> None:
    """Apunta una alerta recién enviada. Si ya había una con la misma clave se
    respeta la vieja: es el mismo sensor rebotando, no una alarma nueva, y
    reiniciar su cuenta atrás la haría no repetirse nunca."""
    datos = leer()
    if clave in datos["pendientes"]:
        return
    datos["pendientes"][clave] = {
        "titulo": titulo, "cuerpo": cuerpo,
        "desde": time.time(), "repeticiones": 0, "ultimo": time.time(),
    }
    escribir(datos)


def confirmar(clave: str, por: str) -> dict | None:
    """Alguien dice «visto». Devuelve la ficha que había, o None."""
    datos = leer()
    ficha = datos["pendientes"].pop(clave, None)
    if ficha is None:
        return None
    ficha["confirmada_por"] = por
    escribir(datos)
    return ficha


def confirmar_todas(por: str) -> int:
    datos = leer()
    cuantas = len(datos["pendientes"])
    if not cuantas:
        return 0
    datos["pendientes"] = {}
    escribir(datos)
    return cuantas


def hay_pendientes() -> int:
    return len(leer()["pendientes"])


def a_repetir(ahora: float | None = None) -> list[tuple[str, dict]]:
    """Las que llevan más de ESPERA sin confirmar desde el último aviso."""
    ahora = ahora or time.time()
    salida = []
    for clave, ficha in leer()["pendientes"].items():
        if ficha.get("repeticiones", 0) >= MAX_REPETICIONES:
            continue
        if ahora - ficha.get("ultimo", 0) >= ESPERA:
            salida.append((clave, ficha))
    return salida


def marcar_repetida(clave: str) -> None:
    datos = leer()
    ficha = datos["pendientes"].get(clave)
    if ficha is None:
        return
    ficha["repeticiones"] = ficha.get("repeticiones", 0) + 1
    ficha["ultimo"] = time.time()
    escribir(datos)


def limpiar_viejas(horas: float = CADUCIDAD) -> int:
    """Una alerta que lleva medio día sin confirmar ya no va a confirmarse.

    Escribe aunque no haya nada que tirar: lo que se guarda entonces es la marca
    de que hoy ya se ha pasado la escoba, que es de lo que vive `limpiar_si_toca`.
    """
    datos = leer()
    limite = time.time() - horas * 3600
    viejas = [k for k, v in datos["pendientes"].items()
              if v.get("desde", 0) < limite]
    for k in viejas:
        datos["pendientes"].pop(k, None)
    datos["ultima_limpieza"] = time.time()
    escribir(datos)
    return len(viejas)


def limpiar_si_toca(horas: float = CADUCIDAD, cada: float = LIMPIEZA_CADA) -> int:
    """`limpiar_viejas` como mucho una vez cada `cada` segundos, para poder
    llamarla desde un bucle que da muchas vueltas.

    Igual que las repeticiones, el reloj está en el disco y no en un
    temporizador: la última limpieza se apunta en el propio alertas.json, así que
    el hueco de una hora no se reinicia cada vez que se reinicia el panel. En el
    caso normal —el de casi todas las vueltas— esto es una lectura y nada más.
    """
    if time.time() - leer().get("ultima_limpieza", 0) < cada:
        return 0
    return limpiar_viejas(horas)


# ── Silencios ────────────────────────────────────────────────────────────
def silenciar(clave: str, minutos: float, por: str = "") -> float:
    """Calla los avisos de ESA clave un rato. Devuelve hasta cuándo."""
    datos = leer()
    hasta = time.time() + minutos * 60
    datos["silencios"][clave] = {"hasta": hasta, "por": por}
    # Silenciar es también decir «ya lo he visto»: dejar la alerta pendiente
    # haría que siguiera repitiéndose justo después de pedir que se calle.
    datos["pendientes"].pop(clave, None)
    escribir(datos)
    return hasta


def silenciado(clave: str) -> bool:
    ficha = leer()["silencios"].get(clave)
    if not ficha:
        return False
    return ficha.get("hasta", 0) > time.time()


def silencios_vivos() -> dict:
    ahora = time.time()
    return {k: v for k, v in leer()["silencios"].items()
            if v.get("hasta", 0) > ahora}


def quitar_silencio(clave: str) -> None:
    datos = leer()
    if datos["silencios"].pop(clave, None) is not None:
        escribir(datos)
