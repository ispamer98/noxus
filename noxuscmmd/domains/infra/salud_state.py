"""
Estado de la pantalla de salud: lanza las comprobaciones y guarda el resultado.

Se comprueba al abrir la pantalla y cuando se pulsa el botón, no en un bucle: son
seis comprobaciones con red y subprocesos, y repetirlas cada dos segundos por cada
pestaña abierta gastaría más de lo que informa. Lo que sí se hace es dejar dicho
cuándo se miró, porque un semáforo en verde sin fecha no dice nada.
"""
import time

import reflex as rx

from . import salud


class SaludState(rx.State):
    piezas: list[dict] = []
    comprobando: bool = False
    cuando: str = ""

    @rx.event
    async def on_load(self):
        # Se LANZA el evento, no se llama a la función: `comprobar` es de fondo
        # (@rx.event(background=True)) y llamarlo a mano devuelve una corrutina
        # que nadie espera. El patrón es el mismo que usa LogsState.on_load con
        # su sync_loop.
        yield SaludState.comprobar

    @rx.event(background=True)
    async def comprobar(self):
        """En segundo plano: el túnel se pregunta con un subproceso y go2rtc por
        red, así que esto puede tardar un segundo y no debe congelar la pantalla."""
        async with self:
            self.comprobando = True
        try:
            piezas = await salud.comprobar()
        except Exception as e:
            piezas = [{"id": "error", "nombre": "No se pudo comprobar",
                       "icono": "triangle-alert", "estado": salud.MAL,
                       "detalle": str(e), "porque": ""}]
        async with self:
            self.piezas = piezas
            self.cuando = time.strftime("%H:%M:%S")
            self.comprobando = False

    @rx.var
    def resumen(self) -> str:
        """Una frase para la cabecera: lo que se lee de un vistazo antes de
        entrar en el detalle."""
        if not self.piezas:
            return "Sin comprobar todavía"
        mal = sum(1 for p in self.piezas if p["estado"] == salud.MAL)
        aviso = sum(1 for p in self.piezas if p["estado"] == salud.AVISO)
        if mal:
            return f"{mal} cosa(s) mal, {aviso} con aviso"
        if aviso:
            return f"Todo en pie, {aviso} con aviso"
        return "Todo en orden"

    @rx.var
    def hay_problemas(self) -> bool:
        return any(p["estado"] != salud.BIEN for p in self.piezas)
