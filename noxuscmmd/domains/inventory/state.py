"""Estado del inventario. Lee de catalogo y escribe en store.

Editar una ficha pide permiso de AJUSTES: el inventario es el mapa de la
instalación —qué hay, dónde está y cómo se llega— y no es algo que deba poder
cambiar cualquiera que abra el panel.
"""
import reflex as rx

from . import catalogo, red, store
from ..auth import permisos
from ..entities import service
from ..security import audit, logs
from ...core import bus, sesiones


class InventoryState(rx.State):
    # Una lista por familia. Se guardan sueltas y no en un diccionario porque
    # rx.foreach sobre un diccionario de listas es mucho más incómodo de pintar
    # que ocho listas con nombre.
    equipos: list[dict] = []
    nodos: list[dict] = []
    sensores: list[dict] = []
    cerraderos: list[dict] = []
    luces: list[dict] = []
    camaras: list[dict] = []
    mandos: list[dict] = []
    sueltos: list[dict] = []
    estancias: list[dict] = []
    accesorios: list[dict] = []
    grupos: list[dict] = []
    automatizaciones: list[dict] = []
    carpetas: list[dict] = []
    planos: list[dict] = []
    widgets: list[dict] = []
    botones: list[dict] = []
    metricas: list[dict] = []
    voz: list[dict] = []
    alexa: list[dict] = []

    total: int = 0
    sin_documentar: int = 0
    hay_tailscale: bool = True

    # Ficha que se está editando
    editando_id: str = ""
    editando_nombre: str = ""
    ed_modelo: str = ""
    ed_ubicacion: str = ""
    ed_notas: str = ""
    ed_ip: str = ""
    ed_mac: str = ""

    # Alta de un elemento suelto
    nuevo_nombre: str = ""
    nuevo_familia: str = "red"

    @rx.event
    def on_load(self):
        self._recargar()
        yield InventoryState.sync_loop

    @rx.event(background=True)
    async def sync_loop(self):
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.ENTIDADES)
        while True:
            try:
                if not await aviso.espera(guardia, 8):
                    return
                async with self:
                    self._recargar()
            except Exception as e:
                print(f"Error en InventoryState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 8):
                    return

    def _recargar(self):
        tablas = catalogo.construir()
        self.equipos = tablas["equipos"]
        self.nodos = tablas["nodos"]
        self.sensores = tablas["sensores"]
        self.cerraderos = tablas["cerraderos"]
        self.estancias = tablas.get("estancias", [])
        self.accesorios = tablas.get("accesorios", [])
        self.grupos = tablas.get("grupos", [])
        self.automatizaciones = tablas.get("automatizaciones", [])
        self.carpetas = tablas.get("carpetas", [])
        self.planos = tablas.get("planos", [])
        self.widgets = tablas.get("widgets", [])
        self.botones = tablas.get("botones", [])
        self.metricas = tablas.get("metricas", [])
        self.voz = tablas.get("voz", [])
        self.alexa = tablas.get("alexa", [])
        self.luces = tablas["luces"]
        self.camaras = tablas["camaras"]
        self.mandos = tablas["mandos"]
        self.sueltos = tablas["sueltos"]
        self.total = sum(len(f) for f in tablas.values())
        self.sin_documentar = catalogo.sin_documentar(tablas)
        self.hay_tailscale = red.hay_tailscale()

    @rx.event
    def actualizar(self):
        """Vuelve a preguntar a la red. La tabla ARP y Tailscale se cachean 30
        s para no lanzar dos procesos por repintado; esto salta ese cacheo."""
        red.olvidar_cache()
        self._recargar()
        return rx.toast.success("Inventario actualizado.", position="top-center")

    @rx.var
    def resumen(self) -> str:
        if self.total == 0:
            return "Todavía no hay nada dado de alta."
        if self.sin_documentar == 0:
            return f"{self.total} elementos, todos con modelo o ubicación."
        return (f"{self.total} elementos · {self.sin_documentar} sin modelo ni "
                "ubicación")

    # ── Editar la ficha de un elemento ───────────────────────────────────
    @rx.event
    def abrir_ficha(self, elemento_id: str, nombre: str):
        campos = store.campos_de(elemento_id)
        self.editando_id = elemento_id
        self.editando_nombre = nombre
        self.ed_modelo = campos.get("modelo", "")
        self.ed_ubicacion = campos.get("ubicacion", "")
        self.ed_notas = campos.get("notas", "")
        self.ed_ip = campos.get("ip_manual", "")
        self.ed_mac = campos.get("mac_manual", "")

    @rx.event
    def cerrar_ficha(self):
        self.editando_id = ""

    @rx.event
    def set_ed_modelo(self, v: str):
        self.ed_modelo = v

    @rx.event
    def set_ed_ubicacion(self, v: str):
        self.ed_ubicacion = v

    @rx.event
    def set_ed_notas(self, v: str):
        self.ed_notas = v

    @rx.event
    def set_ed_ip(self, v: str):
        self.ed_ip = v

    @rx.event
    def set_ed_mac(self, v: str):
        self.ed_mac = v

    @rx.event
    async def guardar_ficha(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.editando_id:
            return
        elemento_id = self.editando_id
        nombre = self.editando_nombre
        if elemento_id.startswith("suelto_"):
            store.editar_suelto(
                elemento_id, modelo=self.ed_modelo, ubicacion=self.ed_ubicacion,
                notas=self.ed_notas, ip_manual=self.ed_ip, mac_manual=self.ed_mac,
            )
        else:
            store.guardar_campos(
                elemento_id, modelo=self.ed_modelo, ubicacion=self.ed_ubicacion,
                notas=self.ed_notas, ip_manual=self.ed_ip, mac_manual=self.ed_mac,
            )
        self.editando_id = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "INVENTARIO_EDITADO", nombre)
        return rx.toast.success(f"Ficha de {nombre} guardada.",
                                position="top-center")

    # ── Elementos que el panel no controla ───────────────────────────────
    @rx.event
    async def borrar_entidad(self, collection: str, entity_id: str, nombre: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not service.delete(collection, entity_id):
            return rx.toast.error("Esta entidad no admite borrado desde el inventario.",
                                  position="top-center")
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "ENTIDAD_ELIMINADA", nombre)
        return rx.toast.success(f"{nombre} eliminado.", position="top-center")

    @rx.event
    def set_nuevo_nombre(self, v: str):
        self.nuevo_nombre = v

    @rx.event
    def set_nuevo_familia(self, v: str):
        self.nuevo_familia = v

    @rx.event
    async def añadir_suelto(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = self.nuevo_nombre.strip()
        if not nombre:
            return rx.toast.error("Ponle un nombre.", position="top-center")
        store.añadir_suelto(nombre, self.nuevo_familia)
        self.nuevo_nombre = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "INVENTARIO_ANADIDO", nombre)
        return rx.toast.success(f"{nombre} añadido al inventario.",
                                position="top-center")

    @rx.event
    async def borrar_suelto(self, suelto_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.borrar_suelto(suelto_id)
        self._recargar()
        return rx.toast.success("Elemento quitado del inventario.",
                                position="top-center")

    @rx.event
    async def limpiar(self):
        """Quita las fichas de elementos que ya no existen."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        quitados = store.limpiar_huerfanos(catalogo.ids_vivos())
        self._recargar()
        if not quitados:
            return rx.toast.success("No había fichas sueltas que limpiar.",
                                    position="top-center")
        return rx.toast.success(
            f"{quitados} fichas de elementos que ya no existen, quitadas.",
            position="top-center")
