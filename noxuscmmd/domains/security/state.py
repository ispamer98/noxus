"""
Estado de seguridad: armado/desarmado, sensores binarios (puerta/tampers) y su
historial.

El abierto/cerrado de los sensores YA NO vive aquí: vive donde el de todos los
demás, en sensor_states de nodos_dinamicos.json (ver ../nodes/store.py), y quien
lo escribe es el callback único de ../nodes/sensor_events.py. Este archivo se
queda con lo que de verdad es suyo: el armado general y la foto reactiva que
consume la vista clásica.

Antes había aquí dos diccionarios escritos a mano, _SENSOR_ACCESSORS (un par
getter/setter por sensor contra estado_seguridad.json) y _SENSOR_META (sus
textos de log). Un sensor que no estuviera en ellos no guardaba su estado en
ningún sitio, y por eso "unos iban y otros no". Añadir un sensor nuevo ya no
pide tocar nada de esto.
"""
import asyncio
import os
import reflex as rx

from ..auth import permisos
from ..devices import registry
from ..devices.mqtt_bus import get_mqtt_bus
from ..nodes import sensor_events
from ..nodes import store as nodes_store
from ..notifications.state import PushState
from . import shared_state
from . import abiertos
from . import arming
from ...core import bus
from ...core import sesiones

_MQTT_STARTED = False


class SecurityState(rx.State):
    sistema_armado: bool = False
    status: str = "Esperando..."

    # Foto de sensor_states (nodos_dinamicos.json) keyed por entity id. Es la
    # MISMA fuente que NodesState.sensor_state — se mantienen las dos Vars
    # porque cada una la lee media aplicación, no porque haya dos estados.
    sensor_abierto: dict[str, bool] = {}

    _logs_update_counter: int = 0

    # ── Accesores cómodos para la UI existente ──────────────────────────
    @rx.var
    def puerta_abierta(self) -> bool:
        return self.sensor_abierto.get("puerta_ppal", False)

    @rx.var
    def tamper1_abierto(self) -> bool:
        return self.sensor_abierto.get("tamper1", False)

    @rx.var
    def tamper2_abierto(self) -> bool:
        return self.sensor_abierto.get("tamper2", False)

    # Ojo con la diferencia entre estos dos, que parecen lo mismo y no lo son:
    # el contador "Abiertos ahora" enseña lo que hay abierto en la casa, y el
    # registro de armado tiene que enseñar solo lo que ESE armado deja de
    # vigilar — o sea, los miembros de su grupo. Antes los dos salían de la
    # misma lista (todos los sensores de fábrica, con el nombre congelado del
    # arranque), y de ahí venían los nombres viejos y los sensores de otros
    # grupos apareciendo en el armado. Ver abiertos.py.
    def obtener_abiertos(self) -> list[str]:
        return abiertos.abiertos_ahora()

    def abiertos_al_armar(self) -> list[str]:
        return abiertos.abiertos_del_principal()

    @rx.var
    def lista_abiertos(self) -> str:
        lista = self.obtener_abiertos()
        return ", ".join(lista) if lista else "Ninguno"

    # ── Logs ─────────────────────────────────────────────────────────────
    def refresh_logs(self):
        """Marca que el registro ha cambiado.

        Ya no repinta nada por sí sola: el desplegable de historial que leía este
        contador se fue con la vista clásica (fase 8.3). Se mantiene el contador
        porque es la señal de "ha pasado algo que se ha apuntado", y la pestaña
        Registros la usa para recargar sin sondear el disco."""
        self._logs_update_counter += 1

    # ── Carga inicial ────────────────────────────────────────────────────
    @rx.event
    async def on_load(self):
        global _MQTT_STARTED
        self.refresh_logs()
        self.sistema_armado = await asyncio.to_thread(shared_state.get_sistema_armado)
        self.sensor_abierto = await asyncio.to_thread(nodes_store.get_all_sensor_states)
        self.status = self._status_text()

        yield SecurityState.sync_loop

        if not _MQTT_STARTED:
            _MQTT_STARTED = True
            mqtt_broker = os.getenv("MQTT_BROKER", "127.0.0.1")
            mqtt_port = int(os.getenv("MQTT_PORT", 1883))
            try:
                # El bus se arranca aquí porque es este dominio el que conoce
                # los sensores del registry (sus topics), pero el callback es
                # el compartido: lo que pasa al cambiar de estado es idéntico
                # para un sensor de fábrica y para uno dado de alta desde la web.
                get_mqtt_bus(mqtt_broker, mqtt_port, sensor_events.on_binary_sensor)
            except Exception as e:
                print(f"⚠️ Error controlado al iniciar MQTT: {e}")

    def _status_text(self) -> str:
        return "🔒 Sistema de Seguridad: ARMADO" if self.sistema_armado else "🔓 Sistema de Seguridad: DESARMADO"

    # ── Armar / desarmar ─────────────────────────────────────────────────
    @rx.event
    async def conmutar_alarma(self):
        """El armado en sí (disco, puente con el grupo principal y registro)
        está en arming.py, que es lo que puede llamar también el motor de
        automatizaciones. Aquí solo queda quién lo ha pulsado y repintar."""
        # Antes de nada: quien no puede armar, no arma. La comprobación va aquí
        # y no solo en el botón porque este evento se puede invocar por el
        # websocket desde cualquier navegador, tenga el botón a la vista o no.
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        push_state = await self.get_state(PushState)
        usuario = push_state.current_user if push_state.current_user.strip() else "sistema"
        nuevo = await arming.toggle_system_armed(usuario)
        self.sistema_armado = nuevo
        self.status = self._status_text()
        self.refresh_logs()

    # ── Sincronización con el disco (una tarea por sesión de socket) ─────
    # Solo PINTA: refleja en la Var lo que hay en disco. No registra logs y no
    # dispara alertas, a propósito.
    #
    # El log lo emite ../nodes/sensor_events.py, que corre una sola vez por
    # proceso. Antes salía de este bucle, y como hay un bucle POR SESIÓN cada
    # uno llevaba su propio "último estado": con dos pestañas abiertas, la misma
    # apertura se registraba dos veces.
    #
    # La alerta push la decide GroupsState.watch_loop mirando de qué grupo(s)
    # armado(s) es miembro el sensor, igual para todos.
    #
    # Ya no relee el disco cada medio segundo: espera a que alguien avise de
    # que el armado o un sensor cambiaron (core/bus.py). El tope de 3 s es el
    # respaldo por si el fichero lo escribiera algo de fuera de este proceso.
    @rx.event(background=True)
    async def sync_loop(self):
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.ARMADO, bus.SENSORES)
        while True:
            try:
                real_armado = await asyncio.to_thread(shared_state.get_sistema_armado)
                real_abierto = await asyncio.to_thread(nodes_store.get_all_sensor_states)

                async with self:
                    if self.sistema_armado != real_armado:
                        self.sistema_armado = real_armado
                        self.status = self._status_text()
                        self.refresh_logs()
                    if self.sensor_abierto != real_abierto:
                        self.sensor_abierto = real_abierto
                        self.refresh_logs()

                if not await aviso.espera(guardia, 3.0):
                    return
            except Exception as e:
                print(f"⚠️ Error en bucle de sincronización: {e}")
                if not await sesiones.espera(guardia, 1):
                    return
