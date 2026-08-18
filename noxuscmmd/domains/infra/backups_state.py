"""
Estado reactivo de las copias de seguridad (pestaña Sistema).

Fino a propósito: todo lo que sabe hacer está en backups.py, que son funciones
planas y se pueden llamar desde donde sea (una automatización, un script, una
prueba). Aquí solo se traduce eso a lo que la pantalla necesita: la lista, un
mensaje y la confirmación de restaurar.
"""
import asyncio
import reflex as rx

from . import backups
from ..auth import permisos
from ..security import audit, logs


class BackupsState(rx.State):
    copias: list[dict] = []
    mensaje: str = ""
    error: bool = False
    trabajando: bool = False

    # Qué copia está esperando confirmación. Restaurar pisa la casa entera, así
    # que no puede ser un clic suelto: el diálogo enseña de cuándo es y qué
    # trae antes de dejar seguir.
    confirmando: str = ""

    @rx.event
    async def on_load(self):
        await self.recargar()

    @rx.event
    async def recargar(self):
        self.copias = await asyncio.to_thread(backups.listar)

    @rx.var
    def hay_copias(self) -> bool:
        return len(self.copias) > 0

    @rx.var
    def ultima_texto(self) -> str:
        if not self.copias:
            return "Todavía no hay ninguna copia"
        return f"Última: {self.copias[0]['fecha_texto']} · {self.copias[0]['motivo']}"

    @rx.var
    def copia_confirmada(self) -> dict:
        """La copia que se está a punto de restaurar, para que el diálogo pueda
        enseñar su fecha sin que la vista tenga que cruzar la lista."""
        for c in self.copias:
            if c["id"] == self.confirmando:
                return c
        return {}

    # ── Crear ────────────────────────────────────────────────────────────
    @rx.event
    async def crear_ahora(self):
        # Una copia lleva dentro el estado de la alarma y las tarjetas de
        # acceso: hacerla es cosa de administradores (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        self.trabajando = True
        self.mensaje = ""
        yield
        try:
            copia = await asyncio.to_thread(backups.crear, backups.MANUAL)
            await self.recargar()
            self.error = False
            self.mensaje = f"Copia guardada: {copia.get('fecha_texto', '')}"
            await audit.registrar(self, logs.SISTEMA, "COPIA_CREADA", copia.get("id", ""))
        except Exception as e:
            self.error = True
            self.mensaje = f"No se pudo hacer la copia: {e}"
        finally:
            self.trabajando = False

    # ── Restaurar ────────────────────────────────────────────────────────
    @rx.event
    def pedir_confirmacion(self, copia_id: str):
        self.confirmando = copia_id
        self.mensaje = ""

    @rx.event
    def cancelar_confirmacion(self):
        self.confirmando = ""

    @rx.event
    def confirmacion_open_change(self, abierto: bool):
        if not abierto:
            self.confirmando = ""

    @rx.event
    async def restaurar_confirmada(self):
        # Restaurar vuelve a poner el estado_seguridad.json de entonces: puede
        # desarmar la casa y resucitar un acceso ya revocado. Solo AJUSTES.
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        copia_id = self.confirmando
        if not copia_id:
            return
        self.trabajando = True
        self.confirmando = ""
        yield
        try:
            resultado = await asyncio.to_thread(backups.restaurar, copia_id)
            await self.recargar()
            self.error = False
            cuantos = len(resultado["restaurados"])
            self.mensaje = (
                f"Restaurada la copia del {copia_id}: {cuantos} ficheros. "
                f"Lo de antes quedó guardado en {resultado['copia_previa']}."
            )
            await audit.registrar(self, logs.SISTEMA, "COPIA_RESTAURADA", copia_id)
        except Exception as e:
            self.error = True
            self.mensaje = f"No se restauró nada: {e}"
        finally:
            self.trabajando = False
