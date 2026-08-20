"""
Infraestructura: estado online/offline de todos los hosts, acciones SSH
genéricas (apagar/reiniciar/temperatura/comando), relés (GPIO) y RDP/WOL.
Construido iterando devices/registry.py — añadir un host nuevo no toca esta
clase, solo el registry.
"""
import asyncio
import base64
import os
from pathlib import Path
import reflex as rx

from ..auth import permisos
from ..devices import registry, ssh_bus, gpio_bus
from ..devices import actions as device_actions
from ..nodes import store as nodes_store, rdp
from ...core.sensors import Sensors
from ...core import bus
from ...core import sesiones

class InfraState(rx.State):
    status: str = "Esperando..."
    host_online: dict[str, bool] = {hid: False for hid in registry.hosts()}
    temperaturas: list[str] = []
    custom_command: dict[str, str] = {}
    custom_output: dict[str, str] = {}
    last_rpi_photo: str = ""
    dialog_foto_abierto: bool = False

    @rx.var
    def online_count(self) -> int:
        """Equipos que responden al ping — para el widget "Equipos en línea"
        del Resumen. Cuenta TODOS: desde la unificación no hay dos clases de
        equipo, así que tampoco hay dos contadores que cuadrar.

        Se filtra por registry.hosts() en vez de sumar el diccionario entero:
        host_online puede arrastrar equipos que ya no existen (borrados antes
        de que delete_host limpiase su estado, o borrados por otra sesión sin
        que esta lo note, porque aquí solo se hace update()). Contarlos daba
        de más — el caso real: un equipo borrado que había quedado en True
        hacía que el widget dijese 6 con 5 equipos en línea."""
        conocidos = registry.hosts()
        return sum(1 for hid, v in self.host_online.items() if v and hid in conocidos)

    # ── Carga inicial ────────────────────────────────────────────────────
    @rx.event
    async def on_load(self):
        # La conexión SSH persistente y su keepalive los arranca el proceso
        # (ver core/ssh_manager.run_forever), no esta pantalla.
        yield InfraState.actualizar_estados

    # ── Ping de TODOS los equipos ────────────────────────────────────────
    # Desde que los equipos añadidos desde la web y los de siempre viven en la
    # misma colección, registry.hosts() los devuelve a todos y basta un bucle.
    #
    # OJO con quién ESCRIBE: este evento se lanza una vez por sesión y su bucle
    # no muere cuando el cliente se va (se ve en el log como "Attempting to send
    # delta to disconnected client"). Si cada uno de esos bucles huérfanos
    # persistiese el estado, N recargas de página = N escrituras con cerrojo
    # EXCLUSIVO sobre nodos_dinamicos.json cada 8s; como las lecturas del store
    # son síncronas dentro del event loop, el backend acababa bloqueado y la UI
    # congelada (no respondía ni al alta de un equipo).
    #
    # Por eso solo el PRIMER bucle del proceso pinga y escribe; los demás se
    # limitan a leer lo que aquel dejó, que es un cerrojo compartido y no frena
    # a nadie. Todos acaban viendo el mismo estado igualmente.
    @rx.event(background=True)
    async def actualizar_estados(self):
        """Refleja en la pantalla quién está en línea. SOLO LEE.

        Quien pinga es infra/ping_motor.py, una tarea de proceso. Antes pingaba
        desde aquí el primer bucle que arrancara, con un global para que los
        demás no repitieran el trabajo; el día que los bucles de sesión
        empezaron a morirse con su navegador, ese global se quedó puesto sin
        nadie detrás y el estado de los equipos dejó de actualizarse hasta
        reiniciar el servicio — un PC apagado seguía figurando en línea. La
        explicación larga está en la cabecera de ping_motor.py."""
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.EQUIPOS)
        while True:
            estados = await asyncio.to_thread(nodes_store.get_all_host_online)
            async with self:
                self.host_online.update(estados)
            # Espera a que el motor avise de que ha pingado (core/bus.py), con
            # su tope por si el fichero lo tocara algo de fuera del proceso.
            if not await aviso.espera(guardia, 8.0):
                return

    # ── Acciones genéricas por host ──────────────────────────────────────
    @rx.event(background=True)
    async def accion_apagar(self, device_key: str):
        host = registry.hosts()[device_key]
        async with self: self.status = f"🔌 Apagando {host.name}..."
        res = await ssh_bus.accion_apagar(host.ssh)
        async with self: self.status = f"✅ {host.name}: {res[:80]}"

    @rx.event(background=True)
    async def accion_reiniciar(self, device_key: str):
        host = registry.hosts()[device_key]
        async with self: self.status = f"🔄 Reiniciando {host.name}..."
        res = await ssh_bus.accion_reiniciar(host.ssh)
        async with self: self.status = f"✅ {host.name}: {res[:80]}"

    @rx.event(background=True)
    async def accion_temperatura(self, device_key: str):
        host = registry.hosts()[device_key]
        async with self: self.status = f"🌡️ Leyendo temperatura de {host.name}..."
        res = await ssh_bus.accion_temperatura(host.ssh)
        async with self: self.status = f"🌡️ {host.name}: {res}"

    @rx.event(background=True)
    async def ejecutar_comando_personalizado(self, device_key: str):
        host = registry.hosts()[device_key]
        cmd = self.custom_command.get(device_key, "")
        if not cmd.strip():
            return
        async with self:
            self.status = f"⚡ Ejecutando en {host.name}: {cmd[:30]}..."
            self.custom_output[device_key] = "Ejecutando..."
        res = await ssh_bus.ssh_execute(host.ssh, cmd)
        async with self:
            self.custom_output[device_key] = res
            self.status = f"✅ {host.name}: comando completado"

    def set_custom_command(self, device_key: str, value: str):
        self.custom_command[device_key] = value

    # ── Relés genéricos ──────────────────────────────────────────────────
    @rx.event(background=True)
    async def accion_gpio(self, relay_id: str, estado: str):
        relay = registry.get_relay(relay_id)
        async with self: self.status = f"🔌 {relay.name} -> {estado}"
        await gpio_bus.set_relay(relay, estado == "on")
        async with self: self.status = f"✅ {relay.name} {estado}"

    @rx.event(background=True)
    async def gpio_17_test(self):
        async with self: self.status = "🌬️ Ventilador ON..."
        try:
            await device_actions.gpio_17_test()
            async with self: self.status = "🌬️ Test completado"
        except Exception as e:
            async with self: self.status = f"❌ GPIO: {e}"

    # ── Acciones especiales cableadas a un equipo concreto (RDP, WOL, foto) ──
    # Cada equipo lleva en su ficha una lista de acciones_extra con el NOMBRE
    # del handler; esto las resuelve al handler real en el servidor. Hace falta
    # porque las tarjetas de equipo se pintan ahora con un rx.foreach sobre una
    # lista reactiva: dentro de un foreach no se puede elegir el manejador en
    # Python, solo pasar el nombre y decidir aquí.
    @rx.event
    def run_accion_extra(self, handler_name: str):
        handlers = {
            "wake_pc": InfraState.wake_pc,
            "rdp_pc": InfraState.rdp_pc,
            "rdp_portatil": InfraState.rdp_portatil,
            "rdp_raspberry": InfraState.rdp_raspberry,
            "gpio_17_test": InfraState.gpio_17_test,
            "tomar_foto_raspberry": InfraState.tomar_foto_raspberry,
        }
        handler = handlers.get(handler_name)
        if handler is not None:
            yield handler

    # ── RDP / WOL ────────────────────────────────────────────────────────
    # Los tres manejadores de RDP abrían un cliente EN EL SERVIDOR
    # (subprocess.Popen de /home/spamer/*_to_*.sh, ficheros que ya no existen),
    # así que no hacían nada visible para quien pulsaba. Ahora los tres bajan
    # el .rdp al navegador de quien pulsa; el equipo que no tenga cuenta de
    # escritorio remoto en su ficha lo dice en el estado en vez de fallar en
    # silencio. Siguen existiendo con estos nombres porque la vista clásica
    # (/clasica) los tiene cableados uno a uno — ver ui/views/device_list.py.
    def rdp_pc(self):
        return self._descargar_rdp("pc")

    def rdp_portatil(self):
        return self._descargar_rdp("portatil")

    def rdp_raspberry(self):
        return self._descargar_rdp("raspberry")

    def _descargar_rdp(self, host_id: str):
        host = nodes_store.find_host_by_id(host_id)
        evento = rdp.evento_abrir(host)
        if evento is None:
            self.status = "❌ Este equipo no tiene escritorio remoto configurado"
            return
        self.status = f"▶ Abriendo escritorio remoto de {host['name']}"
        return evento

    def wake_pc(self):
        device_actions.pc_wol()
        self.status = "⚡ WOL enviado"

    # ── Foto Pi Zero ─────────────────────────────────────────────────────
    @rx.event(background=True)
    async def tomar_foto_raspberry(self):
        async with self:
            if not self.host_online.get("pi_zero", False):
                self.status = "❌ Pi Zero OFFLINE"
                return
            self.status = "📸 Capturando..."
        try:
            foto_bytes = await device_actions.pizero_tomar_foto()
            foto_b64 = base64.b64encode(foto_bytes).decode()
            async with self:
                self.last_rpi_photo = f"data:image/jpeg;base64,{foto_b64}"
                self.dialog_foto_abierto = True
                self.status = "✅ Foto capturada"
        except Exception as e:
            async with self: self.status = f"❌ Foto: {e}"

    def toggle_dialog(self):
        self.dialog_foto_abierto = not self.dialog_foto_abierto

    # ── Subida de archivos ───────────────────────────────────────────────
    async def handle_upload(self, files: list[rx.UploadFile]):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        upload_dir = Path(os.getenv("UPLOAD_FOLDER", "/home/spamer/archivos"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        guardados = 0
        for file in files:
            # El nombre lo pone el cliente: tal cual, un «../../auth_secreto.json»
            # o un «../.ssh/authorized_keys» se escribiría fuera de la carpeta y
            # con los permisos del servicio. .name se queda con la última parte
            # del camino, y sin punto delante para no colar dotfiles.
            nombre = Path(file.name or "").name
            if not nombre or nombre.startswith("."):
                continue
            data = await file.read()
            (upload_dir / nombre).write_bytes(data)
            guardados += 1
        rechazados = len(files) - guardados
        self.status = f"✅ {guardados} archivo(s) subido(s)" + (
            f" · {rechazados} con nombre no válido" if rechazados else "")

    # ── Temperatura CPU (Raspberry, vía SSH persistente) ────────────────
    @rx.event(background=True)
    async def medir_temperatura(self):
        async with self:
            self.temperaturas = []
            self.status = "🌡️ Midiendo..."
        resultados = await asyncio.gather(
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
        )
        async with self:
            self.temperaturas = [f"🌡️ {t:.1f} °C" for t in resultados]
            self.status = f"🌡️ Temp: {resultados[1]:.1f} °C"
