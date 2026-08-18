"""
Estado de la pantalla «Comandos de voz» (Ajustes).

Aquí se atan frases a acciones: «buenas noches» → «Poner la casa en Noche». Es lo
que hace que el reconocimiento sea EXACTO en vez de por parecido, y por eso se
consultan primero (ver devices/comandos.por_frase_guardada): «buenas noches» no se
parece a ningún comando del catálogo y aun así es lo que uno le dice al altavoz.

También se saca de aquí la CLAVE que necesita el atajo del móvil. Es una sesión
firmada normal (auth/sessions.py), lo que significa tres cosas que importan:
hereda los permisos del dispositivo que la creó, caduca sola, y se revoca
cambiándole el rol a ese dispositivo — sin inventar un segundo sistema de llaves
que luego nadie recuerda cómo se cierra.
"""
import reflex as rx

from . import comandos
from ..auth import permisos, sessions
from ..nodes import store as nodes_store
from ..security import audit, logs

# Cuánto vale la clave de voz. Un año: es para dejar montado un atajo, no para
# una sesión de navegador. Se revoca cambiando el rol del dispositivo.
DIAS_CLAVE = 365


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

    @rx.event
    def set_nueva_frase(self, valor: str):
        self.nueva_frase = valor

    @rx.event
    def set_nuevo_comando(self, valor: str):
        self.nuevo_comando = valor

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
