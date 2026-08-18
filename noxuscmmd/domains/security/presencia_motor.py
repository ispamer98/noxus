"""
El que ejecuta la simulación de presencia. Tarea de PROCESO (una, no una por
sesión: ver noxuscmmd.py), porque esto tiene que seguir funcionando con todos
los navegadores cerrados — que es precisamente cuando hace falta.

Reglas de cuándo actúa, y son estrictas a propósito:

  · La simulación tiene que estar encendida en Ajustes.
  · El sistema tiene que estar ARMADO. Es la señal de «no hay nadie» que ya
    existe en esta casa, y no hace falta inventar otra.
  · Solo dentro del plan del día, que se genera una vez cada día y se guarda en
    memoria (ver presencia.plan_del_dia).

Al DESARMAR se olvida el plan y no se toca ninguna luz. Deliberado: si alguien
llega a casa y la simulación tenía un apagado pendiente, apagárselo en la cara
sería peor que dejar la luz encendida.

Lo que enciende se apunta con su propia acción (PRESENCIA_LUZ) y NO como
LUZ_ENCENDIDA. Si usara la misma, el aprendizaje del día siguiente contaría sus
propios encendidos como costumbre de la casa y el patrón se iría deformando solo.
"""
import asyncio
import time

from . import logs, presencia, presencia_store, shared_state
from ..nodes import operations as ops
from . import audit

# Cada cuánto se mira si toca algo. Treinta segundos: el plan va en minutos, y
# así un encendido llega con menos de medio minuto de retraso sin que esto
# despierte al proceso constantemente.
PERIODO = 30.0


class _Dia:
    """El plan de hoy y qué se ha hecho ya de él."""

    def __init__(self):
        self.fecha = ""
        self.plan: list[dict] = []
        self.hechas: set[int] = set()

    def preparar(self, ahora: time.struct_time, patron: dict,
                 luces: list[str]) -> None:
        fecha = time.strftime("%Y-%m-%d", ahora)
        if fecha == self.fecha:
            return
        self.fecha = fecha
        # La semilla es la fecha: el plan de un día es siempre el mismo aunque
        # el panel se reinicie a mitad de tarde, y distinto al del día anterior.
        self.plan = presencia.plan_del_dia(
            patron, ahora.tm_wday, luces or None,
            semilla=int(fecha.replace("-", "")))
        self.hechas = set()
        cuantas = len(self.plan)
        print(f"🏠 Presencia: plan de {fecha} con {cuantas} movimiento(s)")

    def olvidar(self) -> None:
        self.fecha = ""
        self.plan = []
        self.hechas = set()

    def pendientes(self, minuto_ahora: int) -> list[tuple[int, dict]]:
        """Lo que ya tocaba y no se ha hecho. Se mira por minuto y no por
        igualdad exacta para que un reinicio o un tirón de CPU no se salte un
        encendido: si el momento ya pasó, se hace igual."""
        return [(i, a) for i, a in enumerate(self.plan)
                if a["minuto"] <= minuto_ahora and i not in self.hechas]


async def _accionar(luz: str, encender: bool) -> None:
    ficha = ops.find("lights", luz) or {}
    nombre = ficha.get("name", luz)
    if not ficha:
        print(f"⚠️ Presencia: la luz {luz} ya no existe; se salta")
        return
    await ops.set_light(luz, encender)
    # registrar_sistema es síncrono (escribe en SQLite), así que va a un hilo:
    # esto corre en el bucle de eventos del panel y no puede quedarse esperando
    # al disco.
    await asyncio.to_thread(
        audit.registrar_sistema,
        logs.LUCES, "PRESENCIA_LUZ",
        f"{nombre} · {'encendida' if encender else 'apagada'} por la simulación",
        entidad=luz,
    )


async def run_forever() -> None:
    dia = _Dia()
    patron: dict = {}
    patron_de = ""

    while True:
        await asyncio.sleep(PERIODO)
        try:
            config = presencia_store.leer()
            if not config["activada"]:
                dia.olvidar()
                continue
            if not await asyncio.to_thread(shared_state.get_sistema_armado):
                # Hay alguien en casa: se olvida el plan y no se toca nada.
                dia.olvidar()
                continue

            ahora = time.localtime()
            hoy = time.strftime("%Y-%m-%d", ahora)

            # El patrón se reaprende una vez al día: leer el histórico entero es
            # barato pero no gratis, y las costumbres no cambian cada minuto.
            if patron_de != hoy:
                patron = await asyncio.to_thread(presencia.aprender)
                patron_de = hoy
                print(f"🏠 Presencia: {presencia.resumen(patron)}")

            dia.preparar(ahora, patron, config["luces"])
            minuto = ahora.tm_hour * 60 + ahora.tm_min
            for indice, accion in dia.pendientes(minuto):
                dia.hechas.add(indice)
                try:
                    await _accionar(accion["luz"], accion["encender"])
                except Exception as e:
                    print(f"⚠️ Presencia: no se pudo mover {accion['luz']}: {e}")
        except Exception as e:
            print(f"⚠️ Presencia: error en el bucle: {e}")
            await asyncio.sleep(5)
