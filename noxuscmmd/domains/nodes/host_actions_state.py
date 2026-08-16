"""
Interacción unificada con CUALQUIER host — fijo del registry (server, pc,
raspberry...) o extra dado de alta en la pestaña Equipos —: consola SSH
libre, las 3 acciones genéricas de siempre (apagar/reiniciar/temperatura) y
botones de acción totalmente personalizables (comando SSH / escribir pin /
leer pin), persistidos en nodes/store.py (colección host_buttons) referenciados
solo por host_id — no importa si ese id es de un host "de fábrica" o de uno
añadido ayer, el mecanismo es exactamente el mismo para los dos.

Solo puede haber consola/acciones si el equipo tiene usuario SSH; si se dejó
en blanco es de solo ping. Da igual de cuándo sea el equipo: desde que todos
viven en la misma colección, el usuario se busca siempre en el mismo sitio.
"""
import asyncio

import reflex as rx

from . import store as nodes_store, rdp, operations
from ..security import audit, logs
from ..devices import ssh_bus
from ..devices.models import SSHSpec

# La resolución del SSH de un equipo y los nombres de acción del registro
# viven ahora en operations.py, compartidos con el motor de automatizaciones:
# si cada uno usara los suyos, el filtro de Registros acabaría enseñando dos
# vocabularios para el mismo suceso. Se reexportan porque este módulo era el
# sitio de siempre donde buscarlos.
resolve_ssh = operations.host_ssh
_ACCIONES_LOG = operations.ACCIONES_LOG

# Cada cuánto se refresca la temperatura de los equipos que tengan el widget
# "Temperatura" en el Resumen — no es un ping, es un comando SSH de verdad, y
# pedirla a cada equipo cada pocos segundos sería un SSH innecesario detrás de
# cada uno. 30s es lo mismo que usa el motor de automatizaciones para lo mismo.
_PERIODO_TEMPERATURA = 30.0
_TEMP_STARTED = False


def _hosts_con_widget_temp() -> set[str]:
    """A qué equipos hay que sondearles la temperatura AHORA MISMO — se
    recalcula en cada vuelta leyendo el propio almacén de widgets, así que
    añadir o quitar el widget de un equipo empieza o deja de sondearlo sin
    reiniciar nada."""
    return {
        w["target_id"] for w in nodes_store.read_all().get("overview_widgets", [])
        if w.get("kind") == "stat_host_temp" and w.get("target_id")
    }


