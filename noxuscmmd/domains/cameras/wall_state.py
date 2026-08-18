"""
Estado del Mural de vídeo: una única rejilla persistente de cámaras en vivo,
al estilo de un visor de NVR (HikCentral y compañía) — eliges un reparto
(1/4/6/8/9/16), colocas una cámara en cada hueco y se queda así entre
visitas.

La colocación es POR TOQUE, no por arrastre: esta versión de Reflex no
expone los eventos nativos de arrastrar-soltar del navegador sobre elementos
normales (comprobado — `Div` no admite `on_drop`/`on_drag_start`), y
replicarlo a mano con JavaScript propio —como hace el plano de planta para
su arrastre— sería una pieza grande y, sobre todo, NO funcionaría en
móvil (el arrastre HTML5 apenas responde al dedo). Tocar un hueco vacío
abre el mismo selector agrupado con buscador que ya usan Automatizaciones
y los widgets del Resumen (catalog_picker) — funciona igual en cualquier
aparato.

La resolución de qué URL reproducir por cámara vive aquí y no en
CameraState: esta pantalla puede tener varias en pantalla a la vez, así que
construye el catálogo entero de una vez (fábrica + dinámicas) en vez de
resolver una URL cada vez que hace falta.
"""
import asyncio
import os
from urllib.parse import parse_qs, urlparse

import reflex as rx

from ..auth import permisos

from . import wall
from ..nodes import store as nodes_store

# Hueco entre cámaras al ir enseñándolas una a una — ver reveal_gradually.
# Segundos entre cámara y cámara al abrir el mural. 1,2 s NO era suficiente: el
# límite de Tuya para pedir un token va en segundos, y con dos cámaras seguidas
# una de las dos se llevaba igualmente el "请求过于频繁" (demasiadas peticiones
# seguidas). Cuatro segundos lo evitan; se paga con que el mural tarda en
# llenarse, pero la primera cámara sigue apareciendo al instante y una que
# aparece tarde es mucho mejor que una que aparece con un error en chino.
#
# En variable de entorno porque el límite es de Tuya y puede cambiar sin avisar.
_ESPERA_ESCALONADO = float(os.getenv("MURAL_ESPERA_CAMARA", "4"))


def _src_de_url(url: str) -> str:
    """El `src=` de la URL del stream. Es de donde sale el nombre con el que
    go2rtc conoce a esa cámara, y vale para las dos clases (las de fábrica lo
    llevan por convención y las añadidas a mano lo guardan en su ficha) — ver
    cameras/wall.catalogo_camaras."""
    return parse_qs(urlparse(url).query).get("src", [""])[0]


