"""Configurar los retardos: por grupo y por elemento.

Los valores se guardan al salir del campo, no con un botón «Guardar» general:
son números sueltos e independientes, y un formulario con veinte casillas y un
solo botón hace que cambiar uno obligue a repasar los otros diecinueve.
"""
import reflex as rx

from . import groups_store, logs, retardos
from ..auth import permisos
from ..nodes import store as nodes_store
from . import audit


class RetardosState(rx.State):
    grupos: list[dict] = []
    elementos: list[dict] = []

    @rx.event
    def on_load(self):
        self._recargar()

    def _recargar(self):
        datos = retardos.leer()
        self.grupos = [
            {
                "id": g["id"],
                "nombre": g["name"],
                "principal": "sí" if g.get("is_principal") else "",
                "entrada": str(datos["grupos"].get(g["id"], {}).get("entrada", 0) or 0),
                "salida": str(datos["grupos"].get(g["id"], {}).get("salida", 0) or 0),
                "miembros": str(len(g.get("members", []))),
            }
            for g in groups_store.read_all()
        ]
        nodos = nodes_store.read_all()
        self.elementos = [
            {
                "id": s["id"],
                "nombre": s.get("name", s["id"]),
                "tipo": s.get("kind", ""),
                "entrada": str(datos["elementos"].get(s["id"], {}).get("entrada", 0) or 0),
            }
            for s in (nodos.get("sensors", []) + nodos.get("factory_sensors", []))
        ]
        self.elementos.sort(key=lambda e: e["nombre"].lower())

    @rx.event
    async def poner_grupo(self, group_id: str, campo: str, valor: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if campo == "entrada":
            retardos.poner_grupo(group_id, entrada=valor)
        else:
            retardos.poner_grupo(group_id, salida=valor)
        self._recargar()
        nombre = next((g["nombre"] for g in self.grupos if g["id"] == group_id),
                      group_id)
        conf = retardos.config_grupo(group_id)
        await audit.registrar(
            self, logs.GRUPOS, "RETARDOS_CAMBIADOS",
            f"entrada {conf['entrada']} s · salida {conf['salida']} s",
            grupo=nombre)

    @rx.event
    async def poner_elemento(self, sensor_id: str, valor: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        retardos.poner_elemento(sensor_id, entrada=valor)
        self._recargar()
        nombre = next((e["nombre"] for e in self.elementos if e["id"] == sensor_id),
                      sensor_id)
        await audit.registrar(
            self, logs.SENSORES, "RETARDOS_CAMBIADOS",
            f"{nombre}: entrada {retardos.config_elemento(sensor_id)['entrada']} s")
