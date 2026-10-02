"""
Puente genérico entre los formularios de edición de la UI y
registry.apply_override(). Un único handler sirve para cualquier tipo de
entidad estática (host, sensor, relé, cámara) — el formulario decide qué
campos manda según el tipo, y aquí simplemente se reenvían.
"""
import reflex as rx

from ..auth import permisos

from . import registry
from ..security import groups_store
from ...core import bus, sesiones

class RegistryState(rx.State):
    # Nombres mostrados en pantalla de las entidades estáticas — a diferencia
    # del resto de campos (IP, usuario SSH...), que solo se ven actualizados
    # tras reiniciar (ver registry.apply_override), el nombre se guarda además
    # aquí como Var reactiva para que un cambio se refleje al instante en
    # cualquier tarjeta que lo esté mostrando, en la misma sesión.
    names: dict[str, str] = {eid: e.name for eid, e in registry.DEVICES.items()}

    # Mismo motivo que "names", para el icono: registry.apply_override() ya
    # actualiza el registry.DEVICES del proceso al instante, y esta Var hace
    # que el cambio se refleje en las tarjetas de la sesión.
    icons: dict[str, str] = {
        eid: getattr(e, "icon", None) or "" for eid, e in registry.DEVICES.items()
    }

    # Igual que "names": registry.isolated_ids() persiste en disco pero por sí
    # solo no dispara ningún repintado (las tarjetas de sensores estáticos se
    # construyen una vez en Python, no vía rx.foreach) — sin este dict Var, el
    # icono de aislar/reactivar cambiaba el fichero pero la tarjeta se quedaba
    # visualmente igual hasta reiniciar el servicio.
    isolated: dict[str, bool] = {eid: True for eid in registry.isolated_ids()}

    @rx.event
    def on_load(self):
        """Relee del disco lo que se muestra de las entidades "de fábrica".

        Sin esto, los valores de arriba solo se evalúan UNA vez, al importar
        el módulo (arranque del proceso): aislar un sensor se veía en la
        sesión que lo hizo, pero al recargar la página la Var volvía a la
        foto del arranque y parecía que no se hubiera guardado nada — aunque
        en disco sí estuviera. Es el equivalente a NodesState._reload(), que
        es justo por lo que los sensores dados de alta desde la web sí
        conservaban su estado."""
        self._refresh()
        return RegistryState.sync_loop

    @rx.event(background=True)
    async def sync_loop(self):
        """Refleja en ESTA pestaña lo que otra haya editado de las entidades
        de fábrica: nombre, icono, aislado y posición en el plano.

        Hasta ahora este State no tenía bucle ninguno: `apply_override` deja
        `registry.DEVICES` al día en el proceso —así que el dato ya era
        correcto para todos—, pero las Vars de arriba son una copia POR SESIÓN
        y solo las rellenaba `on_load`. Resultado: renombrar la puerta
        principal desde el móvil no se veía en el ordenador hasta recargar.

        No relee ningún fichero: `DEVICES` es del proceso y ya lo tiene todo.
        Solo hay que volver a volcarlo en las Vars cuando algo cambie.
        """
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.ENTIDADES)
        while True:
            try:
                async with self:
                    self._refresh()
                if not await aviso.espera(guardia, 5.0):
                    return
            except Exception as e:
                print(f"⚠️ Error en RegistryState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 2):
                    return

    def _refresh(self):
        self.names = {eid: e.name for eid, e in registry.DEVICES.items()}
        self.icons = {eid: getattr(e, "icon", None) or "" for eid, e in registry.DEVICES.items()}
        self.isolated = {eid: True for eid in registry.isolated_ids()}

    @rx.event
    async def submit_edit_entity(self, form_data: dict):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        entity_id = form_data.get("entity_id", "").strip()
        if not entity_id:
            return
        fields = {k: v for k, v in form_data.items() if k != "entity_id"}
        registry.apply_override(entity_id, **fields)
        new_name = fields.get("name")
        if new_name:
            self.names[entity_id] = new_name
            # Igual que en NodesState.submit_edit_sensor: los grupos llevan el
            # nombre de sus miembros copiado y hay que propagarlo a mano.
            groups_store.rename_member(entity_id, new_name)
        new_icon = fields.get("icon")
        if new_icon:
            self.icons[entity_id] = new_icon
    @rx.event
    def hide_entity(self, entity_id: str):
        registry.hide(entity_id)

    @rx.event
    def unhide_entity(self, entity_id: str):
        registry.unhide(entity_id)

    @rx.event
    def toggle_isolated(self, entity_id: str):
        if registry.is_isolated(entity_id):
            registry.unisolate(entity_id)
        else:
            registry.isolate(entity_id)
        if registry.is_isolated(entity_id):
            self.isolated[entity_id] = True
        else:
            self.isolated.pop(entity_id, None)