class VideoWallState(rx.State):
    layout: str = "4"
    # "0"/"1"/... -> id de cámara. Claves como texto: Reflex serializa las
    # claves de un dict a JSON y ahí siempre son texto; guardarlas ya como
    # texto evita tener que convertir en cada comparación.
    slots: dict[str, str] = {}
    # Catálogo completo de cámaras asignables, ya con su URL de vídeo resuelta
    # — construido en cada _reload(), así que una cámara añadida o borrada en
    # otra pestaña aparece o desaparece aquí sin recargar la página.
    cameras: list[dict] = []

    # Huecos cuyo vídeo YA se está pintando — ver reveal_gradually. Un hueco
    # ocupado que todavía no está aquí enseña "Cargando..." en vez de su
    # iframe.
    visible_slots: list[str] = []
    # slot_id -> cuántas veces se ha pedido recargar SOLO ese hueco (ver
    # retry_slot). Se mete como parte de la URL para forzar al navegador a
    # tratarla como una petición nueva sin tocar los demás huecos.
    reload_nonce: dict[str, int] = {}

    # Aparte de CameraState.cam_mode a propósito: cambiar el modo aquí no debe
    # alterar las ventanas flotantes de cámara suelta, y viceversa.
    cam_mode: str = "pc"

    picker_open: bool = False
    picker_slot: str = ""
    picker_query: str = ""

    @rx.event
    def on_load(self):
        self._reload()
        return VideoWallState.reveal_gradually

    def _reload(self) -> None:
        datos = nodes_store.get_video_wall()
        self.layout = datos["layout"]
        self.slots = dict(datos["slots"])
        self.cameras = wall.catalogo_camaras(self.cam_mode)
        # Un hueco que ya no existe (cambiaste de reparto, lo vaciaste) no se
        # queda "visible" fantasma esperando un vídeo que no va a llegar.
        self.visible_slots = [s for s in self.visible_slots if s in self.slots]

    @rx.event(background=True)
    async def reveal_gradually(self):
        """Enseña las cámaras ocupadas UNA A UNA, con un hueco entre cada una,
        en vez de todas de golpe.

        Esto existe por un fallo muy concreto: abrir el mural (o cerrar y
        volver a abrir la app) monta TODOS los iframes a la vez, y cada uno
        —si la cámara es Tuya— le pide a la nube de Tuya un token de sesión
        nuevo en el mismo instante. Con dos cámaras Tuya eso son dos
        peticiones de token pegadas, y ahí es donde Tuya responde
        "demasiadas peticiones seguidas" (el error en chino que se ve en una
        de las dos) — no es un fallo de esta app, es su límite de peticiones,
        pero abrir las cámaras espaciadas evita tropezar con él."""
        async with self:
            pendientes = [(s, self.slots.get(s, "")) for s in self.slots
                          if s not in self.visible_slots]
            catalogo = {c["id"]: c for c in self.cameras}
        for i, (slot, camara_id) in enumerate(pendientes):
            if i:
                await asyncio.sleep(_ESPERA_ESCALONADO)
            # Se le pide el token PRIMERO desde aquí, y de uno en uno. Es lo que
            # de verdad arregla el error de Tuya: hasta ahora los tokens los
            # pedían los iframes, o sea el navegador, y dos iframes montados casi
            # a la vez son dos peticiones que Tuya rechaza. Pidiéndolo el
            # servidor, en fila, cuando el iframe se monta el productor ya está
            # levantado y no hay token nuevo que pedir.
            #
            # NO se mira si sale bien: su único trabajo es serializar la
            # negociación. Si la cámara está mal (la «fija» no da fotograma ni a
            # la tercera), el hueco se enseña igual — puede que el iframe le
            # funcione por otra vía, y esconderlo sería decidir por el usuario.
            await self._calentar(catalogo.get(camara_id))
            async with self:
                if slot not in self.visible_slots:
                    self.visible_slots = [*self.visible_slots, slot]

    @staticmethod
    async def _calentar(camara: dict | None) -> None:
        """Levanta el productor de esa cámara en go2rtc, sin esperar milagros.

        Se reutiliza la captura de fotograma de la alarma (cameras/fotogramas):
        ya trae temporizador corto, trata un «200 con cero bytes» como fallo y no
        levanta nunca. Pedir un fotograma es la forma más barata de obligar a
        go2rtc a negociar con Tuya."""
        if not camara or not camara.get("playable"):
            return
        src = _src_de_url(camara.get("stream_url", ""))
        if not src:
            return
        try:
            from . import fotogramas
            await fotogramas.capturar(src)
        except Exception as e:
            print(f"⚠️ No se pudo precalentar «{src}»: {e}")

    @rx.event
    def retry_slot(self, slot_id: str):
        """Recarga SOLO este hueco — ni toca los demás ni vuelve a pedir sus
        tokens. Es la alternativa a vaciar el mural entero y volver a colocar
        las cámaras cuando una se queda con el error de Tuya."""
        self.reload_nonce[slot_id] = self.reload_nonce.get(slot_id, 0) + 1

    # ── Reparto ──────────────────────────────────────────────────────────
    @rx.var
    def layouts(self) -> list[dict]:
        return [{"id": lid, "label": label, "total": cols * rows}
                for lid, label, cols, rows in nodes_store.VIDEO_WALL_LAYOUTS]

    @rx.var
    def columnas(self) -> int:
        for lid, _, cols, _ in nodes_store.VIDEO_WALL_LAYOUTS:
            if lid == self.layout:
                return cols
        return 2

    @rx.var
    def slot_ids(self) -> list[str]:
        for lid, _, cols, rows in nodes_store.VIDEO_WALL_LAYOUTS:
            if lid == self.layout:
                return [str(i) for i in range(cols * rows)]
        return ["0", "1", "2", "3"]

    @rx.event
    async def set_layout(self, layout: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.set_video_wall_layout(layout)
        self._reload()

    # ── Huecos ───────────────────────────────────────────────────────────
    @rx.var
    def cameras_by_id(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.cameras}

    @rx.event
    async def clear_slot(self, slot: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.clear_video_wall_slot(slot)
        self._reload()

    @rx.event
    async def clear_all(self):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.clear_video_wall()
        self._reload()

    # ── Selector "tocar para colocar" ───────────────────────────────────
    @rx.event
    def open_picker(self, slot: str):
        self.picker_query = ""
        self.picker_slot = slot
        self._reload()  # por si se añadió/borró una cámara desde otra pestaña
        self.picker_open = True

    @rx.event
    def close_picker(self):
        self.picker_open = False

    @rx.event
    def picker_open_change(self, abierto: bool):
        if not abierto:
            self.picker_open = False

    @rx.event
    def set_picker_query(self, texto: str):
        self.picker_query = texto

    @rx.var
    def picker_sections(self) -> list[dict]:
        """UNA sola sección — a diferencia del selector de widgets/
        automatizaciones no hay familias distintas que agrupar, solo
        cámaras — filtrada por el buscador."""
        busca = self.picker_query.strip().lower()
        opciones = [
            {"label": c["name"], "value": c["id"], "icon": c["icon"]}
            for c in self.cameras if not busca or busca in c["name"].lower()
        ]
        return [{"label": "Cámaras", "icon": "video", "options": opciones}] if opciones else []

    @rx.event
    async def pick(self, camera_id: str):
        # Editar la instalacion es cosa de administradores: «familia»
        # puede USAR todo y no cambiar nada (ver auth/permisos.py).
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if self.picker_slot:
            slot = self.picker_slot
            nodes_store.set_video_wall_slot(slot, camera_id)
            self._reload()
            # Colocar UNA cámara a mano no es la ráfaga que evita
            # reveal_gradually — se enseña ya, sin esperar al escalonado.
            if slot not in self.visible_slots:
                self.visible_slots = [*self.visible_slots, slot]
        self.picker_open = False

    @rx.event
    def toggle_cam_mode(self):
        self.cam_mode = "mobile" if self.cam_mode == "pc" else "pc"
        self._reload()
