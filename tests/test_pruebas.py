"""Los valores forzados de «Pruebas»: solo se ven al leer, caducan y no llegan
a lo que actúa sobre la casa. Todo con la casa temporal de tests.comun."""
import time

from tests.comun import Caso

from noxuscmmd.core import pruebas
from noxuscmmd.domains.nodes import store as nodos


def ejecutar() -> list[Caso]:
    c = Caso("Pruebas: valores forzados de sensores y equipos")
    pruebas.limpiar()
    nodos.set_sensor_state("sensor_prueba", False)
    c.revisar("sin forzar, se lee el valor real",
              nodos.get_all_sensor_states().get("sensor_prueba"), False)
    pruebas.forzar_sensor("sensor_prueba", True)
    c.revisar("forzado abierto: la lectura normal lo ve abierto",
              nodos.get_all_sensor_states().get("sensor_prueba"), True)
    c.revisar("pero lo real sigue cerrado (automatizaciones, acciones)",
              nodos.get_all_sensor_states(real=True).get("sensor_prueba"), False)
    c.revisar("el disco no se toca", nodos.read_all()["sensor_states"].get("sensor_prueba"), False)
    pruebas.forzar_sensor("sensor_prueba", None)
    c.revisar("quitar el forzado devuelve lo real",
              nodos.get_all_sensor_states().get("sensor_prueba"), False)

    nodos.set_host_online_bulk({"host_prueba": True})
    pruebas.forzar_equipo("host_prueba", False)
    c.revisar("equipo forzado caído", nodos.get_all_host_online().get("host_prueba"), False)
    c.revisar("el valor real sigue en línea",
              nodos.get_all_host_online(real=True).get("host_prueba"), True)
    c.cierto("hay prueba activa y caduca a futuro", pruebas.activo() and pruebas.caduca_a() > time.time())

    anterior = pruebas.DURACION_S
    pruebas.DURACION_S = -1
    try:
        pruebas.forzar_sensor("sensor_prueba", True)
        c.revisar("un forzado caducado deja de valer",
                  nodos.get_all_sensor_states().get("sensor_prueba"), False)
    finally:
        pruebas.DURACION_S = anterior
    pruebas.forzar_sensor("a", True)
    pruebas.forzar_equipo("b", True)
    pruebas.limpiar()
    c.cierto("restablecer lo limpia todo", not pruebas.activo())
    return [c]
