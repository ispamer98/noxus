"""Retardos de entrada y salida, exclusiones al armar y armados en espera.

Las tres cosas van juntas porque las tres son lo mismo: **armar no es
instantáneo**. Una alarma de verdad te deja salir, te deja entrar y te deja
armar con la ventana del trastero abierta si tú lo dices — y todo eso son
estados intermedios que alguien tiene que vigilar.

Ese alguien es el vigilante (watcher.py), que ya da una vuelta por segundo. Por
eso aquí no hay ni un temporizador ni una tarea de fondo: **todo se guarda con
la hora a la que tiene que pasar** y el vigilante mira si ya toca. La diferencia
importa el día que se reinicie el panel en mitad de una cuenta atrás de salida:
con un temporizador en memoria, esa cuenta atrás se pierde y la casa se queda
sin armar sin que nadie se entere; con una hora escrita en disco, el vigilante
la recoge al arrancar y la termina.

Qué guarda cada cosa:

- `grupos` / `elementos`: cuántos segundos de retardo. Lo de un elemento pisa lo
  de su grupo, porque la puerta de entrada necesita margen y la ventana del
  salón no.
- `pendientes`: armados que aún no han ocurrido — o porque corre la cuenta
  atrás de salida, o porque se está esperando a que cierren.
- `bypass`: qué se ha dejado fuera del armado en curso. Se borra al desarmar,
  nunca antes: si sobreviviera al desarmado, la próxima vez armarías con un
  agujero que ya no recuerdas haber abierto.
- `entradas`: disparos de alarma en curso de retardo de entrada.
"""
import json
import os
import time
from pathlib import Path

ARCHIVO = Path(os.getenv("RETARDOS_FILE", "retardos.json"))

# Topes de cordura. Un retardo de entrada largo es una alarma que no suena
# cuando tiene que sonar, así que el máximo es deliberadamente corto.
MAX_ENTRADA = 180
MAX_SALIDA = 300

_VACIO = {"grupos": {}, "elementos": {}, "pendientes": {}, "bypass": {},
          "entradas": {}}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            return json.loads(json.dumps(_VACIO))
        datos = json.loads(ARCHIVO.read_text())
        for clave, valor in _VACIO.items():
            datos.setdefault(clave, json.loads(json.dumps(valor)))
        return datos
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e}")
        return json.loads(json.dumps(_VACIO))


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


def _entero(valor, maximo: int) -> int:
    try:
        return max(0, min(int(valor), maximo))
    except (TypeError, ValueError):
        return 0


# ── Configuración de los retardos ────────────────────────────────────────
def config_grupo(group_id: str) -> dict:
    d = leer()["grupos"].get(group_id, {})
    return {"entrada": _entero(d.get("entrada", 0), MAX_ENTRADA),
            "salida": _entero(d.get("salida", 0), MAX_SALIDA)}


def poner_grupo(group_id: str, entrada=None, salida=None) -> None:
    datos = leer()
    ficha = datos["grupos"].setdefault(group_id, {})
    if entrada is not None:
        ficha["entrada"] = _entero(entrada, MAX_ENTRADA)
    if salida is not None:
        ficha["salida"] = _entero(salida, MAX_SALIDA)
    if not any(ficha.values()):
        datos["grupos"].pop(group_id, None)
    escribir(datos)


def config_elemento(sensor_id: str) -> dict:
    d = leer()["elementos"].get(sensor_id, {})
    return {"entrada": _entero(d.get("entrada", 0), MAX_ENTRADA)}


def poner_elemento(sensor_id: str, entrada=None) -> None:
    datos = leer()
    ficha = datos["elementos"].setdefault(sensor_id, {})
    if entrada is not None:
        ficha["entrada"] = _entero(entrada, MAX_ENTRADA)
    if not any(ficha.values()):
        datos["elementos"].pop(sensor_id, None)
    escribir(datos)


