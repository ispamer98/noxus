"""
Simulación de presencia: que el patrón aprendido salga de datos limpios, que el
plan del día caiga en horas con sentido y que dos días no sean iguales.

Se aprende del histórico REAL copiado a la casa de pruebas: es donde aparecen los
días de pruebas que hay que descartar y las lagunas de días sin datos.

No se acciona ninguna luz. Del motor se prueba solo lo que decide qué toca y
cuándo, nunca `_accionar`.
"""
import time

from tests.comun import Caso

from noxuscmmd.domains.security import presencia as p
from noxuscmmd.domains.security import presencia_motor as motor
from noxuscmmd.domains.security import presencia_store as store

PATRON_FALSO = {
    "horas": {1: {19: 0.9, 20: 0.8, 12: 0.9}},
    "luces": {"light_x": {"veces": 5, "horas": {19: 3, 20: 2}}},
    "dias": {1: 5},
    "descartados": [],
    "total_eventos": 50,
}


def _aprendizaje() -> Caso:
    c = Caso("Patrón aprendido del histórico")
    patron = p.aprender(dias=60)
    c.cierto("aprende de algún día", sum(patron["dias"].values()) > 0)
    c.cierto("encuentra señales de gente", patron["total_eventos"] > 0)
    # El 26/07/2026 son 25 armados seguidos de una migración: si se cuela,
    # arrastra el patrón entero hacia el mediodía.
    c.cierto("descarta el día de la migración",
             "2026-07-26" in patron["descartados"])
    # Y no puede descartar media muestra: con eso no quedaría nada que aprender.
    c.cierto("no descarta más de un tercio de los días",
             len(patron["descartados"]) <= max(1, sum(patron["dias"].values())))

    for dow in range(7):
        horas = p.horas_activas(patron, dow)
        c.cierto(f"día {dow}: propone alguna hora", bool(horas))
        c.cierto(f"día {dow}: todas dentro de la ventana de luz",
                 all(h in p.VENTANA_LUZ for h in horas))
    return c


def _plan() -> Caso:
    c = Caso("Plan del día")
    # Con el patrón falso, las 12:00 tienen probabilidad alta pero están fuera de
    # la ventana de luz: no deben salir en el plan.
    horas = p.horas_activas(PATRON_FALSO, 1)
    c.revisar("descarta el mediodía aunque haya costumbre", 12 in horas, False)

    plan = p.plan_del_dia(PATRON_FALSO, 1, ["light_x"], semilla=7)
    c.cierto("genera movimientos", bool(plan))
    c.revisar("cada encendido tiene su apagado",
              sum(1 for a in plan if a["encender"]),
              sum(1 for a in plan if not a["encender"]))
    c.cierto("va ordenado en el tiempo",
             all(plan[i]["minuto"] <= plan[i + 1]["minuto"]
                 for i in range(len(plan) - 1)))
    c.cierto("nada se sale del día", all(0 <= a["minuto"] < 1440 for a in plan))
    c.cierto("solo usa las luces permitidas",
             all(a["luz"] == "light_x" for a in plan))

    # Que no sea siempre igual es el punto: una luz que se enciende a las 21:00
    # en punto todos los días delata que no hay nadie.
    a = p.plan_del_dia(PATRON_FALSO, 1, ["light_x"], semilla=1)
    b = p.plan_del_dia(PATRON_FALSO, 1, ["light_x"], semilla=2)
    c.revisar("dos días seguidos no son iguales", a == b, False)
    c.revisar("sin luces permitidas no hace nada",
              p.plan_del_dia(PATRON_FALSO, 1, [], semilla=1), [])
    return c


def _motor() -> Caso:
    c = Caso("Motor de la simulación (sin accionar nada)")
    store.escribir({"activada": True, "luces": ["light_x"]})
    c.revisar("guarda que está encendida", store.activada(), True)
    c.revisar("guarda las luces", store.luces(), ["light_x"])
    store.poner_activada(False)
    c.revisar("apagarla no borra las luces elegidas",
              (store.activada(), store.luces()), (False, ["light_x"]))

    dia = motor._Dia()
    martes = time.strptime("2026-08-18 10:00", "%Y-%m-%d %H:%M")
    dia.preparar(martes, PATRON_FALSO, ["light_x"])
    c.cierto("prepara el plan del día", bool(dia.plan))
    c.revisar("a las 10:00 todavía no toca nada", dia.pendientes(10 * 60), [])
    pendientes = dia.pendientes(23 * 60 + 59)
    c.revisar("al final del día ya tocaba todo", len(pendientes), len(dia.plan))

    indice = pendientes[0][0]
    dia.hechas.add(indice)
    c.revisar("lo ya hecho no se repite",
              len(dia.pendientes(23 * 60 + 59)), len(dia.plan) - 1)

    antes = list(dia.plan)
    dia.preparar(martes, PATRON_FALSO, ["light_x"])
    c.revisar("el mismo día no se resortea", dia.plan, antes)

    # Al desarmar se olvida: si alguien llega a casa, no se le apaga la luz.
    dia.olvidar()
    c.revisar("olvidar deja el día limpio",
              (dia.fecha, dia.plan, dia.hechas), ("", [], set()))
    return c


def ejecutar() -> list[Caso]:
    return [_aprendizaje(), _plan(), _motor()]