class HostActionsState(rx.State):
    expanded_host: str = ""
    console_input: dict[str, str] = {}
    console_output: dict[str, str] = {}
    running: dict[str, bool] = {}
    buttons: list[dict] = []

    # host_id -> "48.3 °C" ya formado, o "" mientras no se haya podido leer
    # todavía. Lo consume el widget "Temperatura" del Resumen (stat_host_temp).
    host_temps: dict[str, str] = {}

    @rx.event
    def on_load(self):
        self._reload_buttons()
        return HostActionsState.temp_loop

    @rx.event(background=True)
    async def temp_loop(self):
        """Un solo bucle por proceso — igual que el resto de bucles de fondo
        de la app — que mantiene HostActionsState.host_temps al día. No hace
        NADA si nadie tiene un widget de temperatura puesto: la lista de
        objetivos sale vacía y la vuelta no abre ninguna conexión."""
        global _TEMP_STARTED
        if _TEMP_STARTED:
            return
        _TEMP_STARTED = True
        while True:
            try:
                objetivo = await asyncio.to_thread(_hosts_con_widget_temp)
                for host_id in objetivo:
                    if resolve_ssh(host_id) is None:
                        continue
                    try:
                        salida = await operations.host_action(host_id, "temperatura")
                    except operations.OperationError:
                        salida = ""
                    async with self:
                        self.host_temps[host_id] = salida
            except Exception as e:
                print(f"⚠️ Error en HostActionsState.temp_loop: {e}")
            await asyncio.sleep(_PERIODO_TEMPERATURA)

    @staticmethod
    def _nombre_equipo(host_id: str) -> str:
        host = nodes_store.find_host_by_id(host_id)
        return host["name"] if host else host_id

    def _reload_buttons(self):
        self.buttons = nodes_store.read_all().get("host_buttons", [])

    @rx.var
    def buttons_by_host(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for b in self.buttons:
            out.setdefault(b["host_id"], []).append(b)
        return out

    @rx.event
    def toggle_expand(self, host_id: str):
        self.expanded_host = "" if self.expanded_host == host_id else host_id

    # La consola SSH empieza SIEMPRE recogida dentro de la ficha desplegada:
    # es lo que se usa menos y lo que más sitio ocupa (entrada + salida), así
    # que tiene su propio botón para sacarla en vez de venir ya abierta.
    console_shown: dict[str, bool] = {}

    @rx.event
    def toggle_console(self, host_id: str):
        self.console_shown[host_id] = not self.console_shown.get(host_id, False)

    def set_console_input(self, host_id: str, value: str):
        self.console_input[host_id] = value

    @rx.event(background=True)
    async def run_console_command(self, host_id: str):
        async with self:
            cmd = self.console_input.get(host_id, "").strip()
            if not cmd:
                return
            self.running[host_id] = True
            self.console_output[host_id] = "Ejecutando..."
        ssh = resolve_ssh(host_id)
        if ssh is None:
            async with self:
                self.console_output[host_id] = "ERROR: este equipo no tiene usuario SSH configurado."
                self.running[host_id] = False
            return
        out = await ssh_bus.ssh_execute(ssh, cmd, timeout=8)
        async with self:
            self.console_output[host_id] = out
            self.running[host_id] = False
            await audit.registrar(self, logs.EQUIPOS, "COMANDO_SSH",
                                  f"{self._nombre_equipo(host_id)}: {cmd}")

    # ── Acciones genéricas (las mismas que ya había en Infra, para cualquier host) ──
    @rx.event(background=True)
    async def accion_generica(self, host_id: str, accion: str):
        """La clave de `running` es host_id+accion, NO solo host_id: con una
        sola clave por equipo, pulsar "Temperatura" ponía en marcha (visto
        desde fuera) el aro de carga de "Apagar" y "Reiniciar" también, porque
        los tres leían la MISMA bandera. Y el resultado sale por TOAST, no por
        self.console_output: eso alimenta la consola libre, que ahora está
        recogida por defecto — un resultado que nadie ve no sirve de nada."""
        nombre = self._nombre_equipo(host_id)
        clave = host_id + ":" + accion
        if resolve_ssh(host_id) is None:
            yield rx.toast.error(f"{nombre} no tiene usuario SSH configurado.",
                                 position="top-center", duration=6000)
            return
        async with self:
            self.running[clave] = True
        try:
            res = await operations.host_action(host_id, accion)
        except operations.OperationError as e:
            res = f"ERROR: {e}"
        async with self:
            self.running[clave] = False
            await audit.registrar(self, logs.EQUIPOS, _ACCIONES_LOG.get(accion, "ACCION_EQUIPO"), nombre)
        if res.startswith("ERROR"):
            yield rx.toast.error(f"{nombre}: {res[:200]}", position="top-center", duration=10000)
        else:
            yield rx.toast.success(f"{nombre}: {res[:200] or 'hecho'}",
                                   position="top-center", duration=10000)

    # ── Accesos rápidos del Resumen ──────────────────────────────────────
    # Mismos verbos que accion_generica/wake_pc, pero avisan con un TOAST en
    # vez de escribir en self.console_output: ese texto vive dentro de la
    # ficha desplegada de un equipo en la pestaña Equipos, que desde el
    # Resumen no está a la vista — sin el toast, pulsar "Apagar" ahí no daría
    # ninguna señal de que ha pasado algo.
    @rx.event(background=True)
    async def accion_rapida(self, host_id: str, accion: str):
        nombre = self._nombre_equipo(host_id)
        if resolve_ssh(host_id) is None:
            yield rx.toast.error(f"{nombre} no tiene usuario SSH configurado.",
                                 position="top-center", duration=6000)
            return
        try:
            await operations.host_action(host_id, accion)
        except operations.OperationError as e:
            yield rx.toast.error(f"{nombre}: {e}", position="top-center", duration=6000)
            return
        await audit.registrar(self, logs.EQUIPOS, _ACCIONES_LOG.get(accion, "ACCION_EQUIPO"), nombre)
        etiqueta = {"apagar": "apagándose", "reiniciar": "reiniciándose"}.get(accion, accion)
        yield rx.toast.success(f"{nombre} está {etiqueta}", position="top-center", duration=4000)

    @rx.event(background=True)
    async def encender_wol(self, host_id: str):
        """Wake-on-LAN genérico — cualquier equipo con MAC en su ficha, no
        solo el PC de siempre (operations.wake_host, a diferencia del viejo
        InfraState.wake_pc que llevaba la MAC incrustada en el código)."""
        nombre = self._nombre_equipo(host_id)
        try:
            await asyncio.to_thread(operations.wake_host, host_id)
        except operations.OperationError as e:
            yield rx.toast.error(f"{nombre}: {e}", position="top-center", duration=6000)
            return
        await audit.registrar(self, logs.EQUIPOS, "EQUIPO_ENCENDIDO_WOL", nombre)
        yield rx.toast.success(f"Señal de encendido enviada a {nombre}",
                               position="top-center", duration=4000)

    # ── Escritorio remoto ────────────────────────────────────────────────
    # Los dos abren la sesión en el equipo de QUIEN PULSA, no en el servidor —
    # ver domains/nodes/rdp.py. El equipo se relee del almacén en vez de usar
    # el que ya viene pintado en la tarjeta: así, cambiarle la cuenta de RDP en
    # el formulario tiene efecto en el siguiente clic, sin recargar la página.
    @rx.event(background=True)
    async def open_rdp(self, host_id: str):
        """Abre la sesión remota. Dos caminos según lo que tenga el equipo en
        "Lanzar desde": por SSH en otro equipo (lo fiable) o pasándole la
        dirección al navegador de quien pulsa (lo que se pueda)."""
        async with self:
            host = nodes_store.find_host_by_id(host_id)
            problema = self._problema_rdp(host, host_id)
            if problema is not None:
                yield problema
                return
            lanzador_id = (host.get("rdp_launch_host") or "").strip()

        if not lanzador_id:
            yield rdp.evento_abrir(host)
            return

        lanzador = nodes_store.find_host_by_id(lanzador_id)
        if lanzador is None or not lanzador.get("user"):
            yield rx.toast.error(
                "El equipo desde el que se debe abrir la sesión ya no existe o "
                "no tiene usuario SSH configurado.",
                position="top-center", duration=8000,
            )
            return
        if not nodes_store.get_all_host_online().get(lanzador_id, False):
            yield rx.toast.warning(
                f"{lanzador['name']} está apagado o fuera de la VPN.",
                position="top-center", duration=6000,
            )
            return

        spec = SSHSpec(host=lanzador["ip"], user=lanzador["user"], os=lanzador.get("os", "linux"))
        salida = await ssh_bus.ssh_execute(spec, rdp.comando_lanzar(), timeout=15)
        async with self:
            self.console_output[host_id] = salida
            await audit.registrar(self, logs.EQUIPOS, "ESCRITORIO_REMOTO_ABIERTO",
                                  f"{host['name']} desde {lanzador['name']}")
        if "LANZADO" in salida:
            yield rx.toast.success(
                f"Escritorio remoto abierto en {lanzador['name']} — "
                f"doble clic en {host['name']} para entrar.",
                position="top-center", duration=6000,
            )
        else:
            yield rx.toast.error(
                f"No se pudo abrir en {lanzador['name']}: {salida[:180]}",
                position="top-center", duration=10000,
            )

    @rx.event
    async def download_rdp(self, host_id: str):
        """Descarga el .rdp — plan B de toda la vida, para abrirlo a mano."""
        host = nodes_store.find_host_by_id(host_id)
        problema = self._problema_rdp(host, host_id)
        if problema is not None:
            return problema
        await audit.registrar(self, logs.EQUIPOS, "ESCRITORIO_REMOTO_DESCARGADO", host["name"])
        return rdp.evento_descarga(host)

    @staticmethod
    def _problema_rdp(host: dict | None, host_id: str):
        """Toast a mostrar si no se puede ni intentar, o None si todo en orden.

        Comprobar el ping ANTES de abrir nada es lo que evita el peor caso: con
        el equipo apagado el cliente se abre igual, se queda un buen rato
        intentándolo y acaba soltando un error suyo que no distingue si falla
        la contraseña, la VPN o es que el equipo no está. El ping ya lo tenemos
        actualizado cada pocos segundos, así que sale un aviso claro al
        instante. Va en un toast y no en la consola de la ficha porque estos
        eventos se disparan también desde el widget del Resumen, donde no hay
        ninguna consola donde escribir."""
        if host is None or not (host.get("rdp_user") or "").strip() or not (host.get("ip") or "").strip():
            return rx.toast.error(
                "Este equipo no tiene escritorio remoto configurado.",
                position="top-center",
            )
        if not nodes_store.get_all_host_online().get(host_id, False):
            aviso = f"{host['name']} está apagado o sin conexión."
            if host.get("mac"):
                aviso += " Prueba a encenderlo con Wake on LAN y espera un momento."
            return rx.toast.warning(aviso, position="top-center", duration=6000)
        return None

    # ── Botones personalizados (CRUD) ────────────────────────────────────
    @rx.event
    async def submit_add_button(self, form_data: dict):
        host_id = form_data.get("host_id", "")
        label = form_data.get("label", "").strip()
        kind = form_data.get("kind", "ssh_command")
        value = form_data.get("value", "").strip()
        if not host_id or not label or not value:
            return
        nodes_store.add_host_button(host_id, label, kind, value)
        self._reload_buttons()
        await audit.registrar(self, logs.EQUIPOS, "BOTON_CREADO",
                              f"{self._nombre_equipo(host_id)}: «{label}» ({kind} = {value})")

    @rx.event
    async def delete_button(self, button_id: str):
        btn = next((b for b in self.buttons if b["id"] == button_id), None)
        nodes_store.delete_host_button(button_id)
        self._reload_buttons()
        await audit.registrar(
            self, logs.EQUIPOS, "BOTON_ELIMINADO",
            f"{self._nombre_equipo(btn['host_id'])}: «{btn['label']}»" if btn else button_id,
        )

    @rx.event(background=True)
    async def run_button(self, button_id: str):
        """El botón se resuelve dentro de operations, contra el ALMACÉN. Antes
        se buscaba en self.buttons, que solo se rellena en _reload_buttons() de
        ESTA sesión: un botón creado en otra pestaña no se podía ejecutar desde
        aquí hasta recargar la página.

        La clave de `running` es el ID DEL BOTÓN, no el del equipo: con dos
        botones en el mismo equipo, pulsar uno encendía (visto desde fuera)
        también el aro de carga del otro. Y el resultado sale por TOAST, no
        por self.console_output — esa consola está recogida por defecto y un
        resultado que nadie ve no sirve de nada."""
        btn = operations.find("host_buttons", button_id)
        if btn is None:
            return
        async with self:
            self.running[button_id] = True
        try:
            out = await operations.run_host_button(button_id)
        except operations.OperationError as e:
            out = f"ERROR: {e}"
        async with self:
            self.running[button_id] = False
        if out.startswith("ERROR"):
            yield rx.toast.error(f"{btn['label']}: {out[:200]}", position="top-center", duration=10000)
        else:
            yield rx.toast.success(f"{btn['label']}: {out[:200] or 'hecho'}",
                                   position="top-center", duration=10000)
