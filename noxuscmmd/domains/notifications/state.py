"""
Identidad de sesión (qué usuario/dispositivo push es esta pestaña) y gestión
de suscripciones. `status` (línea de estado visible en el panel) vive en
InfraState; aquí solo la actualizamos vía get_state cuando corresponde.
"""
import asyncio
import json
import os
import reflex as rx

from ..infra.state import InfraState
from ..security import audit, logs
from .push import enviar_notificacion
from . import branding, scripts, suscriptores

SUSCRIPTORES_FILE = "suscriptores.json"


class PushState(rx.State):
    current_user: str = ""
    current_session: str = ""

    # Este aparato no está vinculado y no se pudo vincular solo (falta el
    # permiso de notificaciones, que el navegador solo concede si lo pides
    # tras un toque). El panel lo usa para enseñar el aviso de "vincúlame".
    falta_vincular: bool = False

    @rx.event
    def comprobar_suscripcion(self):
        """Al entrar: mira si este navegador ya tiene suscripción push."""
        return rx.call_script(
            scripts.LEER_SUSCRIPCION,
            callback=PushState.cargar_usuario_desde_subscripcion,
        )

    # ── Nombre de la aplicación en los avisos ────────────────────────────
    nombre_app: str = ""
    guardando_nombre: bool = False

    @rx.event
    def cargar_nombre_app(self):
        self.nombre_app = branding.nombre_app()

    @rx.event
    def set_nombre_app(self, valor: str):
        self.nombre_app = valor

    @rx.event
    def guardar_nombre_app(self):
        """Escribe el nombre y regenera el manifest.

        No hay confirmación de "listo, ya lo ves": el cambio NO se ve hasta
        reinstalar el acceso directo en cada dispositivo, porque el sistema lee
        el manifest al instalarlo y no vuelve. Por eso el mensaje dice
        exactamente eso en vez de un "guardado" que haría esperar otra cosa."""
        self.nombre_app = branding.guardar(self.nombre_app)
        return rx.toast.success(
            f"Guardado: los avisos dirán «{self.nombre_app}». Para verlo en un "
            "dispositivo hay que quitar el acceso directo de su pantalla de "
            "inicio y volver a añadirlo.",
            position="top-center", duration=9000,
        )

    @rx.event
    def descartar_aviso_vincular(self):
        """Cerrar el aviso hasta la próxima visita. No se guarda en ningún
        sitio a propósito: si el aparato sigue sin vincular, la próxima vez
        vuelve a salir — es lo que hace que no se olvide para siempre."""
        self.falta_vincular = False

    @rx.event
    def suscribir(self):
        """Alta a petición — el aviso de vincular y el icono de la barra."""
        self.falta_vincular = False
        self.aviso = ""
        return rx.call_script(scripts.SUSCRIBIR, callback=PushState.guardar_subscripcion)

    # ── Gestión de este dispositivo (ventanita del icono de usuario) ──────
    # Mensaje en lenguaje llano de lo último que pasó. Se enseña dentro de la
    # ventanita en vez de en un aviso que se va solo: aquí es donde la persona
    # está mirando cuando algo sale mal, y donde están los botones para
    # arreglarlo.
    aviso: str = ""
    nombre_nuevo: str = ""

    @rx.event
    def abrir_panel(self, is_open: bool = True):
        if is_open:
            self.nombre_nuevo = self.current_user
            self.aviso = ""

    @rx.event
    def set_nombre_nuevo(self, valor: str):
        self.nombre_nuevo = valor

    @rx.event
    def renombrar(self):
        """Cambia el nombre de ESTE dispositivo.

        Los eventos ya registrados se quedan con el nombre que tenían: son un
        histórico de lo que pasó, y reescribirlos sería falsearlo. De aquí en
        adelante se apuntará con el nuevo."""
        nombre = self.nombre_nuevo.strip()
        if not nombre:
            self.aviso = "Ponle un nombre antes de guardar."
            return
        if not self.current_session:
            self.aviso = "Este dispositivo todavía no está vinculado."
            return
        ok, motivo = suscriptores.renombrar(self.current_session, nombre)
        if not ok:
            self.aviso = motivo
            return
        self.current_user = nombre
        self.aviso = f"Listo, este dispositivo se llama ahora «{nombre}»."

    @rx.event
    def reactivar(self):
        """Rehace el aviso desde cero. Para cuando dejaron de llegar: la
        suscripción caduca sola en los servidores de Apple/Google y desde
        fuera no hay forma de distinguirlo de que todo esté bien."""
        self.aviso = "Reactivando..."
        return rx.call_script(scripts.REACTIVAR, callback=PushState.guardar_subscripcion)

    @rx.event
    def desvincular(self):
        """Quita este dispositivo de la lista y suelta su aviso en el
        navegador. Deja de recibir notificaciones y sus acciones vuelven a
        registrarse sin nombre."""
        if self.current_session:
            suscriptores.eliminar(self.current_session)
        self.current_user = ""
        self.current_session = ""
        self.nombre_nuevo = ""
        self.aviso = "Dispositivo desvinculado. Ya no recibirá avisos."
        return rx.call_script(scripts.OLVIDAR)

    @rx.event
    async def cargar_usuario_desde_subscripcion(self, endpoint: str):
        """Vincula esta pestaña con el dispositivo al que pertenece.

        Importa más de lo que parece: de aquí sale el nombre que se ve arriba a
        la derecha Y el que queda escrito en cada línea del registro. Sin esto,
        todo lo que se haga desde este aparato se apunta como "desconocido".

        Si el endpoint no está en suscriptores.json —o no hay suscripción
        ninguna— se intenta dar de alta el aparato en el acto, y si el navegador
        no deja (hace falta un toque para pedir el permiso), se deja la marca
        para que el panel lo pida a la vista."""
        self.current_user = ""
        self.current_session = ""
        try:
            subs = []
            if os.path.exists(SUSCRIPTORES_FILE):
                with open(SUSCRIPTORES_FILE, "r") as f:
                    subs = json.load(f)
            for s in subs:
                if endpoint and s.get("endpoint") == endpoint:
                    self.current_user = s.get("nombre_usuario", "")
                    self.current_session = endpoint
                    self.falta_vincular = False
                    print(f"👤 Usuario cargado: {self.current_user}")
                    return
        except Exception as e:
            print(f"❌ Error cargando usuario: {e}")
            return

        print("👤 Dispositivo sin vincular — intentando darlo de alta")
        return rx.call_script(
            scripts.SUSCRIBIR_AL_ENTRAR, callback=PushState.alta_automatica,
        )

    @rx.event
    async def alta_automatica(self, js_result: str):
        """Resultado del intento de alta al entrar. Si el navegador no dejó
        pedir el permiso sin un toque, se enciende el aviso; cualquier otro
        resultado lo trata guardar_subscripcion, que ya sabe de todos los
        casos. Un "cancelar" del usuario NO enciende el aviso: si acaba de
        decir que no, insistir en la misma visita es de mal gusto."""
        if js_result in ("SIN_PERMISO", "NO_SOPORTADO"):
            self.falta_vincular = True
            return
        if js_result == "USER_CANCEL":
            return
        return PushState.guardar_subscripcion(js_result)

    # Lo que se le enseña a la persona según lo que devolvió el navegador.
    # Sin nombres de errores ni jerga: quien lee esto quiere saber qué hacer.
    _MOTIVOS = {
        "PERMISO_DENEGADO": "No has dado permiso para los avisos, así que este "
                            "dispositivo no podrá recibirlos.",
        "PERMISO_BLOQUEADO": "Los avisos están bloqueados para esta página en los "
                             "ajustes del navegador. Hay que permitirlos ahí y volver "
                             "a intentarlo.",
        "NO_SOPORTADO": "Este navegador no admite avisos. En iPhone hace falta añadir "
                        "Noxus a la pantalla de inicio y abrirlo desde ahí.",
        "USER_CANCEL": "Cancelado, no se ha cambiado nada.",
    }

    @rx.event
    async def guardar_subscripcion(self, js_result: str):
        infra = await self.get_state(InfraState)
        if js_result in self._MOTIVOS:
            self.aviso = self._MOTIVOS[js_result]
            infra.status = self.aviso
            return
        if not js_result or js_result.startswith("ERROR"):
            self.aviso = ("No se pudieron activar los avisos en este dispositivo. "
                          "Prueba a cerrar y abrir la aplicación, y si sigue igual, "
                          "quítala de la pantalla de inicio y vuelve a añadirla.")
            infra.status = self.aviso
            print(f"❌ Push: {js_result}")
            return
        try:
            data = json.loads(js_result)
            sub_dict = data.get("subscription")
            nombre_usuario = data.get("nombre", "").strip()
            if not nombre_usuario:
                infra.status = "❌ Nombre inválido"
                return rx.window_alert("Debe proporcionar un nombre para el dispositivo.")
            subs = []
            if os.path.exists(SUSCRIPTORES_FILE):
                with open(SUSCRIPTORES_FILE) as f:
                    try:
                        subs = json.load(f)
                    except Exception:
                        subs = []
            existe_endpoint = False
            existe_nombre = False
            endpoint_dup = None
            for s in subs:
                if s.get("endpoint") == sub_dict.get("endpoint"):
                    existe_endpoint = True
                    endpoint_dup = s
                    break
                if s.get("nombre_usuario") == nombre_usuario:
                    existe_nombre = True
            if existe_endpoint:
                if endpoint_dup.get("nombre_usuario") != nombre_usuario:
                    endpoint_dup["nombre_usuario"] = nombre_usuario
                    with open(SUSCRIPTORES_FILE, "w") as f:
                        json.dump(subs, f, indent=4)
                    self.current_user = nombre_usuario
                    self.current_session = sub_dict.get("endpoint", "")
                    infra.status = f"🔄 Nombre actualizado: '{nombre_usuario}'"
                    self.aviso = f"Listo, este dispositivo se llama ahora «{nombre_usuario}»."
                    return
                infra.status = "ℹ️ Ya registrado"
                self.aviso = "Este dispositivo ya estaba activado. Todo en orden."
                return
            if existe_nombre:
                infra.status = "❌ Nombre en uso"
                self.aviso = (f"Ya hay otro dispositivo llamado «{nombre_usuario}». "
                              "Ponle uno distinto para no confundirlos.")
                return
            sub_dict["nombre_usuario"] = nombre_usuario
            subs.append(sub_dict)
            with open(SUSCRIPTORES_FILE, "w") as f:
                json.dump(subs, f, indent=4)
            self.current_user = nombre_usuario
            self.current_session = sub_dict.get("endpoint", "")
            infra.status = f"🔔 Vinculado: '{nombre_usuario}'"
            self.nombre_nuevo = nombre_usuario
            self.aviso = f"Activado. Este dispositivo es «{nombre_usuario}» y ya recibe avisos."
            return
        except Exception as e:
            print(f"guardar_subscripcion error: {e}")
            infra.status = "❌ Error al vincular"
            self.aviso = "Algo falló al guardar. Inténtalo otra vez."
            return

    # ── Alerta a medida (widget "Enviar alerta" del Resumen) ─────────────
    # A diferencia de lanzar_alerta_global, aquí se elige TODO: a qué
    # dispositivo va, el título y el texto. La global manda un mensaje fijo a
    # todo el mundo y sigue estando para el botón de pánico de siempre.
    dispositivos: list[str] = []

    # A quién va la alerta. Lista VACÍA = a todos, y no es lo mismo que "nadie":
    # así el estado de partida (nada marcado) es el más útil, y no hay que
    # arrastrar una casilla "todos" que se contradiga con las de abajo.
    destinos: list[str] = []

    @rx.event
    def alternar_destino(self, nombre: str):
        self.destinos = (
            [d for d in self.destinos if d != nombre]
            if nombre in self.destinos
            else [*self.destinos, nombre]
        )

    @rx.event
    def enviar_a_todos(self):
        self.destinos = []

    @rx.var
    def destinos_ui(self) -> list[dict]:
        return [{"nombre": d, "activo": d in self.destinos} for d in self.dispositivos]

    @rx.var
    def a_todos(self) -> bool:
        return not self.destinos

    @rx.var
    def resumen_destinos(self) -> str:
        if not self.destinos:
            return "Se enviará a todos los dispositivos"
        if len(self.destinos) == 1:
            return f"Se enviará solo a {self.destinos[0]}"
        return f"Se enviará a {len(self.destinos)} dispositivos"

    @rx.event
    def refrescar_dispositivos(self, is_open: bool = True):
        """Relee los dispositivos suscritos al ABRIR el diálogo — se dan de alta
        y de baja desde otros dispositivos, así que la lista de esta sesión se
        queda vieja enseguida."""
        if not is_open:
            return
        try:
            if os.path.exists(SUSCRIPTORES_FILE):
                with open(SUSCRIPTORES_FILE) as f:
                    subs = json.load(f)
                self.dispositivos = [s["nombre_usuario"] for s in subs if s.get("nombre_usuario")]
            else:
                self.dispositivos = []
        except Exception as e:
            print(f"❌ refrescar_dispositivos: {e}")
            self.dispositivos = []

    @rx.event
    async def enviar_alerta(self, form_data: dict):
        titulo = (form_data.get("titulo") or "").strip() or "Aviso de Noxus"
        mensaje = (form_data.get("mensaje") or "").strip()
        if not mensaje:
            return rx.toast.error("Escribe el texto de la alerta.", position="top-center")

        destino = list(self.destinos) if self.destinos else "todos"
        a_quien = "todos los dispositivos" if not self.destinos else ", ".join(self.destinos)

        # En un hilo: pywebpush es bloqueante y con varios suscriptores (cada
        # uno con su timeout de 5s) dejaría el evento colgado y la UI parada.
        await asyncio.to_thread(enviar_notificacion, titulo, mensaje, destino)

        infra = await self.get_state(InfraState)
        infra.status = f"📤 Alerta enviada a {a_quien}"
        await audit.registrar(self, logs.SISTEMA, "ALERTA_ENVIADA",
                              f"a {a_quien}: «{titulo}» — {mensaje}")
        return rx.toast.success(f"Alerta enviada a {a_quien}.", position="top-center")

    @rx.event
    async def lanzar_alerta_global(self):
        asyncio.create_task(asyncio.to_thread(
            enviar_notificacion, "Notificación del Panel",
            "Alguien quiere que sepas que hay un mensaje importante.",
        ))
        infra = await self.get_state(InfraState)
        infra.status = "🆘 Alerta Global Enviada"

    @rx.event
    async def lanzar_alerta_global_con_subscripcion(self, subscription_json: str):
        sub_data = None
        if subscription_json and subscription_json != "null":
            try:
                sub_data = json.loads(subscription_json)
            except Exception:
                sub_data = None
        emisor = "Panel de Control"
        try:
            if os.path.exists(SUSCRIPTORES_FILE):
                with open(SUSCRIPTORES_FILE, "r") as f:
                    subs = json.load(f)
                if sub_data and subs:
                    endpoint_buscado = sub_data.get("endpoint")
                    for s in subs:
                        if s.get("endpoint") == endpoint_buscado:
                            emisor = s.get("nombre_usuario", "Panel de Control")
                            break
        except Exception as e:
            print(f"Error leyendo suscriptores: {e}")
            emisor = "Panel de Control"
        titulo = "📢 ¡Notificación de Seguridad!"
        mensaje = f"Alerta manual activada desde **{emisor}**. Revisa las cámaras y el estado de la casa."
        asyncio.create_task(asyncio.to_thread(enviar_notificacion, titulo, mensaje, "todos"))
        infra = await self.get_state(InfraState)
        infra.status = f"📢 Alerta enviada desde {emisor}"
