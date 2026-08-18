"""
Estado de la pantalla «Simulación de presencia» (Ajustes).

Aquí solo se enciende, se eligen las luces y se ENSEÑA lo que se ha aprendido y
lo que va a pasar hoy. Quien lo ejecuta es presencia_motor, que es una tarea de
proceso: esta pantalla puede estar cerrada y la simulación sigue.

Enseñar el plan del día no es un adorno: es la única forma de que alguien pueda
juzgar si el patrón aprendido tiene sentido antes de irse de casa una semana.
"""
import asyncio
import time

import reflex as rx

from . import presencia, presencia_store
from ..auth import permisos
from ..nodes import store as nodes_store
from . import audit, logs

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class PresenciaState(rx.State):
    activada: bool = False
    cargando: bool = False

    resumen: str = ""
    descartados: int = 0

    # Luces de la casa: [{"id", "nombre", "elegida", "historial"}]
    luces: list[dict] = []

    # El plan de hoy, ya en texto: [{"hora", "que"}]
    plan: list[dict] = []
    dia_texto: str = ""

    @rx.event
    async def on_load(self):
        self.cargando = True
        yield
        await self._cargar()
        self.cargando = False

    async def _cargar(self):
        config = await asyncio.to_thread(presencia_store.leer)
        self.activada = config["activada"]
        elegidas = config["luces"]

        patron = await asyncio.to_thread(presencia.aprender)
        self.resumen = presencia.resumen(patron)
        self.descartados = len(patron["descartados"])

        datos = await asyncio.to_thread(nodes_store.read_all)
        self.luces = [
            {
                "id": luz["id"],
                "nombre": luz.get("name", luz["id"]),
                "elegida": (luz["id"] in elegidas) if elegidas else False,
                "historial": (
                    f"{patron['luces'][luz['id']]['veces']} usos en el histórico"
                    if luz["id"] in patron["luces"] else "sin histórico"
                ),
            }
            for luz in datos.get("lights", [])
        ]

        ahora = time.localtime()
        dow = ahora.tm_wday
        self.dia_texto = DIAS[dow]
        acciones = presencia.plan_del_dia(
            patron, dow, elegidas or None,
            semilla=int(time.strftime("%Y%m%d", ahora)))
        nombres = {l["id"]: l["nombre"] for l in self.luces}
        self.plan = [
            {
                "hora": f"{a['minuto'] // 60:02d}:{a['minuto'] % 60:02d}",
                "que": ("Enciende " if a["encender"] else "Apaga ")
                       + nombres.get(a["luz"], a["luz"]),
            }
            for a in acciones
        ]

    @rx.var
    def hay_plan(self) -> bool:
        return bool(self.plan)

    @rx.var
    def estado_texto(self) -> str:
        if not self.activada:
            return "Apagada: no se moverá ninguna luz."
        if not self.plan:
            return ("Encendida, pero hoy no hay nada previsto — revisa que haya "
                    "alguna luz elegida.")
        return (f"Encendida: {len(self.plan)} movimiento(s) previstos para hoy, "
                f"y solo con el sistema armado.")

    @rx.event
    async def alternar(self, valor: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        await asyncio.to_thread(presencia_store.poner_activada, valor)
        self.activada = valor
        await audit.registrar(
            self, logs.LUCES,
            "PRESENCIA_ACTIVADA" if valor else "PRESENCIA_DESACTIVADA",
            "simulación de presencia")
        await self._cargar()

    @rx.event
    async def alternar_luz(self, luz_id: str, valor: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        elegidas = {l["id"] for l in self.luces if l["elegida"]}
        if valor:
            elegidas.add(luz_id)
        else:
            elegidas.discard(luz_id)
        await asyncio.to_thread(presencia_store.poner_luces, sorted(elegidas))
        await self._cargar()

    @rx.event
    async def recalcular(self):
        """Vuelve a aprender y a sortear el plan. Útil tras elegir luces, y para
        ver que dos días no salen iguales."""
        self.cargando = True
        yield
        await self._cargar()
        self.cargando = False
