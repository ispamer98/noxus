"""Entrada y estado efímero de la pantalla fija de una estancia."""
import asyncio

import reflex as rx

from ..auth import permisos, store as auth_store


class KioscoState(rx.State):
    overlay_kind: str = ""
    overlay_id: str = ""
    plano_ampliado: bool = False
    plano_colapsado: bool = False

    # Mural de cámaras: el reparto y las cámaras de cada hueco se guardan en la
    # ficha de la estancia (nodes/store.py: get_room_mural / set_room_mural).
    # Sirena: la tablet suena si salta la alarma. Su configuración vive en la
    # ficha de la estancia y llega por NodesState.kiosco_sirena (así también la
    # controla la pestaña Estancias); aquí solo está si el panel está abierto.
    sirena_ajustes: bool = False

    mural_abierto: bool = False
    mural_layout: str = "4"
    mural_elegir: str = ""
    mural_celdas: list[dict] = []
    mural_catalogo: list[dict] = []
    _mural_slots: dict[str, str] = {}
    _mural_visibles: list[str] = []
    _mural_nonce: dict[str, int] = {}
    _mural_camaras: dict[str, dict] = {}

    @rx.event
    async def entrar(self):
        """Carga solo lo que usa el kiosco y corta antes de exponer la casa."""
        from ...core.entrada import ejecutar_eventos_entrada
        from ..auth.state import AuthState
        from .state import NodesState
        from ...ui.pages.kiosco import (
            EVENTOS_KIOSCO, EVENTOS_KIOSCO_IDENTIFICACION,
        )

        para_cliente = await ejecutar_eventos_entrada(
            self, EVENTOS_KIOSCO_IDENTIFICACION)
        auth = await self.get_state(AuthState)
        nodes = await self.get_state(NodesState)
        eid = str(self.router.page.params.get("eid", ""))

        if auth._rol == auth_store.KIOSCO:
            propia = auth_store.estancia_kiosco(auth._id)
            if not propia:
                nodes._vaciar_kiosco()
                return para_cliente
            if eid != propia:
                nodes._vaciar_kiosco()
                return para_cliente + [rx.redirect(f"/estancia/{propia}")]
        if not auth._ve(permisos.VER):
            nodes._vaciar_kiosco()
            return para_cliente

        resto = EVENTOS_KIOSCO[len(EVENTOS_KIOSCO_IDENTIFICACION):]
        para_cliente += await ejecutar_eventos_entrada(self, resto)
        if not nodes._abrir_estancia(eid):
            nodes._vaciar_kiosco()
            return para_cliente

        # Los marcadores integrados leen su posición desde RegistryState.
        from ..devices.registry_state import RegistryState
        registry = await self.get_state(RegistryState)
        registry.cargar_plano(nodes.plano_actual)
        from . import store as nodes_store
        if (nodes_store.get_room_mural(eid)["activo"]
                and auth._ve(permisos.CAMARAS)):
            para_cliente.append(KioscoState.abrir_mural)
        return para_cliente

    @rx.event
    def abrir_overlay(self, clase: str, entity_id: str):
        if clase not in {"mando", "equipo", "camara"}:
            return
        self.overlay_kind = clase
        self.overlay_id = entity_id

    @rx.event
    def cerrar_overlay(self):
        self.overlay_kind = ""
        self.overlay_id = ""

    @rx.event
    def ampliar_plano(self):
        self.plano_ampliado = True
        self.plano_colapsado = False

    @rx.event
    def cerrar_plano(self):
        self.plano_ampliado = False

    @rx.event
    def alternar_plano_colapsado(self):
        self.plano_colapsado = not self.plano_colapsado

    # ── Mural de cámaras ──────────────────────────────────────────────────────
    # Cualquier cámara del sistema, no solo las de la estancia: sirve para mirar
    # fuera de la habitación. Cada evento exige CAMARAS (una tablet solo la tiene
    # si un administrador se lo concedió) y valida hueco y cámara en el servidor.
    async def _sala_mural(self) -> str:
        from .state import NodesState
        return (await self.get_state(NodesState)).kiosco_room_id

    def _mural_pintar(self) -> None:
        celdas = []
        for i in range(int(self.mural_layout)):
            hueco = str(i)
            cam = self._mural_camaras.get(self._mural_slots.get(hueco, ""))
            if not cam:
                celdas.append({"slot": hueco, "vacia": True, "nombre": "",
                               "url": "", "jugable": True, "visible": False})
                continue
            url = cam["stream_url"]
            if cam["playable"]:
                url += ("&" if "?" in url else "?") + f"_r={self._mural_nonce.get(hueco, 0)}"
            celdas.append({"slot": hueco, "vacia": False, "nombre": cam["name"],
                           "url": url, "jugable": bool(cam["playable"]),
                           "visible": hueco in self._mural_visibles})
        self.mural_celdas = celdas

    def _mural_guardar(self, sala: str) -> None:
        from . import store as nodes_store
        nodes_store.set_room_mural(sala, self.mural_layout, self._mural_slots,
                                   self.mural_abierto)

    @rx.event
    async def abrir_mural(self):
        from ...domains.cameras import wall
        from . import store as nodes_store
        if (no := await permisos.denegar(self, permisos.CAMARAS)):
            return no
        sala = await self._sala_mural()
        if not sala:
            return
        # «mobile»: sin WebRTC (UDP), que no atraviesa el VPS; MSE/HLS sí.
        self._mural_camaras = {c["id"]: c for c in wall.catalogo_camaras("mobile")}
        self.mural_catalogo = [{"id": c["id"], "name": c["name"], "icon": c["icon"]}
                               for c in self._mural_camaras.values()]
        guardado = nodes_store.get_room_mural(sala)
        self.mural_layout = guardado["layout"]
        self._mural_slots = {k: v for k, v in guardado["slots"].items()
                             if v in self._mural_camaras}
        self._mural_visibles = []
        self._mural_nonce = {}
        self.mural_elegir = ""
        self.mural_abierto = True
        self._mural_pintar()
        self._mural_guardar(sala)
        return KioscoState.mural_revelar

    @rx.event
    async def cerrar_mural(self):
        self.mural_abierto = False
        self.mural_elegir = ""
        self.mural_celdas = []
        self._mural_visibles = []
        sala = await self._sala_mural()
        if sala:
            self._mural_guardar(sala)

    @rx.event
    async def alternar_mural(self):
        if self.mural_abierto:
            return KioscoState.cerrar_mural
        return KioscoState.abrir_mural

    @rx.event(background=True)
    async def mural_revelar(self):
        """Abre las cámaras una a una: cada cámara Tuya pide un token a su nube y
        varias a la vez topan con su límite de peticiones (ver
        cameras/wall_state.reveal_gradually, que hace lo mismo con el Mural)."""
        from ...domains.cameras.wall_state import _ESPERA_ESCALONADO, VideoWallState
        async with self:
            if not self.mural_abierto:
                return
            pendientes = [(h, self._mural_slots[h]) for h in self._mural_slots
                          if h not in self._mural_visibles]
            camaras = dict(self._mural_camaras)
        for i, (hueco, cid) in enumerate(pendientes):
            if i:
                await asyncio.sleep(_ESPERA_ESCALONADO)
            await VideoWallState._calentar(camaras.get(cid))
            async with self:
                if not self.mural_abierto:
                    return
                if hueco not in self._mural_visibles:
                    self._mural_visibles = [*self._mural_visibles, hueco]
                    self._mural_pintar()

    @rx.event
    async def mural_repartir(self, reparto: str):
        from . import store as nodes_store
        if reparto not in nodes_store.MURAL_ESTANCIA_REPARTOS:
            return
        if (no := await permisos.denegar(self, permisos.CAMARAS)):
            return no
        sala = await self._sala_mural()
        if not sala or not self.mural_abierto:
            return
        self.mural_layout = reparto
        self._mural_slots = {k: v for k, v in self._mural_slots.items()
                             if int(k) < int(reparto)}
        self._mural_visibles = [h for h in self._mural_visibles if h in self._mural_slots]
        self.mural_elegir = ""
        self._mural_guardar(sala)
        self._mural_pintar()
        return KioscoState.mural_revelar

    @rx.event
    def mural_elegir_hueco(self, hueco: str):
        if self.mural_abierto and hueco in {c["slot"] for c in self.mural_celdas}:
            self.mural_elegir = hueco

    @rx.event
    def mural_cancelar(self):
        self.mural_elegir = ""

    @rx.event
    async def mural_poner(self, camara_id: str):
        hueco = self.mural_elegir
        if (not self.mural_abierto or not hueco
                or camara_id not in self._mural_camaras):
            return
        if (no := await permisos.denegar(self, permisos.CAMARAS)):
            return no
        sala = await self._sala_mural()
        if not sala:
            return
        # Una cámara solo va en un hueco: si estaba en otro, se mueve.
        self._mural_slots = {k: v for k, v in self._mural_slots.items()
                             if v != camara_id}
        self._mural_slots = {**self._mural_slots, hueco: camara_id}
        self._mural_visibles = [h for h in self._mural_visibles
                                if h in self._mural_slots and h != hueco] + [hueco]
        self.mural_elegir = ""
        self._mural_guardar(sala)
        self._mural_pintar()

    @rx.event
    async def mural_quitar(self, hueco: str):
        if not self.mural_abierto or hueco not in self._mural_slots:
            return
        if (no := await permisos.denegar(self, permisos.CAMARAS)):
            return no
        sala = await self._sala_mural()
        if not sala:
            return
        self._mural_slots = {k: v for k, v in self._mural_slots.items() if k != hueco}
        self._mural_visibles = [h for h in self._mural_visibles if h != hueco]
        self._mural_guardar(sala)
        self._mural_pintar()

    @rx.event
    def mural_recargar(self, hueco: str):
        if self.mural_abierto and hueco in self._mural_slots:
            self._mural_nonce = {**self._mural_nonce,
                                 hueco: self._mural_nonce.get(hueco, 0) + 1}
            self._mural_pintar()

    # ── Sirena ────────────────────────────────────────────────────────────────
    async def _sirena_guardar(self, **cambios) -> None:
        from . import store as nodes_store
        from .state import NodesState
        sala = await self._sala_mural()
        if not sala:
            return
        actual = nodes_store.get_room_sirena(sala)
        actual.update(cambios)
        nodes_store.set_room_sirena(sala, actual["activa"], actual["sonido"],
                                    actual["volumen"])
        (await self.get_state(NodesState))._refrescar(nodes_store.read_all())

    @rx.event
    def abrir_sirena_ajustes(self):
        self.sirena_ajustes = True

    @rx.event
    def cerrar_sirena_ajustes(self):
        self.sirena_ajustes = False

    @rx.event
    async def alternar_sirena(self):
        from . import store as nodes_store
        sala = await self._sala_mural()
        if sala:
            await self._sirena_guardar(
                activa=not nodes_store.get_room_sirena(sala)["activa"])

    @rx.event
    async def elegir_sonido(self, sonido: str):
        from . import store as nodes_store
        if sonido in nodes_store.SIRENA_SONIDOS:
            await self._sirena_guardar(sonido=sonido)

    @rx.event
    async def elegir_volumen(self, volumen: str):
        from . import store as nodes_store
        if volumen in nodes_store.SIRENA_VOLUMENES:
            await self._sirena_guardar(volumen=volumen)
