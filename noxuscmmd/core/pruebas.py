"""Valores simulados para probar el panel sin tocar nada real.

Sirve, sobre todo, para probar la alarma sin abrir la puerta: se fuerza «abierto»
en un sensor y el vigilante (domains/security/watcher.py) reacciona igual que si
hubiera saltado de verdad (aviso a los móviles, sirena de la tablet, foto).

Reglas que hacen que esto sea seguro:
- Solo vive en la memoria del panel. Reiniciar el servicio lo borra todo.
- Cada valor forzado caduca solo a los DURACION_S segundos.
- Se aplica al LEER (store.get_all_sensor_states / get_all_host_online), no al
  escribir: lo que llega por MQTT o por ping sigue guardándose tal cual y, al
  quitar el forzado, el valor real está ahí.
- Las automatizaciones y las acciones sobre equipos leen SIEMPRE el valor real
  (real=True): una prueba no enciende luces ni lanza órdenes de verdad.
"""
import os
import threading
import time

DURACION_S = float(os.getenv("PRUEBAS_MINUTOS", "10")) * 60

_cerrojo = threading.Lock()
_sensores: dict[str, tuple[bool, float]] = {}
_equipos: dict[str, tuple[bool, float]] = {}


def _vivos(tabla: dict) -> dict[str, bool]:
    ahora = time.time()
    for clave in [k for k, (_, hasta) in tabla.items() if hasta <= ahora]:
        del tabla[clave]
    return {k: valor for k, (valor, _) in tabla.items()}


def _forzar(tabla: dict, clave: str, valor: bool | None) -> None:
    with _cerrojo:
        if valor is None:
            tabla.pop(clave, None)
        else:
            tabla[clave] = (bool(valor), time.time() + DURACION_S)


def forzar_sensor(entity_id: str, valor: bool | None) -> None:
    _forzar(_sensores, entity_id, valor)


def forzar_equipo(host_id: str, valor: bool | None) -> None:
    _forzar(_equipos, host_id, valor)


def limpiar() -> None:
    with _cerrojo:
        _sensores.clear()
        _equipos.clear()


def sensores_forzados() -> dict[str, bool]:
    with _cerrojo:
        return _vivos(_sensores)


def equipos_forzados() -> dict[str, bool]:
    with _cerrojo:
        return _vivos(_equipos)


def aplicar_sensores(reales: dict) -> dict:
    forzados = sensores_forzados()
    return {**reales, **forzados} if forzados else reales


def aplicar_equipos(reales: dict) -> dict:
    forzados = equipos_forzados()
    return {**reales, **forzados} if forzados else reales


def caduca_a() -> float:
    """Cuándo caduca el último valor forzado (0 si no hay ninguno)."""
    with _cerrojo:
        _vivos(_sensores), _vivos(_equipos)
        todos = [hasta for _, hasta in [*_sensores.values(), *_equipos.values()]]
    return max(todos, default=0.0)


def activo() -> bool:
    return caduca_a() > 0