def retardo_entrada(group_id: str, sensor_id: str, datos: dict | None = None) -> int:
    """Cuántos segundos de margen tiene ESTE sensor en ESTE grupo.

    Manda el del elemento si lo tiene puesto; si no, el del grupo. Un elemento
    con retardo 0 explícito no existe como caso: 0 significa «no tiene el suyo»
    y hereda, porque lo contrario obligaría a distinguir el cero del vacío en
    un formulario donde nadie va a entender la diferencia."""
    datos = datos or leer()
    propio = _entero(datos["elementos"].get(sensor_id, {}).get("entrada", 0), MAX_ENTRADA)
    if propio:
        return propio
    return _entero(datos["grupos"].get(group_id, {}).get("entrada", 0), MAX_ENTRADA)


def retardo_salida(group_id: str, datos: dict | None = None) -> int:
    datos = datos or leer()
    return _entero(datos["grupos"].get(group_id, {}).get("salida", 0), MAX_SALIDA)


# ── Armados en espera ────────────────────────────────────────────────────
POR_TIEMPO = "por_tiempo"     # cuenta atrás de salida
AL_CERRAR = "al_cerrar"       # esperando a que cierren los abiertos


def pendiente(group_id: str) -> dict | None:
    return leer()["pendientes"].get(group_id)


def pendientes() -> dict:
    return leer()["pendientes"]


def programar(group_id: str, modo: str, segundos: int = 0, por: str = "",
              bypass: list[str] | None = None) -> dict:
    datos = leer()
    ficha = {
        "modo": modo,
        "arma_en": time.time() + segundos if modo == POR_TIEMPO else 0,
        "desde": time.time(),
        "por": por,
        "bypass": list(bypass or []),
    }
    datos["pendientes"][group_id] = ficha
    escribir(datos)
    return ficha


def cancelar(group_id: str) -> bool:
    datos = leer()
    if datos["pendientes"].pop(group_id, None) is None:
        return False
    escribir(datos)
    return True


def segundos_restantes(ficha: dict) -> int:
    if not ficha or ficha.get("modo") != POR_TIEMPO:
        return 0
    return max(0, int(round(ficha.get("arma_en", 0) - time.time())))


# ── Exclusiones del armado en curso ──────────────────────────────────────
def bypass_de(group_id: str) -> list[str]:
    return leer()["bypass"].get(group_id, [])


def poner_bypass(group_id: str, sensor_ids: list[str]) -> None:
    datos = leer()
    if sensor_ids:
        datos["bypass"][group_id] = list(sensor_ids)
    else:
        datos["bypass"].pop(group_id, None)
    escribir(datos)


def limpiar_bypass(group_id: str) -> list[str]:
    """Al desarmar. Devuelve lo que había, para poder registrarlo."""
    datos = leer()
    habia = datos["bypass"].pop(group_id, [])
    entradas = {k: v for k, v in datos["entradas"].items()
                if not k.startswith(f"{group_id}:")}
    cambio = bool(habia) or len(entradas) != len(datos["entradas"])
    datos["entradas"] = entradas
    # Desarmar también cancela lo que estuviera esperando: si alguien desarma
    # mientras corre la cuenta atrás de salida, es que ya no se va.
    if datos["pendientes"].pop(group_id, None) is not None:
        cambio = True
    if cambio:
        escribir(datos)
    return habia


# ── Retardos de entrada en curso ─────────────────────────────────────────
def entrada_en_curso(group_id: str, sensor_id: str) -> dict | None:
    return leer()["entradas"].get(f"{group_id}:{sensor_id}")


def abrir_entrada(group_id: str, sensor_id: str, segundos: int) -> dict:
    datos = leer()
    ficha = {"dispara_en": time.time() + segundos, "desde": time.time()}
    datos["entradas"][f"{group_id}:{sensor_id}"] = ficha
    escribir(datos)
    return ficha


def cerrar_entrada(group_id: str, sensor_id: str) -> bool:
    datos = leer()
    if datos["entradas"].pop(f"{group_id}:{sensor_id}", None) is None:
        return False
    escribir(datos)
    return True


def entradas_vencidas(ahora: float | None = None) -> list[tuple[str, str]]:
    """(grupo, sensor) de los retardos de entrada que se han agotado."""
    ahora = ahora or time.time()
    vencidas = []
    for clave, ficha in leer()["entradas"].items():
        if ficha.get("dispara_en", 0) <= ahora:
            grupo, _, sensor = clave.partition(":")
            vencidas.append((grupo, sensor))
    return vencidas
