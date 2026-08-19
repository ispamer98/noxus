"""
Estado de la pantalla «Detección de movimiento» (Ajustes).

Aquí solo se enciende, se eligen las cámaras y se ajusta la sensibilidad. Quien
mira de verdad es movimiento_motor, que es tarea de proceso: esta pantalla puede
estar cerrada y la vigilancia sigue.
"""
import asyncio

import reflex as rx

from . import movimiento, movimiento_store, wall
from ..auth import permisos
from ..security import audit, logs

# Lo que significa cada posición del mando de sensibilidad, en porcentaje de
# celdas cambiadas (ver movimiento.hay_movimiento).
SENSIBILIDADES = (
    ("Muy alta — salta con poco", 0.8),
    ("Alta", 1.4),
    ("Normal", 2.0),
    ("Baja", 3.5),
    ("Muy baja — solo cambios grandes", 6.0),
)


class MovimientoState(rx.State):
    activada: bool = False
    solo_armado: bool = True
    umbral: float = movimiento.UMBRAL_POR_DEFECTO
    camaras: list[dict] = []
    mensaje: str = ""

    @rx.event
    async def on_load(self):
        await self._cargar()

    async def _cargar(self):
        config = await asyncio.to_thread(movimiento_store.leer)
        self.activada = config["activada"]
        self.solo_armado = config["solo_armado"]
        self.umbral = config["umbral"]
        elegidas = set(config["camaras"])
        catalogo = await asyncio.to_thread(wall.catalogo_camaras)
        self.camaras = [
            {
                "id": c["id"],
                "nombre": c["name"],
                "elegida": c["id"] in elegidas,
                # Solo las de go2rtc pueden dar un fotograma; a un embed o a un
                # RTSP no hay a quién pedírselo.
                "sirve": c["kind"] in ("factory", "go2rtc"),
            }
            for c in catalogo
        ]

    @rx.var
    def estado_texto(self) -> str:
        if not self.activada:
            return "Apagada: no se mira ninguna cámara."
        cuantas = sum(1 for c in self.camaras if c["elegida"])
        if not cuantas:
            return "Encendida, pero sin ninguna cámara marcada: no mira nada."
        cuando = "solo con la casa armada" if self.solo_armado else "siempre"
        return f"Vigilando {cuantas} cámara(s), {cuando}."

    @rx.var
    def sensibilidad_texto(self) -> str:
        for etiqueta, valor in SENSIBILIDADES:
            if abs(valor - self.umbral) < 0.01:
                return etiqueta
        return f"{self.umbral}% de la imagen"

    @rx.event
    async def alternar(self, valor: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        await asyncio.to_thread(movimiento_store.poner, "activada", bool(valor))
        self.activada = bool(valor)
        await audit.registrar(
            self, logs.ALARMA,
            "MOVIMIENTO_ACTIVADO" if valor else "MOVIMIENTO_DESACTIVADO",
            "detección de movimiento")

    @rx.event
    async def alternar_solo_armado(self, valor: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        await asyncio.to_thread(movimiento_store.poner, "solo_armado", bool(valor))
        self.solo_armado = bool(valor)

    @rx.event
    async def alternar_camara(self, camara_id: str, valor: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        elegidas = {c["id"] for c in self.camaras if c["elegida"]}
        if valor:
            elegidas.add(camara_id)
        else:
            elegidas.discard(camara_id)
        await asyncio.to_thread(movimiento_store.poner, "camaras", sorted(elegidas))
        await self._cargar()

    @rx.event
    async def poner_umbral(self, valor: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return
        await asyncio.to_thread(movimiento_store.poner, "umbral", numero)
        self.umbral = numero
