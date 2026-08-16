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
import reflex as rx

from . import wall
from ..nodes import store as nodes_store


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

    # Aparte de CameraState.cam_mode a propósito: cambiar el modo aquí no debe
    # alterar las ventanas flotantes de cámara suelta, y viceversa.
    cam_mode: str = "pc"

    picker_open: bool = False
    picker_slot: str = ""
    picker_query: str = ""

    @rx.event
    def on_load(self):
        self._reload()

    def _reload(self) -> None:
        datos = nodes_store.get_video_wall()
        self.layout = datos["layout"]
        self.slots = dict(datos["slots"])
        self.cameras = wall.catalogo_camaras(self.cam_mode)

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
    def set_layout(self, layout: str):
        nodes_store.set_video_wall_layout(layout)
        self._reload()

    # ── Huecos ───────────────────────────────────────────────────────────
    @rx.var
    def cameras_by_id(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.cameras}

    @rx.event
    def clear_slot(self, slot: str):
        nodes_store.clear_video_wall_slot(slot)
        self._reload()

    @rx.event
    def clear_all(self):
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
    def pick(self, camera_id: str):
        if self.picker_slot:
            nodes_store.set_video_wall_slot(self.picker_slot, camera_id)
            self._reload()
        self.picker_open = False

    @rx.event
    def toggle_cam_mode(self):
        self.cam_mode = "mobile" if self.cam_mode == "pc" else "pc"
        self._reload()
