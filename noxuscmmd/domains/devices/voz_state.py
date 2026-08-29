"""
Estado de la pantalla «Alexa y voz» (Ajustes).

Aquí se atan frases a acciones: «buenas noches» → «Poner la casa en Noche». Es lo
que hace que el reconocimiento sea EXACTO en vez de por parecido, y por eso se
consultan primero (ver devices/comandos.por_frase_guardada): «buenas noches» no se
parece a ningún comando del catálogo y aun así es lo que uno le dice al altavoz.

La Skill oficial de Alexa usa el catálogo manual independiente que vive en este
mismo State. Las frases descritas arriba son opcionales y solo pertenecen al
endpoint local/Siri; no participan en Alexa Cloud.

También se saca de aquí la CLAVE que necesita el atajo del móvil. Es una sesión
firmada normal (auth/sessions.py), lo que significa tres cosas que importan:
hereda los permisos del dispositivo que la creó, caduca sola, y se revoca
cambiándole el rol a ese dispositivo — sin inventar un segundo sistema de llaves
que luego nadie recuerda cómo se cierra.
"""
import reflex as rx

from . import comandos
from . import alexa_catalog_store, alexa_cloud_store, alexa_cloud_sync
from .voz import DIAS_CLAVE
from ..auth import permisos, sessions
from ..nodes import store as nodes_store
from ..security import audit, logs


