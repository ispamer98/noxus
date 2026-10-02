"""Cómo trabaja la cerradura de una puerta: un pulso o dos pulsos (portón paso a
paso), y lo que ve el plano durante la maniobra.

El relé está espiado (operations._enviar_a_rele): aquí no sale ninguna orden a
la casa, solo se apunta qué se habría mandado.
"""
import asyncio

from tests.comun import Caso

from noxuscmmd.domains.nodes import operations as ops
from noxuscmmd.domains.nodes import sensor_events, store
from noxuscmmd.domains.nodes.state import _icono_puerta


def _con_rele_espiado(escenario) -> list:
    enviados: list = []

    async def espia(spec, on, *_):
        enviados.append(on)

    async def en_el_loop(func, *args, **kwargs):
        return func(*args, **kwargs)

    original_rele, original_hilo = ops._enviar_a_rele, ops.asyncio.to_thread
    ops._enviar_a_rele, ops.asyncio.to_thread = espia, en_el_loop
    try:
        asyncio.run(escenario(enviados))
    finally:
        ops._enviar_a_rele, ops.asyncio.to_thread = original_rele, original_hilo
    return enviados


def _almacen() -> Caso:
    c = Caso("La ficha guarda cómo trabaja la cerradura")
    d = store.add_door("Portón prueba", "", "nodo_prueba", "porton",
                       modo=store.MODO_DOS_PULSOS, apertura_s=5, espera_s=3, cierre_s=5)
    c.revisar("modo", d["modo"], store.MODO_DOS_PULSOS)
    c.revisar("tiempos", (d["apertura_s"], d["espera_s"], d["cierre_s"]), (5, 3, 5))
    raro = store.add_door("Puerta rara", "", "nodo_prueba", "rara", modo="inventado")
    c.revisar("un modo desconocido se queda en un pulso", raro["modo"], store.MODO_PULSO)
    store.update_door(raro["id"], "Puerta rara", "", "nodo_prueba", "rara",
                      maniobra={"modo": "dos_pulsos", "apertura_s": "4", "espera_s": "",
                                "cierre_s": "-2"})
    editada = ops.find("doors", raro["id"])
    c.revisar("editar sanea los tiempos", (editada["modo"], editada["apertura_s"],
                                           editada["espera_s"], editada["cierre_s"]),
              ("dos_pulsos", 4, 0, 0))
    store.update_door(raro["id"], "Puerta rara 2", "", "nodo_prueba", "rara")
    c.revisar("editar sin maniobra no la toca", ops.find("doors", raro["id"])["modo"],
              "dos_pulsos")
    store.delete_door(d["id"])
    store.delete_door(raro["id"])
    return c


def _mantener_un_pulso() -> Caso:
    c = Caso("Un pulso: mantener = relé activado o suelto")
    d = store.add_door("Portón 1p", "", "nodo_prueba", "p1", apertura_s=5, espera_s=3,
                       cierre_s=5)
    movimientos = []

    async def escenario(enviados):
        for abierta in (True, True, False, False):
            _, se_mueve = await ops.hold_door(d["id"], abierta)
            movimientos.append(se_mueve)

    enviados = _con_rele_espiado(escenario)
    c.revisar("relé", enviados, [True, True, False, False])
    c.revisar("solo se mueve al cambiar", movimientos, [True, False, True, False])
    store.delete_door(d["id"])
    return c


def _mantener_dos_pulsos() -> Caso:
    c = Caso("Dos pulsos: mantener da UN pulso y solo si hace falta")
    d = store.add_door("Portón 2p", "", "nodo_prueba", "p2", 0,
                       modo=store.MODO_DOS_PULSOS, apertura_s=5, espera_s=3, cierre_s=5)
    store.set_sensor_state(d["id"], False)
    pasos = []

    async def escenario(enviados):
        for abierta in (True, True, False, False):
            antes = len(enviados)
            _, se_mueve = await ops.hold_door(d["id"], abierta)
            pasos.append((se_mueve, enviados[antes:]))

    _con_rele_espiado(escenario)
    c.revisar("abrir cerrada: suelta y da un pulso", pasos[0], (True, [False, True, False]))
    c.revisar("abrir ya abierta: ningún pulso", pasos[1], (False, [False]))
    c.revisar("cerrar abierta: un pulso", pasos[2], (True, [False, True, False]))
    c.revisar("cerrar ya cerrada: ningún pulso", pasos[3], (False, [False]))
    c.revisar("queda apuntada cerrada", store.get_sensor_state(d["id"]), False)
    store.delete_door(d["id"])
    return c


