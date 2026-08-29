"""
Estado reactivo de los grupos de armado (zonas). Todo sensor —de registry.py
o dado de alta en caliente— se arma exclusivamente por pertenecer a un grupo
armado; no hay ningún sensor con mecanismo de armado propio. El "armado
general" de siempre no es un caso especial: es el grupo marcado is_principal
(por defecto "Sistema", con los 3 sensores clásicos — ver
groups_store.ensure_principal_group). SecurityState.sistema_armado se
mantiene sincronizado en ambas direcciones con el grupo principal solo para
que la vista clásica (botón de armado de siempre) siga funcionando igual.

La vigilancia —el único disparador de alertas de todo el sistema— ya no está
aquí: vive en security/watcher.py como tarea del ciclo de vida del proceso.
Colgada de este State dependía de que alguien tuviera el panel abierto en un
navegador, así que tras reiniciar el proceso la casa podía quedarse armada sin
nadie mirando.
"""
import asyncio
import reflex as rx

from ..auth import permisos
from . import arming, audit, groups_store, logs
from .state import SecurityState
from ..devices import registry
from ..nodes.state import NodesState
from ..notifications.state import PushState
from ...core import bus, sesiones


class GroupsState(rx.State):
    groups: list[dict] = []

    @rx.var
    def principal(self) -> dict:
        return next(
            (g for g in self.groups if g["is_principal"]),
            {"id": "", "name": "Sistema", "armed": False, "is_principal": False, "members": []},
        )

    @rx.var
    def armed_count(self) -> int:
        return sum(1 for g in self.groups if g["armed"])

    @rx.var
    def groups_by_id(self) -> dict[str, dict]:
        """Para widgets del Resumen que muestran el estado armado/desarmado
        de un grupo concreto sin tener que recorrer self.groups en el
        frontend — ver ui/dashboard/views/overview.py."""
        return {g["id"]: g for g in self.groups}

    @rx.var
    def groups_by_sensor(self) -> dict[str, list[str]]:
        """sensor_id -> nombres de los grupos a los que pertenece — para
        mostrar en su tarjeta (pestaña Alarma) en vez del texto genérico
        "sigue el armado del grupo"."""
        result: dict[str, list[str]] = {}
        for g in self.groups:
            for m in g["members"]:
                result.setdefault(m["id"], []).append(g["name"])
        return result

    @rx.event
    async def on_load(self):
        # Idempotente: si ya hay un grupo principal no hace nada; si no hay
        # ninguno (primera vez), migra los 3 sensores clásicos a un grupo
        # "Sistema" para no perder protección de golpe.
        groups_store.ensure_principal_group()
        self._reload()
        # Por sesión: cada pestaña ve los grupos/armados que cambie cualquier otra.
        yield GroupsState.sync_loop
        # El vigilante ya NO se arranca desde aquí: es una tarea del ciclo de
        # vida del proceso (security/watcher.py, registrada en noxuscmmd.py).
        # Colgado de este on_load, la casa podía quedarse armada sin nadie
        # vigilando hasta que alguien abriera el panel en un navegador.

    def _reload(self):
        self.groups = groups_store.read_all()

    @rx.event(background=True)
    async def sync_loop(self):
        """Espera el aviso de quien escribe en vez de releer cada segundo.

        Los dos temas hacen falta y no son el mismo: `ENTIDADES` cubre armar,
        desarmar y editar un grupo (todo eso pasa por `groups_store._write`),
        y `ARMADO` cubre el camino inverso — armar el sistema desde el escudo
        de la barra mueve el grupo principal a través de
        `shared_state.set_sistema_armado`. Escuchando solo uno, la mitad de
        los armados tardaban hasta un segundo en verse en las demás pestañas.
        """
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.ENTIDADES, bus.ARMADO)
        while True:
            try:
                real = await asyncio.to_thread(groups_store.read_all)
                async with self:
                    if real != self.groups:
                        self.groups = real
                if not await aviso.espera(guardia, 3.0):
                    return
            except Exception as e:
                print(f"⚠️ Error en GroupsState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 1):
                    return

    # ── Alta / baja de grupos ────────────────────────────────────────────
    @rx.event
    async def submit_add_group(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        name = form_data.get("name", "").strip()
        if not name:
            return
        groups_store.add_group(name)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "GRUPO_CREADO", name)

    @rx.event
    async def delete_group(self, group_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self._group_name(group_id)
        groups_store.delete_group(group_id)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "GRUPO_ELIMINADO", nombre)

    @rx.event
    async def submit_edit_group(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        group_id = form_data.get("entity_id", "")
        name = form_data.get("name", "").strip()
        if not group_id or not name:
            return
        anterior = self._group_name(group_id)
        groups_store.rename_group(group_id, name)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "GRUPO_EDITADO",
                              f"{anterior} -> {name}" if anterior != name else name)

    def _group_name(self, group_id: str) -> str:
        return next((g["name"] for g in self.groups if g["id"] == group_id), group_id)

    @rx.event
    async def toggle_group_armed(self, group_id: str):
        """El armado del grupo (disco, puente con el armado general y registro)
        está en arming.py, compartido con el motor de automatizaciones. Aquí
        queda quién lo ha pulsado y el repintado de las dos pantallas."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        push_state = await self.get_state(PushState)
        usuario = push_state.current_user if push_state.current_user.strip() else "sistema"
        try:
            group, nuevo = await arming.toggle_group_armed(group_id, usuario)
        except arming.ArmingError:
            return

        # Puente con el botón clásico de armado general: si este es el grupo
        # PRINCIPAL, su armado/desarmado también mueve sistema_armado (lo que
        # lee la vista clásica) — así ambas interfaces quedan sincronizadas.
        if group["is_principal"]:
            sec = await self.get_state(SecurityState)
            sec.sistema_armado = nuevo
            sec.status = sec._status_text()

        self._reload()

    @rx.event
    async def set_principal_group(self, group_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        groups_store.set_principal(group_id)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "GRUPO_PRINCIPAL_CAMBIADO",
                              f"{self._group_name(group_id)} pasa a ser el grupo del armado general")

    # ── Miembros ─────────────────────────────────────────────────────────
    async def _sensor_name(self, sensor_id: str) -> str:
        static = registry.binary_sensors().get(sensor_id)
        if static:
            return static.name
        nodes_state = await self.get_state(NodesState)
        dyn = next((s for s in nodes_state.sensors if s["id"] == sensor_id), None)
        return dyn["name"] if dyn else sensor_id

    @rx.event
    async def add_sensor_to_group(self, group_id: str, sensor_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not sensor_id:
            return
        name = await self._sensor_name(sensor_id)
        groups_store.add_member(group_id, sensor_id, name)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "SENSOR_AÑADIDO_A_GRUPO",
                              f"{name} -> {self._group_name(group_id)}")

    @rx.event
    async def remove_sensor_from_group(self, group_id: str, sensor_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = await self._sensor_name(sensor_id)
        grupo = self._group_name(group_id)
        groups_store.remove_member(group_id, sensor_id)
        self._reload()
        await audit.registrar(self, logs.GRUPOS, "SENSOR_QUITADO_DE_GRUPO", f"{nombre} <- {grupo}")

    # La vigilancia (alerta si un sensor de un grupo armado se abre) ya no vive
    # aquí: ver security/watcher.py.