class VozState(rx.State):
    guardados: list[dict] = []
    catalogo: list[dict] = []

    nueva_frase: str = ""
    nuevo_comando: str = ""

    # La clave recién generada. NO se guarda en ningún sitio: se enseña una vez
    # para copiarla y se olvida. Si se pierde, se genera otra — es lo mismo que
    # hace cualquier sitio serio con una llave de API, y evita tener un fichero
    # con llaves válidas dentro.
    clave: str = ""
    alexa_event_client_id: str = ""
    alexa_event_client_secret: str = ""
    alexa_codigo_enlace: str = ""
    alexa_ultimo_estado: str = ""

    # Catálogo que la Skill oficial publica. No se rellena desde luces ni
    # equipos: cada ficha existe únicamente porque el propietario la creó.
    alexa_elementos: list[dict] = []
    alexa_catalogo: list[dict] = []
    alexa_error: str = ""

    # Borrador común para alta y edición.
    alexa_editando: str = ""
    # Al abrir el constructor de secuencias se desmonta temporalmente el
    # diálogo. Esta marca impide que su on_open_change interprete el desmontaje
    # como «Cancelar» y borre el borrador que debe reaparecer al volver.
    alexa_editor_suspendido: bool = False
    alexa_secuencia_slot: str = "action"
    alexa_nombre: str = ""
    alexa_comportamiento: str = "power"
    alexa_categoria: str = "SWITCH"
    alexa_on_command: str = ""
    alexa_off_command: str = ""
    alexa_action_command: str = ""
    alexa_scene_operation: str = "activate"
    alexa_on_label: str = ""
    alexa_off_label: str = ""
    alexa_action_label: str = ""
    alexa_repeticiones: str = "1"
    alexa_pausa: str = "0.4"

    # Selector buscable compartido por las tres ranuras de acción.
    alexa_picker_slot: str = ""
    alexa_picker_query: str = ""

    @rx.event
    def on_load(self):
        self._recargar()

    def _recargar(self) -> None:
        todos = comandos.comandos()
        por_id = {c["id"]: c for c in todos}
        self.catalogo = [
            {"id": c["id"], "etiqueta": f"{c['familia']} · {c['etiqueta']}"}
            for c in todos
            # Las de «Ir a» no se ofrecen: cambiar de pestaña no significa nada
            # cuando le hablas a un altavoz, no hay pantalla delante.
            if c["familia"] != "Ir a"
        ]
        self.guardados = [
            {
                "id": g["id"],
                "frase": g["frase"],
                "comando": g.get("comando", ""),
                # Preformateado, y con el aviso puesto si la acción ya no existe
                # (se borró la luz, el mando...). Una frase que apunta al vacío
                # tiene que decirlo, no fallar el día que alguien la diga.
                "etiqueta": (por_id[g["comando"]]["etiqueta"]
                             if g.get("comando") in por_id
                             else "⚠ esa acción ya no existe"),
            }
            for g in nodes_store.list_comandos_voz()
        ]
        if not self.nuevo_comando and self.catalogo:
            self.nuevo_comando = self.catalogo[0]["id"]
        diagnostico = alexa_cloud_store.diagnostico()
        self.alexa_ultimo_estado = str(diagnostico.get("detalle") or "")
        permitidos = [c for c in todos if c.get("alexa_allowed", False)]
        self.alexa_catalogo = [
            {"id": c["id"], "etiqueta": c["etiqueta"],
             "familia": c["familia"], "icono": c.get("icono") or "zap",
             "paso_type": c.get("paso", {}).get("type", "")}
            for c in permitidos
        ]
        etiquetas = {c["id"]: c["etiqueta"] for c in permitidos}
        try:
            fichas = alexa_catalog_store.listar()
            self.alexa_error = ""
        except alexa_catalog_store.ArchivoCorrupto as error:
            fichas = []
            self.alexa_error = str(error)
        self.alexa_elementos = []
        for item in fichas:
            es_accion = item.get("behavior") == "action"
            if es_accion:
                command = str(item.get("command") or "")
                scene_operation = str(
                    item.get("scene_operation") or "activate")
                etiqueta = etiquetas.get(command, "⚠ esa acción ya no existe")
                veces = int(item.get("repeat", 1) or 1)
                detalle = etiqueta + (f" · {veces} veces" if veces > 1 else "")
                tipo = "Acción"
                nombre = item.get("name", "")
                if scene_operation == "deactivate":
                    frase = (f"Alexa, apaga {nombre} · "
                             f"Alexa, desactiva {nombre}")
                else:
                    frase = (f"Alexa, enciende {nombre} · "
                             f"Alexa, activa {nombre}")
                rota = command not in etiquetas
            else:
                on_command = str(item.get("on_command") or "")
                off_command = str(item.get("off_command") or "")
                on_label = etiquetas.get(on_command, "⚠ acción ON inexistente")
                off_label = etiquetas.get(off_command, "⚠ acción OFF inexistente")
                detalle = f"ON: {on_label} · OFF: {off_label}"
                tipo = "Dispositivo"
                frase = (f"Alexa, enciende {item.get('name', '')} · "
                         f"Alexa, apaga {item.get('name', '')}")
                rota = on_command not in etiquetas or off_command not in etiquetas
            self.alexa_elementos.append({
                "id": str(item.get("id") or ""),
                "nombre": str(item.get("name") or ""),
                "tipo": tipo,
                "categoria": str(item.get("category") or ""),
                "detalle": detalle,
                "frase": frase,
                "rota": rota,
            })

    # Buscador del diálogo "Crear un atajo": filtra self.catalogo, que ya vive
    # aquí para el desplegable de "Frases exactas" — un segundo catálogo
    # sería la misma lista dos veces, solo que una de ellas desincronizándose.
    atajo_busqueda: str = ""

    @rx.var
    def catalogo_filtrado(self) -> list[dict]:
        q = comandos.plano(self.atajo_busqueda)
        if not q:
            return self.catalogo
        return [c for c in self.catalogo if q in comandos.plano(c["etiqueta"])]

    @rx.event
    def set_atajo_busqueda(self, valor: str):
        self.atajo_busqueda = valor

    @rx.event
    def set_nueva_frase(self, valor: str):
        self.nueva_frase = valor

    @rx.event
    def set_nuevo_comando(self, valor: str):
        self.nuevo_comando = valor

    @rx.event
    def set_alexa_event_client_id(self, valor: str):
        self.alexa_event_client_id = valor

    @rx.event
    def set_alexa_event_client_secret(self, valor: str):
        self.alexa_event_client_secret = valor

    @rx.event
    def set_alexa_nombre(self, valor: str):
        self.alexa_nombre = valor

    @rx.event
    def set_alexa_comportamiento(self, valor: str):
        self.alexa_comportamiento = valor
        if valor == "power" and self.alexa_categoria == "ACTIVITY_TRIGGER":
            self.alexa_categoria = "SWITCH"

    @rx.event
    def set_alexa_categoria(self, valor: str):
        self.alexa_categoria = valor

    @rx.event
    def set_alexa_scene_operation(self, valor: str):
        self.alexa_scene_operation = valor

    @rx.event
    def set_alexa_repeticiones(self, valor: str):
        self.alexa_repeticiones = valor

    @rx.event
    def set_alexa_pausa(self, valor: str):
        self.alexa_pausa = valor

    def _etiqueta_alexa(self, comando_id: str) -> str:
        return next((c["etiqueta"] for c in self.alexa_catalogo
                     if c["id"] == comando_id), "⚠ esa acción ya no existe")

    @rx.event
    def nuevo_alexa(self):
        self.alexa_editor_suspendido = False
        self.alexa_editando = "nuevo"
        self.alexa_nombre = ""
        self.alexa_comportamiento = "power"
        self.alexa_categoria = "SWITCH"
        self.alexa_on_command = ""
        self.alexa_off_command = ""
        self.alexa_action_command = ""
        self.alexa_scene_operation = "activate"
        self.alexa_on_label = ""
        self.alexa_off_label = ""
        self.alexa_action_label = ""
        self.alexa_repeticiones = "1"
        self.alexa_pausa = "0.4"

    @rx.event
    def editar_alexa(self, endpoint_id: str):
        try:
            item = alexa_catalog_store.obtener(endpoint_id)
        except alexa_catalog_store.ArchivoCorrupto:
            item = None
        if item is None:
            return rx.toast.error("Ese elemento de Alexa ya no existe.",
                                  position="top-center")
        self.alexa_editor_suspendido = False
        self.alexa_editando = endpoint_id
        self.alexa_nombre = str(item.get("name") or "")
        self.alexa_comportamiento = str(item.get("behavior") or "power")
        self.alexa_categoria = str(item.get("category") or "SWITCH")
        self.alexa_on_command = str(item.get("on_command") or "")
        self.alexa_off_command = str(item.get("off_command") or "")
        self.alexa_action_command = str(item.get("command") or "")
        self.alexa_scene_operation = str(
            item.get("scene_operation") or "activate")
        self.alexa_on_label = self._etiqueta_alexa(self.alexa_on_command)
        self.alexa_off_label = self._etiqueta_alexa(self.alexa_off_command)
        self.alexa_action_label = self._etiqueta_alexa(self.alexa_action_command)
        self.alexa_repeticiones = str(item.get("repeat", 1))
        self.alexa_pausa = str(item.get("repeat_pause", 0.4))

    @rx.event
    def cerrar_editor_alexa(self):
        self.alexa_editando = ""
        self.alexa_editor_suspendido = False
        self.alexa_picker_slot = ""

    @rx.event
    def alexa_editor_open_change(self, abierto: bool):
        """Escape/clic fuera cierran; navegar al editor de secuencias no."""
        if not abierto and not self.alexa_editor_suspendido:
            self.alexa_editando = ""
            self.alexa_picker_slot = ""

    def suspender_editor_alexa(self, slot: str = "action") -> None:
        self.alexa_editor_suspendido = True
        self.alexa_secuencia_slot = slot if slot in {"on", "off", "action"} else "action"
        self.alexa_picker_slot = ""

    def reanudar_con_secuencia(self, rule_id: str) -> bool:
        """Recarga el catálogo y selecciona la regla recién creada."""
        self._recargar()
        comando_id = f"regla:{rule_id}"
        elegido = next((c for c in self.alexa_catalogo
                        if c["id"] == comando_id), None)
        if elegido is None:
            self.alexa_error = (
                "La secuencia se guardó, pero contiene una acción no compatible "
                "con Alexa. Revísala en Automatizaciones."
            )
            return False
        if self.alexa_secuencia_slot == "on":
            self.alexa_on_command = comando_id
            self.alexa_on_label = elegido["etiqueta"]
        elif self.alexa_secuencia_slot == "off":
            self.alexa_off_command = comando_id
            self.alexa_off_label = elegido["etiqueta"]
        else:
            self.alexa_comportamiento = "action"
            self.alexa_action_command = comando_id
            self.alexa_action_label = elegido["etiqueta"]
        self.alexa_editor_suspendido = False
        return True

    def reanudar_editor_alexa(self) -> None:
        self.alexa_editor_suspendido = False

    @rx.event
    def abrir_picker_alexa(self, slot: str):
        self.alexa_picker_query = ""
        self.alexa_picker_slot = slot

    @rx.event
    def cerrar_picker_alexa(self):
        self.alexa_picker_slot = ""

    @rx.event
    def picker_alexa_open_change(self, abierto: bool):
        if not abierto:
            self.alexa_picker_slot = ""

    @rx.event
    def set_alexa_picker_query(self, valor: str):
        self.alexa_picker_query = valor

    @rx.event
    def elegir_accion_alexa(self, comando_id: str):
        etiqueta = self._etiqueta_alexa(comando_id)
        if self.alexa_picker_slot == "on":
            self.alexa_on_command, self.alexa_on_label = comando_id, etiqueta
        elif self.alexa_picker_slot == "off":
            self.alexa_off_command, self.alexa_off_label = comando_id, etiqueta
        elif self.alexa_picker_slot == "action":
            self.alexa_action_command, self.alexa_action_label = comando_id, etiqueta
        self.alexa_picker_slot = ""

    @rx.event
    async def guardar_elemento_alexa(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        campos = {
            "name": self.alexa_nombre,
            "behavior": self.alexa_comportamiento,
            "category": self.alexa_categoria,
            "on_command": self.alexa_on_command,
            "off_command": self.alexa_off_command,
            "command": self.alexa_action_command,
            "scene_operation": self.alexa_scene_operation,
            "repeat": self.alexa_repeticiones,
            "repeat_pause": self.alexa_pausa,
        }
        try:
            if self.alexa_editando == "nuevo":
                item = alexa_catalog_store.añadir(**campos)
                accion = "ALEXA_ELEMENTO_CREADO"
            else:
                item = alexa_catalog_store.editar(self.alexa_editando, **campos)
                accion = "ALEXA_ELEMENTO_EDITADO"
            if item is None:
                return rx.toast.error("Ese elemento ya no existe.",
                                      position="top-center")
        except (alexa_catalog_store.CatalogoAlexaError,
                alexa_catalog_store.ArchivoCorrupto) as error:
            return rx.toast.error(str(error), position="top-center", duration=7000)
        self.alexa_editando = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, accion, item["name"])
        return rx.toast.success(
            f"{item['name']} guardado. Se sincronizará automáticamente con Alexa.",
            position="top-center", duration=5000)

    @rx.event
    async def borrar_elemento_alexa(self, endpoint_id: str, nombre: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        try:
            borrado = alexa_catalog_store.borrar(endpoint_id)
        except alexa_catalog_store.ArchivoCorrupto as error:
            return rx.toast.error(str(error), position="top-center", duration=7000)
        if not borrado:
            return rx.toast.error("Ese elemento ya no existe.", position="top-center")
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "ALEXA_ELEMENTO_ELIMINADO", nombre)
        return rx.toast.success(
            f"{nombre} eliminado. Alexa recibirá la baja automáticamente.",
            position="top-center")

    @rx.event
    async def refrescar_alexa_cloud(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self._recargar()

    @rx.event
    async def guardar_alexa_eventos(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not alexa_cloud_sync.guardar_credenciales(
                self.alexa_event_client_id, self.alexa_event_client_secret):
            return rx.toast.error("Pega el Client ID y el Client Secret de Alexa.",
                                  position="top-center")
        self.alexa_event_client_id = ""
        self.alexa_event_client_secret = ""
        await audit.registrar(self, logs.SISTEMA, "ALEXA_EVENTOS_CONFIGURADOS",
                              "credenciales de Event Gateway guardadas")
        return rx.toast.success("Alexa Events configurado.", position="top-center")

    @rx.event
    async def generar_codigo_alexa(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        from ..auth.state import AuthState
        auth = await self.get_state(AuthState)
        if not auth._id:
            return rx.toast.error("Este dispositivo no está identificado.",
                                  position="top-center")
        self.alexa_codigo_enlace = alexa_cloud_store.emitir_autorizacion(auth._id)
        await audit.registrar(self, logs.ACCESOS, "ALEXA_ENLACE_SOLICITADO",
                              "código temporal generado")

    @rx.event
    def ocultar_codigo_alexa(self):
        self.alexa_codigo_enlace = ""

    @rx.event
    async def anadir(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        frase = self.nueva_frase.strip()
        if len(frase) < 3:
            return rx.toast.error("Escribe la frase que vas a decir.",
                                  position="top-center")
        if not self.nuevo_comando:
            return rx.toast.error("Elige qué tiene que hacer.",
                                  position="top-center")
        creado = nodes_store.add_comando_voz(frase, self.nuevo_comando)
        if creado is None:
            return rx.toast.error(f"Ya tienes una frase «{frase.lower()}».",
                                  position="top-center")
        self.nueva_frase = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "COMANDO_VOZ_CREADO",
                              f"«{creado['frase']}»")

    @rx.event
    async def borrar(self, voz_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        frase = next((g["frase"] for g in self.guardados if g["id"] == voz_id),
                     voz_id)
        nodes_store.delete_comando_voz(voz_id)
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "COMANDO_VOZ_ELIMINADO",
                              f"«{frase}»")

    @rx.event
    async def cambiar_accion(self, voz_id: str, comando: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.update_comando_voz(voz_id, comando=comando)
        self._recargar()

    @rx.event
    async def generar_clave(self):
        """Una clave nueva para este dispositivo.

        La anterior sigue valiendo hasta que caduque: no se «rota» nada, porque
        invalidar la que ya está metida en un atajo que funciona, sin avisar, es
        peor que tener dos claves buenas. Para cortar el acceso de verdad se le
        cambia el rol al dispositivo."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        from ..auth.state import AuthState
        auth = await self.get_state(AuthState)
        # El id se lee del State de la sesión, no de un parámetro: así una clave
        # solo se puede emitir para el aparato que la está pidiendo.
        if not auth._id:
            return rx.toast.error("Este dispositivo no está identificado.",
                                  position="top-center")
        self.clave = sessions.emitir_voz(auth._id, duracion=DIAS_CLAVE * 86400)
        await audit.registrar(self, logs.ACCESOS, "CLAVE_VOZ_CREADA",
                              f"válida {DIAS_CLAVE} días")

    @rx.event
    def olvidar_clave(self):
        """Quita la clave de la pantalla. No la invalida: solo deja de estar a
        la vista de quien pase por delante del ordenador."""
        self.clave = ""

    @rx.var
    def hay_clave(self) -> bool:
        return self.clave != ""

    @rx.var
    def hay_guardados(self) -> bool:
        return len(self.guardados) > 0

    @rx.var
    def alexa_eventos_configurados(self) -> bool:
        return alexa_cloud_sync.eventos_configurados()

    @rx.var
    def hay_codigo_alexa(self) -> bool:
        return self.alexa_codigo_enlace != ""

    @rx.var
    def hay_elementos_alexa(self) -> bool:
        return len(self.alexa_elementos) > 0

    @rx.var
    def editor_alexa_abierto(self) -> bool:
        return self.alexa_editando != "" and not self.alexa_editor_suspendido

    @rx.var
    def alexa_es_accion(self) -> bool:
        return self.alexa_comportamiento == "action"

    @rx.var
    def alexa_nombre_visible(self) -> str:
        """Nombre usado en las ayudas del editor mientras el campo está vacío."""
        return self.alexa_nombre.strip() or "<nombre>"

    @rx.var
    def alexa_frase_encender(self) -> str:
        return f"Alexa, enciende {self.alexa_nombre_visible}"

    @rx.var
    def alexa_frase_apagar(self) -> str:
        return f"Alexa, apaga {self.alexa_nombre_visible}"

    @rx.var
    def alexa_frase_activar(self) -> str:
        return f"Alexa, activa {self.alexa_nombre_visible}"

    @rx.var
    def alexa_frase_desactivar(self) -> str:
        return f"Alexa, desactiva {self.alexa_nombre_visible}"

    @rx.var
    def alexa_accion_es_desactivar(self) -> bool:
        return (self.alexa_comportamiento == "action" and
                self.alexa_scene_operation == "deactivate")

    @rx.var
    def alexa_frase_accion_principal(self) -> str:
        if self.alexa_accion_es_desactivar:
            return self.alexa_frase_apagar
        return self.alexa_frase_encender

    @rx.var
    def alexa_frase_accion_alternativa(self) -> str:
        if self.alexa_accion_es_desactivar:
            return self.alexa_frase_desactivar
        return self.alexa_frase_activar

    @rx.var
    def alexa_nombre_power_con_verbo(self) -> bool:
        """Detecta el error común de guardar el verbo dentro del nombre."""
        nombre = self.alexa_nombre.lstrip().casefold()
        return (self.alexa_comportamiento == "power" and
                nombre.startswith(("enciende ", "apaga ")))

    @rx.var
    def alexa_nombre_accion_con_verbo(self) -> bool:
        """En escenas el verbo también lo aporta Alexa, no el nombre."""
        nombre = self.alexa_nombre.lstrip().casefold()
        return (self.alexa_comportamiento == "action" and
                nombre.startswith(("enciende ", "activa ", "apaga ",
                                    "desactiva ")))

    @rx.var
    def picker_alexa_abierto(self) -> bool:
        return self.alexa_picker_slot != ""

    @rx.var
    def alexa_picker_title(self) -> str:
        return {"on": "Acción al encender", "off": "Acción al apagar",
                "action": "Acción que ejecutará Alexa"}.get(
                    self.alexa_picker_slot, "Elegir acción")

    @rx.var
    def alexa_picker_sections(self) -> list[dict]:
        busca = self.alexa_picker_query.strip().lower()
        secciones: list[dict] = []
        for comando in self.alexa_catalogo:
            if (self.alexa_picker_slot in {"on", "off"} and
                    comando["paso_type"] not in {
                        "light.set", "ir_button.press", "host.wol", "host.action",
                        # Una secuencia manual permite que «apaga Habitación»
                        # apague TV, PC, ventilador y luces de una sola vez.
                        "rule.run",
                    }):
                continue
            if busca and busca not in comando["etiqueta"].lower() and busca not in comando["familia"].lower():
                continue
            seccion = next((s for s in secciones if s["label"] == comando["familia"]), None)
            if seccion is None:
                seccion = {"label": comando["familia"], "icon": comando["icono"],
                           "options": []}
                secciones.append(seccion)
            seccion["options"].append({"label": comando["etiqueta"],
                                        "value": comando["id"]})
        return secciones