def _pase_dos_pulsos() -> Caso:
    c = Caso("Dos pulsos: abrir para pasar da el pulso de cierre al acabar la espera")
    d = store.add_door("Portón pase", "", "nodo_prueba", "p3", 0,
                       modo=store.MODO_DOS_PULSOS, apertura_s=1, espera_s=0, cierre_s=1)
    fases = []

    async def escenario(enviados):
        tarea = ops.pulse_door(d["id"], 0.01)
        await asyncio.sleep(0.2)
        fases.append(ops.fase_pase(d["id"]))
        await tarea

    enviados = _con_rele_espiado(escenario)
    c.revisar("abre y cierra con dos pulsos", enviados, [True, False, True, False])
    c.revisar("a mitad está abriendo", fases, ["abriendo"])
    store.delete_door(d["id"])
    return c


def _mantener_a_mitad_del_pase() -> Caso:
    c = Caso("Mantener abierta a mitad del pase cancela el pulso de cierre")
    d = store.add_door("Portón mitad", "", "nodo_prueba", "p4", 0,
                       modo=store.MODO_DOS_PULSOS, apertura_s=1, espera_s=0, cierre_s=1)
    store.set_sensor_state(d["id"], False)
    movio = []

    async def escenario(enviados):
        ops.pulse_door(d["id"], 0.01)
        await asyncio.sleep(0.2)
        _, se_mueve = await ops.hold_door(d["id"], True)
        movio.append(se_mueve)
        await asyncio.sleep(1.2)

    enviados = _con_rele_espiado(escenario)
    c.revisar("ya estaba abriéndose: no se mueve", movio, [False])
    c.revisar("sin segundo pulso (solo el de abrir y el soltar)", enviados,
              [True, False, False])
    c.revisar("queda mantenida abierta", store.get_sensor_state(d["id"]), True)
    store.delete_door(d["id"])
    return c


def _eco_del_rele() -> Caso:
    c = Caso("Con dos pulsos, el eco del relé no pisa si la puerta está abierta")
    d = store.add_door("Portón eco", "", "nodo_prueba", "p5",
                       modo=store.MODO_DOS_PULSOS)
    store.set_sensor_state(d["id"], True)
    sensor_events.on_binary_sensor(d["id"], False)
    c.revisar("se ignora", store.get_sensor_state(d["id"]), True)
    normal = store.add_door("Cerradero eco", "", "nodo_prueba", "p6")
    sensor_events.on_binary_sensor(normal["id"], True)
    c.revisar("con un pulso sí cuenta", store.get_sensor_state(normal["id"]), True)
    store.delete_door(d["id"])
    store.delete_door(normal["id"])
    return c


def _iconos() -> Caso:
    c = Caso("El icono sigue a la puerta abierta o cerrada")
    c.revisar("puerta cerrada", _icono_puerta("door-closed", False), "door-closed")
    c.revisar("puerta abierta", _icono_puerta("", True), "door-open")
    c.revisar("portón cerrado", _icono_puerta("warehouse", False), "warehouse")
    c.revisar("portón levantado", _icono_puerta("warehouse", True), "warehouse-open")
    c.revisar("icono sin pareja se respeta", _icono_puerta("fence", True), "fence")
    return c


def ejecutar() -> list[Caso]:
    return [_almacen(), _mantener_un_pulso(), _mantener_dos_pulsos(), _pase_dos_pulsos(),
            _mantener_a_mitad_del_pase(), _eco_del_rele(), _iconos()]
