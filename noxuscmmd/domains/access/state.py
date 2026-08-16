"""
Estado reactivo del control de accesos (tarjetas/tags + niveles). Mismo
patrón que GroupsState: un sync_loop por sesión para que todas las pestañas
vean los cambios de las demás.
"""
import asyncio
import reflex as rx

from . import store
from ..nodes.state import NodesState
from ..security import audit, logs


class AccessControlState(rx.State):
    levels: list[dict] = []
    credentials: list[dict] = []

    @rx.event
    async def on_load(self):
        self._reload()
        yield AccessControlState.sync_loop

    def _reload(self):
        data = store.read_all()
        self.levels = data["levels"]
        self.credentials = data["credentials"]

    @rx.event(background=True)
    async def sync_loop(self):
        while True:
            try:
                real = await asyncio.to_thread(store.read_all)
                async with self:
                    if real["levels"] != self.levels:
                        self.levels = real["levels"]
                    if real["credentials"] != self.credentials:
                        self.credentials = real["credentials"]
                await asyncio.sleep(1)
            except Exception as e:
                print(f"⚠️ Error en AccessControlState.sync_loop: {e}")
                await asyncio.sleep(1)

    async def _log(self, accion: str, detalle: str = "") -> None:
        await audit.registrar(self, logs.ACCESOS, accion, detalle)

    @staticmethod
    def _nombre(coleccion, item_id: str, clave: str = "name") -> str:
        return next((x[clave] for x in coleccion if x["id"] == item_id), item_id)

    def _level_name(self, level_id: str) -> str:
        if not level_id:
            return ""
        lv = next((l for l in self.levels if l["id"] == level_id), None)
        return lv["name"] if lv else ""

    # ── Niveles de acceso ─────────────────────────────────────────────────
    @rx.event
    async def submit_add_level(self, form_data: dict):
        name = form_data.get("name", "").strip()
        if not name:
            return
        store.add_level(name)
        self._reload()
        await self._log("NIVEL_CREADO", name)

    @rx.event
    async def submit_edit_level(self, form_data: dict):
        level_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        if not level_id or not name:
            return
        anterior = self._level_name(level_id)
        store.update_level(level_id, name)
        self._reload()
        await self._log("NIVEL_EDITADO", f"{anterior} -> {name}" if anterior != name else name)

    @rx.event
    async def delete_level(self, level_id: str):
        nombre = self._level_name(level_id)
        store.delete_level(level_id)
        self._reload()
        await self._log("NIVEL_ELIMINADO", nombre)

    @rx.event
    async def add_door_to_level(self, level_id: str, door_id: str):
        if not door_id:
            return
        nodes_state = await self.get_state(NodesState)
        door = next((d for d in nodes_state.doors if d["id"] == door_id), None)
        if door is None:
            return
        store.add_door_to_level(level_id, door_id, door["name"])
        self._reload()
        await self._log("PUERTA_AÑADIDA_A_NIVEL", f"{door['name']} -> {self._level_name(level_id)}")

    @rx.event
    async def remove_door_from_level(self, level_id: str, door_id: str):
        nivel = self._level_name(level_id)
        puerta = next(
            (d["name"] for l in self.levels if l["id"] == level_id for d in l.get("doors", [])
             if d["id"] == door_id),
            door_id,
        )
        store.remove_door_from_level(level_id, door_id)
        self._reload()
        await self._log("PUERTA_QUITADA_DE_NIVEL", f"{puerta} <- {nivel}")

    # ── Credenciales (tarjetas / tags) ──────────────────────────────────────
    @rx.event
    async def submit_add_credential(self, form_data: dict):
        holder_name = form_data.get("holder_name", "").strip()
        tag_id = form_data.get("tag_id", "").strip()
        level_id = form_data.get("level_id", "")
        if not holder_name or not tag_id:
            return
        store.add_credential(holder_name, tag_id, level_id, self._level_name(level_id))
        self._reload()
        await self._log("CREDENCIAL_CREADA",
                        f"{holder_name} · tarjeta {tag_id} · nivel {self._level_name(level_id) or 'ninguno'}")

    @rx.event
    async def submit_edit_credential(self, form_data: dict):
        cred_id = form_data.get("entity_id", "")
        holder_name = form_data.get("holder_name", "").strip()
        tag_id = form_data.get("tag_id", "").strip()
        level_id = form_data.get("level_id", "")
        if not cred_id or not holder_name or not tag_id:
            return
        anterior = self._nombre(self.credentials, cred_id, "holder_name")
        store.update_credential(cred_id, holder_name, tag_id, level_id, self._level_name(level_id))
        self._reload()
        cambio = f"{anterior} -> {holder_name}" if anterior != holder_name else holder_name
        await self._log("CREDENCIAL_EDITADA",
                        f"{cambio} · tarjeta {tag_id} · nivel {self._level_name(level_id) or 'ninguno'}")

    @rx.event
    async def delete_credential(self, cred_id: str):
        nombre = self._nombre(self.credentials, cred_id, "holder_name")
        store.delete_credential(cred_id)
        self._reload()
        await self._log("CREDENCIAL_ELIMINADA", nombre)
