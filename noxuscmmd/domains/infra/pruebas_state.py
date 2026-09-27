"""Pantalla «Pruebas»: forzar el estado de sensores y de conexión de equipos.

Los valores forzados viven en core/pruebas.py (memoria, caducan solos). Aquí solo
está la parte de la pantalla: qué se puede forzar, quién puede y el registro.
"""
import time

import reflex as rx

from ...core import bus, pruebas
from ..auth import permisos
from ..nodes import store as nodes_store
from ..security import audit, logs

_SENSORES = (("factory_sensors", "Sensor de fábrica"), ("sensors", "Sensor"),
             ("doors", "Puerta"))
_MODOS_SENSOR = {"real": None, "abierto": True, "cerrado": False}
_MODOS_EQUIPO = {"real": None, "online": True, "caido": False}


class PruebasState(rx.State):
    sensores: list[dict] = []
    equipos: list[dict] = []
    hay_forzados: bool = False
    caduca: str = ""

    def _refrescar(self) -> None:
        datos = nodes_store.read_all()
        reales = datos.get("sensor_states", {})
        forzados = pruebas.sensores_forzados()
        self.sensores = [
            {"id": it["id"], "nombre": it.get("name", it["id"]), "tipo": tipo,
             "real": "Abierto" if reales.get(it["id"]) else "Cerrado",
             "modo": ("real" if it["id"] not in forzados
                      else ("abierto" if forzados[it["id"]] else "cerrado"))}
            for coleccion, tipo in _SENSORES for it in datos.get(coleccion, [])
        ]
        conectados = datos.get("host_online", {})
        forzados_eq = pruebas.equipos_forzados()
        self.equipos = [
            {"id": h["id"], "nombre": h.get("name", h["id"]),
             "real": "En línea" if conectados.get(h["id"]) else "Sin respuesta",
             "modo": ("real" if h["id"] not in forzados_eq
                      else ("online" if forzados_eq[h["id"]] else "caido"))}
            for h in datos.get("hosts", [])
        ]
        hasta = pruebas.caduca_a()
        self.hay_forzados = hasta > 0
        self.caduca = time.strftime("%H:%M", time.localtime(hasta)) if hasta else ""

    @rx.event
    async def cargar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self._refrescar()

    @rx.event
    async def forzar_sensor(self, entity_id: str, modo: str):
        if modo not in _MODOS_SENSOR:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if entity_id not in {it["id"] for it in self.sensores}:
            return
        pruebas.forzar_sensor(entity_id, _MODOS_SENSOR[modo])
        bus.publicar(bus.SENSORES)
        await audit.registrar(self, logs.SENSORES, "PRUEBA_SENSOR",
                              f"Prueba: {entity_id} forzado a «{modo}»")
        self._refrescar()

    @rx.event
    async def forzar_equipo(self, host_id: str, modo: str):
        if modo not in _MODOS_EQUIPO:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if host_id not in {h["id"] for h in self.equipos}:
            return
        pruebas.forzar_equipo(host_id, _MODOS_EQUIPO[modo])
        bus.publicar(bus.EQUIPOS)
        await audit.registrar(self, logs.SENSORES, "PRUEBA_EQUIPO",
                              f"Prueba: {host_id} forzado a «{modo}»")
        self._refrescar()

    @rx.event
    async def restablecer(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        pruebas.limpiar()
        bus.publicar(bus.SENSORES)
        bus.publicar(bus.EQUIPOS)
        await audit.registrar(self, logs.SENSORES, "PRUEBA_FIN",
                              "Prueba: todos los valores forzados se han quitado")
        self._refrescar()
