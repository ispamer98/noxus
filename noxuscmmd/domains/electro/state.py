"""Estado Reflex de los electrodomésticos simulados."""
import asyncio
import time

import reflex as rx

from ...core import sesiones
from ..auth import permisos
from ..nodes import store
from ..security import audit, logs
from . import simulador


class ElectroState(rx.State):
    # Con su vista ya derivada y sus `posiciones` por plano: el marcador decide
    # en el cliente si sale en el plano que se está mirando (NodesState.plano_actual),
    # así cambiar de plano no espera a este estado.
    electrodomesticos: list[dict] = []
    kiosco_electros: list[dict] = []

    async def _contexto(self) -> tuple[str, str]:
        # Import diferido: NodesState no necesita conocer ElectroState.
        from ..nodes.state import NodesState
        nodes = await self.get_state(NodesState)
        return nodes.plano_actual, nodes.kiosco_room_id

    def _cargar(self, data: dict, ahora: float, plano_id: str, room_id: str) -> None:
        items = [simulador.vista(item, ahora) for item in data["electrodomesticos"]]
        for item in items:
            item["posiciones"] = item.get("posiciones") or {}
        self.electrodomesticos = items
        refs = store.referencias_estancia(room_id, data) if room_id else set()
        self.kiosco_electros = [x for x in items
                                if f"electrodomesticos:{x['id']}" in refs]

    @rx.event
    async def on_load(self):
        plano_id, room_id = await self._contexto()
        data = await asyncio.to_thread(store.read_all)
        self._cargar(data, time.time(), plano_id, room_id)
        yield ElectroState.sync_loop

    @rx.event(background=True)
    async def sync_loop(self):
        """Actualiza fases y temporizadores, como máximo cada diez segundos."""
        guardia = await sesiones.guardia(self)
        while True:
            try:
                data = await asyncio.to_thread(store.read_all)
                plano_id, room_id = await self._contexto()
                async with self:
                    self._cargar(data, time.time(), plano_id, room_id)
            except Exception as exc:
                print(f"⚠️ Error en ElectroState.sync_loop: {exc}")
            if not await sesiones.espera(guardia, 10):
                return

    @rx.event
    async def electro_cmd(self, electro_id: str, accion: str, valor: str = ""):
        referencia = f"electrodomesticos:{electro_id}"
        if (no := await permisos.denegar_entidad(self, permisos.EQUIPOS, referencia)):
            return no
        data = await asyncio.to_thread(store.read_all)
        item = next((x for x in data["electrodomesticos"] if x["id"] == electro_id), None)
        if item is None:
            return rx.toast.error("El electrodoméstico ya no existe.")
        try:
            estado = simulador.comando(item, accion, valor, time.time())
        except ValueError as exc:
            return rx.toast.error(str(exc))
        await asyncio.to_thread(store.set_electro_estado, electro_id, estado)
        await audit.registrar(self, logs.EQUIPOS, "ELECTRODOMESTICO_ACCION",
                              f"{item['name']}: {accion}", entidad=referencia)
        plano_id, room_id = await self._contexto()
        data = await asyncio.to_thread(store.read_all)
        self._cargar(data, time.time(), plano_id, room_id)

