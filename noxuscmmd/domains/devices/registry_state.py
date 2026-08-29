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

# Forma completa de una entrada de floor_pos. Toda escritura parcial en esa Var
# tiene que partir de aquí (o de la entrada que ya hubiera): al marcador del
# plano le hacen falta las CINCO claves, y una que llegue a `undefined` no da
# error, simplemente pinta mal — el color se cae al de por defecto y
# `subtle != ""` se cumple, así que el icono se queda en modo integrado sin que
# nadie lo haya pedido (ver _marker en ui/views/device_list.py).
_FLOOR_POS_VACIO = {"top": "", "left": "", "icon": "", "subtle": "", "color": "",
                    "color_on": ""}


class RegistryState(rx.State):
    # Nombres mostrados en pantalla de las entidades estáticas — a diferencia
    # del resto de campos (IP, usuario SSH...), que solo se ven actualizados
    # tras reiniciar (ver registry.apply_override), el nombre se guarda además
    # aquí como Var reactiva para que un cambio se refleje al instante en
    # cualquier tarjeta que lo esté mostrando, en la misma sesión.
    names: dict[str, str] = {eid: e.name for eid, e in registry.DEVICES.items()}

    # Mismo motivo que "names", para el icono: registry.apply_override() ya
    # actualiza el registry.DEVICES del proceso al instante (lo dice su propio
    # docstring), pero una tarjeta como la de CCTV se construye con literales
    # fijos ("cam_fija", "cam_ptz") UNA sola vez al compilar la app — cambiar
    # el icono de una cámara de fábrica se guardaba, pero la tarjeta seguía
    # enseñando el icono viejo hasta reiniciar el servicio entero.
    icons: dict[str, str] = {
        eid: getattr(e, "icon", None) or "" for eid, e in registry.DEVICES.items()
    }

    # Igual que "names": registry.isolated_ids() persiste en disco pero por sí
    # solo no dispara ningún repintado (las tarjetas de sensores estáticos se
    # construyen una vez en Python, no vía rx.foreach) — sin este dict Var, el
    # icono de aislar/reactivar cambiaba el fichero pero la tarjeta se quedaba
    # visualmente igual hasta reiniciar el servicio.
    isolated: dict[str, bool] = {eid: True for eid in registry.isolated_ids()}

    # Igual que "names"/"isolated": posición + icono en el plano de planta de
    # un sensor/cámara "de fábrica" (puerta_ppal, cam_fija...) — se persiste
    # en disco vía registry.apply_override/set_factory_floor_pos, pero sin
    # esta Var reactiva, ni el arrastre ni el toggle "mostrar en el plano" se
    # verían en pantalla hasta reiniciar (ver ui/views/device_list.py).
    floor_pos: dict[str, dict[str, str]] = {
        eid: {
            "top": e.floor_top or "", "left": e.floor_left or "",
            "icon": e.floor_icon or "", "subtle": "1" if e.floor_subtle else "",
            "color": e.floor_color or "",
            "color_on": e.floor_color_on or "",
        }
        for eid, e in registry.DEVICES.items() if hasattr(e, "floor_top")
    }

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
        self.floor_pos = {
            eid: {
                "top": e.floor_top or "", "left": e.floor_left or "",
                "icon": e.floor_icon or "", "subtle": "1" if e.floor_subtle else "",
                "color": e.floor_color or "",
            "color_on": e.floor_color_on or "",
            }
            for eid, e in registry.DEVICES.items() if hasattr(e, "floor_top")
        }

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
        stored = registry.apply_override(entity_id, **fields)
        new_name = fields.get("name")
        if new_name:
            self.names[entity_id] = new_name
            # Igual que en NodesState.submit_edit_sensor: los grupos llevan el
            # nombre de sus miembros copiado y hay que propagarlo a mano.
            groups_store.rename_member(entity_id, new_name)
        new_icon = fields.get("icon")
        if new_icon:
            self.icons[entity_id] = new_icon
        if "floor_top" in stored or "floor_icon" in stored:
            # Sobre lo que ya hubiera: el formulario de edición no trae color ni
            # modo integrado, y reconstruir la entrada desde cero los borraba de
            # la Var (en disco seguían), así que guardar la ficha de un sensor
            # le cambiaba el aspecto en el plano hasta recargar.
            current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
            self.floor_pos[entity_id] = {
                **current,
                "top": stored.get("floor_top") or "",
                "left": stored.get("floor_left") or "",
                "icon": stored.get("floor_icon") or "",
            }

    # OJO: los cuatro métodos de plano de abajo NO llevan @rx.event, a
    # propósito. Los llama NodesState (no la UI) sobre la instancia que
    # devuelve get_state(), y un método decorado con @rx.event es un
    # EventHandler (Reflex convierte TODO método público de un State en uno,
    # con decorador o sin él), y un EventHandler no es descriptor: llamarlo
    # sobre una instancia
    # devuelve un EventSpec y el cuerpo de la función no se ejecuta nunca.
    # Con el decorador puesto, arrastrar/añadir/quitar un sensor o cámara "de
    # fábrica" en el plano no guardaba nada, en silencio.
    def cargar_plano(self, plano_id: str) -> None:
        """Rellena floor_pos con las posiciones que las entidades de fábrica
        tienen EN ESE PLANO.

        Hace falta porque las de fábrica no viven en ninguna colección reactiva:
        su posición se pinta desde esta Var, que se construyó una vez al arrancar
        con la del plano principal. Sin esto, al cambiar de plano los sensores y
        cámaras de fábrica se quedarían clavados donde estaban en el principal —
        y encima moverlos ahí sobrescribiría el sitio del otro plano.

        Se lee del store y no de registry.DEVICES porque DEVICES solo guarda una
        posición (la del principal, que es el espejo)."""
        from ..nodes import store as nodes_store

        datos = nodes_store.read_all()
        nuevo = dict(self.floor_pos)
        for coleccion in ("factory_sensors", "factory_cameras"):
            for item in datos[coleccion]:
                sitio = (item.get("posiciones") or {}).get(plano_id) or {}
                actual = nuevo.get(item["id"], _FLOOR_POS_VACIO)
                nuevo[item["id"]] = {
                    **actual,
                    # Vacío = no está en este plano, y el marcador no se pinta
                    # (su rx.cond mira `top != ""`).
                    "top": sitio.get("top", ""),
                    "left": sitio.get("left", ""),
                }
        self.floor_pos = nuevo

    def _reflect_factory_floor_pos(self, entity_id: str, top: str, left: str):
        """Solo lo que se ve: Var reactiva + DEVICES. El disco ya lo escribió
        set_floor_positions_bulk (guardado en bloque al pulsar "Listo")."""
        registry.reflect_floor_pos(entity_id, top, left)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "top": top, "left": left}

    def _set_factory_floor_pos(self, entity_id: str, top: str, left: str):
        """Persiste + refleja al instante el arrastre de un marcador "de
        fábrica" sobre el plano — llamado desde NodesState.set_floor_pos
        (ver domains/nodes/state.py), que decide si la entidad es de fábrica
        o dada de alta desde la web."""
        registry.set_factory_floor_pos(entity_id, top, left)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "top": top, "left": left}

    # ── Plano de planta: alta/baja/icono desde el propio plano ───────────
    # Equivalentes a store.set_floor_position/clear_floor_position/
    # set_floor_icon para las entidades "de fábrica", que no viven en ninguna
    # colección reactiva — de ahí que además de persistir haya que actualizar
    # floor_pos a mano para que el plano se repinte al instante.
    def _place_factory_on_floor(self, entity_id: str, icon: str):
        registry.apply_override(entity_id, show_on_floor="on", floor_icon=icon)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "top": "50%", "left": "50%", "icon": icon}

    def _remove_factory_from_floor(self, entity_id: str):
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        registry.apply_override(entity_id, show_on_floor="", floor_icon=current.get("icon", ""))
        # Se conservan icono, color y modo integrado: quitar algo del plano no
        # es olvidar cómo se veía — al volver a ponerlo aparece igual que estaba.
        self.floor_pos[entity_id] = {**current, "top": "", "left": ""}

    def _set_factory_floor_color(self, entity_id: str, color: str):
        registry.set_factory_floor_color(entity_id, color)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "color": color}

    def _set_factory_floor_color_on(self, entity_id: str, color: str):
        registry.set_factory_floor_color_on(entity_id, color)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "color_on": color}

    def _toggle_factory_floor_subtle(self, entity_id: str):
        actual = registry.toggle_factory_floor_subtle(entity_id)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "subtle": "1" if actual else ""}

    def _set_factory_floor_icon(self, entity_id: str, icon: str):
        registry.set_factory_floor_icon(entity_id, icon)
        current = self.floor_pos.get(entity_id, _FLOOR_POS_VACIO)
        self.floor_pos[entity_id] = {**current, "icon": icon}

    @rx.event
    def hide_entity(self, entity_id: str):
        registry.hide(entity_id)

    @rx.event
    def delete_factory_entity(self, entity_id: str):
        """Borrado real (no ocultar) de un equipo/sensor/cámara "de fábrica"
        — ver registry.delete_factory_entity. Solo se ve reflejado tras
        reiniciar el servicio, igual que cualquier otra edición estática."""
        registry.delete_factory_entity(entity_id)
        self.names.pop(entity_id, None)
        self.isolated.pop(entity_id, None)
        self.floor_pos.pop(entity_id, None)

    @rx.event
    def unhide_entity(self, entity_id: str):
        registry.unhide(entity_id)

    @rx.event
    def toggle_isolated(self, entity_id: str):
        if registry.is_isolated(entity_id):
            registry.unisolate(entity_id)
        else:
            registry.isolate(entity_id)
        # El estado que se pinta se relee del disco en vez de darlo por hecho:
        # isolated_ids() es la unión de factory_sensors + registry_overrides,
        # así que asumir el resultado puede desincronizar lo que se ve de lo
        # que hay guardado (que es justo lo que pasaba antes).
        if registry.is_isolated(entity_id):
            self.isolated[entity_id] = True
        else:
            self.isolated.pop(entity_id, None)
