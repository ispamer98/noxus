"""Electrodomésticos simulados (domains/electro/simulador.py): órdenes válidas e
inválidas, cuenta atrás y apagado por temporizador. Puro: no toca ningún fichero."""
from tests.comun import Caso

from noxuscmmd.domains.electro import simulador as sim

T0 = 1_700_000_000  # instante real: 0 es «sin fecha» para el simulador


def _orden(tipo, estado, accion, valor, t):
    return sim.comando({"tipo": tipo, "estado": estado}, accion, valor, T0 + t)


def _vista(tipo, estado, t):
    return sim.vista({"tipo": tipo, "estado": estado}, T0 + t)


def _rechaza(tipo, accion, valor) -> bool:
    try:
        _orden(tipo, {}, accion, valor, 0)
    except ValueError:
        return True
    return False


def _lavadora() -> Caso:
    c = Caso("Lavadora: programa, marcha, pausa y fin")
    e = _orden("lavadora", {}, "elegir_programa", "rápido", 0)
    e = _orden("lavadora", e, "iniciar", "", 0)
    c.revisar("restante al empezar", _vista("lavadora", e, 0)["restante"], 30 * 60)
    c.revisar("a mitad lava", _vista("lavadora", e, 600)["fase"], "lavado")
    e = _orden("lavadora", e, "pausar", "", 600)
    c.revisar("pausada guarda lo que queda", _vista("lavadora", e, 5000)["restante"], 1200)
    e = _orden("lavadora", e, "reanudar", "", 5000)
    c.revisar("termina", _vista("lavadora", e, 5000 + 1200)["fase"], "terminado")
    c.cierto("programa inventado", _rechaza("lavadora", "elegir_programa", "lana"))
    return c


def _placa_horno() -> Caso:
    c = Caso("Placa y horno: niveles, límites y temporizador")
    e = _orden("placa", {}, "nivel", "2:7", 0)
    c.revisar("zona 2 a 7", _vista("placa", e, 0)["zonas"][1]["nivel"], 7)
    c.cierto("nivel 10 no existe", _rechaza("placa", "nivel", "1:10"))
    e = _orden("horno", {}, "encendido", "true", 0)
    e = _orden("horno", e, "temporizador", "15", 0)
    c.cierto("precalienta al principio", _vista("horno", e, 10)["precalentando"])
    c.revisar("se apaga al acabar", _vista("horno", e, 15 * 60 + 1)["texto"], "Terminado")
    c.cierto("300 °C no", _rechaza("horno", "temp", "300"))
    return c


def _aire() -> Caso:
    c = Caso("Aire: consigna en medios grados, modos y apagado temporizado")
    e = _orden("aire", {}, "encendido", "true", 0)
    e = _orden("aire", e, "consigna", "22.5", 0)
    c.revisar("baja hacia la consigna", _vista("aire", e, 540)["temperatura_ambiente"], 24.0)
    c.revisar("la alcanza", _vista("aire", e, 99999)["temperatura_ambiente"], 22.5)
    c.cierto("31 °C no", _rechaza("aire", "consigna", "31"))
    c.cierto("22,3 °C no", _rechaza("aire", "consigna", "22.3"))
    c.cierto("modo inventado", _rechaza("aire", "modo", "tormenta"))
    e = _orden("aire", e, "temporizador", "30", 100)
    c.cierto("apagado a los 30 min", not _vista("aire", e, 100 + 1801)["en_marcha"])
    return c


def _nevera_freidora_extractor() -> Caso:
    c = Caso("Nevera, freidora y extractor")
    e = _orden("nevera", {}, "puerta", "true", 0)
    c.cierto("avisa con la puerta abierta más de un minuto", _vista("nevera", e, 61)["aviso_puerta"])
    c.cierto("nevera a 12 °C no", _rechaza("nevera", "consigna_nevera", "12"))
    e = _orden("freidora", {}, "programa", "pescado", 0)
    e = _orden("freidora", e, "iniciar", "", 0)
    c.revisar("pescado: 12 min", _vista("freidora", e, 0)["restante"], 12 * 60)
    c.cierto("pide agitar a mitad", _vista("freidora", e, 6 * 60 + 5)["agitar"])
    e = _orden("extractor", {}, "velocidad", "4", 0)
    e = _orden("extractor", e, "temporizador", "5", 0)
    c.cierto("extractor se para solo", not _vista("extractor", e, 301)["en_marcha"])
    return c


def ejecutar() -> list[Caso]:
    return [_lavadora(), _placa_horno(), _aire(), _nevera_freidora_extractor()]
