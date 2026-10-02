"""Pantalla «Pruebas»: forzar el estado de cualquier elemento o equipo.

Los valores forzados viven en core/pruebas.py (memoria, caducan solos). Aquí solo
está la parte de la pantalla: qué se puede forzar, agrupado por tipo, quién puede
y el registro. Forzar NUNCA actúa sobre un aparato: solo cambia lo que ve el
panel (sensores y estado de luces y cerraduras por un lado, conexión de nodos y
equipos por otro).
"""
import time

import reflex as rx

from ...core import bus, pruebas
from ..auth import permisos
from ..nodes import store as nodes_store
from ..security import audit, logs

# Los grupos, en el orden en que salen. Cada uno: clave, título, icono, de qué
# tabla de forzados es ("sensor" = estado; "equipo" = conexión), las palabras
# de sus dos estados y el color de cada botón.
_GRUPOS = (
    ("magneticos", "Magnéticos", "magnet", "sensor", "Abierto", "Cerrado", "red", "green"),
    ("tampers", "Tampers", "shield-alert", "sensor", "Disparado", "Normal", "red", "green"),
    ("sensores", "Otros sensores", "radar", "sensor", "Activo", "Reposo", "red", "green"),
    ("cerraduras", "Cerraduras", "lock", "sensor", "Liberada", "Bloqueada", "amber", "green"),
    ("luces", "Luces", "lightbulb", "sensor", "Encendida", "Apagada", "amber", "gray"),
    ("persianas", "Persianas", "blinds", "sensor", "Subida", "Bajada", "amber", "gray"),
    ("aparatos", "Aparatos", "tv", "sensor", "Encendido", "Apagado", "amber", "gray"),
    ("nodos", "Nodos", "cpu", "equipo", "En línea", "Caído", "green", "red"),
    ("equipos", "Equipos", "server", "equipo", "En línea", "Caído", "green", "red"),
)
_MODOS = {"real": None, "on": True, "off": False}


def _grupo_sensor(sensor: dict) -> str:
    tipo = sensor.get("kind") or ""
    if tipo in ("door", "window"):
        return "magneticos"
    return "tampers" if tipo == "tamper" else "sensores"


def _grupo_luz(luz: dict) -> str:
    aspecto = luz.get("aspecto") or "luz"
    return {"luz": "luces", "persiana": "persianas"}.get(aspecto, "aparatos")


class PruebasState(rx.State):
    grupos: list[dict] = []
    hay_forzados: bool = False
    cuantos: int = 0
    caduca: str = ""
    # {id: "sensor" | "equipo"}: qué se puede forzar y en qué tabla. Privado:
    # es la lista blanca contra la que se comprueba cada orden.
    _tabla: dict[str, str] = {}

    def _refrescar(self) -> None:
        datos = nodes_store.read_all()
        reales = datos.get("sensor_states", {})
        conectados = datos.get("host_online", {})
        f_sensor = pruebas.sensores_forzados()
        f_equipo = pruebas.equipos_forzados()

        miembros: dict[str, list[tuple[str, str]]] = {g[0]: [] for g in _GRUPOS}
        for s in datos.get("sensors", []):
            miembros[_grupo_sensor(s)].append((s["id"], s.get("name", s["id"])))
        for d in datos.get("doors", []):
            miembros["cerraduras"].append((d["id"], d.get("name", d["id"])))
        for luz in datos.get("lights", []):
            miembros[_grupo_luz(luz)].append((luz["id"], luz.get("name", luz["id"])))
        for n in datos.get("nodes", []):
            miembros["nodos"].append((n["id"], n.get("name", n["id"])))
        for h in datos.get("hosts", []):
            miembros["equipos"].append((h["id"], h.get("name", h["id"])))

        grupos, tabla, total = [], {}, 0
        for clave, titulo, icono, de, si, no, color_si, color_no in _GRUPOS:
            forzados = f_sensor if de == "sensor" else f_equipo
            estados = reales if de == "sensor" else conectados
            filas = []
            for eid, nombre in sorted(miembros[clave], key=lambda x: x[1].lower()):
                tabla[eid] = de
                modo = "real" if eid not in forzados else ("on" if forzados[eid] else "off")
                filas.append({"id": eid, "nombre": nombre, "modo": modo,
                              "real_on": bool(estados.get(eid, False))})
            if not filas:
                continue
            n_forzados = sum(1 for f in filas if f["modo"] != "real")
            total += n_forzados
            grupos.append({"clave": clave, "titulo": titulo, "icono": icono,
                           "si": si, "no": no, "color_si": color_si, "color_no": color_no,
                           "forzados": n_forzados, "total": len(filas), "filas": filas})
        self.grupos = grupos
        self._tabla = tabla
        self.cuantos = total
        hasta = pruebas.caduca_a()
        self.hay_forzados = hasta > 0
        self.caduca = time.strftime("%H:%M", time.localtime(hasta)) if hasta else ""

    @rx.event
    async def cargar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self._refrescar()

    @rx.event
    async def forzar(self, entity_id: str, modo: str):
        if modo not in _MODOS:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        de = self._tabla.get(entity_id)
        if de is None:
            return
        if de == "equipo":
            pruebas.forzar_equipo(entity_id, _MODOS[modo])
            bus.publicar(bus.EQUIPOS)
        else:
            pruebas.forzar_sensor(entity_id, _MODOS[modo])
            bus.publicar(bus.SENSORES)
        await audit.registrar(self, logs.SENSORES,
                              "PRUEBA_EQUIPO" if de == "equipo" else "PRUEBA_SENSOR",
                              f"Prueba: {entity_id} forzado a «{modo}»")
        self._refrescar()

    @rx.event
    async def forzar_grupo(self, clave: str, modo: str):
        """Todo un grupo a la vez (p. ej. todas las luces encendidas)."""
        if modo not in _MODOS:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        grupo = next((g for g in self.grupos if g["clave"] == clave), None)
        if grupo is None:
            return
        for fila in grupo["filas"]:
            if self._tabla.get(fila["id"]) == "equipo":
                pruebas.forzar_equipo(fila["id"], _MODOS[modo])
            else:
                pruebas.forzar_sensor(fila["id"], _MODOS[modo])
        bus.publicar(bus.SENSORES)
        bus.publicar(bus.EQUIPOS)
        await audit.registrar(self, logs.SENSORES, "PRUEBA_SENSOR",
                              f"Prueba: grupo {grupo['titulo']} forzado a «{modo}»")
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
